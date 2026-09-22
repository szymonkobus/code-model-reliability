#!/usr/bin/env bash
#SBATCH --job-name=humanevalplus
#SBATCH --partition=<partition>
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH --output=logs/%x-%j.out
#SBATCH --dependency=singleton
#SBATCH --signal=B:USR1@300

set -euo pipefail

# Slurm requeues preemptions (--requeue) but never TIMEOUT. USR1 arrives 300s
# before the wall; requeue only if this incarnation grew the samples file
# (guards against requeue-looping a wedged run) and under a restart cap.
# Long payloads run via run_traced so bash can act on the signal mid-command.
SNAPSHOT_FILE=""
_snapshot() { wc -lc "$SNAPSHOT_FILE" 2>/dev/null | awk '{print $1"/"$2}' || true; }
START_SNAPSHOT=""
on_usr1() {
  if [[ "${SLURM_RESTART_COUNT:-0}" -lt 12 && -n "$SNAPSHOT_FILE" && "$(_snapshot)" != "$START_SNAPSHOT" ]]; then
    echo "TIMEOUT imminent: progress this incarnation (restarts: ${SLURM_RESTART_COUNT:-0}); requeueing"
    scontrol requeue "$SLURM_JOB_ID"
  else
    echo "TIMEOUT imminent: no progress or restart cap reached — failing loudly, NOT requeueing" >&2
  fi
  exit 1
}
trap on_usr1 USR1
run_traced() { "$@" & wait "$!"; }

STAGE="${1:?usage: sbatch job.sbatch smoke|oracle|greedy|full [hf-model-id] [humaneval|mbpp] [repeat-k]}"

BASE="$PWD"   # sbatch preserves the submission cwd; submit.sh cds to the cluster's base dir
VENV="$BASE/venv"
# Repeat runs (run-to-run variance arms) write to their own root so the
# resume logic never collides with the landed original.
REPEAT="${4:-}"
RUNS="$BASE/runs${REPEAT:+-rep$REPEAT}"

export XDG_CACHE_HOME="$BASE/cache"      # evalplus dataset + ground-truth cache
export HF_HOME="$BASE/cache/huggingface" # model weights
export TOKENIZERS_PARALLELISM=false
export PATH="$VENV/bin:$PATH"            # vLLM JIT kernel compiles invoke `ninja` from PATH

MODEL="${2:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"
MODEL_ID="${MODEL//\//--}"   # evalplus derives file names from this

DATASET="${3:-humaneval}"
case "$DATASET" in
  humaneval) EXPECT_TASKS=164 ;;
  mbpp)      EXPECT_TASKS=378 ;;   # MbppPlus v0.2.0
  *) echo "unknown dataset: $DATASET" >&2; exit 1 ;;
esac
if [[ "$STAGE" == "smoke" && "$DATASET" != "humaneval" ]]; then
  echo "smoke is humaneval-only: --id_range 0,1 matches no Mbpp task id (they start at Mbpp/2)" >&2
  exit 1
fi
echo "job: stage=$STAGE dataset=$DATASET model=$MODEL"
mkdir -p "$RUNS/$DATASET"   # codegen's jsonl mode never creates it

case "$STAGE" in
  smoke)  GEN_ARGS="--greedy --id_range 0,1 --enable_chunked_prefill"; TEMP="0.0"; DO_EVAL=0; EXPECT_N=1 ;;
  oracle) GEN_ARGS=""                                                ; TEMP="none"; DO_EVAL=1; EXPECT_N=1 ;;
  greedy) GEN_ARGS="--greedy --enable_chunked_prefill"               ; TEMP="0.0"; DO_EVAL=1; EXPECT_N=1 ;;
  full)   GEN_ARGS="--n_samples 128 --temperature 0.8 --bs 128 --enable_chunked_prefill"; TEMP="0.8"; DO_EVAL=1; EXPECT_N=128 ;;
  *) echo "unknown stage: $STAGE" >&2; exit 1 ;;
esac

# Multi-GPU models (e.g. DeepSeek-Coder-V2 236B): tensor parallelism =
# allocated GPU count, single node. Submit with GPUS=8 (submit.sh hook).
NGPU="${SLURM_GPUS_ON_NODE:-1}"
if [[ "$NGPU" -gt 1 && "$STAGE" != "oracle" ]]; then
  GEN_ARGS="$GEN_ARGS --tp $NGPU"
fi
# trust-remote-code cases: DeepSeek frontier (vendor recipe requirement);
# every Kimi rung (custom TikToken tokenizer via auto_map).
case "$MODEL" in
  deepseek-ai/DeepSeek-V3*|deepseek-ai/DeepSeek-R1*|moonshotai/*)
    [[ "$STAGE" != "oracle" ]] && GEN_ARGS="$GEN_ARGS --trust_remote_code" ;;
esac

TORCH_BACKEND=""
TORCH_BACKEND="${TORCH_BACKEND:-}"   # set TORCH_BACKEND=cu129 in the job environment on a cluster whose GPU driver predates CUDA 13
bash "$BASE/code/setup_env.sh" "$VENV" "$BASE/code/requirements.txt" "$TORCH_BACKEND"
# Pin this job to the generation current at its start: a later rebuild
# repoints the symlink without changing what this incarnation imports.
VENV="$(readlink -f "$VENV")"

if [[ "$STAGE" == "oracle" ]]; then
  # Judging-path check, no model involved: run the dataset's own canonical
  # solutions through evaluate (evaluate judges solution = prompt +
  # canonical_solution, the same concatenation get_groundtruth executes).
  # The python writes the file itself: on a cold cache, evalplus prints
  # dataset-download progress to stdout, which must not land in the jsonl.
  SAMPLES="$RUNS/$DATASET/canonical.jsonl"
  "$VENV/bin/python" - "$SAMPLES" "$DATASET" <<'EOF'
import json, sys
from evalplus.data import get_human_eval_plus, get_mbpp_plus
tasks = {"humaneval": get_human_eval_plus, "mbpp": get_mbpp_plus}[sys.argv[2]]()
with open(sys.argv[1], "w") as f:
    for task_id, p in tasks.items():
        f.write(json.dumps({"task_id": task_id, "solution": p["prompt"] + p["canonical_solution"]}) + "\n")
EOF
else
  # This is the file name evalplus.codegen derives from (root, model, backend, temperature).
  SAMPLES="$RUNS/$DATASET/${MODEL_ID}_vllm_temp_${TEMP}.jsonl"

  # A preemption can leave a half-written last line, which would crash
  # codegen's resume.
  "$VENV/bin/python" "$BASE/code/repair_jsonl.py" "$SAMPLES" "${SAMPLES%.jsonl}.raw.jsonl"

  SNAPSHOT_FILE="$SAMPLES"; START_SNAPSHOT="$(_snapshot)"
  run_traced "$VENV/bin/python" -m evalplus.codegen \
    --model "$MODEL" --dataset "$DATASET" --backend vllm --root "$RUNS" $GEN_ARGS

  RAW="${SAMPLES%.jsonl}.raw.jsonl"
  if [[ -f "$RAW" && "$(wc -l < "$SAMPLES")" != "$(wc -l < "$RAW")" ]]; then
    echo "WARNING: line counts differ: $(wc -l < "$SAMPLES") sanitized vs $(wc -l < "$RAW") raw — raw-file pairing unreliable" >&2
  fi
fi

if [[ "$DO_EVAL" == 1 ]]; then
  # Wrong counts mean a duplicate submission, resume against an old file,
  # or a truncated dataset cache.
  "$VENV/bin/python" "$BASE/code/check_counts.py" "$SAMPLES" "$EXPECT_N" "$EXPECT_TASKS"
  # evaluate silently reuses an existing results file; remove it (both
  # current and legacy naming) so this run's samples are always re-judged.
  rm -f "${SAMPLES%.jsonl}.eval_results.json" "${SAMPLES%.jsonl}_eval_results.json"
  export EVALPLUS_MAX_MEMORY_BYTES=12884901888
  run_traced "$VENV/bin/python" "$BASE/code/judge/board_evaluate.py" \
    --dataset "$DATASET" --samples "$SAMPLES" --parallel 8
fi

# Record what actually ran.
mkdir -p "$RUNS/manifests"
uv pip freeze --python "$VENV/bin/python" > "$RUNS/manifests/pip-freeze-$STAGE-$DATASET-$MODEL_ID.txt"
{
  echo "stage: $STAGE"
  echo "compare: numeric-tolerant-v2 (judge/board_evaluate.py; pinned patch sha16 $(sha256sum "$BASE/code/judge/board_compare/compare_numeric_patch.py" | cut -c1-16))"
  echo "dataset: $DATASET"
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)  slurm_job: ${SLURM_JOB_ID:-none}"
  echo "gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  echo "model: $MODEL"
  echo "model_revision: $(cat "$HF_HOME/hub/models--$MODEL_ID/refs/main" 2>/dev/null || echo unknown)"
  if [[ "$STAGE" == "oracle" ]]; then
    echo "codegen: skipped (samples are the dataset's canonical solutions)"
  else
    echo "codegen_args: --model $MODEL --dataset $DATASET --backend vllm --root $RUNS $GEN_ARGS"
  fi
  if [[ "$DO_EVAL" == 1 ]]; then
    echo "evaluate_args: --dataset $DATASET --samples $SAMPLES --parallel 8"
    echo "judge_env: EVALPLUS_MAX_MEMORY_BYTES=${EVALPLUS_MAX_MEMORY_BYTES:-unset(default 4GB)}"
  else
    echo "evaluate_args: skipped"
  fi
  echo "samples_file: $SAMPLES"
  echo "samples_sha256: $(sha256sum "$SAMPLES" | cut -d' ' -f1)"
} > "$RUNS/manifests/$STAGE-$DATASET-$MODEL_ID.txt"

echo "STAGE $STAGE ($DATASET, $MODEL_ID) DONE"

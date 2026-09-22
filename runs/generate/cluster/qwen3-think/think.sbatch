#!/usr/bin/env bash
#SBATCH --job-name=qwen3think
#SBATCH --partition=<partition>
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH --output=logs/%x-%j.out
#SBATCH --dependency=singleton
#SBATCH --signal=B:USR1@300

set -euo pipefail
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

MODEL="${1:?usage: sbatch think.sbatch <hf-model-id> [humaneval|mbpp] [n]}"
DATASET="${2:-humaneval}"
N="${3:-128}"
case "$DATASET" in humaneval) TASKS=164 ;; mbpp) TASKS=378 ;; *) echo "unknown dataset: $DATASET" >&2; exit 2 ;; esac
BASE="$PWD"
# readlink pins this job to the venv generation current at its start (the
# stable name is a symlink under setup_env.sh's generation scheme).
VENV="$(readlink -f "$BASE/venv")"
export XDG_CACHE_HOME="$BASE/cache"
export HF_HOME="$BASE/cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export PATH="$VENV/bin:$PATH"

MODEL_ID="${MODEL//\//--}"
OUTDIR="$BASE/runs/${DATASET}-think"
mkdir -p "$OUTDIR"
OUT="$OUTDIR/${MODEL_ID}_think2phase_T0.6"
SAMPLES="$OUT.jsonl"
RECORDS="$OUT.records.jsonl"

echo "job: stage=think dataset=$DATASET model=$MODEL n=$N"

# Pair-integrity guard: samples/records are written in lockstep, so any
# common prefix is a valid pair; align to it and fail on residual mismatch.
"$VENV/bin/python" "$BASE/code/repair_jsonl.py" --pair "$SAMPLES" "$RECORDS"

SNAPSHOT_FILE="$SAMPLES"; START_SNAPSHOT="$(_snapshot)"
run_traced "$VENV/bin/python" "$BASE/code/qwen3-think/runner.py" "$MODEL" "$OUT" --n "$N" --dataset "$DATASET"

"$VENV/bin/python" "$BASE/code/check_counts.py" "$SAMPLES" "$N" "$TASKS"

# evaluate silently reuses an existing results file (both naming variants).
rm -f "${SAMPLES%.jsonl}.eval_results.json" "${SAMPLES%.jsonl}_eval_results.json"
export EVALPLUS_MAX_MEMORY_BYTES=12884901888
run_traced "$VENV/bin/python" -m evalplus.evaluate --dataset "$DATASET" --samples "$SAMPLES" --parallel 16

"$VENV/bin/python" - "$SAMPLES" "$RECORDS" <<'EOF'
import collections, json, sys
res = json.load(open(sys.argv[1].replace(".jsonl", ".eval_results.json")))["eval"]
passed = {}
for t, samples in res.items():
    for i, s in enumerate(samples):
        passed[(t, i)] = (s["base_status"] == "pass" and s["plus_status"] == "pass")
stat = collections.defaultdict(lambda: [0, 0])
n_records = 0
for line in open(sys.argv[2]):
    r = json.loads(line)
    n_records += 1
    s = stat[r["closure"]]
    s[1] += 1
    s[0] += passed[(r["task_id"], r["sample"])]
assert n_records == len(passed) > 0, f"records ({n_records}) != judged samples ({len(passed)})"
for c, (p, n) in sorted(stat.items()):
    print(f"closure={c}: plus-pass {p}/{n} = {p/n:.4f}")
EOF

TEMPLATE_CLASS="$("$VENV/bin/python" - "$MODEL" 2>/dev/null <<'PYEOF' || echo unknown
import sys
from transformers import AutoTokenizer
t = AutoTokenizer.from_pretrained(sys.argv[1])
p = t.apply_chat_template([{"role": "user", "content": "x"}], tokenize=False, add_generation_prompt=True, enable_thinking=True)
print("thinking-only (opens <think> in prompt)" if p.rfind("<think>") > p.rfind("</think>") else "hybrid (enable_thinking switch)")
PYEOF
)"
mkdir -p "$BASE/runs/manifests"
uv pip freeze --python "$VENV/bin/python" > "$BASE/runs/manifests/pip-freeze-think-$DATASET-$MODEL_ID.txt"
{
  echo "stage: think2phase"
  echo "dataset: $DATASET"
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)  slurm_job: ${SLURM_JOB_ID:-none}"
  echo "gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  echo "model: $MODEL"
  echo "model_revision: $(cat "$HF_HOME/hub/models--$MODEL_ID/refs/main" 2>/dev/null || echo unknown)"
  echo "protocol: phase1 no-prefill enable_thinking, T=0.6/top_p=0.95/top_k=20/min_p=0, budget 32768, stop-string </think>; phase2 forced RESP prefix + fence, budget 2048, pipeline stops; prefix caching on"
  echo "template_class: $TEMPLATE_CLASS"
  echo "n: $N"
  echo "judge_env: EVALPLUS_MAX_MEMORY_BYTES=${EVALPLUS_MAX_MEMORY_BYTES:-unset(default 4GB)}"
  echo "samples_file: $SAMPLES"
  echo "samples_sha256: $(sha256sum "$SAMPLES" | cut -d' ' -f1)"
  echo "records_sha256: $(sha256sum "$RECORDS" | cut -d' ' -f1)"
} > "$BASE/runs/manifests/think-$DATASET-$MODEL_ID.txt"

echo "STAGE think ($DATASET, $MODEL_ID) DONE"

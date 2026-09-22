#!/usr/bin/env bash
# Sync this repo's pipeline code to a cluster and submit one stage.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

STAGE="${1:?usage: ./submit.sh smoke|oracle|greedy|full|think [hf-model-id] [humaneval|mbpp] [cluster-name]}"
MODEL="${2:-}"     # empty = job.sbatch's default (Qwen/Qwen2.5-Coder-1.5B-Instruct)
DATASET="${3:-}"   # empty = the sbatch scripts' default (humaneval)
CLUSTER="${4:-${CLUSTER_NAME:-cluster}}"

# Pre-flight copies of job.sbatch's own checks: fail here, not after queueing.
case "$STAGE" in
  smoke|oracle|greedy|full|think) ;;
  *) echo "unknown stage: $STAGE" >&2; exit 2 ;;
esac
case "$DATASET" in
  ""|humaneval|mbpp) ;;
  *) echo "unknown dataset: $DATASET (want humaneval|mbpp)" >&2; exit 2 ;;
esac
case "$MODEL" in
  humaneval|mbpp)
    echo "'$MODEL' looks like a dataset in the model slot; use: ./submit.sh $STAGE '' $MODEL" >&2; exit 2 ;;
esac
if [[ "$STAGE" == "smoke" && -n "$DATASET" && "$DATASET" != "humaneval" ]]; then
  echo "smoke is humaneval-only" >&2; exit 2
fi
if [[ "$STAGE" == "think" ]]; then
  [[ -n "$MODEL" ]] || { echo "think needs an explicit model" >&2; exit 2; }
fi

# The cluster map: CLUSTER_HOST is the ssh host and CLUSTER_BASE the base directory on it, both from the environment.
HOST="${CLUSTER_HOST:?set CLUSTER_HOST to the ssh host of the cluster}"
BASE="${CLUSTER_BASE:?set CLUSTER_BASE to the base directory on the cluster}"

# Per-run job name: singleton then serializes only same-run submissions
# (protecting each resume file) instead of the whole pipeline. smoke+greedy
# share a name on purpose — they write the same temp_0.0 samples file.
MODEL_EFF="${MODEL:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"
DATASET_EFF="${DATASET:-humaneval}"
MODEL_KEY="${MODEL_EFF//\//--}"
case "$STAGE" in
  smoke|greedy) NAME="ev-$DATASET_EFF-$MODEL_KEY-t0.0" ;;
  full)         NAME="ev-$DATASET_EFF-$MODEL_KEY-t0.8" ;;
  oracle)       NAME="ev-$DATASET_EFF-oracle" ;;
  think)        NAME="think-$DATASET_EFF-$MODEL_KEY" ;;
esac
# Repeat arms (REPEAT=k env): distinct name + own output root via job.sbatch arg 4.
NAME="${NAME}${REPEAT:+-rep$REPEAT}"

if ssh "$HOST" "squeue -h -u \$USER -o %j" 2>/dev/null | grep -qE '^(humanevalplus$|qwen3think|q3think-)'; then
  if [[ "${FORCE:-0}" != 1 ]]; then
    echo "old-name jobs still queued on $CLUSTER; refusing new-name submission (FORCE=1 to override if unrelated)" >&2
    exit 3
  fi
fi

ssh "$HOST" "mkdir -p '$BASE/code' '$BASE/logs' '$BASE/runs'"
rsync -a --delete \
  --exclude .git --exclude runs --exclude logs \
  --exclude __pycache__ \
  ./ "$HOST:$BASE/code/"
rsync -a --delete ../../judge/ "$HOST:$BASE/code/judge/"
if [[ "$STAGE" == "think" ]]; then
  ssh "$HOST" "cd '$BASE' && sbatch --job-name='$NAME' ${QOS:+--qos=$QOS} ${WALL:+--time=$WALL} ${EXCLUDE:+--exclude=$EXCLUDE} code/qwen3-think/think.sbatch '$MODEL' '$DATASET_EFF' '${N:-128}'"
else
  ssh "$HOST" "cd '$BASE' && sbatch --job-name='$NAME' ${QOS:+--qos=$QOS} ${WALL:+--time=$WALL} ${EXCLUDE:+--exclude=$EXCLUDE} ${GPUS:+--gres=gpu:$GPUS} ${CPUS:+--cpus-per-task=$CPUS} ${MEM:+--mem=$MEM} code/job.sbatch '$STAGE' '$MODEL' '$DATASET' '${REPEAT:-}'"
fi

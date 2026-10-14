#!/usr/bin/env bash
#SBATCH --job-name=cmr-judge
#SBATCH --cpus-per-task=4
#SBATCH --mem=40G
#SBATCH --time=06:00:00
#SBATCH --output=logs/%x-%A_%a.out
#
# Judge one arm's samples on one task set, as an array over arms. Every path, partition and environment setting is
# a variable set in this script or in the environment file it reads; nothing is passed on the sbatch line.
#
#   sbatch --array=0-$((N-1)) --partition=<partition> cluster/judge.sbatch
#
# Memory: one evaluator worker holds the judged process at the record's memory limit (8 GiB) plus its own
# interpreter; four workers need about 40 GB on the node. The task set, the samples root and the output root come
# from the environment file.
set -euo pipefail
ENV_FILE="${CMR_ENV_FILE:-cluster/environment.sh}"
# shellcheck source=/dev/null
source "$ENV_FILE"                       # defines CMR_PYTHON, CMR_TASKS, CMR_SAMPLES_ROOT, CMR_OUT_ROOT, CMR_ARMS_FILE
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
ARM="$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$CMR_ARMS_FILE")"
[ -n "$ARM" ] || { echo "no arm at index $SLURM_ARRAY_TASK_ID in $CMR_ARMS_FILE"; exit 2; }
SAMPLES="$CMR_SAMPLES_ROOT/$ARM/samples.jsonl"
OUT="$CMR_OUT_ROOT/$ARM"
mkdir -p "$OUT" logs
echo "judging $ARM: tasks $CMR_TASKS, samples $SAMPLES, out $OUT"
"$CMR_PYTHON" -m code_model_reliability.cli judge \
  --tasks "$CMR_TASKS" --samples "$SAMPLES" --out "$OUT" \
  --workers "${SLURM_CPUS_PER_TASK:-4}" --per-test --cache "$CMR_OUT_ROOT/.reference-cache"

#!/usr/bin/env bash
#SBATCH --job-name=cmr-generate
#SBATCH --partition=<partition>
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH --output=logs/%x-%j.out
#
# One generation run on a Slurm cluster: a model, a task set, a protocol, so many attempts per task.
# Everything about the machine is set below or taken from the allocation; nothing travels on the sbatch line's
# environment. The run resumes from the attempts already on disk, so a pre-empted and requeued job continues.
#
# Submit from the repository root, for example:
#   sbatch cluster/generate.sbatch Qwen/Qwen2.5-Coder-7B-Instruct data/tasks/wave2 plain-chat out/wave2 128
# Arguments: <model> <task set: file, directory or humaneval|mbpp> <protocol> <output root> [attempts]
# A model that needs more than one GPU takes it from the allocation (--gres=gpu:N on the command line; the run
# reads SLURM_GPUS_ON_NODE for its tensor-parallel degree).
set -euo pipefail

MODEL="${1:?model id}"
TASKS="${2:?task set}"
PROTOCOL="${3:?protocol name}"
OUT_ROOT="${4:?output root}"
ATTEMPTS="${5:-128}"

ROOT="$PWD"                              # the repository root (sbatch keeps the submission directory)
VENV="${ROOT}/.venv-generate"            # built by cluster/environment.sh
CACHE="${ROOT}/.cache"                   # model weights and the harness's task files
export HF_HOME="${CACHE}/huggingface"
export XDG_CACHE_HOME="${CACHE}"
export TOKENIZERS_PARALLELISM=false

bash "${ROOT}/cluster/environment.sh" "$VENV"
VENV="$(readlink -f "$VENV")"            # this job keeps the environment current at its start
export PATH="${VENV}/bin:${PATH}"

STEM="${MODEL//\//--}"
SET_NAME="$(basename "${TASKS%.jsonl.gz}")"; SET_NAME="${SET_NAME%.jsonl}"
mkdir -p "${OUT_ROOT}/${SET_NAME}" logs
# the arm id is the output directory's name, composed as the package composes it: stem, protocol token, temperature
ARM="$(python -c "from code_model_reliability.generate import protocols as P; print(P.PROTOCOLS['${PROTOCOL}']('${MODEL}').arm)")"
OUT="${OUT_ROOT}/${SET_NAME}/${ARM}"

echo "job ${SLURM_JOB_ID:-none} on $(hostname): ${MODEL} x ${TASKS} under ${PROTOCOL}, ${ATTEMPTS} attempts -> ${OUT}"
cmr generate run --model "$MODEL" --tasks "$TASKS" --set-name "$SET_NAME" --protocol "$PROTOCOL" \
    --attempts "$ATTEMPTS" --out "$OUT" --tensor-parallel "${SLURM_GPUS_ON_NODE:-1}"
echo "done: ${OUT}"

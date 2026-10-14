#!/usr/bin/env bash
#SBATCH --job-name=cmr-tests
#SBATCH --partition=<partition>
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
#
# The test suite with the fitting engine's own tests on a CPU node: the unit tests of every stage, the end-to-end
# smoke on the fixture set, and the engine tests (a self-test, and a small fit run twice giving the same draws),
# which take minutes under the pinned numerical libraries. Everything about the environment is set below; nothing
# travels on the sbatch line's environment. Submit from the repository root: sbatch cluster/tests.sbatch
set -euo pipefail

ROOT="$PWD"                                 # the repository root (sbatch keeps the submission directory)
export UV_CACHE_DIR="${ROOT}/.cache/uv"
export CMR_FIT_ENGINE_TESTS=1               # the engine tests run only when asked, since they need the fit extra
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export XLA_FLAGS="--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"

cd "$ROOT"
uv run --python 3.12 --with pytest --with-editable '.[fit,judge,plot]' python -m pytest -q tests

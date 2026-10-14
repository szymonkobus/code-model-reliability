#!/usr/bin/env bash
# environment.sh — build the generation environment on a cluster's shared file system with uv.
#
# Usage: bash cluster/environment.sh <venv-dir> [cu129]
#   <venv-dir>  where the environment lives (a stable path the job scripts refer to)
#   cu129       on a machine whose GPU driver predates the default wheels' CUDA version: the inference engine's CUDA 12.9
#               wheel from its release page and the matching torch index are used instead
#
# Idempotent: the requirements file, the harness pin and the backend choice are hashed into a stamp inside the
# environment; when the stamp matches, nothing is rebuilt. A rebuild happens beside the old environment (a hash-named
# sibling) and the stable path is repointed atomically, so a running job keeps the environment it started with.
# The package itself is installed editable from the repository root, so `cmr` is on the environment's path.
set -euo pipefail

VENV="${1:?usage: environment.sh <venv-dir> [cu129]}"
BACKEND="${2:-}"
case "$BACKEND" in ""|cu129) ;; *) echo "unsupported backend: $BACKEND (use cu129 or nothing)" >&2; exit 2 ;; esac

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REQS="$HERE/requirements-generate.txt"
HARNESS_COMMIT="26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"
HARNESS_PIN="evalplus @ git+https://github.com/evalplus/evalplus.git@${HARNESS_COMMIT}"
VLLM_CU129_WHEEL="https://github.com/vllm-project/vllm/releases/download/v0.26.0/vllm-0.26.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"

mkdir -p "$(dirname "$VENV")"
exec 9>"$VENV.lock"
flock 9

want="$( { cat "$REQS"; echo "$HARNESS_PIN"; echo "backend=$BACKEND"; } | sha256sum | cut -d' ' -f1)"
if [[ -x "$VENV/bin/python" && "$(cat "$VENV/.stamp" 2>/dev/null)" == "$want" ]]; then
  echo "environment up to date: $VENV"
  exit 0
fi

GEN="$VENV-${want:0:12}"
if ! [[ -x "$GEN/bin/python" && "$(cat "$GEN/.stamp" 2>/dev/null)" == "$want" ]]; then
  rm -rf "$GEN"
  uv venv "$GEN" --python "$(command -v python3)"
  if [[ "$BACKEND" == cu129 ]]; then
    grep -v '^vllm==' "$REQS" > "$GEN/.requirements-without-vllm.txt"
    uv pip install --python "$GEN/bin/python" --torch-backend=cu129 "vllm @ $VLLM_CU129_WHEEL" -r "$GEN/.requirements-without-vllm.txt"
  else
    uv pip install --python "$GEN/bin/python" -r "$REQS"
  fi
  uv pip install --python "$GEN/bin/python" --no-deps "$HARNESS_PIN"
  uv pip install --python "$GEN/bin/python" --no-deps -e "$ROOT"
  echo "$want" > "$GEN/.stamp"
fi
if [[ -d "$VENV" && ! -L "$VENV" ]]; then
  mv "$VENV" "$VENV.previous.$(date +%s)"
fi
ln -sfn "$(basename "$GEN")" "$VENV"
echo "environment ready: $VENV -> $(basename "$GEN")"

#!/usr/bin/env bash
# Build the python env for the benchmark on the shared FS with uv. Idempotent:
# skips all work when the pinned requirements are unchanged since last build.
set -euo pipefail

VENV="${1:?usage: setup_env.sh <venv_dir> <requirements.txt> [cu129]}"
REQS="${2:?usage: setup_env.sh <venv_dir> <requirements.txt> [cu129]}"
TORCH_BACKEND="${3:-}"   # "cu129" on clusters whose GPU driver predates the default wheels' CUDA 13
case "$TORCH_BACKEND" in ""|cu129) ;; *) echo "unsupported torch backend: $TORCH_BACKEND" >&2; exit 2 ;; esac
STAMP="$VENV/.requirements.sha256"

# A cluster may pin a prebuilt environment: set PINNED_VENV to its path and this script only repoints the symlink.
if [[ -n "${PINNED_VENV:-}" ]]; then
  if [[ ! -x "$PINNED_VENV/bin/python" ]]; then
    echo "setup_env: pinned env $PINNED_VENV missing or broken; refusing to build or repoint" >&2; exit 3
  fi
  if [[ -e "$VENV" && ! -L "$VENV" ]]; then
    echo "setup_env: $VENV is a real directory, left untouched; use the pin $PINNED_VENV" >&2; exit 0
  fi
  ln -sfn "$PINNED_VENV" "$VENV"
  echo "setup_env: $VENV -> $PINNED_VENV (pinned; no rebuild)"
  exit 0
fi

# Installed with --no-deps: see the comment in requirements.txt.
EVALPLUS_PIN="evalplus @ git+https://github.com/evalplus/evalplus.git@26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"

# Per-run job names allow concurrent builds; serialize them.
exec 9>"$VENV.lock"
flock 9

want="$( { cat "$REQS" && echo "$EVALPLUS_PIN" && echo "tb=$TORCH_BACKEND"; } | sha256sum | cut -d' ' -f1)"
if [[ -x "$VENV/bin/python" && -f "$STAMP" && "$(cat "$STAMP")" == "$want" ]]; then
  echo "venv up to date: $VENV"
  exit 0
fi

# Generation scheme: $VENV is a stable symlink to a hash-named sibling.
# A rebuild never deletes a tree a running job may hold — it builds the new
# generation beside it and atomically repoints the symlink; stale
# generations die by disuse. ($VENV as a plain dir = pre-scheme build: it
# is displaced by rename, not deleted, on its first mismatch.)
GEN="$VENV-${want:0:12}"
if ! [[ -x "$GEN/bin/python" && "$(cat "$GEN/.requirements.sha256" 2>/dev/null)" == "$want" ]]; then
  rm -rf "$GEN"
  # --python pins the system interpreter: a uv-managed python would land in
  # the node-local home and break the venv for jobs on other nodes.
  uv venv "$GEN" --python "$(command -v python3)"
  if [[ -n "$TORCH_BACKEND" ]]; then
    VLLM_CU129="https://github.com/vllm-project/vllm/releases/download/v0.26.0/vllm-0.26.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
    grep -v '^vllm==' "$REQS" > "$GEN/.reqs-novllm.txt"
    uv pip install --python "$GEN/bin/python" --torch-backend=cu129 \
      "vllm @ $VLLM_CU129" -r "$GEN/.reqs-novllm.txt"
    uv pip install --python "$GEN/bin/python" --no-deps --reinstall \
      --index-url https://download.pytorch.org/whl/cu129 "torchcodec==0.16.0+cu129"
  else
    uv pip install --python "$GEN/bin/python" -r "$REQS"
  fi
  uv pip install --python "$GEN/bin/python" --no-deps "$EVALPLUS_PIN"
  echo "$want" > "$GEN/.requirements.sha256"
fi
if [[ -d "$VENV" && ! -L "$VENV" ]]; then
  mv "$VENV" "$VENV.displaced.$(date +%s)"
fi
ln -sfn "$(basename "$GEN")" "$VENV"
echo "venv ready: $VENV -> $(basename "$GEN")"

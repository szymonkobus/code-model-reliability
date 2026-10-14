#!/usr/bin/env bash
#SBATCH --job-name=cmr-fit
#SBATCH --partition=<partition>
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=16:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH --output=logs/%x-%A_%a.out
#
# One Slurm array task per line of a fit's manifest.tsv: each fits one arm with the settings of record and writes
# posterior_summary_<arm>.json. Submit from the fit directory (the one holding manifest.tsv and inputs/):
#
#   sbatch --array=0-$(($(wc -l < manifest.tsv)-1))%12 cluster/fit.sbatch
#
# Set the partition above and REPO_DIR below for your site. Every setting the fit needs is in this file, the
# manifest and the repository; nothing is passed through the submitting shell's environment, and no --export
# option belongs on the sbatch line. With --requeue a task that is stopped restarts and skips an arm whose
# result file already exists (the engine writes it once, at the end, so a non-empty file is a complete one).
# A full-length fit of an arm with about 1,300 tasks takes a few hours on 16 cores.

set -euo pipefail

FIT_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
REPO_DIR="${CMR_REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
MANIFEST="$FIT_DIR/manifest.tsv"

LINE="$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$MANIFEST")"
[ -n "$LINE" ] || { echo "no manifest line for array task $SLURM_ARRAY_TASK_ID" >&2; exit 2; }
NPZ="$(printf '%s' "$LINE" | cut -f1)"
EIV="$(printf '%s' "$LINE" | cut -f2)"
case "$EIV" in on|off) ;; *) echo "bad errors-in-variables switch '$EIV' in: $LINE" >&2; exit 2 ;; esac
[ -s "$FIT_DIR/inputs/$NPZ" ] || { echo "missing $FIT_DIR/inputs/$NPZ" >&2; exit 2; }

ARM="${NPZ%.npz}"
OUT="$FIT_DIR/posterior_summary_${ARM}.json"
mkdir -p "$FIT_DIR/logs"
if [ -s "$OUT" ]; then
  echo "already done: $OUT"
  exit 0
fi

# a node-local package cache: a shared network cache races when many cold tasks start at once
export UV_CACHE_DIR="${TMPDIR:-/tmp}/uv-cache-$(id -un)"
command -v uv >/dev/null 2>&1 || { echo "uv is required on the compute node" >&2; exit 2; }

echo "array task $SLURM_ARRAY_TASK_ID: arm=$ARM eiv=$EIV"
cd "$REPO_DIR"
PYTHONUNBUFFERED=1 uv run --extra fit cmr fit run --inputs "$FIT_DIR/inputs/$NPZ" --out "$OUT" --eiv "$EIV"
echo "done: $OUT"

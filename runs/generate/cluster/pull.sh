#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.."

CLUSTER="${1:-${CLUSTER_NAME:-cluster}}"
# Cluster map: keep in sync with submit.sh.
# The cluster map: CLUSTER_HOST is the ssh host and CLUSTER_BASE the base directory on it, both from the environment.
HOST="${CLUSTER_HOST:?set CLUSTER_HOST to the ssh host of the cluster}"
BASE="${CLUSTER_BASE:?set CLUSTER_BASE to the base directory on the cluster}"

mkdir -p runs/staging runs/logs
rsync -a "$HOST:$BASE/runs/" runs/staging/
rsync -a "$HOST:$BASE/logs/" runs/logs/
echo "pulled from $CLUSTER to runs/staging and runs/logs"

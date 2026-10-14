#!/usr/bin/env bash
cd "$(dirname "$0")/.."
LOG=data/.fold.log; : > "$LOG"
step() { local name="$1"; shift; local t0=$(date +%s); nice -n 10 "$@" >> "$LOG" 2>&1; local rc=$?; echo "STEP $name exit $rc ($(( $(date +%s) - t0 ))s)" | tee -a "$LOG"; }
run() { step "$1" uv run "scripts/$1.py"; }
echo "FOLD start $(date -u +%Y-%m-%dT%H:%M:%SZ) on fail-reruns map $(stat -c %y runs/fail-reruns/out/consistency_board_fullset.json | cut -c1-19)"
run clash_ownership; run identity_gradient; run clash_content; run task_trapness; run trap_susceptibility
run string_axis_replication; run clash_axes; run derivations
run rl_checkpoints; run build_knowledge_slots; run scoreboard_numbers; run build_details; run build_site
echo "FOLD end $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "failed steps: $(/usr/bin/grep -c -E '^STEP .* exit [1-9]' "$LOG")"
python3 scripts/check_wave_names.py || true

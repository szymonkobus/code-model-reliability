#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
OUTDIR=runs/fail-reruns/out
MAP=$OUTDIR/consistency_board_fullset.json
STATE=data/fold_state.json; LOG=data/.round.log; T0=$(date -u +%FT%TZ)
[ -r "$MAP" ] || { printf '%s | FOLD WATCH ERR: map unreadable at %s\n' "$T0" "$MAP" >> "$LOG"; bash scripts/round_alarm.sh "$(tail -n 1 "$LOG")"; exit 0; }
COUNTS=research/training/train-eval-liaison/out/trainprobe
RLFILES=$(grep -o -E 'counts_full_[A-Za-z0-9_.-]+\.csv' scripts/rl_checkpoints.py | sort -u)
VEC=$OUTDIR/fullset_vectors.jsonl.gz
SHA=$( { sha256sum "$MAP"; sha256sum "$VEC" 2>/dev/null; for f in $RLFILES; do if [ -e "$COUNTS/$f" ]; then ls -l --time-style=+%s "$COUNTS/$f"; else echo "missing $f"; fi; done; } | sha256sum | cut -c1-16); MT=$(stat -c %y "$MAP" | cut -c1-19)
[ "${1:-}" = --key ] && { echo "$SHA"; exit 0; }
LAST=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('map_sha',''))" "$STATE" 2>/dev/null)
[ "$SHA" = "$LAST" ] && exit 0   # quiet tick: the map has not moved since the last fold
if [ "$(pgrep -fc '^bash scripts/refresh_poolb.sh|^bash scripts/rebuild_frame.sh|^bash scripts/fold_clash.sh' || true)" != 0 ]; then
  printf '%s | fold deferred (chain in flight; map %s sha %s)\n' "$T0" "$MT" "$SHA" >> "$LOG"; exit 0
fi
B=data/.logs/fold_before_$(date -u +%Y%m%d_%H%MZ); mkdir -p "$B"
cp data/clash_ownership.json data/knowledge_slots.json data/scoreboard.json "$B"/ 2>/dev/null
bash scripts/fold_clash.sh > data/.fold.out 2>&1; RC=$?
FAILED=$(grep -a -c -E '^STEP \S+ exit [1-9]' data/.fold.out)
SUMMARY=$(python3 - "$B" "$SHA" "$MT" "${FAILED:-0}" <<'EOF'
import json, sys
from datetime import datetime, timezone
B, sha, mt, failed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
def leaves(o, path=''):
    if isinstance(o, dict):
        for k, v in o.items(): yield from leaves(v, f'{path}.{k}')
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from leaves(v, f'{path}[{i}]')
    else: yield path, o
def moved(name):
    try:
        a = dict(leaves(json.load(open(f'{B}/{name}')))); b = dict(leaves(json.load(open(f'data/{name}'))))
    except Exception:
        return -1   # unreadable: the review looks
    return sum(1 for p in set(a) | set(b) if a.get(p) != b.get(p))
def cov(path):
    try: return json.load(open(path)).get('coverage') or {}
    except Exception: return {}
cov_a, cov_b = cov(f'{B}/clash_ownership.json'), cov('data/clash_ownership.json')
st = {'map_sha': sha, 'map_mtime': mt, 'folded_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
      'failed_steps': failed, 'coverage': cov_b, 'coverage_before': cov_a,
      'knowledge_slots_leaves_moved': moved('knowledge_slots.json'), 'scoreboard_leaves_moved': moved('scoreboard.json'),
      'clash_ownership_leaves_moved': moved('clash_ownership.json'), 'before_copies': B}
json.dump(st, open('data/fold_state.json', 'w'), indent=1)
print(f"coverage cells {cov_a.get('cells')}->{cov_b.get('cells')} rows {cov_a.get('rows_complete')}/{cov_a.get('rows_total')}->{cov_b.get('rows_complete')}/{cov_b.get('rows_total')}"
      f" | slots leaves moved {st['knowledge_slots_leaves_moved']} | scoreboard leaves moved {st['scoreboard_leaves_moved']} | clash leaves moved {st['clash_ownership_leaves_moved']}")
EOF
)
CHECK=$(python3 scripts/round_check.py 2>&1 | tail -n 1)
printf '%s | FOLD on fail-reruns map %s sha %s rc=%s failed_steps=%s | %s | %s\n' "$T0" "$MT" "$SHA" "$RC" "${FAILED:-0}" "$(printf '%s' "$SUMMARY" | tr '\n' ' ')" "$CHECK" >> "$LOG"
bash scripts/round_alarm.sh "$(tail -n 1 "$LOG")"

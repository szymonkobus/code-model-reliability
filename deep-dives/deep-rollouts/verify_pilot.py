#!/usr/bin/env python3
"""Usage: python3 verify_pilot.py <rep-eval_results.json> <canonical-eval_results.json> [<rep-samples.jsonl> <canonical-samples.jsonl>]"""
import json
import math
import sys


def fails_by_task(path):
    ev = json.load(open(path))["eval"]
    return {t: sum(1 for s in ss if not (s.get("base_status") == "pass"
                                         and s.get("plus_status") == "pass"))
            for t, ss in ev.items()}, {t: len(ss) for t, ss in ev.items()}


def binom_two_sided_p(k, n, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    # exact two-sided via summing probabilities <= P(k)
    from math import comb
    pk = comb(n, k) * p**k * (1-p)**(n-k)
    tot = 0.0
    for i in range(n + 1):
        pi = comb(n, i) * p**i * (1-p)**(n-i)
        if pi <= pk * (1 + 1e-12):
            tot += pi
    return min(1.0, tot)


rep_f, rep_n = fails_by_task(sys.argv[1])
can_f, can_n = fails_by_task(sys.argv[2])

# A: counts
bad = [t for t, n in rep_n.items() if n != 128]
print(f"A counts: {len(rep_n)} tasks, per-task n=128 exact: {'PASS' if not bad else f'FAIL {bad[:5]}'}"
      f" (total {sum(rep_n.values())})")

# B: score
rp = 1 - sum(rep_f.values()) / sum(rep_n.values())
cp = 1 - sum(can_f.values()) / sum(can_n.values())
print(f"B plus-pass@1: repeat {rp:.4f} vs canonical {cp:.4f} (delta {rp-cp:+.4f})")

# C: per-task consistency
suspects = []
for t in can_f:
    if t not in rep_f:
        continue
    p_hat = can_f[t] / 128
    # Jeffreys-smoothed null to avoid p=0 degenerate
    p0 = (can_f[t] + 0.5) / 129
    pv = binom_two_sided_p(rep_f[t], rep_n[t], p0)
    if pv < 1e-4:
        suspects.append((t, can_f[t], rep_f[t], pv))
mean_shift = (sum(rep_f.values()) - sum(can_f.values())) / len(can_f)
print(f"C protocol identity: {len(suspects)} drift-suspect tasks (p<1e-4); "
      f"mean fail shift/task {mean_shift:+.3f}")
for t, cf, rf, pv in suspects[:10]:
    print(f"   {t}: canonical fails={cf} of 128 vs repeat fails={rf} of 128 (p={pv:.2e})")

# D: duplication
if len(sys.argv) > 4:
    def sols(path):
        d = {}
        for line in open(path):
            r = json.loads(line)
            d.setdefault(r["task_id"], []).append(r["solution"])
        return d
    a, b = sols(sys.argv[3]), sols(sys.argv[4])
    same = sum(1 for t in a if sorted(a[t]) == sorted(b.get(t, [])))
    print(f"D duplication: {same}/{len(a)} tasks byte-identical to canonical "
          f"({'PASS' if same < len(a) * 0.05 else 'FAIL — seed duplication?'})")

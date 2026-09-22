# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Cycle 5: how much of the residual can ANY small trait combination
explain, honestly (leave-one-out validated)?

Target: official combined-panel residual (41 models).
Features: breadth (n easy tasks with a failure), easy-band failure
entropy, consistency fingerprint entropy, trap rate, thinking flag.
All subsets of size 1-3, ordinary least squares, LOO R^2.
The stable-trait ceiling from the stability decomposition is ~40%.
"""

import itertools
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
traits = json.load(open(HERE / "data" / "traits.json"))
trap = json.load(open(HERE / "data" / "trap_traits.json"))

FEATS = ["n_easy_fail_tasks", "easy_H", "cons_entropy_fp",
         "cons_weighted_modal_share_fp", "deep_share", "baseline"]
rows = []
for m, v in traits.items():
    tr = trap.get(m, {}).get("trap_rate_comb")
    if any(v.get(f) is None for f in FEATS) or tr is None:
        continue
    rows.append([v["resid"]] + [v[f] for f in FEATS] +
                [tr, 1.0 if v["mode"] == "thinking" else 0.0])
data = np.array(rows)
y = data[:, 0]
X = data[:, 1:]
names = FEATS + ["trap_rate", "thinking"]
n = len(y)
print(f"n={n} models with all features")


def loo_r2(cols):
    errs = []
    for i in range(n):
        idx = [j for j in range(n) if j != i]
        A = np.hstack([np.ones((n - 1, 1)), X[np.ix_(idx, cols)]])
        beta, *_ = np.linalg.lstsq(A, y[idx], rcond=None)
        pred = np.hstack([[1.0], X[i, cols]]) @ beta
        errs.append((y[i] - pred) ** 2)
    return 1 - np.sum(errs) / np.sum((y - y.mean()) ** 2)


best = []
for k in (1, 2, 3):
    for cols in itertools.combinations(range(len(names)), k):
        best.append((loo_r2(list(cols)),
                     " + ".join(names[c] for c in cols)))
best.sort(reverse=True)
print("\ntop trait combinations by LOO R^2 (ceiling ~0.40):")
for r, desc in best[:12]:
    print(f"  {r:6.3f}  {desc}")
print("\nworst (for calibration):", f"{best[-1][0]:.3f} {best[-1][1]}")
import json as _json
_json.dump({"n_models": int(n), "top": [{"loo_r2": float(r), "combo": d} for r, d in best[:12]],
            "worst": {"loo_r2": float(best[-1][0]), "combo": best[-1][1]}},
           open(HERE / "data" / "multitrait.json", "w"), indent=1)

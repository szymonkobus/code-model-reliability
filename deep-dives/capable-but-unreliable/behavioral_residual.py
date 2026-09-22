# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Is the divergence a stable behavioral trait once the crossing
estimator's geometry is set aside?

Behavioral reliability proxy per pool: log easy-band failure rate
(failing attempts / attempts on kept tasks with pooled difficulty
< 20%). Residualize it on the pool's capability (official 50%
crossing). Compare:
  (a) cross-pool stability of this behavioral residual
  (b) cross-pool stability of the official crossing residual (0.35)
  (c) how well the behavioral residual predicts the official one
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EASY = 0.20

diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])

counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))

resid_json = json.load(open(HERE / "data" / "residuals.json"))
perb = json.load(open(HERE / "data" / "per_benchmark_residuals.json"))
models = sorted(counts)


def easy_rate(m, pred):
    f = sum(counts[m][t][1] - counts[m][t][0]
            for t in counts[m] if diff.get(t, 1) < EASY and pred(t))
    a = sum(counts[m][t][1]
            for t in counts[m] if diff.get(t, 1) < EASY and pred(t))
    return (f + 0.5) / (a + 1)


def residualize(xy):
    x = np.array([p[0] for p in xy])
    y = np.array([p[1] for p in xy])
    A = np.vstack([np.ones_like(x), x]).T
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


SCOPES = {
    "he": (lambda t: t.startswith("HumanEval"), "cap_he"),
    "mbpp": (lambda t: t.startswith("Mbpp"), "cap_mbpp"),
    "comb": (lambda t: True, "cap"),
}

beh = {}
for scope, (pred, capkey) in SCOPES.items():
    sub = []
    for m in models:
        v = resid_json["models"].get(m, {})
        cap = v.get(capkey, [None, math.inf])[1]
        if cap is None or not math.isfinite(cap):
            continue
        sub.append((m, cap, math.log(easy_rate(m, pred))))
    res = residualize([(c, r) for _, c, r in sub])
    beh[scope] = {m: float(r) for (m, _, _), r in zip(sub, res)}
    print(f"{scope}: n={len(sub)} behavioral-residual sd={res.std():.3f}")


def corr(d1, d2):
    common = sorted(set(d1) & set(d2))
    x = np.array([d1[m] for m in common])
    y = np.array([d2[m] for m in common])
    r = np.corrcoef(x, y)[0, 1]
    rs = np.corrcoef(np.argsort(np.argsort(x)),
                     np.argsort(np.argsort(y)))[0, 1]
    return r, rs, len(common)


r, rs, n = corr(beh["he"], beh["mbpp"])
print(f"\n(a) behavioral residual stability corr(HE,MBPP) = {r:.3f} "
      f"(spearman {rs:.3f}, n={n})")
r, rs, n = corr(perb["he"], perb["mbpp"])
print(f"(b) official crossing residual stability          = {r:.3f} "
      f"(spearman {rs:.3f}, n={n})")

off_comb = {m: v["residual"] for m, v in resid_json["models"].items()
            if v["residual"] is not None}
corr_official = {}
for scope, off in [("he", perb["he"]), ("mbpp", perb["mbpp"]),
                   ("comb", off_comb)]:
    r, rs, n = corr(beh[scope], off)
    corr_official[scope] = {"r": float(r), "spearman": float(rs), "n": int(n)}
    print(f"(c) behavioral vs official residual [{scope}]: r={r:.3f} "
          f"R2={r*r:.3f} (n={n})")
beh["corr_official"] = corr_official

json.dump(beh, open(HERE / "data" / "behavioral_residuals.json", "w"),
          indent=1)

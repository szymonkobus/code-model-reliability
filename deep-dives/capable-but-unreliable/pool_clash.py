# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Cycle 4: what is the systematic model x pool clash made of?

Tests:
 1. Family structure: eta^2 + leave-one-out R^2 of clash by family.
    If lineages share their clash, post-training data decides WHICH
    pool a model diverges on.
 2. Also: quadratic capability term on the combined official residual
    (is part of the 'divergence' just line curvature?).
 3. Task-level carriers: for each family with |mean clash| large,
    list the easy tasks where its members' pooled failure rate most
    exceeds the rest of the board's (per pool).
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EASY = 0.20

beh = json.load(open(HERE / "data" / "behavioral_residuals.json"))
resid_json = json.load(open(HERE / "data" / "residuals.json"))
fam = {m: v["family"] for m, v in resid_json["models"].items()}

clash = {m: beh["he"][m] - beh["mbpp"][m]
         for m in beh["he"] if m in beh["mbpp"]}
y = np.array(list(clash.values()))
ms = list(clash)
print(f"clash sd = {y.std():.3f} (n={len(ms)})")

grand = y.mean()
sst = ((y - grand) ** 2).sum()
ssb = 0.0
loo_pred = []
for m in ms:
    peers = [clash[m2] for m2 in ms if fam[m2] == fam[m] and m2 != m]
    loo_pred.append(np.mean(peers) if peers else grand)
for f in set(fam[m] for m in ms):
    grp = y[[i for i, m in enumerate(ms) if fam[m] == f]]
    ssb += len(grp) * (grp.mean() - grand) ** 2
eta2 = ssb / sst
k = len(set(fam[m] for m in ms))
loo = 1 - ((y - np.array(loo_pred)) ** 2).sum() / sst
print(f"clash by family: k={k} eta2={eta2:.3f} LOO_R2={loo:.3f}")

print("\nfamily mean clash (positive = relatively better on HE+):")
fmeans = defaultdict(list)
for m in ms:
    fmeans[fam[m]].append(clash[m])
for f, vs in sorted(fmeans.items(), key=lambda kv: -abs(np.mean(kv[1]))):
    print(f"  {f:22s} {np.mean(vs):+.3f} (n={len(vs)}, sd {np.std(vs):.3f})")

# 2. curvature check on the official combined residual
off = {m: v["residual"] for m, v in resid_json["models"].items()
       if v["residual"] is not None}
cap = {m: v["cap"][1] for m, v in resid_json["models"].items()
       if v["residual"] is not None}
x = np.array([cap[m] for m in off])
yy = np.array([off[m] for m in off])
A = np.vstack([np.ones_like(x), x, x ** 2]).T
beta, res_, *_ = np.linalg.lstsq(A, yy, rcond=None)
pred = A @ beta
r2 = 1 - ((yy - pred) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()
print(f"\ncurvature: residual ~ cap + cap^2: R2={r2:.3f} "
      f"(quad coef {beta[2]:+.3f})")
json.dump({"n": len(ms), "clash_sd": float(y.std()), "k_families": int(k), "eta2": float(eta2), "loo_r2": float(loo),
           "family_mean_clash": {f: float(np.mean(v)) for f, v in fmeans.items()},
           "curvature_r2": float(r2), "curvature_quad_coef": float(beta[2])},
          open(HERE / "data" / "pool_clash.json", "w"), indent=1)

# 3. task carriers for the biggest-clash families
diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])
counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))

big_fams = [f for f, vs in fmeans.items()
            if abs(np.mean(vs)) > 0.25 and len(vs) >= 3]
for f in big_fams:
    members = [m for m in ms if fam[m] == f]
    others = [m for m in counts if m not in members]
    worse_pool = "HumanEval" if np.mean(fmeans[f]) < 0 else "Mbpp"
    rows = []
    for t in diff:
        if diff[t] >= EASY or not t.startswith(worse_pool):
            continue
        fr_fam = np.mean([(counts[m][t][1] - counts[m][t][0]) /
                          counts[m][t][1] for m in members
                          if t in counts[m]])
        fr_oth = np.mean([(counts[m][t][1] - counts[m][t][0]) /
                          counts[m][t][1] for m in others
                          if t in counts[m]])
        rows.append((fr_fam - fr_oth, t, fr_fam, fr_oth))
    rows.sort(reverse=True)
    print(f"\n{f} (mean clash {np.mean(fmeans[f]):+.2f}; worse on "
          f"{worse_pool}) — top excess-failure easy tasks there:")
    for d, t, a, b in rows[:8]:
        print(f"  {t:16s} family fail {a:5.1%} vs board {b:5.1%} "
              f"(excess {d:+.1%})")

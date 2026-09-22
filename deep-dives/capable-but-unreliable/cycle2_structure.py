# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Structure checks that bound the divergence question."""

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
d = json.load(open(HERE / "data" / "residuals.json"))
models = d["models"]
SLOPE = d["fit"]["slope"]


def fit_and_residuals(cap_key, rel_key):
    pts = {m: (v[cap_key][1], v[rel_key][1]) for m, v in models.items()
           if cap_key in v and rel_key in v
           and math.isfinite(v[cap_key][1]) and math.isfinite(v[rel_key][1])}
    x = np.array([p[0] for p in pts.values()])
    y = np.array([p[1] for p in pts.values()])
    b = ((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
    a = y.mean() - b * x.mean()
    return {m: (yy - (a + b * xx)) for m, (xx, yy) in pts.items()}, b


he, b_he = fit_and_residuals("cap_he", "rel_he")
mb, b_mb = fit_and_residuals("cap_mbpp", "rel_mbpp")
common = sorted(set(he) & set(mb))
xh = np.array([he[m] for m in common])
xm = np.array([mb[m] for m in common])
r = np.corrcoef(xh, xm)[0, 1]
rs = np.corrcoef(np.argsort(np.argsort(xh)), np.argsort(np.argsort(xm)))[0, 1]
print(f"per-benchmark residuals: n={len(common)} "
      f"(HE slope {b_he:.3f}, MBPP slope {b_mb:.3f})")
print(f"corr(HE resid, MBPP resid) = {r:.3f} (R2 {r*r:.3f}), "
      f"spearman {rs:.3f}")
print(f"HE resid sd {xh.std():.3f}, MBPP resid sd {xm.std():.3f}")

json.dump({"he": he, "mbpp": mb, "corr": float(r), "spearman": float(rs)},
          open(HERE / "data" / "per_benchmark_residuals.json", "w"), indent=1)

# --- delta-method noise floor on the combined panel ---
noise_vars, resids = [], []
skipped = 0
for m, v in models.items():
    if v["residual"] is None:
        continue
    cl, cm, ch = v["cap"]
    rl, rm, rh = v["rel"]
    if not all(map(math.isfinite, [cl, ch, rl, rh])):
        skipped += 1
        continue
    se_c = (ch - cl) / (2 * 1.96)
    se_r = (rh - rl) / (2 * 1.96)
    noise_vars.append(se_r ** 2 + (SLOPE * se_c) ** 2)
    resids.append(v["residual"])
resids = np.array(resids)
var_tot = resids.var()
noise = float(np.mean(noise_vars))
print(f"\nnoise floor (delta method, {len(resids)} models, "
      f"{skipped} skipped for censored interval ends):")
print(f"observed residual variance {var_tot:.4f} (sd {var_tot**.5:.3f})")
print(f"mean noise variance (indep upper bound) {noise:.4f} "
      f"(sd {noise**.5:.3f})")
print(f"noise share upper bound {noise/var_tot:.3f} -> explainable "
      f"share lower bound {1-noise/var_tot:.3f}")

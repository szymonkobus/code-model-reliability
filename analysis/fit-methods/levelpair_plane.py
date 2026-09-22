"""Level-pair plane: for every pair of failure levels (a1, a2), the
between-model relation of crossing difficulties {(f_m(l1), f_m(l2))}.

Estimators per pair (models with both crossings finite, need >= 20):
  ols   = OLS slope of z(l2) on z(l1)  (attenuated by x-noise)
  rma   = reduced-major-axis slope = sign * sd(y)/sd(x)
          (errors-in-variables-robust when the two coordinates carry
          comparable noise, which holds by symmetry of construction)
  R     = Pearson correlation
Outputs fits/levelpair_plane.csv (l1, l2, a1, a2, n, ols, rma, R) and
prints a summary over the resolved region.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
GRID_LO, GRID_HI, GRID_N = -10.982711, 3.94182, 454
LEV = np.linspace(GRID_LO, GRID_HI, GRID_N)
STRIDE = 8  # every ~0.26 logit


def main():
    cr = pd.read_csv(BASE / "data/crossings.csv")
    piv = cr.pivot(index="model", columns="level_logit",
                   values="z_mid")
    piv = piv.replace([np.inf, -np.inf], np.nan)
    levels = np.array(sorted(piv.columns))[::STRIDE]
    Z = piv[levels].to_numpy()  # models x levels
    rows = []
    for i, l1 in enumerate(levels):
        for j, l2 in enumerate(levels):
            if j <= i:
                continue
            x, y = Z[:, i], Z[:, j]
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 20:
                continue
            xv, yv = x[ok], y[ok]
            sx, sy = xv.std(ddof=1), yv.std(ddof=1)
            r = float(np.corrcoef(xv, yv)[0, 1])
            ols = r * sy / sx
            rma = np.sign(r) * sy / sx
            rows.append(dict(
                l1=float(l1), l2=float(l2),
                a1=float(1 / (1 + np.exp(-l1))),
                a2=float(1 / (1 + np.exp(-l2))),
                n=int(ok.sum()), ols=float(ols), rma=float(rma),
                R=r))
    df = pd.DataFrame(rows)
    df.to_csv(BASE / "fits/levelpair_plane.csv", index=False)
    print(f"{len(df)} pairs with n>=20 of 28 models")
    # resolved region summary: both levels between failure 1% and 90%
    res = df[(df.a1 >= 0.01) & (df.a2 <= 0.90)]
    print("\nRESOLVED region (1% <= a1, a2 <= 90%):", len(res), "pairs")
    for col in ("ols", "rma", "R"):
        q = res[col].quantile([0.05, 0.5, 0.95])
        print(f"  {col}: median {q[0.5]:.3f}, 5-95% [{q[0.05]:.3f}, "
              f"{q[0.95]:.3f}]")
    # where does rma depart from 1 by >0.15?
    dep = res[np.abs(res.rma - 1) > 0.15]
    print(f"  |rma-1|>0.15 in {len(dep)}/{len(res)} resolved pairs")
    if len(dep):
        print("  departure locations (a1 -> a2, rma):")
        for _, r_ in dep.sort_values("rma").head(8).iterrows():
            print(f"    {100*r_.a1:5.1f}% -> {100*r_.a2:5.1f}%  "
                  f"rma={r_.rma:.2f} R={r_.R:.2f} n={r_.n}")
    # gap dependence: rma vs level gap (l2-l1) in resolved region
    res = res.assign(gap=res.l2 - res.l1)
    for glo, ghi in ((0, 2), (2, 4), (4, 8)):
        s = res[(res.gap >= glo) & (res.gap < ghi)]
        if len(s):
            print(f"  gap {glo}-{ghi} logits: median rma "
                  f"{s.rma.median():.3f}, median R {s.R.median():.3f} "
                  f"({len(s)} pairs)")


if __name__ == "__main__":
    main()

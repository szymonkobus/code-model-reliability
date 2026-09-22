"""Two theory tests on the existing arcs (no fitting):

Writes fits/evt_crossk.csv, fits/shape_collapse.csv; prints summaries.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
GRID_LO, GRID_HI, GRID_N = -10.982711, 3.94182, 454
LEV = np.linspace(GRID_LO, GRID_HI, GRID_N)


def main():
    slopes = pd.read_csv(BASE / "data/trace_slopes.csv")
    traces = pd.read_csv(BASE / "data/traces.csv")
    cross = pd.read_csv(BASE / "data/crossings.csv")

    # --- 1. EVT cross-K ---
    rows = []
    for model, g in slopes.groupby("model"):
        r = {"model": model}
        for K in (10, 50):
            gk = g[g.K == K].sort_values("l")
            n20 = max(int(len(gk) * 0.2), 5)
            sl = gk.slope.iloc[:n20]
            sl = sl[np.isfinite(sl) & (sl > 0)]
            if len(sl) >= 3:
                r[f"slope{K}"] = float(np.median(sl))
                r[f"gamma{K}"] = float(np.log(np.median(sl)) / np.log(K))
        if "gamma10" in r and "gamma50" in r:
            r["gamma_diff"] = r["gamma50"] - r["gamma10"]
            rows.append(r)
    evt = pd.DataFrame(rows)
    evt.to_csv(BASE / "fits/evt_crossk.csv", index=False)
    print("EVT cross-K: gamma10 vs gamma50 (should match if RV-tail)")
    print(evt[["gamma10", "gamma50", "gamma_diff"]].describe()
          .loc[["mean", "50%", "std"]].round(3))

    # --- 2. Shape collapse ---
    # c and m per model from the crossing function around level 0
    cm = {}
    for model, g in cross.groupby("model"):
        g = g.sort_values("level_logit")
        z = g.z_mid.to_numpy().copy()
        z[~np.isfinite(z)] = np.nan
        fin = np.isfinite(z)
        lf, zf = LEV[fin], z[fin]
        if lf.min() > -0.5 or lf.max() < 0.5:
            continue
        c = float(np.interp(0.0, lf, zf))
        # local slope from +-0.75 logit window around 0
        w = (lf > -0.75) & (lf < 0.75)
        m = float(np.polyfit(lf[w], zf[w], 1)[0])
        cm[model] = (c, m)

    ugrid = np.linspace(-6, 3, 60)
    rows = []
    curves = {10: [], 50: []}
    for (model, K), g in traces.groupby(["model", "K"]):
        if model not in cm:
            continue
        c, m = cm[model]
        u = (g.x.to_numpy() - c) / m
        v = (g.y.to_numpy() - c) / m
        o = np.argsort(u)
        vi = np.interp(ugrid, u[o], v[o], left=np.nan, right=np.nan)
        theory = ugrid - np.log(K) - np.logaddexp(0, ugrid)
        dev = vi - theory
        rows.append(dict(model=model, K=K,
                         rms_dev_theory=float(np.sqrt(np.nanmean(dev**2))),
                         n_grid=int(np.isfinite(dev).sum())))
        curves[K].append(vi)
    col = pd.DataFrame(rows)
    col.to_csv(BASE / "fits/shape_collapse.csv", index=False)
    print("\nShape collapse: RMS deviation from theory softplus "
          "(normalized units = logit-difficulty / m):")
    print(col.groupby("K").rms_dev_theory.describe()
          .loc[:, ["mean", "50%", "max"]].round(3))
    for K in (10, 50):
        M = np.vstack(curves[K])
        iqr = np.nanpercentile(M, 75, axis=0) - np.nanpercentile(M, 25,
                                                                 axis=0)
        print(f"K={K}: cross-model IQR of normalized v: "
              f"median {np.nanmedian(iqr):.3f}, max {np.nanmax(iqr):.3f}")


if __name__ == "__main__":
    main()

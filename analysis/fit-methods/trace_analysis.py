"""Build the K-fold traces (z(a), z(a/K)) and decompose their slope.

Identity (exact, by chain rule): along the trace, with l = logit(a),
l_K = logit(a/K), f = crossing function z(.):

T runs 1 -> 0 as a -> 1: the construction alone yields a knee.
S depends on the trend's shape (linear logit-logit trend => f linear
=> S = 1 identically).

Outputs:
  data/traces.csv          model, K, l, a, x, y (finite region only)
  data/trace_slopes.csv    model, K, l, a, slope, T, S (log-slope
                           decomposition; finite differences)
  fits/knee_summary.csv    per model+K: knee location (max |d log
                           slope / dl|), slope-1 regime slope, plateau
                           slope, log-slope drop attributable to T vs S
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
GRID_LO, GRID_HI, GRID_N = -10.982711, 3.94182, 454
STEP = (GRID_HI - GRID_LO) / (GRID_N - 1)
LEV = np.linspace(GRID_LO, GRID_HI, GRID_N)
KS = [10, 50]


def logit(p):
    return math.log(p / (1 - p))


def expit(x):
    return 1 / (1 + np.exp(-x))


def interp_cross(lev_grid, z_grid, lq):
    """z at arbitrary level lq by linear interpolation on the grid,
    NaN outside the finite region."""
    finite = np.isfinite(z_grid)
    if finite.sum() < 2:
        return np.full_like(lq, np.nan)
    lo, hi = lev_grid[finite][0], lev_grid[finite][-1]
    out = np.interp(lq, lev_grid[finite], z_grid[finite])
    out[(lq < lo) | (lq > hi)] = np.nan
    return out


def main():
    cross = pd.read_csv(BASE / "data/crossings.csv")
    trace_rows, slope_rows, summary = [], [], []

    for model, g in cross.groupby("model"):
        g = g.sort_values("level_logit")
        zg = g.z_mid.to_numpy().copy()
        zg[~np.isfinite(zg)] = np.nan
        for K in KS:
            a = expit(LEV)
            lK = np.log(a / K) - np.log1p(-a / K)
            x = interp_cross(LEV, zg, LEV)
            y = interp_cross(LEV, zg, lK)
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 10:
                continue
            l_ok, a_ok, x_ok, y_ok = LEV[ok], a[ok], x[ok], y[ok]
            for li, ai, xi, yi in zip(l_ok, a_ok, x_ok, y_ok):
                trace_rows.append((model, K, li, ai, xi, yi))

            # slope + decomposition via central differences on the
            # finite subgrid (uniform in l)
            dx = np.gradient(x_ok, l_ok)
            dy = np.gradient(y_ok, l_ok)
            slope = dy / dx
            T = K * (1 - a_ok) / (K - a_ok)
            # S = slope / T (exact given slope = T*S)
            S = slope / T
            for li, ai, si, ti, ssi in zip(l_ok, a_ok, slope, T, S):
                slope_rows.append((model, K, li, ai, si, ti, ssi))

            # knee: max |d log slope / dl| where slope>0
            pos = slope > 1e-6
            ls = np.full(len(slope), np.nan)
            ls[pos] = np.log(slope[pos])
            dls = np.gradient(ls, l_ok)
            if np.isfinite(dls).sum() > 5:
                knee_i = np.nanargmax(np.abs(dls))
                # regime slopes: median slope in first and last quartile
                q = len(slope) // 4
                early = np.nanmedian(slope[:q])
                late = np.nanmedian(slope[-q:])
                # attribution over the whole arc: total drop in log
                # slope = drop in log T + drop in log S
                lt = np.log(T)
                lss = np.where(S > 1e-6, np.log(np.maximum(S, 1e-6)),
                               np.nan)
                dT = lt[-1] - lt[0]
                fin = np.isfinite(lss)
                dS = (lss[fin][-1] - lss[fin][0]) if fin.sum() > 2 else np.nan
                dtot = (ls[pos][-1] - ls[pos][0]) if pos.sum() > 2 else np.nan
                summary.append((model, K, l_ok[knee_i], a_ok[knee_i],
                                x_ok[knee_i], y_ok[knee_i], early, late,
                                dtot, dT, dS))

    pd.DataFrame(trace_rows, columns=["model", "K", "l", "a", "x", "y"]
                 ).to_csv(BASE / "data/traces.csv", index=False)
    pd.DataFrame(slope_rows,
                 columns=["model", "K", "l", "a", "slope", "T", "S"]
                 ).to_csv(BASE / "data/trace_slopes.csv", index=False)
    df = pd.DataFrame(summary, columns=[
        "model", "K", "knee_l", "knee_a", "knee_x", "knee_y",
        "early_slope", "late_slope", "dlog_slope_total",
        "dlog_T", "dlog_S"])
    (BASE / "fits").mkdir(exist_ok=True)
    df.to_csv(BASE / "fits/knee_summary.csv", index=False)
    pd.set_option("display.width", 200)
    print(df.round(3).to_string(index=False))
    print("\nMedians by K:")
    print(df.groupby("K")[["knee_a", "early_slope", "late_slope",
                           "dlog_slope_total", "dlog_T", "dlog_S"]]
          .median().round(3))


if __name__ == "__main__":
    main()

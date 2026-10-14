"""The draw-free summary of one arm's fit, the file the figures and the two pages read.

From a result file (about 11 MB with its draws) to about 60 KB per arm: the curve ribbons, the level tables, the
two crossings under both curve definitions, the dispersion parameters and the densities of the crossing draws.
One object per arm::

    {"arm": "<arm id>",
     "curves": {"zgrid": [121], "quantiles_pct": [5, 10, 25, 50, 75, 90, 95],
                "average": [7 rows of 121: the average-rate curve's logit failure rate per quantile],
                "median_task": [7 rows of 121]},
     "levels": {"average": {"method", "rule", "levels_fail_rate", "median_z", "cri80_lo_z", "cri80_hi_z",
                            "p_left_censored", "p_right_censored"}, "median_task": {the same keys}},
     "estimands": {"average": {"d50": {"median_z", "cri80_z": [lo, hi], "p_left_censored", "p_right_censored",
                                       "status"}, "d99": {the same}}, "median_task": {"d50": ..., "d99": ...}},
     "tau": {"median", "cri80": [lo, hi]}, "rho": {"median", "cri80": [lo, hi]},
     "density": {"grid": [220: the fit grid's low end minus 0.2 to its high end plus 0.2],
                 "average": {"d50": [220], "d99": [220]}, "median_task": {"d50": [220], "d99": [220]}}}

The estimands are read by ``crossings.level_read`` (the all-draws median and interval with the censored draws
beyond the ends), so the summary and the crossings table carry one number. A density is a Gaussian kernel
estimate over every exported draw of the crossing, a censored draw placed at the grid end it lies past,
Silverman's bandwidth 0.9 sd n^(-1/5) with a floor of 0.02, normalised to its maximum. Floats are rounded to
four decimals.

Reads ``posterior_summary_<arm>.json`` files. Writes ``arms/<arm>.json``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

import numpy as np

from .crossings import arm_of, draws_of, level_read, load_result

DENSITY_N = 220
DENSITY_MARGIN = 0.2
BANDWIDTH_FLOOR = 0.02
LEVEL_KEYS = ("levels_fail_rate", "median_z", "cri80_lo_z", "cri80_hi_z", "p_left_censored", "p_right_censored")


def kde(vals, grid):
    """A Gaussian kernel density of ``vals`` on ``grid``, normalised to its maximum; zeros for fewer than ten values."""
    vals = np.asarray(vals, float)
    grid = np.asarray(grid, float)
    if len(vals) < 10:
        return np.zeros_like(grid)
    sd = vals.std()
    bw = max(0.9 * sd * len(vals) ** (-1 / 5), BANDWIDTH_FLOOR)
    d = np.zeros_like(grid)
    for i in range(0, len(vals), 4000):
        v = vals[i:i + 4000]
        d += np.exp(-0.5 * ((grid[None, :] - v[:, None]) / bw) ** 2).sum(0)
    d /= d.max() if d.max() > 0 else 1.0
    return d


def _r4(x):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [_r4(v) for v in x]
    return round(float(x), 4)


def _density_draws(result, curve, level, lo, hi):
    z, cen, _ = draws_of(result, curve, level)
    if z is None:
        return None
    vals = []
    for v, c in zip(z, cen):
        if c < 0:
            vals.append(lo)
        elif c > 0:
            vals.append(hi)
        elif v is not None:
            vals.append(float(v))
    return vals


def arm_summary(result: dict, arm: str) -> dict:
    cv = result.get("curves") or {}
    grid = result.get("grid") or {}
    glo, ghi = float(grid["lo"]), float(grid["hi"])
    dgrid = np.linspace(glo - DENSITY_MARGIN, ghi + DENSITY_MARGIN, DENSITY_N)
    out = {
        "arm": arm,
        "curves": {"zgrid": _r4(cv.get("zgrid")), "quantiles_pct": cv.get("quantiles_pct"),
                   "average": _r4(cv.get("average_logit")), "median_task": _r4(cv.get("typical_logit"))},
        "levels": {},
        "estimands": {"average": {}, "median_task": {}},
        "tau": {"median": _r4((result.get("tau") or {}).get("median")), "cri80": _r4((result.get("tau") or {}).get("cri80"))},
        "rho": {"median": _r4((result.get("rho_icc") or {}).get("median")), "cri80": _r4((result.get("rho_icc") or {}).get("cri80"))},
        "density": {"grid": _r4(list(dgrid)), "average": {}, "median_task": {}},
    }
    for curve, key in (("average", "levels_table_avg"), ("median_task", "levels_table")):
        lt = result.get(key) or {}
        out["levels"][curve] = {"method": lt.get("method"), "rule": lt.get("rule"),
                                **{k: _r4(lt.get(k)) if k != "levels_fail_rate" else lt.get(k) for k in LEVEL_KEYS}}
        for lv in ("d50", "d99"):
            r = level_read(result, curve, lv)
            out["estimands"][curve][lv] = {"median_z": _r4(r["z"]), "cri80_z": _r4([r["lo"], r["hi"]]),
                                           "p_left_censored": _r4(r["p_left_censored"]),
                                           "p_right_censored": _r4(r["p_right_censored"]), "status": r["status"]}
            vals = _density_draws(result, curve, lv, glo, ghi)
            out["density"][curve][lv] = None if vals is None else _r4(list(kde(vals, dgrid)))
    return out


def write_summaries(results_dir, out_dir, pattern="posterior_summary_*.json") -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for path in sorted(glob.glob(os.path.join(results_dir, pattern))):
        arm = arm_of(path)
        s = arm_summary(load_result(path), arm)
        p = out_dir / f"{arm}.json"
        p.write_text(json.dumps(s, separators=(",", ":")) + "\n", encoding="utf-8")
        written.append(str(p))
    return written


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit summaries", description="draw-free per-arm summaries for the figures and pages")
    ap.add_argument("--results", required=True)
    ap.add_argument("--out-dir", required=True, help="the arms/ directory to write")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    written = write_summaries(args.results, args.out_dir)
    print(f"summaries: {len(written)} arms written under {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

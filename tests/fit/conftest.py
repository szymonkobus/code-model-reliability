"""Shared builders for the fit stage's tests: a synthetic engine result with known draws, and a cells table."""

from __future__ import annotations

import csv
import json
import math

import numpy as np
import pytest

from code_model_reliability.fit import rules


def _logistic_curve(zgrid, mid, slope):
    return 1.0 / (1.0 + np.exp(-slope * (zgrid - mid)))


def make_result(n_chains=4, per_chain=50, grid_lo=-4.0, grid_hi=4.0, d50_center=0.0, d99_center=-3.0,
                left_share_d99=0.0, right_share_d50=0.0, chain_shift=0.0, seed=0, with_full=True, rule="middle"):
    """A result dict in the engine's shape whose crossing draws are drawn from known normals.

    ``left_share_d99``: the share of D99 draws censored below the scale; ``right_share_d50``: the share of D50
    draws censored above it; ``chain_shift``: an offset added to the last chain's draws (a mixing failure)."""
    rng = np.random.default_rng(seed)
    n = n_chains * per_chain
    out = {"model_id": "arm-x", "config": {"chains": n_chains, "warmup": 10, "samples": per_chain, "n_tasks": 60,
                                           "crossing_rule": rule, "engine_sha256": "0" * 64, "m_basis": 40, "hsgp_L": 9.0},
           "grid": {"lo": grid_lo, "hi": grid_hi, "n": rules.GRID_N},
           "diagnostics": {"num_divergences": 0, "divergence_gate": "pass", "rhat_gate": "pass", "ess_gate": "pass",
                           "rhat_max_gated": 1.0, "bulk_ess_min_gated": 1000.0, "all_pass": True,
                           "rhat_gated": {"eta": 1.0, "ell": 1.0, "tau": 1.0, "mu1": 1.0, "d50": 1.0, "d99": 1.0},
                           "bulk_ess_gated": {"eta": 1000.0, "ell": 1000.0, "tau": 1000.0, "mu1": 1000.0, "d50": 1000.0, "d99": 1000.0}},
           "tau": {"median": 1.5, "cri80": [1.4, 1.6], "mean": 1.5},
           "rho_icc": {"median": 0.4, "cri80": [0.38, 0.42], "mean": 0.4},
           "ell": {"median": 1.0, "cri80": [0.8, 1.2], "mean": 1.0},
           "estimands": {}, "estimands_avg": {}, "draws": {}, "draws_avg": {}, "draws_avg_full": {}}

    def draws(center, sd, left, right):
        z = rng.normal(center, sd, n)
        if chain_shift:
            z[-per_chain:] += chain_shift
        cen = np.zeros(n, int)
        k_left, k_right = int(round(left * n)), int(round(right * n))
        order = np.argsort(z)
        cen[order[:k_left]] = -1
        cen[order[n - k_right:]] = 1 if k_right else cen[order[n - k_right:]]
        zl = [None if c != 0 else round(float(v), 5) for v, c in zip(z, cen)]
        return zl, [int(c) for c in cen]

    for lv, center, left, right in (("d50", d50_center, 0.0, right_share_d50), ("d99", d99_center, left_share_d99, 0.0)):
        z, c = draws(center, 0.3, left, right)
        blk = {"thin": 1, "order": "chain-major", "z": z, "censor": c, "rule_of_record": rule}
        if with_full:
            out["draws_avg_full"][lv] = blk
        out["draws_avg"][lv] = {"thin": 10, "z": z[::10], "censor": c[::10]}
        zt, ct = draws(center + 0.5, 0.3, 0.0, 0.0)
        out["draws"][lv] = {"z": zt, "censor": ct}
        for key, zz, cc in (("estimands_avg", z, c), ("estimands", zt, ct)):
            unc = np.array([v for v, k in zip(zz, cc) if k == 0], float)
            out[key][lv] = {"level_fail_rate": rules.ALL_LEVELS[lv], "n_draws": n, "n_uncensored": int(unc.size),
                            "p_left_censored": float(np.mean(np.array(cc) == -1)),
                            "p_right_censored": float(np.mean(np.array(cc) == 1)),
                            "median_z": float(np.median(unc)) if unc.size else None,
                            "cri80_z": [float(np.quantile(unc, 0.1)), float(np.quantile(unc, 0.9))] if unc.size else None,
                            "median_z_conditional": float(np.median(unc)) if unc.size else None}
    # level tables: a monotone logistic curve's crossings at every table level, the same on both curves
    levels = rules.level_table_levels()
    lt = {k: [] for k in ("levels_fail_rate", "median_z", "cri80_lo_z", "cri80_hi_z", "p_left_censored", "p_right_censored", "n_uncensored")}
    for p in levels:
        zc = d50_center + math.log(p / (1 - p)) / 1.2
        lt["levels_fail_rate"].append(round(float(p), 6))
        lt["median_z"].append(round(zc, 5))
        lt["cri80_lo_z"].append(round(zc - 0.2, 5))
        lt["cri80_hi_z"].append(round(zc + 0.2, 5))
        lt["p_left_censored"].append(0.0)
        lt["p_right_censored"].append(0.0)
        lt["n_uncensored"].append(n)
    out["levels_table_avg"] = {"method": "exact per-draw average-rate crossing", "rule": "middle", **lt}
    out["levels_table"] = {"method": "crossing draws (exact)", "rule": "middle", **lt}
    zg = np.linspace(grid_lo, grid_hi, 121)
    qs = [5, 10, 25, 50, 75, 90, 95]
    curve = 1.2 * (zg - d50_center)
    out["curves"] = {"zgrid": [round(float(v), 4) for v in zg], "quantiles_pct": qs,
                     "typical_logit": [[round(float(v + 0.01 * (q - 50)), 4) for v in curve] for q in qs],
                     "average_logit": [[round(float(v + 0.01 * (q - 50) - 0.3), 4) for v in curve] for q in qs]}
    return out


@pytest.fixture
def synthetic_result():
    return make_result


@pytest.fixture
def write_result(tmp_path):
    def _write(result, arm="arm-x", directory=None):
        d = directory or tmp_path
        p = d / f"posterior_summary_{arm}_eivon.json"
        p.write_text(json.dumps(result))
        return p
    return _write


def write_cells(path, rows):
    """rows: (arm, task_id, failures, attempts)."""
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "task_id", "failures", "attempts"])
        for r in rows:
            w.writerow(r)
    return path


@pytest.fixture
def cells_file(tmp_path):
    def _make(rows, name="cells.csv"):
        return write_cells(tmp_path / name, rows)
    return _make

"""Fit the failure-against-difficulty curve of one arm and read its crossings and diagnostics.

Data. For one arm and the tasks t = 1..T it was run on: f_t failures out of n_t attempts, and the task's
difficulty estimate z_hat_t with its standard error sd_t (both from ``axis``), read from an ``inputs/<arm>.npz``
file written by ``inputs``.

Model (the logit failure rate g as a smooth function of difficulty, with a deviation per task)::

    z_t ~ Normal(z_hat_t, sd_t)                 the task's true difficulty (errors in variables; off: z_t = z_hat_t)
    g(z) = mu0 + mu1 z + GP(z; eta, ell)        a line plus a squared-exponential Gaussian process, the process
                                                approximated by a Hilbert-space basis of m sine functions on
                                                [-L, L] (Riutort-Mayol et al. 2023), m from ``rules.m_basis_rule``
    u_t = tau u_raw_t,  u_raw_t ~ Normal(0, 1)  the task's own deviation from the curve
    f_t ~ Binomial(n_t, sigmoid(g(z_t) + u_t))

Priors: eta ~ HalfNormal(2); ell ~ LogNormal(log 1.1, 0.5); mu0 ~ Normal(0, 3); mu1 ~ HalfNormal(3);
tau ~ HalfNormal(1); the basis weights ~ Normal(0, 1).

Inference: NumPyro's NUTS with the settings in ``rules`` (four chains of 2,000 warm-up and 8,000 kept draws,
target acceptance 0.995, tree depth 10, seed 20260825). Two curves are read from every draw: the median-task
curve sigmoid(g(z)), the failure rate of a task with no deviation, and the average-rate curve, the mean of
sigmoid(g(z) + tau u) over u ~ Normal(0, 1) by 21-point Gauss-Hermite quadrature, which is the share of all
attempts expected to fail at difficulty z. The crossings of record, D50 and D99, are read from the average-rate
curve; the median-task crossings are carried beside.

Per draw the curve's crossing of each level is located by ``rules.middle_crossings`` (or ``first_crossings`` when
asked), interpolated in the logit of the rate between grid points; a draw whose crossing lies below the easiest
task or beyond the hardest is censored to that side. The summaries, the convergence statistics (divergences,
rank-normalised split R-hat and bulk effective sample size of eta, ell, tau, mu1 and the two crossings' draws),
the continuous level table, the curve ribbons and the raw draws of the gated quantities are written to one JSON
file per arm, from which ``crossings``, ``gates`` and ``summaries`` read.

Command line::

    cmr fit run --inputs fits/<fit>/inputs/<arm>.npz --out fits/<fit>/posterior_summary_<arm>.json
    cmr fit run --self-test          # a prior-predictive check and a recovery of a synthetic arm with short chains

The library pins in ``pyproject.toml`` (numpy, scipy, numpyro, jax) are part of the method: with them a rerun
reproduces the draws bit for bit; across library versions the crossings move by up to about 0.05 on the scale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import numpyro

from . import rules
from .rules import (ALL_LEVELS, C_EXPAND, CHAINS, CROSSING_RULE_DEFAULT, EIV_DEFAULT, GATE_DIVERGENCE_NOTE,
                    GATE_ESS_MIN, GATE_RHAT_MAX, GATED_PARAMETERS, GRID_N, LEVELS, MAX_TREE_DEPTH, SAMPLES, SEED,
                    TARGET_ACCEPT, WARMUP, WIDEN_SD_MULT, crossing_counts, crossings_by_rule, estimand_block,
                    first_crossings, hsgp_domain, level_table_levels, m_basis_rule, middle_crossings)


def _host_devices() -> int:
    """How many CPU devices to give JAX, read before it initialises: the environment variable
    CMR_FIT_HOST_DEVICES, else the ``--chains`` argument, at least four. Fewer devices than chains makes
    NumPyro run the chains one after another, several times slower."""
    if os.environ.get("CMR_FIT_HOST_DEVICES"):
        return int(os.environ["CMR_FIT_HOST_DEVICES"])
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--chains" and i + 1 < len(argv):
            return max(4, int(argv[i + 1]))
        if a.startswith("--chains="):
            return max(4, int(a.split("=", 1)[1]))
    return 4


numpyro.set_host_device_count(_host_devices())
numpyro.enable_x64()

import jax  # noqa: E402  (after the device count is set)
import jax.numpy as jnp  # noqa: E402
import numpyro.distributions as dist  # noqa: E402
from jax import random  # noqa: E402
from numpyro.infer import MCMC, NUTS, Predictive  # noqa: E402
from scipy.special import expit  # noqa: E402

from .diagnostics import bulk_ess, rhat  # noqa: E402

M_BASIS = rules.M_BASIS_FLOOR
"""The number of basis functions in use; ``run_inference`` sets it per fit from the domain by the rule."""


def engine_sha256() -> str | None:
    """The sha256 of this file's bytes, written into every result so a reader can tell which engine wrote it."""
    try:
        with open(__file__, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------------- HSGP
def hsgp_basis(x, center, L):
    """The Hilbert-space basis: Laplacian eigenfunctions on [-L, L] with Dirichlet boundary,
    phi_j(x) = sqrt(1/L) sin(w_j (x - center + L)), w_j = j pi / (2L), j = 1..m. Returns (phi, w)."""
    j = jnp.arange(1, M_BASIS + 1)
    w = j * jnp.pi / (2.0 * L)
    phi = jnp.sqrt(1.0 / L) * jnp.sin(w * (x[..., None] - center + L))
    return phi, w


def se_sqrt_spd(w, eta, ell):
    """The square root of the squared-exponential spectral density s(w) = eta^2 sqrt(2 pi) ell exp(-(ell w)^2 / 2),
    so that the process is phi(x) @ (sqrt(s(w_j)) beta_j) with beta_j ~ Normal(0, 1)."""
    return (eta * (2.0 * jnp.pi) ** 0.25 * jnp.sqrt(ell) * jnp.exp(-0.25 * (ell * w) ** 2))


# ------------------------------------------------------------------------------------------------------ model
def model(z_hat, sd, f, n, center, L, eiv):
    T = z_hat.shape[0]
    eta = numpyro.sample("eta", dist.HalfNormal(2.0))
    ell = numpyro.sample("ell", dist.LogNormal(math.log(1.1), 0.5))
    mu0 = numpyro.sample("mu0", dist.Normal(0.0, 3.0))
    mu1 = numpyro.sample("mu1", dist.HalfNormal(3.0))
    beta = numpyro.sample("beta", dist.Normal(0.0, 1.0).expand([M_BASIS]).to_event(1))
    tau = numpyro.sample("tau", dist.HalfNormal(1.0))
    u_raw = numpyro.sample("u_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
    if eiv:
        z_raw = numpyro.sample("z_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
        z = z_hat + sd * z_raw
    else:
        z = z_hat
    phi, w = hsgp_basis(z, center, L)
    g = mu0 + mu1 * z + phi @ (se_sqrt_spd(w, eta, ell) * beta)
    numpyro.sample("f", dist.Binomial(total_count=n, logits=g + tau * u_raw), obs=f)


def curves_on_grid(samples, zgrid, center, L):
    """The logit curves g(zgrid) per draw, shape (draws, grid), from flat posterior or prior samples."""
    phi, w = hsgp_basis(jnp.asarray(zgrid), center, L)
    phi = np.asarray(phi)
    w = np.asarray(w)
    eta = np.asarray(samples["eta"], float).reshape(-1, 1)
    ell = np.asarray(samples["ell"], float).reshape(-1, 1)
    sq = (eta * (2.0 * np.pi) ** 0.25 * np.sqrt(ell) * np.exp(-0.25 * (ell * w[None, :]) ** 2))
    gp = (np.asarray(samples["beta"], float) * sq) @ phi.T
    mu0 = np.asarray(samples["mu0"], float).reshape(-1, 1)
    mu1 = np.asarray(samples["mu1"], float).reshape(-1, 1)
    return mu0 + mu1 * zgrid[None, :] + gp


def _summary(a):
    a = np.asarray(a, float)
    return {"median": float(np.median(a)), "cri80": [float(np.quantile(a, 0.10)), float(np.quantile(a, 0.90))],
            "mean": float(np.mean(a))}


# -------------------------------------------------------------------------------------------------- inference
def run_inference(inputs, eiv, chains, warmup, samples, seed, max_tree_depth=MAX_TREE_DEPTH,
                  target_accept=TARGET_ACCEPT):
    """Sample the posterior. Returns (chain-grouped samples, divergence count, seconds, centre, L, chain method)."""
    center, L = hsgp_domain(inputs["z_hat"], inputs["sd"])
    global M_BASIS
    M_BASIS = m_basis_rule(L)
    method = "parallel" if jax.local_device_count() >= chains else "sequential"
    mcmc = MCMC(NUTS(model, target_accept_prob=target_accept, max_tree_depth=max_tree_depth),
                num_warmup=warmup, num_samples=samples, num_chains=chains, chain_method=method, progress_bar=False)
    t0 = time.perf_counter()
    mcmc.run(random.PRNGKey(seed),
             z_hat=jnp.asarray(inputs["z_hat"], float), sd=jnp.asarray(inputs["sd"], float),
             f=jnp.asarray(inputs["f"]), n=jnp.asarray(inputs["n"]),
             center=center, L=L, eiv=eiv, extra_fields=("diverging",))
    samp_c = {k: np.asarray(v) for k, v in mcmc.get_samples(group_by_chain=True).items()}
    div = int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum())
    elapsed = time.perf_counter() - t0
    return samp_c, div, elapsed, center, L, method


def analyze(inputs, samp_c, div, center, L, rule=CROSSING_RULE_DEFAULT):
    """Estimands, diagnostics, tables, ribbons and draw exports from chain-grouped samples.
    Returns (result dict, extras with the raw per-draw median-task crossing arrays per level)."""
    z_hat = np.asarray(inputs["z_hat"], float)
    zgrid = np.linspace(z_hat.min(), z_hat.max(), GRID_N)
    C, S = samp_c["eta"].shape[:2]
    flat = {k: v.reshape((C * S,) + v.shape[2:]) for k, v in samp_c.items()}
    g_logit = np.asarray(curves_on_grid(flat, zgrid, center, L))
    rates = expit(g_logit)

    # ---- the median-task curve: crossings per level ----
    estimands, draws_blk, extras = {}, {}, {}
    diag_arrays = {k: samp_c[k] for k in GATED_PARAMETERS}
    for name, lev in ALL_LEVELS.items():
        zc, cen = crossings_by_rule(rates, zgrid, lev, rule)
        estimands[name] = estimand_block(zc, cen, lev, zgrid[0], zgrid[-1], rule)
        draws_blk[name] = {"z": [None if not np.isfinite(v) else float(v) for v in zc], "censor": [int(c) for c in cen]}
        if name in LEVELS:   # only the two crossings of record enter the convergence gates
            dg = zc.copy()
            dg[cen == -1] = -np.inf
            dg[cen == 1] = np.inf
            diag_arrays[name] = dg.reshape(C, S)
        extras[name] = (zc, cen)

    # ---- the continuous level table on the median-task curve ----
    lt_levels = level_table_levels()
    lt = {k: [] for k in ("levels_fail_rate", "median_z", "cri80_lo_z", "cri80_hi_z", "p_left_censored",
                          "p_right_censored", "n_uncensored")}
    for lev_p in lt_levels:
        zc_l, cen_l = crossings_by_rule(rates, zgrid, float(lev_p), rule)
        blk = estimand_block(zc_l, cen_l, float(lev_p), zgrid[0], zgrid[-1], rule)
        lt["levels_fail_rate"].append(round(float(lev_p), 6))
        lt["median_z"].append(None if blk["median_z"] is None else round(blk["median_z"], 5))
        lt["cri80_lo_z"].append(None if blk["cri80_z"] is None else round(blk["cri80_z"][0], 5))
        lt["cri80_hi_z"].append(None if blk["cri80_z"] is None else round(blk["cri80_z"][1], 5))
        lt["p_left_censored"].append(round(blk["p_left_censored"], 5))
        lt["p_right_censored"].append(round(blk["p_right_censored"], 5))
        lt["n_uncensored"].append(blk["n_uncensored"])
    rule_text = {
        "middle": ("per draw the middle crossing (the interior sign changes of rate - level plus an edge crossing where "
                   "the curve is above the level at the easiest grid point or below it at the hardest; the middle of "
                   "that odd list; an easy-edge middle is a left-censored draw, a hard-edge middle a right-censored "
                   "draw), the position interpolated in the logit of the rate between grid points; quantiles over all "
                   "draws with the censored ones beyond their ends; the named levels are table members exactly"),
        "first": ("per draw the first upward crossing after the curve has been below the level, interpolated in the "
                  "logit of the rate between grid points; quantiles over the uncensored draws; the named levels are "
                  "table members exactly"),
    }[rule]
    levels_table = {"method": "crossing draws (exact)", "curve": "median-task", "rule": rule_text, **lt}

    # ---- convergence ----
    rhats = {k: rhat(v) for k, v in diag_arrays.items()}
    esss = {k: bulk_ess(v) for k, v in diag_arrays.items()}
    ess_na = sorted(k for k, v in esss.items() if math.isnan(v))
    ess_num = [v for v in esss.values() if not math.isnan(v)]
    max_rhat_all = max(float(np.max(split_rhat_plain(v))) for v in samp_c.values() if v.shape[1] >= 4)
    gates = {
        "num_divergences": div,
        "divergence_gate": ("pass" if div == 0 else "pass_with_note" if div < GATE_DIVERGENCE_NOTE else "FAIL"),
        "rhat_max_gated": max(rhats.values()),
        "rhat_gate": "pass" if max(rhats.values()) <= GATE_RHAT_MAX else "FAIL",
        "bulk_ess_min_gated": min(ess_num),
        "ess_gate": ("FAIL" if min(ess_num) < GATE_ESS_MIN else "pass" if not ess_na else "pass_with_note"),
    }
    if ess_na:
        gates["ess_gate_note"] = (f"{ess_na} censored to one side on every draw: no numeric draws, the effective "
                                  "sample size does not apply (null); the numeric gate covers the other quantities")
    gates["all_pass"] = (gates["divergence_gate"] != "FAIL" and gates["rhat_gate"] == "pass" and gates["ess_gate"] != "FAIL")

    tau_d = flat["tau"]
    rho_d = tau_d ** 2 / (tau_d ** 2 + math.pi ** 2 / 3.0)
    result = {
        "estimands": estimands,
        "tau": _summary(tau_d),
        "rho_icc": {**_summary(rho_d), "note": "intraclass correlation of attempts within a task, "
                                               "rho = tau^2 / (tau^2 + pi^2 / 3) (logit-normal approximation)"},
        "ell": _summary(flat["ell"]),
        "eta": _summary(flat["eta"]),
        "mu0": _summary(flat["mu0"]),
        "mu1": _summary(flat["mu1"]),
        "diagnostics": {**gates, "rhat_gated": rhats,
                        "bulk_ess_gated": {k: (None if math.isnan(v) else v) for k, v in esss.items()},
                        "max_split_rhat_all_sites_plain": max_rhat_all},
        "draws": draws_blk,
        # the raw draws of the gated parameters, chain-major: reshape to (chains, samples) with config.chains to
        # recompute R-hat or the effective sample size downstream
        "param_draws": {k: [float(x) for x in samp_c[k].reshape(-1)] for k in GATED_PARAMETERS},
        "levels_table": levels_table,
        "grid": {"lo": float(zgrid[0]), "hi": float(zgrid[-1]), "n": GRID_N},
    }

    # ---- the average-rate curve: the share of attempts failing at each difficulty, E_u[sigmoid(g + tau u)] by
    # 21-point Gauss-Hermite quadrature, on the full grid; the crossings of record are read from it ----
    from numpy.polynomial.hermite import hermgauss as _hg
    _xh, _wh = _hg(21)
    _tau_col = flat["tau"][:, None]
    _avg_full = np.zeros_like(g_logit)
    for _xi, _wi in zip(_xh, _wh):
        _avg_full += (_wi / math.sqrt(math.pi)) * expit(g_logit + _tau_col * math.sqrt(2.0) * _xi)
    _avg_full = np.clip(_avg_full, 1e-9, 1 - 1e-9)
    est_avg, draws_avg = {}, {}
    for name, lev in ALL_LEVELS.items():
        zc_a, cen_a = crossings_by_rule(_avg_full, zgrid, lev, rule)
        est_avg[name] = estimand_block(zc_a, cen_a, lev, zgrid[0], zgrid[-1], rule)
        est_avg[name]["p_multi"] = float(np.mean(crossing_counts(_avg_full, zgrid, lev) > 1))
        draws_avg[name] = {"thin": 10,
                           "z": [None if not np.isfinite(v) else round(float(v), 5) for v in zc_a[::10]],
                           "censor": [int(c) for c in cen_a[::10]]}
    lta = {k: [] for k in ("levels_fail_rate", "median_z", "cri80_lo_z", "cri80_hi_z", "p_left_censored",
                           "p_right_censored", "n_uncensored", "median_z_conditional", "cri80_lo_z_conditional",
                           "cri80_hi_z_conditional")}
    for lev_p in lt_levels:
        zc_l, cen_l = crossings_by_rule(_avg_full, zgrid, float(lev_p), rule)
        blk = estimand_block(zc_l, cen_l, float(lev_p), zgrid[0], zgrid[-1], rule)
        lta["levels_fail_rate"].append(round(float(lev_p), 6))
        lta["median_z"].append(None if blk["median_z"] is None else round(blk["median_z"], 5))
        lta["cri80_lo_z"].append(None if blk["cri80_z"] is None else round(blk["cri80_z"][0], 5))
        lta["cri80_hi_z"].append(None if blk["cri80_z"] is None else round(blk["cri80_z"][1], 5))
        lta["p_left_censored"].append(round(blk["p_left_censored"], 5))
        lta["p_right_censored"].append(round(blk["p_right_censored"], 5))
        lta["n_uncensored"].append(blk["n_uncensored"])
        _mc = blk.get("median_z_conditional")
        _cc = blk.get("cri80_z_conditional")
        lta["median_z_conditional"].append(None if _mc is None else round(_mc, 5))
        lta["cri80_lo_z_conditional"].append(None if _cc is None else round(_cc[0], 5))
        lta["cri80_hi_z_conditional"].append(None if _cc is None else round(_cc[1], 5))
    result["estimands_avg"] = est_avg
    result["draws_avg"] = draws_avg
    # every draw's average-rate crossing of the two levels of record, chain-major, with both rules and the
    # crossing count beside, so a table can be re-read from the stored draws under either rule
    result["draws_avg_full"] = {}
    for name, lev in LEVELS.items():
        zc_a, cen_a = crossings_by_rule(_avg_full, zgrid, lev, rule)
        _zf, _cf = first_crossings(_avg_full, zgrid, lev)
        _zm, _cm = middle_crossings(_avg_full, zgrid, lev)
        _nk = crossing_counts(_avg_full, zgrid, lev)
        result["draws_avg_full"][name] = {
            "thin": 1, "order": "chain-major",
            "z": [None if not np.isfinite(v) else round(float(v), 5) for v in zc_a],
            "censor": [int(c) for c in cen_a],
            "rule_of_record": rule,
            "n_crossings": [int(k) for k in _nk],
            "z_first": [None if not np.isfinite(v) else round(float(v), 5) for v in _zf], "censor_first": [int(c) for c in _cf],
            "z_middle": [None if not np.isfinite(v) else round(float(v), 5) for v in _zm], "censor_middle": [int(c) for c in _cm],
        }
    result["levels_table_avg"] = {"method": "exact per-draw average-rate crossing", "curve": "average-rate",
                                  "rule": rule_text, **lta}
    del _avg_full

    # ---- curve ribbons on a thinned grid: the median-task curve g and the average-rate curve, both in logit,
    # at seven percentiles over the draws ----
    thin = 10
    zg_t = zgrid[::thin]
    gt = g_logit[:, ::thin]
    from numpy.polynomial.hermite import hermgauss
    xh, wh = hermgauss(21)
    tau_col = flat["tau"][:, None]
    avg = np.zeros_like(gt)
    for xi, wi in zip(xh, wh):
        avg += (wi / math.sqrt(math.pi)) * expit(gt + tau_col * math.sqrt(2.0) * xi)
    avg = np.clip(avg, 1e-9, 1 - 1e-9)
    avg_logit = np.log(avg / (1 - avg))
    qs = [5, 10, 25, 50, 75, 90, 95]
    result["curves"] = {
        "zgrid": [round(float(z), 4) for z in zg_t],
        "quantiles_pct": qs,
        "typical_logit": [[round(float(v), 4) for v in row] for row in np.percentile(gt, qs, axis=0)],
        "average_logit": [[round(float(v), 4) for v in row] for row in np.percentile(avg_logit, qs, axis=0)],
    }

    # ---- per-draw line statistics: the least-squares line of each draw's logit curve over the fitted range and
    # the draw's departure from its own line, overall and in three rate bands ----
    def _linefit(mat):
        zc = zg_t - zg_t.mean()
        denom = float((zc ** 2).sum())
        slope = (mat @ zc) / denom
        intercept = mat.mean(axis=1)
        resid = mat - (intercept[:, None] + np.outer(slope, zc))
        floor_l = math.log((1 / 128) / (1 - 1 / 128))   # one failure in 128 attempts, in logit
        half_l = 0.0

        def banded(mask_lo, mask_hi):
            out = []
            for r_row, m_row in zip(resid, (mat >= mask_lo) & (mat < mask_hi)):
                out.append(None if not m_row.any() else round(float(np.sqrt((r_row[m_row] ** 2).mean())), 5))
            return out
        return {
            "slope": [round(float(v), 5) for v in slope],
            "intercept_at_zmid": [round(float(v), 5) for v in intercept],
            "rms_dev": [round(float(v), 5) for v in np.sqrt((resid ** 2).mean(axis=1))],
            "max_dev": [round(float(v), 5) for v in np.abs(resid).max(axis=1)],
            "rms_dev_below_floor": banded(-np.inf, floor_l),
            "rms_dev_floor_to_half": banded(floor_l, half_l),
            "rms_dev_above_half": banded(half_l, np.inf),
        }

    result["linefit"] = {
        "note": ("per draw the least-squares line of the logit curve over the fitted range on the thinned grid; "
                 "the intercept at zmid = mean(zgrid); rms and max deviation are the draw's departure from its "
                 "own line, in logit units"),
        "zmid": round(float(zg_t.mean()), 5),
        "zrange": [round(float(zg_t[0]), 4), round(float(zg_t[-1]), 4)],
        "typical": _linefit(gt),
        "average": _linefit(avg_logit),
    }
    return result, extras


def split_rhat_plain(v):
    """NumPyro's plain split R-hat of a chain-grouped array (no rank normalisation), for the all-sites summary."""
    from numpyro.diagnostics import split_gelman_rubin
    return split_gelman_rubin(v)


# ------------------------------------------------------------------------------------------------------- data
def npz_inputs(path):
    """Read one arm's inputs file: model_id, z_hat, sd, f, n and task_ids (see ``inputs``)."""
    d = np.load(path, allow_pickle=False)
    return {"model_id": str(d["model_id"]),
            "z_hat": np.asarray(d["z_hat"], float), "sd": np.asarray(d["sd"], float),
            "f": np.asarray(d["f"], np.int64), "n": np.asarray(d["n"], np.int64),
            "task_ids": ([str(t) for t in d["task_ids"]] if "task_ids" in d.files else None)}


# --------------------------------------------------------------------------------------------------- self-test
def self_test(out_path="fit_self_test.json", chains=2, warmup=300, samples=300):
    """Two checks with short chains: (a) 200 prior curves through the model span under 1% to over 99% failure and
    at least a tenth of them cross one half, so the prior is weakly informative and not degenerate; (b) a
    synthetic arm drawn from the model is recovered, its true D50 inside the 90% interval of the fitted one and
    the gated R-hat under 1.05. Writes the report to ``out_path``; returns 0 on pass."""
    t_all = time.perf_counter()
    report = {}
    rng = np.random.default_rng(SEED)
    T = 60
    z_hat = np.sort(rng.uniform(-4.0, 4.0, T))
    sd = rng.uniform(0.05, 0.15, T)
    n = np.full(T, 128, np.int64)
    center, L = hsgp_domain(z_hat, sd)
    zgrid = np.linspace(z_hat.min(), z_hat.max(), 401)

    prior = Predictive(model, num_samples=200)(random.PRNGKey(SEED + 1), z_hat=jnp.asarray(z_hat), sd=jnp.asarray(sd),
                                               f=None, n=jnp.asarray(n), center=center, L=L, eiv=False)
    rates = expit(curves_on_grid({k: np.asarray(v) for k, v in prior.items()}, zgrid, center, L))
    span_lo, span_hi = float(rates.min()), float(rates.max())
    frac_cross50 = float(np.mean((rates.min(axis=1) < 0.5) & (rates.max(axis=1) > 0.5)))
    prior_pass = span_lo < 0.01 and span_hi > 0.99 and frac_cross50 >= 0.10
    report["prior_predictive"] = {"n_curves": 200, "ensemble_min_rate": span_lo, "ensemble_max_rate": span_hi,
                                  "frac_curves_crossing_50pct": frac_cross50, "pass": bool(prior_pass)}
    print(f"[self-test a] prior curves span {span_lo:.2e} .. {1 - span_hi:.2e} from 1; {frac_cross50:.0%} cross 50% "
          f"-> {'PASS' if prior_pass else 'FAIL'}")

    true = {"eta": 0.6, "ell": 1.5, "tau": 0.35, "mu0": -0.5, "mu1": 1.1}
    beta_true = rng.standard_normal(M_BASIS)

    def g_true(x):
        return curves_on_grid({"eta": [true["eta"]], "ell": [true["ell"]], "mu0": [true["mu0"]], "mu1": [true["mu1"]],
                               "beta": beta_true[None, :]}, np.asarray(x), center, L)[0]

    z_true = z_hat + sd * rng.standard_normal(T)
    u_true = true["tau"] * rng.standard_normal(T)
    f_obs = rng.binomial(128, expit(g_true(z_true) + u_true))
    truth = {}
    for name, lev in LEVELS.items():
        tz, tc = crossings_by_rule(expit(g_true(zgrid))[None, :], zgrid, lev)
        truth[name] = (float(tz[0]) if tc[0] == 0 else None, int(tc[0]))
    inputs = {"model_id": "synthetic", "z_hat": z_hat, "sd": sd, "f": f_obs.astype(np.int64), "n": n, "task_ids": None}
    samp_c, div, elapsed, center2, L2, method = run_inference(inputs, eiv=True, chains=chains, warmup=warmup,
                                                              samples=samples, seed=SEED + 2)
    result, extras = analyze(inputs, samp_c, div, center2, L2)

    z50, cen50 = extras["d50"]
    unc = z50[cen50 == 0]
    if unc.size:
        q05, q95 = (float(np.quantile(unc, q)) for q in (0.05, 0.95))
    else:
        q05 = q95 = float("nan")
    in_cri = (truth["d50"][0] is not None and unc.size > 0 and q05 <= truth["d50"][0] <= q95)
    rhat_max = result["diagnostics"]["rhat_max_gated"]
    rhat_ok = rhat_max < 1.05
    report["synthetic_recovery"] = {
        "truth": true, "truth_d50_z": truth["d50"][0], "truth_d99_z": truth["d99"][0],
        "posterior_d50": result["estimands"]["d50"], "posterior_d99": result["estimands"]["d99"],
        "d50_cri90_z": [q05, q95], "truth_d50_in_cri90": bool(in_cri),
        "rhat_max_gated": rhat_max, "rhat_lt_1.05": bool(rhat_ok),
        "num_divergences": div, "chain_method": method, "mcmc_seconds": elapsed,
        "tau_posterior": result["tau"], "eta_posterior": result["eta"], "ell_posterior": result["ell"]["median"],
        "pass": bool(in_cri and rhat_ok)}
    med50 = result["estimands"]["d50"]["median_z"]
    print(f"[self-test b] truth d50 z={truth['d50'][0]}; post median={med50 if med50 is None else round(med50, 3)}, "
          f"90% CrI=[{q05:.3f},{q95:.3f}] -> {'IN' if in_cri else 'OUT'}; Rhat_max={rhat_max:.3f} "
          f"({'ok' if rhat_ok else 'BAD'}); div={div}; {elapsed:.0f}s MCMC ({method})")

    report["total_seconds"] = time.perf_counter() - t_all
    report["pass"] = bool(prior_pass and report["synthetic_recovery"]["pass"])
    Path(out_path).write_text(json.dumps(report, indent=1))
    print(f"[self-test] total {report['total_seconds']:.0f}s -> {'PASS' if report['pass'] else 'FAIL'}; wrote {out_path}")
    return 0 if report["pass"] else 1


# -------------------------------------------------------------------------------------------------------- run
def write_json_atomic(out, text):
    """Write ``text`` to a temporary name beside ``out``, check the bytes read back, then rename into place, so
    a partial file never stands as a result. Returns the sha256 of the bytes."""
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f".tmp-{os.getpid()}")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != digest:
        tmp.unlink()
        raise OSError(f"read-back of {tmp} differs from the payload")
    os.replace(tmp, out)
    return digest


def fit_arm(inputs, *, eiv=EIV_DEFAULT, chains=CHAINS, warmup=WARMUP, samples=SAMPLES, seed=SEED,
            max_tree_depth=MAX_TREE_DEPTH, target_accept=TARGET_ACCEPT, rule=CROSSING_RULE_DEFAULT,
            inputs_name=None, inputs_sha256=None):
    """Fit one arm from an inputs dict and return the full result with its ``config`` block."""
    samp_c, div, elapsed, center, L, method = run_inference(inputs, eiv, chains, warmup, samples, seed,
                                                            max_tree_depth=max_tree_depth, target_accept=target_accept)
    result, _ = analyze(inputs, samp_c, div, center, L, rule)
    return {
        "model_id": inputs["model_id"],
        "config": {
            "eiv": "on" if eiv else "off", "chains": chains, "warmup": warmup, "samples": samples,
            "target_accept": target_accept, "max_tree_depth": max_tree_depth, "seed": seed,
            "m_basis": M_BASIS, "m_basis_rule": "max(40, 10 * ceil(1.75 L / 4)): the squared-exponential adequacy "
                                                "rule at the prior's 2.5th-percentile length scale 0.4",
            "c_expand": C_EXPAND, "widen_sd_mult": WIDEN_SD_MULT, "hsgp_center": center, "hsgp_L": L,
            "n_tasks": len(inputs["z_hat"]), "chain_method": method, "crossing_rule": rule,
            "engine_sha256": engine_sha256(), "inputs": inputs_name, "inputs_sha256": inputs_sha256,
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        **result,
        "runtime_seconds_mcmc": elapsed,
    }


def cmd_run(args) -> int:
    path = Path(args.inputs)
    inputs = npz_inputs(path)
    eiv = args.eiv == "on"
    print(f"[run] arm={inputs['model_id']} eiv={args.eiv} T={len(inputs['z_hat'])} chains={args.chains} "
          f"warmup={args.warmup} samples={args.samples} seed={SEED} rule={args.crossing_rule}")
    result = fit_arm(inputs, eiv=eiv, chains=args.chains, warmup=args.warmup, samples=args.samples,
                     max_tree_depth=args.max_tree_depth, target_accept=args.target_accept, rule=args.crossing_rule,
                     inputs_name=path.name, inputs_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    digest = write_json_atomic(args.out, json.dumps(result, indent=1))
    d = result["diagnostics"]
    print(f"[run] MCMC {result['runtime_seconds_mcmc']:.1f}s ({result['config']['chain_method']}); "
          f"divergences={d['num_divergences']} [{d['divergence_gate']}]; Rhat_max={d['rhat_max_gated']:.4f} "
          f"[{d['rhat_gate']}]; ESS_min={d['bulk_ess_min_gated']:.0f} [{d['ess_gate']}]")
    for name in LEVELS:
        e = result["estimands_avg"][name]
        med = ("-" if e["median_pct"] is None
               else f"{e['median_pct']:.2f}% [{e['cri80_pct'][0]:.2f},{e['cri80_pct'][1]:.2f}]")
        print(f"[run] {name} (average-rate curve): median/CrI80 {med}  P(left-cens)={e['p_left_censored']:.3f} "
              f"P(right-cens)={e['p_right_censored']:.3f}")
    print(f"[run] tau median={result['tau']['median']:.3f}, rho median={result['rho_icc']['median']:.3f}, "
          f"ell median={result['ell']['median']:.3f}")
    print(f"[run] wrote {args.out} sha256 {digest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit run", description="fit one arm's failure curve (or run the self-test)")
    ap.add_argument("--self-test", action="store_true", help="the prior-predictive and synthetic-recovery checks with short chains")
    ap.add_argument("--self-test-out", default="fit_self_test.json", help="where the self-test report goes")
    ap.add_argument("--inputs", default=None, help="the arm's inputs file, inputs/<arm>.npz")
    ap.add_argument("--out", default=None, help="the result JSON to write")
    ap.add_argument("--eiv", choices=["on", "off"], default="on" if EIV_DEFAULT else "off",
                    help="task difficulties with their standard errors (on, the fits of record) or as fixed values")
    ap.add_argument("--chains", type=int, default=CHAINS)
    ap.add_argument("--warmup", type=int, default=WARMUP)
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--max-tree-depth", type=int, default=MAX_TREE_DEPTH)
    ap.add_argument("--target-accept", type=float, default=TARGET_ACCEPT)
    ap.add_argument("--crossing-rule", choices=list(rules.CROSSING_RULES), default=CROSSING_RULE_DEFAULT,
                    help="which crossing counts when a curve crosses a level more than once (middle is the rule of record)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test(args.self_test_out)
    if not args.inputs or not args.out:
        build_parser().error("--inputs and --out are required (or --self-test)")
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())

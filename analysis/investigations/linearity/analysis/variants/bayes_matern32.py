# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "matplotlib", "numpyro", "jax"]
# ///
"""Data: per kept combined task t of the target model, failures f_t out of
n_t = 128 rollouts; task-difficulty estimates z_hat_t (logit of
DIFFICULTY.md's D_t) with measurement sd sd_t (delta method on the
logit axis: sd_D / (D(1-D)), Var(D) = (1/M^2) sum_m p_m(1-p_m)/(n_m+2),
p_m the Jeffreys mean).

Model:
  z_t ~ Normal(z_hat_t, sd_t)          errors-in-variables, non-centered
                                       (EIV-OFF config: z_t = z_hat_t)
  g(z) = mu0 + mu1*z + GP_SE(z; eta, ell)  via HSGP: m=40 sin eigenbasis
        on [-L, L], L = 1.5 * half-width of the z_hat range widened by
        3*max sd; SE spectral density (written out below)
  u_t = tau * u_raw_t, u_raw_t ~ Normal(0,1)   non-centered task effects
  f_t ~ Binomial(128, sigmoid(g(z_t) + u_t))
Priors: eta ~ HalfNormal(2); ell ~ LogNormal(log 1.1, 0.5); mu0 ~
Normal(0,3); mu1 ~ HalfNormal(3); tau ~ HalfNormal(1); beta_j ~ N(0,1).

Inference: NumPyro NUTS, 4 chains x (1000 warmup + 1000 samples),
target_accept 0.9, seed 20260825. Gates: zero divergences (<5 with a
note), rank-normalized split R-hat <= 1.01 and bulk-ESS >= 400 for
eta, ell, tau, mu1 and the derived d50/d1 draws.
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import numpyro

numpyro.set_host_device_count(4)   # parallel chains on CPU
numpyro.enable_x64()

import jax
import jax.numpy as jnp
import numpyro.distributions as dist
from jax import random
from numpyro.diagnostics import effective_sample_size, split_gelman_rubin
from numpyro.infer import MCMC, NUTS, Predictive
from scipy.special import expit, ndtri
from scipy.stats import rankdata

SEED = 20260825
DEFAULT_MODEL = "Qwen/Qwen3-8B"
M_BASIS = 40           # HSGP basis functions
C_EXPAND = 1.5         # HSGP domain expansion factor
WIDEN_SD_MULT = 3.0    # widen the z_hat range by 3*max sd before expanding
GRID_N = 1201          # fine grid over the observed z_hat range
LEVELS = {"d50": 0.50, "d1": 0.01}   # failure-rate levels
TARGET_ACCEPT = 0.9
SPEC_HOUSE_SIGMA = 1.09
LOGIT_SIGMA_FRAC = 0.10     # house kernel width fraction of the logit range
GATED = ("eta", "ell", "tau", "mu1")
HERE = Path(__file__).resolve().parent


# ----------------------------------------------------------------- HSGP

def hsgp_domain(z_hat, sd):
    """(center, L): the z_hat range widened by 3*max sd, then expanded
    by c = 1.5 about its center (L is the half-width of the expanded
    domain)."""
    lo = float(np.min(z_hat) - WIDEN_SD_MULT * np.max(sd))
    hi = float(np.max(z_hat) + WIDEN_SD_MULT * np.max(sd))
    center = 0.5 * (lo + hi)
    L = C_EXPAND * 0.5 * (hi - lo)
    return center, L


def hsgp_basis(x, center, L):
    """Standard HSGP sqrt-eigenfunction construction (Riutort-Mayol et
    al. 2023): Laplacian eigenpairs on [-L, L] with Dirichlet boundary,
      phi_j(x) = sqrt(1/L) * sin(w_j * (x - center + L)),
      w_j = j*pi/(2L) = sqrt(lambda_j),  j = 1..m.
    Returns (phi with trailing axis m, w (m,))."""
    j = jnp.arange(1, M_BASIS + 1)
    w = j * jnp.pi / (2.0 * L)
    phi = jnp.sqrt(1.0 / L) * jnp.sin(w * (x[..., None] - center + L))
    return phi, w


def se_sqrt_spd(w, eta, ell):
    """sqrt of the squared-exponential spectral density
      s(w) = eta^2 * sqrt(2*pi) * ell * exp(-(ell*w)^2 / 2),
    so f(x) ~= phi(x) @ (sqrt(s(w_j)) * beta_j), beta_j ~ N(0,1)."""
    # VARIANT: Matern-3/2 spectral density
    #   s(w) = 12*sqrt(3) * eta^2 / (ell^3 * (3/ell^2 + w^2)^2)
    return (eta * jnp.sqrt(12.0 * jnp.sqrt(3.0)) / ell ** 1.5
            / (3.0 / ell ** 2 + w ** 2))


# ---------------------------------------------------------------- model

def model(z_hat, sd, f, n, center, L, eiv):
    T = z_hat.shape[0]
    eta = numpyro.sample("eta", dist.HalfNormal(2.0))
    ell = numpyro.sample("ell", dist.LogNormal(math.log(1.1), 0.5))
    mu0 = numpyro.sample("mu0", dist.Normal(0.0, 3.0))
    mu1 = numpyro.sample("mu1", dist.HalfNormal(3.0))
    beta = numpyro.sample(
        "beta", dist.Normal(0.0, 1.0).expand([M_BASIS]).to_event(1))
    tau = numpyro.sample("tau", dist.HalfNormal(1.0))
    u_raw = numpyro.sample(
        "u_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
    if eiv:
        z_raw = numpyro.sample(
            "z_raw", dist.Normal(0.0, 1.0).expand([T]).to_event(1))
        z = z_hat + sd * z_raw          # non-centered z_t ~ N(z_hat, sd)
    else:
        z = z_hat
    phi, w = hsgp_basis(z, center, L)
    g = mu0 + mu1 * z + phi @ (se_sqrt_spd(w, eta, ell) * beta)
    numpyro.sample(
        "f", dist.Binomial(total_count=n, logits=g + tau * u_raw), obs=f)


def curves_on_grid(samples, zgrid, center, L):
    """Logit curves g(zgrid) per draw, shape (S, G), from a dict of
    flat posterior/prior samples (numpy)."""
    phi, w = hsgp_basis(jnp.asarray(zgrid), center, L)
    phi = np.asarray(phi)
    w = np.asarray(w)
    eta = np.asarray(samples["eta"], float).reshape(-1, 1)
    ell = np.asarray(samples["ell"], float).reshape(-1, 1)
    sq = (eta * np.sqrt(12.0 * np.sqrt(3.0)) / ell ** 1.5
          / (3.0 / ell ** 2 + w[None, :] ** 2))
    gp = (np.asarray(samples["beta"], float) * sq) @ phi.T
    mu0 = np.asarray(samples["mu0"], float).reshape(-1, 1)
    mu1 = np.asarray(samples["mu1"], float).reshape(-1, 1)
    return mu0 + mu1 * zgrid[None, :] + gp


# ------------------------------------------------------------ estimands

def first_crossings(rates, zgrid, level):
    """Vectorized house crossing (threshold_common._first_crossing) read
    at grid resolution: skip a leading above-level hook; the crossing is
    the first grid z at/above `level` after the curve has been below it.
    Returns (z (S,), censor (S,)): z = NaN when censored; censor -1 =
    left-censored (never below the level in range), +1 = right-censored
    (never reaches it from below), 0 = uncensored."""
    below = rates < level
    has_below = below.any(axis=1)
    i0 = below.argmax(axis=1)
    idx = np.arange(rates.shape[1])[None, :]
    after = (~below) & (idx > i0[:, None])
    has_cross = after.any(axis=1) & has_below
    i1 = after.argmax(axis=1)
    z = np.where(has_cross, zgrid[i1], np.nan)
    censor = np.where(~has_below, -1, np.where(has_cross, 0, 1)).astype(int)
    return z, censor


def estimand_block(z, censor, level):
    unc = z[censor == 0]
    blk = {
        "level_fail_rate": level,
        "n_draws": int(z.size),
        "n_uncensored": int(unc.size),
        "p_left_censored": float(np.mean(censor == -1)),
        "p_right_censored": float(np.mean(censor == 1)),
    }
    if unc.size:
        med = float(np.median(unc))
        q10, q90 = (float(np.quantile(unc, q)) for q in (0.10, 0.90))
        blk.update(
            median_z=med, cri80_z=[q10, q90],
            median_pct=float(100 * expit(med)),
            cri80_pct=[float(100 * expit(q10)), float(100 * expit(q90))])
    else:
        blk.update(median_z=None, cri80_z=None,
                   median_pct=None, cri80_pct=None)
    return blk


# ---------------------------------------------------- diagnostics (V21)
# Rank-normalized split R-hat and bulk-ESS per Vehtari et al. (2021).
# Rank-based, so censored (+-inf) estimand draws are handled naturally.

def _rank_normal(x):
    r = rankdata(x, method="average", axis=None).reshape(x.shape)
    return ndtri((r - 0.375) / (x.size + 0.25))


def _split_halves(x):
    c, n = x.shape
    h = n // 2
    return x[:, :2 * h].reshape(c * 2, h)


def bulk_ess(x):
    """Bulk-ESS: classic ESS of rank-normalized split chains.

    A constant FINITE array (posterior pinned to one grid point) keeps
    the ESS = n_draws convention. A constant INFINITE array is a fully
    (one-sided) censored estimand — there are no numeric draws to have
    an ESS, so return NaN and let the gate handle it explicitly rather
    than pass vacuously."""
    x = np.asarray(x, float)
    if np.all(x == x.flat[0]):
        return float(x.size) if np.isfinite(x.flat[0]) else float("nan")
    return float(effective_sample_size(_split_halves(_rank_normal(x))))


def rhat(x):
    """max(rank-normalized split R-hat, folded version)."""
    x = np.asarray(x, float)
    if np.all(x == x.flat[0]):
        return 1.0
    r_bulk = float(split_gelman_rubin(_rank_normal(x)))
    med = np.median(x)
    if np.isinf(med):
        # >50% of draws censored to one side, so the median is +-inf
        # and the arithmetic fold is NaN at like-signed infs. Fold
        # directly instead: draws at the infinite median are at zero
        # distance from it, everything else (finite or opposite-sign
        # inf) folds to +inf. Rank-identical to |x - med| where that
        # is defined, and NaN-free.
        folded = np.where(x == med, 0.0, np.inf)
    else:
        folded = np.abs(x - med)
    r_tail = (1.0 if np.all(folded == folded.flat[0])
              else float(split_gelman_rubin(_rank_normal(folded))))
    return max(r_bulk, r_tail)


def _summary(a):
    a = np.asarray(a, float)
    return {"median": float(np.median(a)),
            "cri80": [float(np.quantile(a, 0.10)),
                      float(np.quantile(a, 0.90))],
            "mean": float(np.mean(a))}


# ------------------------------------------------------------ inference

def run_inference(inputs, eiv, chains, warmup, samples, seed,
                  max_tree_depth=10, target_accept=TARGET_ACCEPT):
    center, L = hsgp_domain(inputs["z_hat"], inputs["sd"])
    method = "parallel" if jax.local_device_count() >= chains else "sequential"
    mcmc = MCMC(NUTS(model, target_accept_prob=target_accept,
                     max_tree_depth=max_tree_depth),
                num_warmup=warmup, num_samples=samples, num_chains=chains,
                chain_method=method, progress_bar=False)
    t0 = time.perf_counter()
    mcmc.run(random.PRNGKey(seed),
             z_hat=jnp.asarray(inputs["z_hat"], float),
             sd=jnp.asarray(inputs["sd"], float),
             f=jnp.asarray(inputs["f"]), n=jnp.asarray(inputs["n"]),
             center=center, L=L, eiv=eiv,
             extra_fields=("diverging",))
    samp_c = {k: np.asarray(v)
              for k, v in mcmc.get_samples(group_by_chain=True).items()}
    div = int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum())
    elapsed = time.perf_counter() - t0
    return samp_c, div, elapsed, center, L, method


def analyze(inputs, samp_c, div, center, L):
    """Estimands + diagnostics from chain-grouped samples. Returns
    (result dict, extras with raw per-draw crossing arrays)."""
    z_hat = np.asarray(inputs["z_hat"], float)
    zgrid = np.linspace(z_hat.min(), z_hat.max(), GRID_N)
    C, S = samp_c["eta"].shape[:2]
    flat = {k: v.reshape((C * S,) + v.shape[2:]) for k, v in samp_c.items()}
    g_logit = np.asarray(curves_on_grid(flat, zgrid, center, L))
    rates = expit(g_logit)

    estimands, draws_blk, extras = {}, {}, {}
    diag_arrays = {k: samp_c[k] for k in GATED}
    for name, lev in LEVELS.items():
        zc, cen = first_crossings(rates, zgrid, lev)
        estimands[name] = estimand_block(zc, cen, lev)
        draws_blk[name] = {
            "z": [None if not np.isfinite(v) else float(v) for v in zc],
            "censor": [int(c) for c in cen],
        }
        dg = zc.copy()
        dg[cen == -1] = -np.inf
        dg[cen == 1] = np.inf
        diag_arrays[name] = dg.reshape(C, S)
        extras[name] = (zc, cen)

    rhats = {k: rhat(v) for k, v in diag_arrays.items()}
    esss = {k: bulk_ess(v) for k, v in diag_arrays.items()}
    # bulk_ess is NaN for a fully (one-sided) censored estimand: no
    # numeric draws exist there. Exclude it from the numeric ESS gate
    # but say so explicitly (ess_gate 'pass_with_note' + note + null in
    # bulk_ess_gated) instead of passing vacuously.
    ess_na = sorted(k for k, v in esss.items() if math.isnan(v))
    ess_num = [v for v in esss.values() if not math.isnan(v)]
    max_rhat_all = max(
        float(np.max(split_gelman_rubin(v)))
        for v in samp_c.values() if v.shape[1] >= 4)
    gates = {
        "num_divergences": div,
        "divergence_gate": ("pass" if div == 0 else
                            "pass_with_note" if div < 5 else "FAIL"),
        "rhat_max_gated": max(rhats.values()),
        "rhat_gate": "pass" if max(rhats.values()) <= 1.01 else "FAIL",
        "bulk_ess_min_gated": min(ess_num),
        "ess_gate": ("FAIL" if min(ess_num) < 400
                     else "pass" if not ess_na else "pass_with_note"),
    }
    if ess_na:
        gates["ess_gate_note"] = (
            f"estimand(s) {ess_na} fully censored to one side: no "
            "numeric draws, bulk-ESS not applicable (null); the numeric "
            "gate covers the remaining quantities")
    gates["all_pass"] = (gates["divergence_gate"] != "FAIL"
                         and gates["rhat_gate"] == "pass"
                         and gates["ess_gate"] != "FAIL")

    tau_d = flat["tau"]
    rho_d = tau_d ** 2 / (tau_d ** 2 + math.pi ** 2 / 3.0)
    house_sigma_data = LOGIT_SIGMA_FRAC * float(z_hat.max() - z_hat.min())
    ell_d = flat["ell"]
    result = {
        "estimands": estimands,
        "tau": _summary(tau_d),
        "rho_icc": {**_summary(rho_d),
                    "note": ("intraclass correlation via the logit-normal "
                             "approximation rho = tau^2/(tau^2 + pi^2/3)")},
        "ell": {**_summary(ell_d),
                "house_sigma_nominal_spec": SPEC_HOUSE_SIGMA,
                "house_sigma_from_inputs": house_sigma_data,
                "p_ell_gt_house_nominal":
                    float(np.mean(ell_d > SPEC_HOUSE_SIGMA)),
                "p_ell_gt_house_from_inputs":
                    float(np.mean(ell_d > house_sigma_data))},
        "eta": _summary(flat["eta"]),
        "mu0": _summary(flat["mu0"]),
        "mu1": _summary(flat["mu1"]),
        "diagnostics": {**gates,
                        "rhat_gated": rhats,
                        "bulk_ess_gated": {
                            k: (None if math.isnan(v) else v)
                            for k, v in esss.items()},
                        "max_split_rhat_all_sites_plain": max_rhat_all},
        "draws": draws_blk,
        "grid": {"lo": float(zgrid[0]), "hi": float(zgrid[-1]),
                 "n": GRID_N},
    }
    thin = 10
    zg_t = zgrid[::thin]
    gt = g_logit[:, ::thin]
    from numpy.polynomial.hermite import hermgauss
    xh, wh = hermgauss(21)
    tau_col = flat["tau"][:, None]
    avg = np.zeros_like(gt)
    for xi, wi in zip(xh, wh):
        avg += (wi / math.sqrt(math.pi)) * expit(
            gt + tau_col * math.sqrt(2.0) * xi)
    avg = np.clip(avg, 1e-9, 1 - 1e-9)
    avg_logit = np.log(avg / (1 - avg))
    qs = [5, 10, 25, 50, 75, 90, 95]
    result["curves"] = {
        "zgrid": [round(float(z), 4) for z in zg_t],
        "quantiles_pct": qs,
        "typical_logit": [[round(float(v), 4) for v in row]
                          for row in np.percentile(gt, qs, axis=0)],
        "average_logit": [[round(float(v), 4) for v in row]
                          for row in np.percentile(avg_logit, qs,
                                                   axis=0)],
    }
    return result, extras


# ----------------------------------------------------------------- data

def difficulty_arrays(by_model, order, task_difficulty):
    """(z_hat, sd) on the logit axis per DIFFICULTY.md: D_t from
    task_difficulty; Var(D_t) = (1/M^2) sum_m p_m(1-p_m)/(n_m+2) with
    p_m the Jeffreys mean (c+0.5)/(n+1); delta method sd_z =
    sd_D / (D(1-D)).

    The variance population is the SAME one task_difficulty averages
    over: models holding the task minus families in
    plot_difficulty.EXCLUDE_FROM_DIFFICULTY (empty today). The Jeffreys
    mean is re-derived from that population and checked against
    task_difficulty per task, so any future population drift raises
    loudly instead of silently feeding a mismatched sd_t to EIV."""
    from plot_difficulty import EXCLUDE_FROM_DIFFICULTY, model_info
    keep = [m for m in by_model
            if model_info(m)[0] not in EXCLUDE_FROM_DIFFICULTY]
    z_hat = np.empty(len(order))
    sdz = np.empty(len(order))
    for i, t in enumerate(order):
        D = task_difficulty(by_model, t)
        vals = [by_model[m][t] for m in keep if t in by_model[m]]
        M = len(vals)
        p = [(c + 0.5) / (nn + 1) for c, nn in vals]
        if abs((1.0 - sum(p) / M) - D) > 1e-9:
            raise RuntimeError(
                f"difficulty population mismatch vs task_difficulty on {t}: "
                f"variance population gives D={1.0 - sum(p) / M!r}, "
                f"task_difficulty gives D={D!r}")
        var_D = sum(pp * (1 - pp) / (nn + 2)
                    for pp, (_, nn) in zip(p, vals)) / M ** 2
        z_hat[i] = math.log(D / (1 - D))
        sdz[i] = math.sqrt(var_D) / (D * (1 - D))
    return z_hat, sdz


def board_inputs(model_id):
    """Target-model inputs from the board loaders (needs the repo)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from plot_difficulty import (DATASETS, build_data, load_dataset,
                                 task_difficulty)
    raw = {ds: load_dataset(ds) for ds in DATASETS}
    data, _ = build_data(raw, True)
    _, by_model, order = data["combined"]
    if model_id not in by_model:
        sys.exit(f"error: {model_id!r} not in the combined pool")
    missing = [t for t in order if t not in by_model[model_id]]
    if missing:
        sys.exit(f"error: {model_id!r} covers only "
                 f"{len(order) - len(missing)}/{len(order)} kept tasks")
    z_hat, sdz = difficulty_arrays(by_model, order, task_difficulty)
    counts = [by_model[model_id][t] for t in order]
    return {"model_id": model_id, "z_hat": z_hat, "sd": sdz,
            "f": np.array([nn - c for c, nn in counts], np.int64),
            "n": np.array([nn for _, nn in counts], np.int64),
            "task_ids": list(order)}


def npz_inputs(path):
    d = np.load(path, allow_pickle=False)
    return {"model_id": str(d["model_id"]),
            "z_hat": np.asarray(d["z_hat"], float),
            "sd": np.asarray(d["sd"], float),
            "f": np.asarray(d["f"], np.int64),
            "n": np.asarray(d["n"], np.int64),
            "task_ids": ([str(t) for t in d["task_ids"]]
                         if "task_ids" in d.files else None)}


# ------------------------------------------------------------ self-test

def self_test():
    t_all = time.perf_counter()
    report = {}
    rng = np.random.default_rng(SEED)
    T = 60
    z_hat = np.sort(rng.uniform(-4.0, 4.0, T))
    sd = rng.uniform(0.05, 0.15, T)
    n = np.full(T, 128, np.int64)
    center, L = hsgp_domain(z_hat, sd)
    zgrid = np.linspace(z_hat.min(), z_hat.max(), 401)

    # (a) prior-predictive sanity: 200 prior curves through the actual
    # model code; weakly informative = the ensemble spans <1% .. >99%
    # failure over the range and is not degenerate.
    prior = Predictive(model, num_samples=200)(
        random.PRNGKey(SEED + 1), z_hat=jnp.asarray(z_hat),
        sd=jnp.asarray(sd), f=None, n=jnp.asarray(n),
        center=center, L=L, eiv=False)
    rates = expit(curves_on_grid(
        {k: np.asarray(v) for k, v in prior.items()}, zgrid, center, L))
    span_lo, span_hi = float(rates.min()), float(rates.max())
    frac_cross50 = float(np.mean((rates.min(axis=1) < 0.5)
                                 & (rates.max(axis=1) > 0.5)))
    prior_pass = span_lo < 0.01 and span_hi > 0.99 and frac_cross50 >= 0.10
    report["prior_predictive"] = {
        "n_curves": 200, "ensemble_min_rate": span_lo,
        "ensemble_max_rate": span_hi,
        "frac_curves_crossing_50pct": frac_cross50, "pass": bool(prior_pass)}
    print(f"[self-test a] prior curves span {span_lo:.2e} .. "
          f"{1 - span_hi:.2e} from 1; {frac_cross50:.0%} cross 50% "
          f"-> {'PASS' if prior_pass else 'FAIL'}")

    # (b) tiny-synthetic recovery from the exact model.
    true = {"eta": 0.6, "ell": 1.5, "tau": 0.35, "mu0": -0.5, "mu1": 1.1}
    beta_true = rng.standard_normal(M_BASIS)

    def g_true(x):
        return curves_on_grid(
            {"eta": [true["eta"]], "ell": [true["ell"]],
             "mu0": [true["mu0"]], "mu1": [true["mu1"]],
             "beta": beta_true[None, :]}, np.asarray(x), center, L)[0]

    z_true = z_hat + sd * rng.standard_normal(T)      # z_t ~ N(z_hat, sd)
    u_true = true["tau"] * rng.standard_normal(T)
    f_obs = rng.binomial(128, expit(g_true(z_true) + u_true))
    truth = {}
    for name, lev in LEVELS.items():
        tz, tc = first_crossings(expit(g_true(zgrid))[None, :], zgrid, lev)
        truth[name] = (float(tz[0]) if tc[0] == 0 else None, int(tc[0]))
    inputs = {"model_id": "synthetic", "z_hat": z_hat, "sd": sd,
              "f": f_obs.astype(np.int64), "n": n, "task_ids": None}
    samp_c, div, elapsed, center2, L2, method = run_inference(
        inputs, eiv=True, chains=2, warmup=300, samples=300, seed=SEED + 2)
    result, extras = analyze(inputs, samp_c, div, center2, L2)

    z50, cen50 = extras["d50"]
    unc = z50[cen50 == 0]
    if unc.size:
        q05, q95 = (float(np.quantile(unc, q)) for q in (0.05, 0.95))
    else:
        q05 = q95 = float("nan")
    in_cri = (truth["d50"][0] is not None and unc.size > 0
              and q05 <= truth["d50"][0] <= q95)
    rhat_max = result["diagnostics"]["rhat_max_gated"]
    rhat_ok = rhat_max < 1.05
    report["synthetic_recovery"] = {
        "truth": true, "truth_d50_z": truth["d50"][0],
        "truth_d1_z": truth["d1"][0],
        "posterior_d50": result["estimands"]["d50"],
        "posterior_d1": result["estimands"]["d1"],
        "d50_cri90_z": [q05, q95], "truth_d50_in_cri90": bool(in_cri),
        "rhat_max_gated": rhat_max, "rhat_lt_1.05": bool(rhat_ok),
        "num_divergences": div, "chain_method": method,
        "mcmc_seconds": elapsed,
        "tau_posterior": result["tau"], "eta_posterior": result["eta"],
        "ell_posterior": result["ell"]["median"],
        "pass": bool(in_cri and rhat_ok)}
    med50 = result["estimands"]["d50"]["median_z"]
    print(f"[self-test b] truth d50 z={truth['d50'][0]}; "
          f"post median={med50 if med50 is None else round(med50, 3)}, "
          f"90% CrI=[{q05:.3f},{q95:.3f}] -> "
          f"{'IN' if in_cri else 'OUT'}; Rhat_max={rhat_max:.3f} "
          f"({'ok' if rhat_ok else 'BAD'}); div={div}; "
          f"{elapsed:.0f}s MCMC ({method})")

    report["total_seconds"] = time.perf_counter() - t_all
    report["pass"] = bool(prior_pass and report["synthetic_recovery"]["pass"])
    out = HERE / "self_test.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"[self-test] total {report['total_seconds']:.0f}s -> "
          f"{'PASS' if report['pass'] else 'FAIL'}; wrote {out}")
    return 0 if report["pass"] else 1


# ------------------------------------------------------------------ run

def cmd_run(args):
    inputs = (npz_inputs(Path(args.inputs)) if args.inputs
              else board_inputs(args.model or DEFAULT_MODEL))
    eiv = args.eiv == "on"
    print(f"[run] model={inputs['model_id']} eiv={args.eiv} "
          f"T={len(inputs['z_hat'])} chains={args.chains} "
          f"warmup={args.warmup} samples={args.samples} seed={SEED}")
    samp_c, div, elapsed, center, L, method = run_inference(
        inputs, eiv, args.chains, args.warmup, args.samples, SEED,
        max_tree_depth=args.max_tree_depth,
        target_accept=args.target_accept)
    result, _ = analyze(inputs, samp_c, div, center, L)
    result = {
        "model_id": inputs["model_id"],
        "config": {
            "eiv": args.eiv, "chains": args.chains, "warmup": args.warmup,
            "samples": args.samples, "target_accept": args.target_accept,
            "max_tree_depth": args.max_tree_depth,
            "seed": SEED, "m_basis": M_BASIS, "c_expand": C_EXPAND,
            "widen_sd_mult": WIDEN_SD_MULT, "hsgp_center": center,
            "hsgp_L": L, "n_tasks": len(inputs["z_hat"]),
            "chain_method": method,
            "inputs": args.inputs or "board",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        **result,
        "runtime_seconds_mcmc": elapsed,
    }
    out = Path(args.out)
    out.write_text(json.dumps(result, indent=1))
    d = result["diagnostics"]
    print(f"[run] MCMC {elapsed:.1f}s ({method}); divergences={div} "
          f"[{d['divergence_gate']}]; Rhat_max={d['rhat_max_gated']:.4f} "
          f"[{d['rhat_gate']}]; ESS_min={d['bulk_ess_min_gated']:.0f} "
          f"[{d['ess_gate']}]")
    for name in LEVELS:
        e = result["estimands"][name]
        med = ("-" if e["median_pct"] is None
               else f"{e['median_pct']:.2f}% "
                    f"[{e['cri80_pct'][0]:.2f},{e['cri80_pct'][1]:.2f}]")
        print(f"[run] {name}: median/CrI80 {med}  "
              f"P(left-cens)={e['p_left_censored']:.3f} "
              f"P(right-cens)={e['p_right_censored']:.3f}")
    print(f"[run] tau median={result['tau']['median']:.3f}, "
          f"rho_icc median={result['rho_icc']['median']:.3f}, "
          f"ell median={result['ell']['median']:.3f} "
          f"(house sigma data={result['ell']['house_sigma_from_inputs']:.3f},"
          f" spec nominal={SPEC_HOUSE_SIGMA})")
    print(f"[run] wrote {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--eiv", choices=["on", "off"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--inputs", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--chains", type=int, default=4)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--samples", type=int, default=1000)
    ap.add_argument("--max-tree-depth", type=int, default=10,
                    help="NUTS max tree depth (10 = NumPyro default; the "
                         "spec leaves it unspecified)")
    ap.add_argument("--target-accept", type=float, default=TARGET_ACCEPT,
                    help="NUTS target accept prob (0.9 = FROZEN spec; any "
                         "other value is a declared deviation)")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    if args.run:
        if not args.eiv:
            ap.error("--run requires --eiv on|off")
        if not args.out:
            ap.error("--run requires --out <json>")
        sys.exit(cmd_run(args))
    ap.error("choose --self-test or --run")


if __name__ == "__main__":
    main()

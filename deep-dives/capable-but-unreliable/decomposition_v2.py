# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""Variance-component decomposition of the reliability divergence,
on a stated statistical footing (generalizability theory).

MODEL.  For model m and task pool p (HumanEval+ easy band, MBPP+ easy
band), let Y_mp be the pool reliability deficit of model m: the
log easy-band failure rate of m on pool p, residualized (least
squares, across models) on the model's official capability. Assume

    Y_mp = tau_m + gamma_mp + eps_mp

  tau_m     stable model trait          (variance V_tau)
  gamma_mp  systematic model-x-pool term (variance V_gamma_p)
  eps_mp    finite-sample term: task lottery + attempt noise
            (variance V_eps_p)

IDENTIFICATION (all covariances taken across models):
  Cov(Y_he, Y_mbpp)                 -> V_tau      (eps and gamma
                                       independent across pools)
  E_splits Cov(Y_pA, Y_pB)          -> V_tau + V_gamma_p
     (A,B random halves of pool p's tasks; lottery independent
      across disjoint halves; each half's Y computed the same way)
  Var(Y_p) - (V_tau + V_gamma_p)    -> V_eps_p
  attempt-noise part of V_eps_p     -> from the binomial bootstrap
     (data/bootstrap_noise.json analogue at rate level, computed
      here directly); task-lottery part = remainder.

ADDITIVITY: components are estimated on the covariance scale and by
construction V_tau + V_gamma_p + V_eps_p = Var(Y_p) exactly; the
scientific checks are (a) each component is positive, (b) stable
under bootstrap over models, (c) the same story holds for a second
estimand (mean unbiased P(all 32 attempts pass), residualized on mean
pass rate) — reported side by side.

UNCERTAINTY: percentile intervals from 1000 bootstrap resamples of
the model set (components re-estimated per resample; splits fixed).

Output: data/decomposition_v2.json + printed table.
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import gammaln

HERE = Path(__file__).resolve().parent
EASY = 0.20
N_SPLITS = 100
N_BOOT = 1000
K = 32
rng = np.random.default_rng(20260825)

# ---------- data matrices ----------
diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])

counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))
models = sorted(counts)
M = len(models)

resid_json = json.load(open(HERE / "data" / "residuals.json"))
cap = np.array([resid_json["models"][m]["cap"][1] for m in models])
ok = np.isfinite(cap)
models = [m for m, o in zip(models, ok) if o]
cap = cap[ok]
M = len(models)

POOL_TASKS = {}
for pool, pref in [("he", "HumanEval"), ("mbpp", "Mbpp")]:
    POOL_TASKS[pool] = sorted(
        t for t in diff if diff[t] < EASY and t.startswith(pref)
        and all(t in counts[m] for m in models))
# the COMBINED pool (both benchmarks' easy bands as one task set) — the
# panel the official residual is defined on; decomposed with the same
# identification, using it as a pool of its own
POOL_TASKS["comb"] = POOL_TASKS["he"] + POOL_TASKS["mbpp"]

FAIL, ATT = {}, {}
for pool, ts in POOL_TASKS.items():
    FAIL[pool] = np.array([[counts[m][t][1] - counts[m][t][0]
                            for t in ts] for m in models], dtype=float)
    ATT[pool] = np.array([[counts[m][t][1] for t in ts]
                          for m in models], dtype=float)

# pass^32 needs per-task unbiased estimator, all kept tasks per pool
ALL_TASKS = {}
for pool, pref in [("he", "HumanEval"), ("mbpp", "Mbpp")]:
    ALL_TASKS[pool] = sorted(
        t for t in diff if t.startswith(pref)
        and all(t in counts[m] for m in models))
ALL_TASKS["comb"] = ALL_TASKS["he"] + ALL_TASKS["mbpp"]


def p_allk_matrix(pool):
    ts = ALL_TASKS[pool]
    c = np.array([[counts[m][t][0] for t in ts] for m in models],
                 dtype=float)
    n = np.array([[counts[m][t][1] for t in ts] for m in models],
                 dtype=float)
    with np.errstate(invalid="ignore"):
        lg = (gammaln(c + 1) - gammaln(np.maximum(c - K, 0) + 1)
              - gammaln(n + 1) + gammaln(n - K + 1))
    p = np.where(c >= K, np.exp(lg), 0.0)
    sc = c / n
    return p, sc


PK, SC = {}, {}
for pool in ("he", "mbpp", "comb"):
    PK[pool], SC[pool] = p_allk_matrix(pool)


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def residualize(x, y):
    A = np.vstack([np.ones_like(x), x]).T
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


def y_rate(pool, cols=None, rows=slice(None)):
    F = FAIL[pool][rows] if cols is None else FAIL[pool][rows][:, cols]
    A = ATT[pool][rows] if cols is None else ATT[pool][rows][:, cols]
    y = np.log((F.sum(1) + 0.5) / (A.sum(1) + 1))
    return residualize(cap[rows], y)


def y_p32(pool, cols=None, rows=slice(None)):
    P = PK[pool][rows] if cols is None else PK[pool][rows][:, cols]
    S = SC[pool][rows] if cols is None else SC[pool][rows][:, cols]
    return residualize(logit(S.mean(1)), logit(P.mean(1)))


def cov(a, b):
    return float(np.mean((a - a.mean()) * (b - b.mean())))


def components(yfun, task_sets, boot_rows=None, splits=None):
    """Estimate all components for one estimand. Returns dict."""
    rows = slice(None) if boot_rows is None else boot_rows
    Y = {p: yfun(p, None, rows) for p in ("he", "mbpp", "comb")}
    v_tau = cov(Y["he"], Y["mbpp"])
    out = {"V_tau": v_tau}
    for p in ("he", "mbpp", "comb"):
        nt = len(task_sets[p])
        covs = []
        for (a_idx, b_idx) in splits[p]:
            covs.append(cov(yfun(p, a_idx, rows), yfun(p, b_idx, rows)))
        systematic = float(np.mean(covs))
        var_p = cov(Y[p], Y[p])
        out[f"var_{p}"] = var_p
        out[f"V_gamma_{p}"] = systematic - v_tau
        out[f"V_eps_{p}"] = var_p - systematic
    return out


SPLITS = {}
for p in ("he", "mbpp", "comb"):
    nt = len(POOL_TASKS[p])
    SPLITS[p] = []
    for _ in range(N_SPLITS):
        perm = rng.permutation(nt)
        SPLITS[p].append((perm[: nt // 2], perm[nt // 2:]))
SPLITS_ALL = {}
for p in ("he", "mbpp", "comb"):
    nt = len(ALL_TASKS[p])
    SPLITS_ALL[p] = []
    for _ in range(N_SPLITS):
        perm = rng.permutation(nt)
        SPLITS_ALL[p].append((perm[: nt // 2], perm[nt // 2:]))

# attempt-noise floor at the rate level: binomial resample of counts
def attempt_noise(pool, B=60):
    """Binomial resample of the fail counts -> variance of the rate
    estimand attributable to the finiteness of 128 attempts."""
    ys = []
    for _ in range(B):
        Fb = rng.binomial(ATT[pool].astype(int),
                          np.clip(FAIL[pool] / ATT[pool], 0, 1))
        y = np.log((Fb.sum(1) + 0.5) / (ATT[pool].sum(1) + 1))
        ys.append(residualize(cap, y))
    ys = np.array(ys)
    return float(np.mean(ys.var(0)))


results = {}
for name, yfun, tsets, spl in [
        ("log_easy_fail_rate", y_rate, POOL_TASKS, SPLITS),
        ("pass32", y_p32, ALL_TASKS, SPLITS_ALL)]:
    est = components(yfun, tsets, splits=spl)
    boots = []
    for _ in range(N_BOOT):
        rows = rng.integers(0, M, M)
        boots.append(components(yfun, tsets, boot_rows=rows, splits={
            p: spl[p][:20] for p in spl}))
    ci = {}
    for kk in est:
        vals = np.array([b[kk] for b in boots])
        ci[kk] = [float(np.percentile(vals, 2.5)),
                  float(np.percentile(vals, 97.5))]
    entry = {"estimate": est, "ci95_boot_models": ci}
    if name == "log_easy_fail_rate":
        entry["attempt_noise"] = {p: attempt_noise(p)
                                  for p in ("he", "mbpp", "comb")}
    results[name] = entry
    print(f"\n=== estimand: {name} ===")
    for p in ("he", "mbpp", "comb"):
        vt, vg, ve = est["V_tau"], est[f"V_gamma_{p}"], est[f"V_eps_{p}"]
        tot = est[f"var_{p}"]
        print(f" {p}: var {tot:.3f} = trait {vt:.3f} "
              f"({vt/tot:.0%}, CI {ci['V_tau'][0]/tot:.0%}-"
              f"{ci['V_tau'][1]/tot:.0%})"
              f" + pool {vg:.3f} ({vg/tot:.0%})"
              f" + finite-sample {ve:.3f} ({ve/tot:.0%})")
        if "attempt_noise" in entry:
            an = entry["attempt_noise"][p]
            print(f"    finite-sample = task lottery {ve-an:.3f} "
                  f"({(ve-an)/tot:.0%}) + attempt noise {an:.3f} "
                  f"({an/tot:.0%})")

json.dump({"n_models": M, "easy_band": EASY,
           "n_easy_tasks": {p: len(POOL_TASKS[p]) for p in POOL_TASKS},
           "results": results},
          open(HERE / "data" / "decomposition_v2.json", "w"), indent=1)
print("\nwritten data/decomposition_v2.json")

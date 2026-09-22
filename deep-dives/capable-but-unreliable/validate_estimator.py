# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Synthetic boards built on the real frame (real 46-arm capabilities,
real per-task board failure rates on the real easy bands, n=128):

  log easy-rate of arm m on pool p =
      alpha_p + beta * cap_m + tau_m + gamma_mp
  per-(arm, task) rate = pool rate shaped by the task's real relative
      difficulty, times a log-normal pair-task wobble (creates the
      task-lottery component); counts ~ Binomial(128, rate).

tau ~ N(0, V_tau_true); gamma_mp ~ N(0, V_gamma_true), correlated
across pools at rho (rho = 0 is the estimator's assumption).

For each of R synthetic boards, run the EXACT estimator (cross-pool
covariance -> V_tau; mean split-half covariance -> V_tau + V_gamma;
remainder -> V_eps) and compare with ground truth. Ground-truth V_eps
is measured by Monte Carlo (redraw wobble+counts holding tau/gamma).
Also: bias curve under the correlated-gamma violation, and bootstrap
CI coverage at rho = 0.

Output: data/estimator_validation.json + printed table.
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EASY = 0.20
R = 300
N_SPLITS = 60
N = 128
rng = np.random.default_rng(20260831)

# ---- real frame ----
diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])
counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))
resid_json = json.load(open(HERE / "data" / "residuals.json"))
arms = [m for m in sorted(counts)
        if math.isfinite(resid_json["models"][m]["cap"][1])]
caps = np.array([resid_json["models"][m]["cap"][1] for m in arms])
M = len(arms)

POOL = {}
for p, pref in (("he", "HumanEval"), ("mbpp", "Mbpp")):
    ts = sorted(t for t in diff if diff[t] < EASY and t.startswith(pref))
    w = np.array([max(diff[t], 1e-4) for t in ts])   # board fail rate
    POOL[p] = w / w.mean()                            # relative weight
    # real pool-level fit alpha_p + beta*cap on the true data
    y = []
    for m in arms:
        f = sum(counts[m][t][1] - counts[m][t][0] for t in ts)
        a = sum(counts[m][t][1] for t in ts)
        y.append(math.log((f + 0.5) / (a + 1)))
    A = np.vstack([np.ones(M), caps]).T
    beta, *_ = np.linalg.lstsq(A, np.array(y), rcond=None)
    POOL[p] = (POOL[p], float(beta[0]), float(beta[1]))

V_TAU_TRUE = 0.31
V_GAMMA_TRUE = 0.43
SIG_WOBBLE = 1.1   # per-(arm,task) log-normal sd -> realistic lottery

SPLITS = {p: [rng.permutation(len(POOL[p][0])) for _ in range(N_SPLITS)]
          for p in POOL}


def synth_board(tau, gamma):
    """counts matrices per pool given latent tau (M,) gamma {p:(M,)}."""
    out = {}
    for p, (w, a0, b) in POOL.items():
        L = a0 + b * caps + tau + gamma[p]                # (M,)
        wob = rng.lognormal(0.0, SIG_WOBBLE, (M, len(w)))
        q = np.clip(np.exp(L)[:, None] * w[None, :] * wob, 1e-6, 0.95)
        out[p] = rng.binomial(N, q)                        # fails (M,T)
    return out


def y_of(F, cols=None):
    Fc = F if cols is None else F[:, cols]
    ntask = Fc.shape[1]
    y = np.log((Fc.sum(1) + 0.5) / (ntask * N + 1))
    A = np.vstack([np.ones(M), caps]).T
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


def estimate(boards):
    Y = {p: y_of(boards[p]) for p in boards}
    cov = float(np.mean((Y["he"] - Y["he"].mean())
                        * (Y["mbpp"] - Y["mbpp"].mean())))
    est = {"V_tau": cov}
    for p in boards:
        nt = boards[p].shape[1]
        cs = []
        for perm in SPLITS[p]:
            ya = y_of(boards[p], perm[: nt // 2])
            yb = y_of(boards[p], perm[nt // 2:])
            cs.append(float(np.mean((ya - ya.mean()) * (yb - yb.mean()))))
        syst = float(np.mean(cs))
        var = float(np.var(Y[p]))
        est[f"V_gamma_{p}"] = syst - cov
        est[f"V_eps_{p}"] = var - syst
        est[f"var_{p}"] = var
    return est


def run_condition(rho, reps, coverage=False):
    keys = ["V_tau", "V_gamma_he", "V_gamma_mbpp", "V_eps_he",
            "V_eps_mbpp"]
    got = {k: [] for k in keys}
    cover = 0
    for _ in range(reps):
        tau = rng.normal(0, math.sqrt(V_TAU_TRUE), M)
        g_he = rng.normal(0, math.sqrt(V_GAMMA_TRUE), M)
        g_mb = (rho * g_he + math.sqrt(1 - rho ** 2)
                * rng.normal(0, math.sqrt(V_GAMMA_TRUE), M)
                ) if rho else rng.normal(0, math.sqrt(V_GAMMA_TRUE), M)
        boards = synth_board(tau, {"he": g_he, "mbpp": g_mb})
        est = estimate(boards)
        for k in keys:
            got[k].append(est[k])
        if coverage:
            bs = []
            for _ in range(200):
                idx = rng.integers(0, M, M)
                Yb = {p: y_of(boards[p])[idx] for p in boards}
                bs.append(float(np.mean(
                    (Yb["he"] - Yb["he"].mean())
                    * (Yb["mbpp"] - Yb["mbpp"].mean()))))
            lo, hi = np.percentile(bs, [2.5, 97.5])
            cover += int(lo <= V_TAU_TRUE + rho * V_GAMMA_TRUE <= hi)
    res = {k: (float(np.mean(v)), float(np.std(v))) for k, v in got.items()}
    if coverage:
        res["ci_coverage_V_tau"] = cover / reps
    return res


# ground-truth V_eps by Monte Carlo (tau=gamma=0 -> Var(Y) is eps only)
eps_true = {}
for p in POOL:
    ys = []
    z = np.zeros(M)
    for _ in range(120):
        b = synth_board(z, {"he": z, "mbpp": z})
        ys.append(y_of(b[p]))
    eps_true[p] = float(np.mean(np.var(np.array(ys), axis=0)))

print(f"frame: {M} arms; ground truth V_tau={V_TAU_TRUE} "
      f"V_gamma={V_GAMMA_TRUE} V_eps(MC)="
      f"he {eps_true['he']:.3f} / mbpp {eps_true['mbpp']:.3f}")

base = run_condition(0.0, R, coverage=True)
print(f"\nrho=0 (assumptions hold), {R} boards:")
print(f"  V_tau:   est {base['V_tau'][0]:.3f} ± {base['V_tau'][1]:.3f} "
      f"(truth {V_TAU_TRUE})")
for p in ("he", "mbpp"):
    print(f"  V_gamma_{p}: est {base[f'V_gamma_{p}'][0]:.3f} ± "
          f"{base[f'V_gamma_{p}'][1]:.3f} (truth {V_GAMMA_TRUE})")
    print(f"  V_eps_{p}:   est {base[f'V_eps_{p}'][0]:.3f} ± "
          f"{base[f'V_eps_{p}'][1]:.3f} (truth ~{eps_true[p]:.3f})")
print(f"  bootstrap 95% CI coverage for V_tau: "
      f"{base['ci_coverage_V_tau']:.0%}")

viol = {}
for rho in (0.15, 0.3, 0.5):
    r = run_condition(rho, 120)
    viol[rho] = r
    exp_bias = rho * V_GAMMA_TRUE
    print(f"rho={rho}: V_tau est {r['V_tau'][0]:.3f} "
          f"(truth {V_TAU_TRUE}, predicted contaminated "
          f"{V_TAU_TRUE + exp_bias:.3f})")

json.dump({"M": M, "truth": {"V_tau": V_TAU_TRUE,
                             "V_gamma": V_GAMMA_TRUE,
                             "V_eps_mc": eps_true},
           "rho0": base, "violations": {str(k): v for k, v in viol.items()},
           "R": R},
          open(HERE / "data" / "estimator_validation.json", "w"), indent=1)
print("\nwritten data/estimator_validation.json")

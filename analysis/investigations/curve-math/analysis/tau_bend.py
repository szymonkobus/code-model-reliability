# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""Does the bend of the average-rate curve follow from the task spread alone?

The median-task curve g(z) is the log-odds of failure for the typical task at
difficulty z. Tasks at the same difficulty scatter around it by tau*u, u ~ N(0,1).
The average-rate curve is h(z) = logit( E_u[ sigmoid(g(z) + tau u) ] ).
If g is straight, every bend in h comes from the transform g -> h, which depends on
tau only. Prediction for the average-rate exchange rate, from tau and nothing else:
  S_pred = h'(g_y) / h'(g_x) with g_x = the g at which h = logit(50%), g_y = the g at
  which h = logit(1%)  (slopes of h as a function of g; g' cancels when g is straight)
  G_pred = T * S_pred
Compared with the measured G on the average-rate median curve (results.json), per arm.
Also: the shift between the two chains' 1% crossings that the same transform predicts
(g_y - logit(1%)) / g' — compared with the measured x/y differences between chains.
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit, logit

HERE = Path(__file__).resolve().parent
R = json.load(open(HERE / "results.json"))
T = R["constants"]["T"]
L_A, L_B = R["constants"]["l_a"], R["constants"]["l_b"]
UG = np.linspace(-9, 9, 1801)
WG = np.exp(-0.5 * UG ** 2); WG /= WG.sum()
GG = np.linspace(-40, 40, 8001)          # g grid for the cached transform (step 0.01)
_CACHE = {}


def h_table(tau):
    """h(g) = logit E_u[sigmoid(g + tau u)] on GG, chunked (memory ~ 3 MB), cached per tau."""
    key = round(float(tau), 4)
    if key not in _CACHE:
        out = np.empty_like(GG)
        for i in range(0, len(GG), 200):
            blk = GG[i:i + 200]
            avg = expit(blk[:, None] + tau * UG[None, :]) @ WG
            out[i:i + 200] = logit(np.clip(avg, 1e-15, 1 - 1e-15))
        _CACHE[key] = out
    return _CACHE[key]


def h_of_g(g, tau):
    return np.interp(np.atleast_1d(np.asarray(g, float)), GG, h_table(tau))


def invert_h(target, tau):
    return float(np.interp(target, h_table(tau), GG))


def hprime(g, tau, eps=0.05):
    return float((h_of_g(g + eps, tau)[0] - h_of_g(g - eps, tau)[0]) / (2 * eps))


def predict(tau):
    gx = invert_h(L_A, tau); gy = invert_h(L_B, tau)
    # S = f'(l_b)/f'(l_a) = h'(x)/h'(y) in z; with g straight, g' cancels: S = (dh/dg at g_x)/(dh/dg at g_y)
    S = hprime(gx, tau) / hprime(gy, tau)
    return {"g_x": gx, "g_y": gy, "S_pred": S, "G_pred": T * S,
            "dh_dg_at_50": hprime(gx, tau), "dh_dg_at_1": hprime(gy, tau),
            # the 1% crossing of the average curve sits where g = g_y instead of logit(1%):
            # the shift in g units; divide by g' (per arm) for the shift in difficulty
            "shift_g_units_at_1pct": gy - L_B, "shift_g_units_at_50pct": gx - L_A}


blocks = {(b["dataset"], b["estimator"]): b for b in R["blocks"]}
out = {"note": __doc__, "datasets": {}}
for ds in ("board", "new tasks"):
    avg = {r["cfg"]: r for r in blocks[(ds, "Bayesian (average-rate)")]["rows"]}
    med = {r["cfg"]: r for r in blocks[(ds, "Bayesian (median-task)")]["rows"]}
    rows = []
    for cfg, ra in avg.items():
        rm = med.get(cfg)
        if not rm or ra.get("G") is None:
            continue
        tau = ra["tau"]
        p = predict(tau)
        row = {"cfg": cfg, "label": ra["label"], "tau": tau, "G_avg_measured": ra["G"],
               "G_pred_from_tau": p["G_pred"], "G_median_task": rm.get("G"),
               "S_avg_measured": ra["S"], "S_pred": p["S_pred"], "S_median_task": rm.get("S")}
        # predicted shift of the 1% crossing between chains, in difficulty units: the
        # average curve reaches 1% where g = g_y; with local slope 1/s_b (median-task)
        if rm.get("s_b") and rm.get("y") is not None and ra.get("y") is not None:
            row["pred_y_avg_minus_y_med"] = p["shift_g_units_at_1pct"] * rm["s_b"]
            row["meas_y_avg_minus_y_med"] = ra["y"] - rm["y"]
        if rm.get("x") is not None and ra.get("x") is not None:
            row["meas_x_avg_minus_x_med"] = ra["x"] - rm["x"]
        rows.append(row)
    d = np.array([[r["G_avg_measured"], r["G_pred_from_tau"]] for r in rows])
    err = d[:, 0] - d[:, 1]
    # how much of the arm-to-arm spread of the measured average-rate G does tau explain?
    sd_meas = float(np.std(d[:, 0], ddof=1)); sd_resid = float(np.std(err, ddof=1))
    corr = float(np.corrcoef(d[:, 0], d[:, 1])[0, 1])
    gm = np.array([r["G_median_task"] for r in rows if r.get("G_median_task") is not None])
    ys = [(r["meas_y_avg_minus_y_med"], r["pred_y_avg_minus_y_med"]) for r in rows if "pred_y_avg_minus_y_med" in r]
    ys = np.array(ys) if ys else None
    summ = {"n": len(rows), "G_avg_measured_median": float(np.median(d[:, 0])),
            "G_pred_median": float(np.median(d[:, 1])),
            "median_abs_err": float(np.median(np.abs(err))), "sd_measured": sd_meas, "sd_residual": sd_resid,
            "corr_measured_vs_pred": corr,
            "count_pred_within_20pct": int((np.abs(err / d[:, 1]) <= 0.2).sum()),
            "count_pred_within_10pct": int((np.abs(err / d[:, 1]) <= 0.1).sum()),
            "G_median_task_median": float(np.median(gm)) if gm.size else None,
            "tau_median": float(np.median([r["tau"] for r in rows])),
            "tau_range": [float(min(r["tau"] for r in rows)), float(max(r["tau"] for r in rows))],
            "y_shift_between_chains": None if ys is None else {
                "measured_median": float(np.median(ys[:, 0])), "predicted_median": float(np.median(ys[:, 1])),
                "median_abs_err": float(np.median(np.abs(ys[:, 0] - ys[:, 1]))),
                "corr": float(np.corrcoef(ys[:, 0], ys[:, 1])[0, 1]) if len(ys) > 2 else None}}
    out["datasets"][ds] = {"summary": summ, "rows": rows}
    print(f"\n== {ds}: n {summ['n']}; tau median {summ['tau_median']:.2f} range {summ['tau_range']}")
    print(f"   G avg measured median {summ['G_avg_measured_median']:.3f}; predicted from tau median {summ['G_pred_median']:.3f}; G median-task median {summ['G_median_task_median']}")
    print(f"   |err| median {summ['median_abs_err']:.3f}; sd measured {sd_meas:.3f} -> residual {sd_resid:.3f}; corr {corr:.2f}; within20% {summ['count_pred_within_20pct']}/{summ['n']}, within10% {summ['count_pred_within_10pct']}")
    print(f"   1% crossing shift between chains (avg - median-task): {summ['y_shift_between_chains']}")
    for r in rows[:60]:
        print(f"   {r['label'][:26]:26s} tau {r['tau']:.2f}  G avg {r['G_avg_measured']:.3f}  pred {r['G_pred_from_tau']:.3f}  G med-task {r['G_median_task'] if r['G_median_task'] is None else round(r['G_median_task'],3)}  yshift meas {r.get('meas_y_avg_minus_y_med')} pred {r.get('pred_y_avg_minus_y_med')}")

# the transform's own table: predicted G_avg and shift as a function of tau (page figure data)
table = []
for tau in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0):
    p = predict(tau); p["tau"] = tau; table.append(p)
out["tau_table"] = table
print("\n tau -> G_pred (straight median-task curve):", [(t["tau"], round(t["G_pred"], 3), round(t["shift_g_units_at_1pct"], 2)) for t in table])
(HERE / "tau_bend.json").write_text(json.dumps(out, indent=1, default=float))
print("wrote", HERE / "tau_bend.json")

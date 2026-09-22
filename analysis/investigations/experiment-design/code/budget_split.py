# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Item 4: for a total budget of attempts, how to split it over arms x attempts-per-arm to learn the
law (reliability against capability) best. Measured pieces: (a) the per-arm error of the two crossings
at a per-arm budget b (house battery, one attempt per task on the frame, difficulty known; medians over
golden arms), (b) the population of arms = the served board's house crossings (law_leaveout.json).
Simulation: draw k arms at random from the population, perturb each arm's capability and reliability
by Gaussian noise with the measured RMS errors at budget b, fit the line, compare its slope with the
full-population slope and its predictions for the other arms. Repeat 400 times per (k, b).
Writes data/budget_split.json."""
import json, math, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
H = json.load(open(os.path.join(DATA, "house_summary.json"))); L = json.load(open(os.path.join(DATA, "law_leaveout.json")))
rng = np.random.default_rng(20260904)
cells = [c for c in H["cells"] if c["pop"] == "golden12" and c["mode"] == "known" and c["m"] == 1]
budgets = {}
for c in cells:
    budgets.setdefault(c["total_attempts"], []).append(c)
err = {}
for tot, cs in sorted(budgets.items()):
    e1 = [c["z1"]["rms"] for c in cs if c["z1"]["rms"] is not None]; e50 = [c["z50"]["rms"] for c in cs if c["z50"]["rms"] is not None]
    if e1 and e50: err[tot] = (float(np.median(e1)), float(np.median(e50)), int(cs[0]["T"]))
# extend beyond one pass with m attempts per task on all tasks (breadth continues as 2,4,8... per task)
for c in H["cells"]:
    if c["pop"] == "golden12" and c["mode"] == "known" and c["T"] == 438 and c["m"] > 1:
        tot = c["total_attempts"]; budgets.setdefault(tot, []).append(c)
for tot, cs in budgets.items():
    if tot not in err:
        e1 = [c["z1"]["rms"] for c in cs if c["z1"]["rms"] is not None]; e50 = [c["z50"]["rms"] for c in cs if c["z50"]["rms"] is not None]
        if e1 and e50: err[tot] = (float(np.median(e1)), float(np.median(e50)), 438)
o = L["instruments"]["house"]; pts = o["points"]; arms = o["arms"]
X = np.array([pts[a]["cap"] for a in arms]); Y = np.array([pts[a]["rel"] for a in arms])
def ols(x, y):
    mx, my = x.mean(), y.mean(); sxx = ((x - mx) ** 2).sum()
    if sxx < 1e-9: return None
    b = ((x - mx) * (y - my)).sum() / sxx; return b, my - b * mx
full_b, full_a = ols(X, Y)
rows = []
# per-arm error as a function of attempts per arm (one attempt per task up to 438 tasks, then 2, 4, ... per task): log-log interpolation
tot_sorted = sorted(err); e1_curve = np.array([err[t][0] for t in tot_sorted]); e50_curve = np.array([err[t][1] for t in tot_sorted]); T_curve = np.array([err[t][2] for t in tot_sorted])
def per_arm(attempts):
    a = float(np.clip(attempts, tot_sorted[0], tot_sorted[-1])); la = np.log(a); lt = np.log(tot_sorted)
    return float(np.exp(np.interp(la, lt, np.log(e1_curve)))), float(np.exp(np.interp(la, lt, np.log(e50_curve)))), int(round(np.interp(la, lt, T_curve)))
BUDGETS = [2000, 4000, 8000, 16000, 32000, 64000, 128000, 256000]
ARMS = [4, 6, 8, 12, 16, 24, 32, 40, 48]
for B in BUDGETS:
    for k in ARMS:
        if k >= len(arms): continue
        per = B / k
        if per < tot_sorted[0]: continue
        e1, e50, T = per_arm(per)
        sl, pe = [], []
        for _ in range(400):
            idx = rng.choice(len(arms), size=k, replace=False); mask = np.ones(len(arms), bool); mask[idx] = False
            x = X[idx] + rng.normal(0, e50, k); y = Y[idx] + rng.normal(0, e1, k)
            f = ols(x, y)
            if f is None: continue
            sl.append(f[0]); pred = f[1] + f[0] * X[mask]; pe.append(float(np.sqrt(np.mean((pred - Y[mask]) ** 2))))
        rows.append({"budget_attempts": B, "arms": k, "attempts_per_arm": per, "tasks_per_arm": T, "attempts_per_task": per / T, "per_arm_err_1pct": e1, "per_arm_err_50pct": e50,
                     "slope_rms_err": float(np.sqrt(np.mean((np.asarray(sl) - full_b) ** 2))), "slope_sd": float(np.std(sl, ddof=1)), "heldout_rms_median": float(np.median(pe))})
out = {"full_slope": full_b, "n_population": len(arms), "per_arm_errors": {str(k): {"err_1pct": v[0], "err_50pct": v[1], "tasks": v[2]} for k, v in err.items()}, "rows": rows, "budgets": BUDGETS, "arms_grid": ARMS}
best = []
for B in BUDGETS:
    cand = [r for r in rows if r["budget_attempts"] == B]
    if cand: best.append(min(cand, key=lambda r: r["slope_rms_err"]))
out["best_split"] = best
json.dump(out, open(os.path.join(DATA, "budget_split.json"), "w"), indent=1)
print("per-arm errors by attempts per arm:", {k: (round(v[0], 2), round(v[1], 2), v[2]) for k, v in sorted(err.items())})
print(f"{'budget':>8s} " + " ".join(f"{k:>6d}" for k in ARMS) + "   (slope rms error by arms)")
for B in BUDGETS:
    print(f"{B:8d} " + " ".join(f"{next((r['slope_rms_err'] for r in rows if r['budget_attempts'] == B and r['arms'] == k), float('nan')):6.3f}" for k in ARMS))

# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
import glob, json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")


def fin(v):
    v = np.asarray([x if x is not None else np.nan for x in v], float); return v[np.isfinite(v)]


def _pct(z):
    z = np.asarray(z, float); return 100.0 / (1.0 + np.exp(-z))


def summarize(fits, truth, T=None):
    """fits: list of per-rep records for one (mode, arm); truth: crossing dict. Errors on three
    scales: log-odds (z), points of difficulty (100 x the pooled failure chance, the 0-100 scale),
    and tasks (share of the frame's task list between estimate and truth, x T)."""
    out = {}
    for lev in ("1", "50"):
        z = np.asarray([f[f"z{lev}"] if f[f"z{lev}"] is not None else np.nan for f in fits], float)
        ok = np.isfinite(z); t = truth["cross"][lev]["mid"]
        if ok.any() and t is not None and math.isfinite(t):
            pe = _pct(z[ok]) - _pct(t)
            out[f"z{lev}_pct"] = {"rms": float(np.sqrt(np.mean(pe ** 2))), "bias": float(np.mean(pe)), "true_pct": float(_pct(t)), "median_pct": float(np.median(_pct(z[ok])))}
        else:
            out[f"z{lev}_pct"] = {"rms": None, "bias": None, "true_pct": float(_pct(t)) if (t is not None and math.isfinite(t)) else None, "median_pct": None}
        out[f"z{lev}_reps"] = [float(v) for v in z[ok]]
        out[f"z{lev}"] = {"n": int(len(z)), "n_defined": int(ok.sum()), "censored_share": float(1 - ok.mean()),
                          "rms": float(np.sqrt(np.mean((z[ok] - t) ** 2))) if ok.any() and t is not None and math.isfinite(t) else None,
                          "bias": float(np.mean(z[ok]) - t) if ok.any() and t is not None and math.isfinite(t) else None,
                          "sd": float(np.std(z[ok], ddof=1)) if ok.sum() > 1 else None,
                          "median": float(np.median(z[ok])) if ok.any() else None}
        sh = fin([f[f"share{lev}"] for f in fits]); ts = truth.get(f"share{lev}")
        okk = sh.size and ts is not None and math.isfinite(ts)
        out[f"share{lev}"] = {"rms": float(np.sqrt(np.mean((sh - ts) ** 2))) if okk else None,
                              "bias": float(np.mean(sh) - ts) if okk else None,
                              "tasks_rms": float(np.sqrt(np.mean((sh - ts) ** 2)) * T) if (okk and T) else None,
                              "tasks_bias": float((np.mean(sh) - ts) * T) if (okk and T) else None}
    pr = fin([f["pred_rms"] for f in fits]); mis = fin([f["mis1"] for f in fits])
    out["pred_rms"] = float(np.sqrt(np.mean(pr ** 2))) if pr.size else None
    out["mis1"] = float(np.mean(mis)) if mis.size else None
    return out


def main():
    files = sorted(glob.glob(os.path.join(DATA, "house", "house_*_d*.json")))
    cells = []; truths = {}
    for fn in files:
        d = json.load(open(fn)); pop = d["pop"]
        truths.setdefault(pop, d["truth"])
        by = {}
        for f in d["fits"]:
            by.setdefault((f["mode"], f["arm"]), []).append(f)
        ax = {}
        for a in d["axis"]:
            ax.setdefault(a["mode"], []).append(a)
        axis_summary = {m: {"rms_z": float(np.mean([a["rms_z"] for a in v])), "spearman": float(np.nanmean([a["spearman"] for a in v])),
                            "z_min": float(np.mean([a["z_min"] for a in v])), "z_min_true": float(np.mean([a["z_min_true"] for a in v])),
                            "z_max": float(np.mean([a["z_max"] for a in v])), "z_max_true": float(np.mean([a["z_max_true"] for a in v]))} for m, v in ax.items()}
        for (mode, arm), fits in by.items():
            cells.append({"pop": pop, "b": d["budget_attempts_per_task"], "m": d["attempts_per_task_m"], "T": d["tasks_T"],
                          "total_attempts": d["total_attempts_per_arm"], "mode": mode, "arm": arm, "reps": d["reps"],
                          "frame_T": (1769 if pop == "goldenpool" else 438),
                          **summarize(fits, d["truth"][arm], T=(1769 if pop == "goldenpool" else 438)), "axis": axis_summary.get(mode)})
    out = {"n_files": len(files), "cells": cells, "truth": truths, "effective_attempts": effective_attempts(cells), "variance_decomposition": variance_decomposition(cells)}
    json.dump(out, open(os.path.join(DATA, "house_summary.json"), "w"), indent=0, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else float(x))
    print(f"{len(files)} files, {len(cells)} cells")
    # console table: known axis, median over arms of z1 rms by (b, m)
    for pop in sorted(set(c["pop"] for c in cells)):
        print(f"\n== {pop}: median over golden arms of RMS error vs full data (log-odds); rows = budget b (attempts per frame task), cols = m attempts per task")
        for mode in ("known", "learned-perarm", "learned-pooled"):
            print(f"-- axis {mode}: z1 rms | z50 rms | task-prediction rms | wrong-side share")
            bs = sorted(set(c["b"] for c in cells if c["pop"] == pop)); ms = sorted(set(c["m"] for c in cells if c["pop"] == pop))
            for b in bs:
                row = []
                for m in ms:
                    cc = [c for c in cells if c["pop"] == pop and c["mode"] == mode and c["b"] == b and c["m"] == m]
                    if not cc: row.append(" " * 27); continue
                    z1 = np.nanmedian([c["z1"]["rms"] if c["z1"]["rms"] is not None else np.nan for c in cc]); z50 = np.nanmedian([c["z50"]["rms"] if c["z50"]["rms"] is not None else np.nan for c in cc])
                    pr = np.nanmedian([c["pred_rms"] if c["pred_rms"] is not None else np.nan for c in cc]); mis = np.nanmedian([c["mis1"] if c["mis1"] is not None else np.nan for c in cc])
                    cen = np.mean([c["z1"]["censored_share"] for c in cc])
                    row.append(f"{z1:5.2f}/{z50:4.2f}/{pr:4.2f}/{mis:4.2f}{'*' if cen > .2 else ' '}")
                print(f"b={b:>7g}: " + " | ".join(row))
    vd = out["variance_decomposition"]
    for lev in ("z1", "z50"):
        if lev in vd: print(f"\n== population view {lev}: rho' median {vd[lev]['rho_population_median']:.2f} IQR [{vd[lev]['rho_q25']:.2f},{vd[lev]['rho_q75']:.2f}] boot80 [{vd[lev]['rho_boot80_median_lo']:.2f},{vd[lev]['rho_boot80_median_hi']:.2f}] r2 {vd[lev]['r2_median']:.2f} over {vd[lev]['arms']} arms; effective attempts:", {k: round(v, 2) for k, v in vd[lev]['effective_attempts_population'].items()})
    ea = out["effective_attempts"]
    if ea.get("table"):
        print("\n== effective attempts (known axis, all 438 tasks): variance of the crossing at 1 attempt per task / at m attempts per task")
        for r in ea["table"]: print(f"  m={r['m']:2d} {r['level']:3s}: k_eff(var) {r['k_eff_var']:6.1f} [{r['k_eff_q25']:.1f},{r['k_eff_q75']:.1f}]  k_eff(rms) {r['k_eff_rms'] if r['k_eff_rms'] is None else round(r['k_eff_rms'],1)}  formula rho=0.5: {r['formula_rho_0.5']:.2f}  rho=bayes: {r['formula_rho_bayes'] if r['formula_rho_bayes'] is None else round(r['formula_rho_bayes'],2)}")


def effective_attempts(cells):
    """Direct check of 'effective attempts' (the order-of-filling page's n/(1+(n-1)rho) line):
    under the known axis, all 438 tasks, compare the spread of the 1% crossing across the 40
    thinnings for m attempts per task with the spread for 1 attempt per task. If m attempts on a
    task were worth k_eff independent single attempts, the variance would fall by k_eff, so
    k_eff(m) = var(1)/var(m). Median over the golden arms (arms with >= 10 defined crossings at
    both m). Also the RMS-error ratio (spread plus bias) and the beta-binomial formula's value
    m/(1+(m-1)rho) at rho = 0.5 (the page's figure) and at the rho the golden Bayesian fits report."""
    known = [c for c in cells if c["pop"] == "golden12" and c["mode"] == "known" and c["T"] == 438]
    if not known: return {}
    arms = sorted(set(c["arm"] for c in known)); ms = sorted(set(c["m"] for c in known))
    try:
        rho_b = json.load(open(os.path.join(DATA, "golden_rho.json")))["rho_median"]
    except Exception:
        rho_b = None
    table = []
    for m in ms:
        if m == 1: continue
        for lev in ("z1", "z50"):
            ratios = []; rms_ratios = []
            for arm in arms:
                c1 = [c for c in known if c["arm"] == arm and c["m"] == 1]; cm = [c for c in known if c["arm"] == arm and c["m"] == m]
                if c1 and cm and c1[0][lev]["sd"] and cm[0][lev]["sd"] and c1[0][lev]["n_defined"] >= 10 and cm[0][lev]["n_defined"] >= 10:
                    ratios.append((c1[0][lev]["sd"] / cm[0][lev]["sd"]) ** 2)
                    if c1[0][lev]["rms"] and cm[0][lev]["rms"]: rms_ratios.append((c1[0][lev]["rms"] / cm[0][lev]["rms"]) ** 2)
            if not ratios: continue
            table.append({"m": m, "level": lev, "k_eff_var": float(np.median(ratios)), "k_eff_q25": float(np.quantile(ratios, .25)), "k_eff_q75": float(np.quantile(ratios, .75)),
                          "k_eff_rms": float(np.median(rms_ratios)) if rms_ratios else None, "arms": len(ratios),
                          "formula_rho_0.5": m / (1 + (m - 1) * 0.5), "formula_rho_bayes": (m / (1 + (m - 1) * rho_b)) if rho_b else None})
    return {"table": table, "rho_bayes_median": rho_b, "note": "k_eff = var(1 attempt per task)/var(m attempts per task) of the crossing across 40 thinnings, all 438 tasks, difficulty known; golden arms"}


def variance_decomposition(cells, n_boot=200):
    known = [c for c in cells if c["pop"] == "golden12" and c["mode"] == "known"]
    arms = sorted(set(c["arm"] for c in known)); N = 128.0; Nt = 438.0
    rng = np.random.default_rng(20260904)
    def design_matrix(rows):
        return np.array([[(Nt - c["T"]) / ((Nt - 1) * c["T"]), (N - c["m"]) / ((N - 1) * c["T"] * c["m"])] for c in rows])
    def irls(X, y):
        coef = np.maximum(np.linalg.lstsq(X, y, rcond=None)[0], 1e-12)
        for _ in range(15):
            pred = np.maximum(X @ coef, 1e-9); w = 1.0 / pred ** 2
            coef_new = np.maximum(np.linalg.lstsq(X * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0], 0.0)
            if np.allclose(coef_new, coef, rtol=1e-6, atol=1e-12): coef = coef_new; break
            coef = coef_new
        return coef
    out = {"arms": {}, "note": "var = A (Nt-T)/((Nt-1) T) + B (N-m)/((N-1) T m), IRLS 1/pred^2, known axis, golden arms; interval by re-thinning bootstrap"}
    for lev in ("z1", "z50"):
        rhos, los, his, r2s = [], [], [], []
        for arm in arms:
            rows = [c for c in known if c["arm"] == arm and c[lev]["sd"] is not None and c[lev]["n_defined"] >= 20]
            if len(rows) < 6: continue
            X = design_matrix(rows); y = np.array([c[lev]["sd"] ** 2 for c in rows])
            coef = irls(X, y); A, Bc = float(coef[0]), float(coef[1])
            pred = X @ coef; r2 = 1 - float(np.sum((y - pred) ** 2) / max(np.sum((y - y.mean()) ** 2), 1e-12))
            rho = A / (A + Bc) if (A + Bc) > 0 else None
            # re-thinning bootstrap over the replicate crossings of every cell
            boots = []
            reps = [np.asarray(c[lev + "_reps"], float) for c in rows]
            for _ in range(n_boot):
                yb = np.array([np.var(rng.choice(r, size=r.size, replace=True), ddof=1) for r in reps])
                cb = irls(X, yb)
                if cb.sum() > 0: boots.append(cb[0] / cb.sum())
            lo, hi = (float(np.quantile(boots, .1)), float(np.quantile(boots, .9))) if boots else (None, None)
            out["arms"].setdefault(arm, {})[lev] = {"A_between_task": A, "B_within_task": Bc, "rho_population": rho, "rho_boot80": [lo, hi], "r2": r2, "n_cells": len(rows)}
            if rho is not None: rhos.append(rho); r2s.append(r2)
            if lo is not None: los.append(lo); his.append(hi)
        if rhos:
            rm = float(np.median(rhos))
            out[lev] = {"rho_population_median": rm, "rho_q25": float(np.quantile(rhos, .25)), "rho_q75": float(np.quantile(rhos, .75)), "arms": len(rhos),
                        "rho_boot80_median_lo": float(np.median(los)) if los else None, "rho_boot80_median_hi": float(np.median(his)) if his else None,
                        "r2_median": float(np.median(r2s)),
                        "effective_attempts_population": {str(m): m / (1 + (m - 1) * rm) for m in (1, 2, 4, 8, 16, 32, 128)}}
    return out


if __name__ == "__main__":
    main()

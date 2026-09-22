#!/usr/bin/env python3
"""Would we get the same answers with a correct extractor from the start? Compare the official numbers with the
corrected ones (every candidate restored = 'high'; plus confirmed false passes removed = 'high_demote') for the three
things read off the board: each model's pass rate, its reliability crossing, its capability crossing; and the ORDER of
models by each. Writes results/same_answers.json."""
import json, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
sw = json.load(open(os.path.join(HERE, "results", "swing.json")))["models"]
def order(key, scen):
    return [m for m, r in sorted(sw.items(), key=lambda kv: -(kv[1][scen][key] if isinstance(kv[1][scen][key], (int, float)) else -1))]
out = {"n_models": len(sw), "metrics": {}}
for key, label in (("pass_rate", "pass rate"), ("rel_pct", "reliability crossing"), ("cap_pct", "capability crossing")):
    off = order(key, "official")
    for scen in ("corrected", "hi", "hi_demote"):
        cor = order(key, scen)
        pos_off = {m: i for i, m in enumerate(off)}; pos_cor = {m: i for i, m in enumerate(cor)}
        moved = {m: pos_cor[m] - pos_off[m] for m in off if pos_cor[m] != pos_off[m]}
        maxmove = max((abs(v) for v in moved.values()), default=0)
        deltas = {m: (sw[m][scen][key] - sw[m]["official"][key]) * (100 if key == "pass_rate" else 1) for m in sw}
        big = sorted(deltas.items(), key=lambda kv: -abs(kv[1]))[:5]
        out["metrics"][f"{key}|{scen}"] = {"label": label, "scenario": scen, "models_changing_rank": len(moved), "max_rank_move": maxmove,
                                           "rank_moves": moved, "max_abs_delta": max(abs(v) for v in deltas.values()), "largest_deltas": big,
                                           "top10_official": off[:10], "top10_corrected": cor[:10]}
# capability-vs-reliability relationship: OLS slope/intercept of rel on cap over models with finite crossings
def fit(scen):
    pts = [(r[scen]["cap_pct"], r[scen]["rel_pct"]) for r in sw.values() if 0 < r[scen]["cap_pct"] < 100 and 0 < r[scen]["rel_pct"] < 100]
    n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts); sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    b = sxy / sxx; a = my - b * mx
    return {"n": n, "slope": b, "intercept": a}
out["cap_rel_fit"] = {s: fit(s) for s in ("official", "corrected", "hi", "hi_demote")}
json.dump(out, open(os.path.join(HERE, "results", "same_answers.json"), "w"), indent=1)
for k, v in out["metrics"].items():
    print(f"{k:22s} rank changes {v['models_changing_rank']:2d} max move {v['max_rank_move']} max |delta| {v['max_abs_delta']:.2f} largest {[(m.split('/')[-1], round(d, 2)) for m, d in v['largest_deltas'][:3]]}")
print(out["cap_rel_fit"])

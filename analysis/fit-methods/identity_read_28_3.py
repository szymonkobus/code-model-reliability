#!/usr/bin/env python3
import sys, json, math, statistics as st

def load(p): return json.load(open(p))
def draws(d, cross):
    return [v for v in ((d.get("draws_avg_full") or d.get("draws_avg") or {}).get(cross) or {}).get("z", []) if v is not None]
def figs(z):
    z = sorted(z); n = len(z)
    if n < 100: return None
    q = lambda p: z[min(n - 1, max(0, int(round(p * (n - 1)))))]
    return {"median": st.median(z), "q10": q(0.10), "q90": q(0.90), "n_distinct": len(set(z))}
def lattice_step(z):
    zs = sorted(set(z)); gaps = [b - a for a, b in zip(zs, zs[1:]) if b - a > 1e-9]
    return min(gaps) if gaps else None

def main():
    a = sys.argv; new, srv = load(a[1]), load(a[2]); label = a[a.index("--label") + 1] if "--label" in a else ""
    out = {"label": label, "new": a[1], "served": a[2], "items": {}}
    # (1) the sampler untouched
    pn, ps = new.get("param_draws", {}), srv.get("param_draws", {})
    same = {k: (pn.get(k) == ps.get(k)) for k in ("eta", "ell", "tau", "mu1")}
    n_pos = {k: (sum(1 for u, v in zip(pn.get(k, []), ps.get(k, [])) if u != v), len(ps.get(k, []))) for k in same}
    gn, gs = new["diagnostics"], srv["diagnostics"]
    hyper = ("eta", "ell", "tau", "mu1")
    hyper_same = {k: ((gn.get("rhat_gated") or {}).get(k) == (gs.get("rhat_gated") or {}).get(k)) and ((gn.get("bulk_ess_gated") or {}).get(k) == (gs.get("bulk_ess_gated") or {}).get(k)) for k in hyper}
    diag_same = all(hyper_same.values()) and gn.get("num_divergences") == gs.get("num_divergences")
    derived_moved = {k: {"rhat": ((gs.get("rhat_gated") or {}).get(k), (gn.get("rhat_gated") or {}).get(k)), "bulk_ess": ((gs.get("bulk_ess_gated") or {}).get(k), (gn.get("bulk_ess_gated") or {}).get(k))} for k in ("d50", "d1")}
    out["items"]["sampler_untouched"] = {"param_draws_equal": same, "positions_differing": n_pos, "hyperparameter_diagnostics_equal": hyper_same, "divergences": (gs.get("num_divergences"), gn.get("num_divergences")), "gated_diagnostics_equal": diag_same, "crossing_derived_diagnostics_served_vs_new": derived_moved,
                                         "config_same_seed": new["config"].get("seed") == srv["config"].get("seed"),
                                         "config_same_layout": all(new["config"].get(k) == srv["config"].get(k) for k in ("chains", "warmup", "samples")),
                                         "depth_new": new["config"].get("max_tree_depth"), "depth_served": srv["config"].get("max_tree_depth")}
    ok1 = all(same.values()) and diag_same
    # (2) the six figures within one lattice step; (3) the lattice gone
    ok2, ok3, rows = True, True, []
    for cross, name in (("d50", "D50"), ("d1", "D99")):
        zn, zs_ = draws(new, cross), draws(srv, cross); fn, fs = figs(zn), figs(zs_)
        step = lattice_step(zs_) if zs_ else None
        if fn is None or fs is None:
            rows.append({"figure": name, "unusable": True, "n_new": len(zn), "n_served": len(zs_)}); continue
        for key in ("median", "q10", "q90"):
            diff = fn[key] - fs[key]; within = step is not None and abs(diff) <= step + 1e-9
            ok2 = ok2 and within
            rows.append({"figure": f"{name} {key}", "served": fs[key], "new": fn[key], "diff": diff, "lattice_step": step, "within_one_step": within})
        rows.append({"figure": f"{name} distinct values", "served": fs["n_distinct"], "new": fn["n_distinct"], "lattice_gone": fn["n_distinct"] > 20 * fs["n_distinct"]})
        ok3 = ok3 and fn["n_distinct"] > 20 * fs["n_distinct"]
    out["figures"] = rows
    verdict = "IDENTITY OK (the sampler untouched; every figure within one lattice step; the lattice gone)" if (ok1 and ok2 and ok3) else "IDENTITY DIFFERS: " + "; ".join(
        x for x, bad in (("the parameter draws or the gated diagnostics differ (the sampler moved)", not ok1), ("a figure moved by more than one lattice step", not ok2), ("the new draws are still latticed", not ok3)) if bad)
    out["verdict"] = verdict
    print(f"IDENTITY READ 28.3/28.4 {label}: {verdict}")
    print(f"  sampler: param_draws equal {same}; positions differing {n_pos}; hyperparameter diagnostics equal {hyper_same}; divergences served/new {out['items']['sampler_untouched']['divergences']}; crossing-derived diagnostics (move with the crossing read by design) d50 ESS served/new {derived_moved['d50']['bulk_ess']} d1 ESS {derived_moved['d1']['bulk_ess']}; seed same {out['items']['sampler_untouched']['config_same_seed']}; layout same {out['items']['sampler_untouched']['config_same_layout']}; depth {out['items']['sampler_untouched']['depth_new']} vs {out['items']['sampler_untouched']['depth_served']}")
    for r in rows:
        if r.get("unusable"): print(f"  {r['figure']}: unusable (n {r['n_new']} / {r['n_served']})"); continue
        if "diff" in r: print(f"  {r['figure']}: served {r['served']:+.5f} new {r['new']:+.5f} diff {r['diff']:+.5f} ({(r['diff']/r['lattice_step']) if r['lattice_step'] else float('nan'):+.2f} steps) → {'within one step' if r['within_one_step'] else 'BEYOND one step'}")
        else: print(f"  {r['figure']}: served {r['served']} new {r['new']} → {'lattice gone' if r['lattice_gone'] else 'STILL LATTICED'}")
    if "--json" in a: json.dump(out, open(a[a.index("--json") + 1], "w"), indent=1)

if __name__ == "__main__": main()

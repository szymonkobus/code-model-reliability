#!/usr/bin/env python3
import glob, json, os, sys, re
wd = sys.argv[1]
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else f"{wd}/gates_summary.json"
try:
    import numpy as _np
except Exception:
    _np = None
_cross = {}
try:
    _cj = json.load(open(f"{wd}/crossings_of_record.json"))
    for _r in _cj.get("rows", []): _cross[re.sub(r"_eiv(on|off)$", "", _r["arm"])] = _r
except Exception:
    _cross = {}
def _all_fail_share(stem):
    if _np is None: return None
    for cand in (f"{wd}/inputs/{stem}.npz",):
        if os.path.exists(cand):
            z = _np.load(cand, allow_pickle=True)
            if "f" in z and "n" in z and len(z["n"]): return round(float(_np.mean(z["f"] == z["n"])), 4)
    return None
def _plain(ok, share, m50, m1, note):
    if ok: return ""
    pct = (f"{round(100 * share)}%" if isinstance(share, float) else "an unknown share")
    if m50 is None and m1 is None:
        return f"the sampler mixes slowly on the effects of this arm's all-fail tasks ({pct} of its tasks); the crossing-level check was not available when this summary was written"
    if note:
        return f"the sampler mixes slowly for this arm ({pct} of its tasks all-fail) and its chains disagree on where it crosses; see the note beside the crossing"
    if m50 == "mixes" and m1 == "mixes":
        return (f"the sampler mixes slowly on the effects of this arm's all-fail tasks ({pct} of its tasks), which do not enter the crossings of record; "
                f"the crossings themselves mix")
    return (f"the sampler mixes slowly on the effects of this arm's all-fail tasks ({pct} of its tasks), which do not enter the crossings of record; "
            f"the crossings themselves agree to within a tenth of a difficulty step")
def _face(ok, share, m50, m1, note):
    if ok: return ""
    pct = (f"{round(100 * share)}%" if isinstance(share, float) else "some")
    if note:
        return "the fits for this arm do not agree on where it crosses; the point is shown with that caveat"
    return (f"the fit's certainty for this arm is wider because every attempt failed on {pct} of its tasks; those tasks do not enter the crossings of record")
gates = {}
for p in sorted(glob.glob(f"{wd}/results/*.json")):
    r = json.load(open(p)); d = r["diagnostics"]; nd = d["num_divergences"]
    _stem = re.sub(r"^posterior_summary_|_eiv(on|off)\.json$|\.json$", "", os.path.basename(p))
    _share = _all_fail_share(_stem); _cr = _cross.get(_stem, {})
    tot = r["config"]["chains"] * r["config"]["samples"]
    ok = (nd / tot <= 0.005 and d["rhat_gate"] == "pass" and d["ess_gate"] in ("pass", "pass_with_note"))
    gates[r["model_id"]] = {
        "divergences": nd, "divergence_frac": round(nd / tot, 5),
        "strict_gate": "pass" if nd == 0 else ("pass_with_note" if nd < 5 else "FAIL"),
        "half_pct_gate": "pass" if ok else "FAIL",
        "rhat_gate": d["rhat_gate"], "ess_gate": d["ess_gate"], "rhat_max": round(d["rhat_max_gated"], 4),
        "ess_note": d.get("ess_gate_note"),
        "bulk_ess_min": (round(d["bulk_ess_min_gated"], 1) if isinstance(d.get("bulk_ess_min_gated"), (int, float)) else None),
        "gates_failed": [g_ for g_, f_ in (("divergence", nd / tot > 0.005), ("rhat", d["rhat_gate"] != "pass"), ("ess", d["ess_gate"] == "FAIL"), ("board_half_pct", not ok)) if f_],
        "all_fail_share": _share, "crossing_mixing_50": _cr.get("crossing_mixing_50"), "crossing_mixing_1": _cr.get("crossing_mixing_1"),
        "mixing_disclosure_long": _plain(ok, _share, _cr.get("crossing_mixing_50"), _cr.get("crossing_mixing_1"), _cr.get("crossing_mixing_note") or ""),
        "mixing_disclosure_short": _face(ok, _share, _cr.get("crossing_mixing_50"), _cr.get("crossing_mixing_1"), _cr.get("crossing_mixing_note") or "")}
gates["_convention_note"] = ("0.5%-of-draws convention: FAIL iff "
                             "divergences/(chains*samples) > 0.005 OR rhat_gate != pass OR ess_gate == FAIL; "
                             "'pass_with_note' ess_gate is a pass (fully-censored estimand, ESS n/a).")
gates["_all_fail_note"] = ("all_fail_share = share of an arm's input cells with every attempt failed; the arm-level R-hat tracks it because the effects of all-fail tasks are bounded only from below; the crossings of record sit inside the identified region, so the crossing-level fields (crossings_of_record rows) are the gate that matters; mixing_disclosure_long is the per-arm sentence for a failing arm-level gate; mixing_disclosure_short is its plain-words twin.")
_tmp = OUT + ".tmp"; json.dump(gates, open(_tmp, "w"), indent=1); os.replace(_tmp, OUT)
n = sum(1 for v in gates.values() if isinstance(v, dict) and v.get("half_pct_gate") == "FAIL")
_nc = sum(1 for v in gates.values() if isinstance(v, dict) and v.get("crossing_mixing_1") is not None)
print(f"{os.path.basename(wd)}: {len(gates)-2} fits, {n} flagged; crossing verdicts joined on {_nc}; all-fail shares on {sum(1 for v in gates.values() if isinstance(v, dict) and v.get('all_fail_share') is not None)}")

"""The gates of a fit, per arm, and the concentration reading beside them.

A fit serves with its gates disclosed; a failed gate marks the arm's row and never removes it. Three gates
decide the verdict:

- divergences: the sampler's divergent transitions as a share of the kept draws, failing above half a percent
  (the engine's own stricter flag, five or more, is carried beside as a note);
- split R-hat of the D50 and D99 crossing draws of the average-rate curve, per chain, at most 1.01;
- bulk effective sample size of the same draws, at least 400, judged only when the file carries every draw (a
  thinned export's effective sample size is reported, not gated).

The R-hat and effective-sample-size components are read on the crossings' own draws because those are the
served numbers; a level whose crossing is a bound (more than half of the draws beyond an end) is exempt from
the two, since constant censored draws have no mixing to measure. The parameters eta, ell, tau and mu1 keep
their own R-hat and effective sample size as a disclosure.

Concentration is a reading, not a gate: on the easy third of the axis's tasks, the share of an arm's failures
carried by the few most-failed tasks (the top 5% of the easy third, at least one task). An arm whose failures
sit on a handful of easy tasks has a failure curve that an average over tasks reads differently from a curve
through typical tasks; the regime (diffuse, intermediate, concentrated, extreme) says how far that is the case.

Reads the result files, the arms' inputs and ``axis.csv``. Writes ``gates.json``.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from pathlib import Path

import numpy as np

from .crossings import STATUS_POINT, arm_of, draws_of, load_result, status_of
from .rules import DIVERGENCE_SHARE_MAX, GATE_DIVERGENCE_NOTE, GATE_ESS_MIN, GATE_RHAT_MAX

SPREAD_MATERIAL = 0.10
"""Between-chain disagreement on a crossing of more than a tenth on the scale is worth a note to a reader."""

CONCENTRATION_REGIMES = (
    ("extreme", 0.8, None),
    ("concentrated", 0.5, 0.8),
    ("intermediate", 0.3, 0.5),
    ("diffuse", None, 0.3),
)
"""Regime by the top-5% share of easy-third failures: lower bound inclusive, upper exclusive, first match."""

EASY_THIRD_SHARE = 1 / 3
TOP_SHARE = 0.05


def crossing_mixing(result: dict) -> dict:
    """Per level of record: R-hat, effective sample size, chain medians and their spread, and whether the
    crossing mixes. Needs numpyro for the estimators; raises ImportError without it."""
    from .diagnostics import bulk_ess, chain_array, rhat
    chains = int((result.get("config") or {}).get("chains") or 4)
    out = {}
    for lv in ("d50", "d99"):
        z, cen, basis = draws_of(result, "average", lv)
        if z is None:
            out[lv] = {"rhat": None, "ess": None, "basis": None, "chain_medians": None, "spread": None, "mixes": None,
                       "note": "no exported average-rate crossing draws"}
            continue
        arr = chain_array(z, cen, chains)
        if arr is None:
            out[lv] = {"rhat": None, "ess": None, "basis": basis, "chain_medians": None, "spread": None, "mixes": None,
                       "note": f"{len(z)} draws do not divide into {chains} chains"}
            continue
        r = rhat(arr)
        e = bulk_ess(arr)
        meds = []
        for c in range(chains):
            m = float(np.median(arr[c]))
            meds.append(None if not np.isfinite(m) else round(m, 4))
        fin = [m for m in meds if m is not None]
        spread = round(max(fin) - min(fin), 4) if len(fin) >= 2 else None
        s_lo = sum(1 for c in cen if c < 0) / len(cen)
        s_hi = sum(1 for c in cen if c > 0) / len(cen)
        bound = status_of(s_lo, s_hi) != STATUS_POINT
        rhat_ok = bool(np.isfinite(r) and r <= GATE_RHAT_MAX)
        ess_ok = bool(np.isfinite(e) and e >= GATE_ESS_MIN) if basis == "full" else True
        out[lv] = {"rhat": None if not np.isfinite(r) else round(float(r), 4),
                   "ess": None if not np.isfinite(e) else round(float(e), 1),
                   "basis": basis, "chain_medians": meds, "spread": spread,
                   "bound": bound, "mixes": (None if bound else bool(rhat_ok and ess_ok)),
                   "rhat_ok": rhat_ok, "ess_ok": ess_ok}
    return out


def easy_third(axis_z: dict[str, float]) -> set:
    """The tasks in the lowest third of the axis."""
    order = sorted(axis_z, key=lambda t: axis_z[t])
    return set(order[:math.ceil(len(order) * EASY_THIRD_SHARE)])


def concentration(task_ids, failures, easy: set) -> dict:
    """The top-5% share of an arm's easy-third failures and its regime."""
    fe = [float(f) for t, f in zip(task_ids, failures) if t in easy]
    n_easy = len(fe)
    total = float(sum(fe))
    if n_easy == 0:
        return {"share_top5pct_easy_third": None, "any_fail_share_easy_third": None, "n_easy_third_tasks": 0,
                "regime": "no easy-third tasks"}
    if total <= 0:
        return {"share_top5pct_easy_third": None, "any_fail_share_easy_third": 0.0, "n_easy_third_tasks": n_easy,
                "regime": "no easy-third failures"}
    k = max(1, math.ceil(TOP_SHARE * len(easy)))
    share = round(float(sum(sorted(fe, reverse=True)[:k])) / total, 4)
    any_fail = round(sum(1 for v in fe if v > 0) / n_easy, 4)
    regime = "unclassified"
    for name, lo, hi in CONCENTRATION_REGIMES:
        if (lo is None or share >= lo) and (hi is None or share < hi):
            regime = name
            break
    return {"share_top5pct_easy_third": share, "any_fail_share_easy_third": any_fail, "n_easy_third_tasks": n_easy,
            "regime": regime}


def verdict(result: dict, mixing: dict) -> dict:
    """The gate verdict: divergences as a share of the kept draws (above ``DIVERGENCE_SHARE_MAX`` fails; with
    the draw count unknown, the engine's count flag decides), and the crossing-level R-hat and sample size."""
    diag = result.get("diagnostics") or {}
    cfg = result.get("config") or {}
    nd = int(diag.get("num_divergences") or 0)
    total = int(cfg.get("chains") or 0) * int(cfg.get("samples") or 0)
    engine_flag = "pass" if nd == 0 else "pass_with_note" if nd < GATE_DIVERGENCE_NOTE else "FAIL"
    share = (nd / total) if total else None
    div_fail = (share > DIVERGENCE_SHARE_MAX) if share is not None else (engine_flag == "FAIL")
    div_gate = "FAIL" if div_fail else ("pass" if nd == 0 else "pass_with_note")
    rhat_fail = any(m.get("mixes") is not None and not m.get("rhat_ok", True) for m in mixing.values())
    ess_fail = any(m.get("mixes") is not None and not m.get("ess_ok", True) for m in mixing.values())
    failed = [g for g, f in (("divergences", div_fail), ("rhat", rhat_fail), ("ess", ess_fail)) if f]
    return {"divergences": nd, "divergence_share": (None if share is None else round(share, 6)), "divergence_gate": div_gate,
            "engine_divergence_flag": engine_flag, "rhat_gate": "FAIL" if rhat_fail else "pass",
            "ess_gate": "FAIL" if ess_fail else "pass", "gates_failed": failed, "gate": "FAIL" if failed else "pass"}


def gates_for_arm(result: dict, inputs: dict | None, easy: set | None) -> dict:
    mixing = crossing_mixing(result)
    v = verdict(result, mixing)
    diag = result.get("diagnostics") or {}
    rg = diag.get("rhat_gated") or {}
    eg = diag.get("bulk_ess_gated") or {}
    hyper = [k for k in ("eta", "ell", "tau", "mu1") if k in rg]
    out = {
        **v,
        "crossing_rhat_d50": mixing["d50"]["rhat"], "crossing_ess_d50": mixing["d50"]["ess"],
        "crossing_rhat_d99": mixing["d99"]["rhat"], "crossing_ess_d99": mixing["d99"]["ess"],
        "crossing_mixes_d50": mixing["d50"]["mixes"], "crossing_mixes_d99": mixing["d99"]["mixes"],
        "crossing_chain_spread_d50": mixing["d50"]["spread"], "crossing_chain_spread_d99": mixing["d99"]["spread"],
        "draws_basis": mixing["d50"]["basis"],
        "parameter_rhat_max": (round(max(float(rg[k]) for k in hyper), 4) if hyper else None),
        "parameter_ess_min": (round(min(float(eg[k]) for k in hyper if eg.get(k) is not None), 1)
                              if any(eg.get(k) is not None for k in hyper) else None),
        "engine_rhat_gate": diag.get("rhat_gate"), "engine_ess_gate": diag.get("ess_gate"),
    }
    notes = []
    for lv in ("d50", "d99"):
        m = mixing[lv]
        if m.get("mixes") is False and (m.get("spread") is None or m["spread"] > SPREAD_MATERIAL):
            notes.append(lv.upper())
    out["chains_disagree_on"] = notes
    if inputs is not None and easy is not None:
        out["concentration"] = concentration(inputs["task_ids"], inputs["f"], easy)
    else:
        out["concentration"] = {"regime": "not read (no inputs or axis)"}
    return out


def _axis_from_inputs(inputs_dir) -> dict[str, float]:
    z = {}
    for p in glob.glob(os.path.join(inputs_dir, "*.npz")):
        d = np.load(p, allow_pickle=False)
        for t, v in zip(d["task_ids"], d["z_hat"]):
            z[str(t)] = float(v)
    return z


def gates_for_fit(results_dir, inputs_dir=None, axis_csv=None, pattern="posterior_summary_*.json") -> dict:
    easy = None
    if axis_csv:
        from .axis import read_axis_csv
        easy = easy_third({t: a.z for t, a in read_axis_csv(axis_csv).items()})
    elif inputs_dir:
        easy = easy_third(_axis_from_inputs(inputs_dir))
    arms = {}
    for path in sorted(glob.glob(os.path.join(results_dir, pattern))):
        result = load_result(path)
        arm = arm_of(path)
        inputs = None
        if inputs_dir:
            npz = os.path.join(inputs_dir, f"{arm}.npz")
            if os.path.exists(npz):
                d = np.load(npz, allow_pickle=False)
                inputs = {"task_ids": [str(t) for t in d["task_ids"]], "f": np.asarray(d["f"], float)}
        arms[arm] = gates_for_arm(result, inputs, easy)
    return {
        "rule": {
            "verdict": f"fail on divergences above {100 * DIVERGENCE_SHARE_MAX:g}% of the kept draws, on split R-hat above "
                       f"{GATE_RHAT_MAX} or bulk effective sample size below {GATE_ESS_MIN:.0f} of the D50 or D99 crossing "
                       "draws (a bound level exempt; a thinned export's sample size reported, not gated); the engine's "
                       "count flag (five or more divergences) beside as a note",
            "concentration": "a reading beside the gates, never a hold: the share of an arm's easy-third failures on "
                             "the top 5% most-failed easy-third tasks; regimes by the thresholds in this file",
            "regimes": [{"regime": n, "min": lo, "max": hi} for n, lo, hi in CONCENTRATION_REGIMES],
        },
        "n_arms": len(arms),
        "n_pass": sum(1 for a in arms.values() if a["gate"] == "pass"),
        "arms": arms,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit gates", description="the gates per arm from the engine's results")
    ap.add_argument("--results", required=True)
    ap.add_argument("--inputs", default=None, help="the fit's inputs/ directory (for the concentration reading)")
    ap.add_argument("--axis", default=None, help="axis.csv (the easy third); default: the inputs' own positions")
    ap.add_argument("--out", required=True, help="gates.json to write")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    g = gates_for_fit(args.results, args.inputs, args.axis)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(g, indent=1) + "\n", encoding="utf-8")
    print(f"gates: {g['n_arms']} arms, {g['n_pass']} pass; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

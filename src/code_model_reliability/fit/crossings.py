"""The crossings table: D50 and D99 per arm, read from the engine's result files.

Which curve. Capability and reliability are read from the average-rate curve: D50 where the share of attempts
expected to fail is one half, D99 where it is one in a hundred. The median-task D99 (the curve of a task with
no deviation) is carried beside, under the same reading rule.

How a crossing is read. Every exported draw of the crossing counts. The number is the median over all draws,
with a draw whose crossing lies below the easiest task counted as beyond the easy end of the scale and one
beyond the hardest task as beyond the hard end; the 80% interval is the 10th and 90th percentiles taken the same
way, so an interval edge that falls among censored draws prints as the scale's end. The status is ``point``
unless more than half of the draws lie beyond one end: then the crossing is a ``bound below`` (it lies below the
easiest task used; the value reported is that task's difficulty) or a ``bound above`` (above the hardest task
used; the hardest task's difficulty). Every arm has a number at every level; a wide interval never removes a
row. The shares beyond each end and the median over the uncensored draws alone (``*_z_conditional``) are kept
beside.

Further levels. D97, D95 and D90 (3%, 5% and 10% failure) come from the same fit under the same rule. D1 (99%
failure, the hard end of a curve) is read from the fit's level table between the two levels bracketing 99%,
linear in the logit of the level, with the same bound rule.

Reads ``posterior_summary_<arm>.json`` files (an older file keyed ``d1``/``d3``/``d5``/``d10`` reads too), an
optional names map (arm id to printed name) and an optional ``gates.json`` whose per-arm verdict and crossing
statistics are merged in. Writes ``crossings.csv`` and ``crossings.json`` (the rows plus the rule in words).
``load_crossings`` reads either this table or an older one whose columns carried the ``*_of_record`` names.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import glob
import hashlib
import json
import math
import os
from pathlib import Path

from .rules import LEVEL_ALIASES

LEVELS_OF_RECORD = ("d50", "d99")
EXTRA_LEVELS = ("d97", "d95", "d90")
HARD_END_LEVEL = ("d1", 0.99)
BOUND_SHARE = 0.5
"""More than half of the draws beyond an end makes the crossing a bound at that end."""
EDGE_SHARE = 0.10
"""A tenth or more of the draws beyond an end, on a point, is recorded as a censored edge of its interval."""

STATUS_POINT, STATUS_BELOW, STATUS_ABOVE, STATUS_NA = "point", "bound below", "bound above", "unavailable"

COLUMNS = (
    ["arm", "model_name"]
    + [f"{lv}_{s}" for lv in ("d50", "d99") for s in
       ("z", "lo", "hi", "status", "bound_z", "p_left_censored", "p_right_censored", "z_conditional", "censored_edge")]
    + [f"d99_median_task_{s}" for s in ("z", "lo", "hi", "status", "p_left_censored", "p_right_censored")]
    + [f"{lv}_{s}" for lv in EXTRA_LEVELS + ("d1",) for s in ("z", "lo", "hi", "status", "p_left_censored", "p_right_censored")]
    + ["tau", "tau_lo", "tau_hi", "rho", "rho_lo", "rho_hi", "ell_median",
       "crossing_rhat_d50", "crossing_ess_d50", "crossing_rhat_d99", "crossing_ess_d99", "divergences", "gate", "gates_failed",
       "n_tasks", "grid_lo_z", "grid_hi_z", "m_basis", "hsgp_L", "crossing_rule", "draws_basis", "engine_sha256_12", "source_sha256_12"]
)

OLD_NAMES = {
    "model_id": "arm",
    "d50_of_record_z": "d50_z", "d50_of_record_cri80_lo": "d50_lo", "d50_of_record_cri80_hi": "d50_hi",
    "d50_of_record_status": "d50_status", "d50_of_record_p_left_censored": "d50_p_left_censored",
    "d50_of_record_p_right_censored": "d50_p_right_censored", "d50_conditional_median_z": "d50_z_conditional",
    "d50_of_record_censored_edge": "d50_censored_edge",
    "d1_of_record_z": "d99_z", "d1_of_record_cri80_lo": "d99_lo", "d1_of_record_cri80_hi": "d99_hi",
    "d1_of_record_status": "d99_status", "d1_of_record_p_left_censored": "d99_p_left_censored",
    "d1_of_record_p_right_censored": "d99_p_right_censored", "d1_conditional_median_z": "d99_z_conditional",
    "d1_of_record_censored_edge": "d99_censored_edge",
    "d1_median_task_z": "d99_median_task_z", "d1_median_task_cri80_lo": "d99_median_task_lo",
    "d1_median_task_cri80_hi": "d99_median_task_hi", "d1_median_task_status": "d99_median_task_status",
    "d1_median_task_p_left_censored": "d99_median_task_p_left_censored",
    "d1_median_task_p_right_censored": "d99_median_task_p_right_censored",
    "tau_median": "tau", "tau_cri80_lo": "tau_lo", "tau_cri80_hi": "tau_hi",
    "rho_icc_median": "rho", "rho_icc_cri80_lo": "rho_lo", "rho_icc_cri80_hi": "rho_hi",
    "crossing_rhat_50": "crossing_rhat_d50", "crossing_ess_50": "crossing_ess_d50",
    "crossing_rhat_1": "crossing_rhat_d99", "crossing_ess_1": "crossing_ess_d99",
    "n_axis_tasks": "n_tasks", "fit_crossing_rule": "crossing_rule",
}
for _old, _new in (("d3", "d97"), ("d5", "d95"), ("d10", "d90")):
    OLD_NAMES.update({f"{_old}_of_record_z": f"{_new}_z", f"{_old}_of_record_cri80_lo": f"{_new}_lo",
                      f"{_old}_of_record_cri80_hi": f"{_new}_hi", f"{_old}_of_record_status": f"{_new}_status",
                      f"{_old}_of_record_p_left_censored": f"{_new}_p_left_censored",
                      f"{_old}_of_record_p_right_censored": f"{_new}_p_right_censored"})


# ------------------------------------------------------------------------------------------------- reading
def load_result(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _alias(d: dict, key: str):
    """A level's block from a dict keyed by the new or the older level names."""
    if key in d:
        return d[key]
    for old, new in LEVEL_ALIASES.items():
        if new == key and old in d:
            return d[old]
    return None


def arm_of(path) -> str:
    name = os.path.basename(path)
    if name.startswith("posterior_summary_"):
        name = name[len("posterior_summary_"):]
    if name.endswith(".json"):
        name = name[:-5]
    for suf in ("_eivon", "_eivoff"):
        if name.endswith(suf):
            name = name[:-len(suf)]
    return name


def draws_of(result: dict, curve: str, level: str):
    """(z list, censor list, basis) of a level's exported crossing draws on one curve: for the average-rate
    curve every draw when the file carries them, else every tenth; for the median-task curve every draw."""
    if curve == "average":
        blk = _alias(result.get("draws_avg_full") or {}, level)
        if blk and blk.get("z"):
            return blk["z"], blk["censor"], "full"
        blk = _alias(result.get("draws_avg") or {}, level)
        if blk and blk.get("z"):
            return blk["z"], blk["censor"], "thinned"
        return None, None, None
    blk = _alias(result.get("draws") or {}, level)
    if blk and blk.get("z"):
        return blk["z"], blk["censor"], "full"
    return None, None, None


def _quantile_linear(arr_sorted, pct):
    """The linear-interpolation quantile at ``pct`` percent of a sorted list."""
    if not arr_sorted:
        return None
    k = (len(arr_sorted) - 1) * pct / 100.0
    fl = int(math.floor(k))
    ce = min(fl + 1, len(arr_sorted) - 1)
    return arr_sorted[fl] + (arr_sorted[ce] - arr_sorted[fl]) * (k - fl)


def censored_read(z, censor, grid_lo, grid_hi) -> dict | None:
    """The all-draws median and 10th/90th percentiles of a crossing with its censored draws beyond the ends."""
    n = len(z)
    if n == 0 or len(censor) != n:
        return None
    s_lo = sum(1 for c in censor if c < 0) / n
    s_hi = sum(1 for c in censor if c > 0) / n
    unc = sorted(float(v) for v, c in zip(z, censor) if c == 0 and v is not None and v == v)

    def edge(alpha):
        if alpha <= s_lo:
            return float(grid_lo)
        if alpha >= 1 - s_hi:
            return float(grid_hi)
        return _quantile_linear(unc, 100.0 * (alpha - s_lo) / (1 - s_lo - s_hi))

    med_cond = _quantile_linear(unc, 50.0)
    return {"med": edge(0.50), "lo": edge(0.10), "hi": edge(0.90), "s_lo": s_lo, "s_hi": s_hi,
            "n_draws": n, "n_uncensored": len(unc), "med_conditional": med_cond}


def status_of(s_lo, s_hi) -> str:
    """point, or a bound at the end beyond which more than half the draws lie."""
    if s_lo > BOUND_SHARE:
        return STATUS_BELOW
    if s_hi > BOUND_SHARE:
        return STATUS_ABOVE
    return STATUS_POINT


def censored_edge(s_lo, s_hi, status) -> str:
    if status != STATUS_POINT:
        return ""
    if s_lo >= EDGE_SHARE and s_hi >= EDGE_SHARE:
        return "both"
    if s_lo >= EDGE_SHARE:
        return "lower"
    if s_hi >= EDGE_SHARE:
        return "upper"
    return ""


def level_read(result: dict, curve: str, level: str) -> dict:
    """One level on one curve: z, lo, hi, status, bound_z, shares, the conditional median, the draws basis.

    The read is over every exported draw when the file carries them all for the level; when it carries only
    every tenth draw, or none, the engine's own summary of the level (computed over the full chain) is the
    number, with the status from its censored shares."""
    grid = result.get("grid") or {}
    glo, ghi = grid.get("lo"), grid.get("hi")
    z, cen, basis = draws_of(result, curve, level)
    if z is not None and basis == "full" and glo is not None and ghi is not None:
        r = censored_read(z, cen, glo, ghi)
        if r is not None:
            st = status_of(r["s_lo"], r["s_hi"])
            bound_z = glo if st == STATUS_BELOW else ghi if st == STATUS_ABOVE else None
            return {"z": r["med"], "lo": r["lo"], "hi": r["hi"], "status": st, "bound_z": bound_z,
                    "p_left_censored": r["s_lo"], "p_right_censored": r["s_hi"], "z_conditional": r["med_conditional"],
                    "censored_edge": censored_edge(r["s_lo"], r["s_hi"], st), "basis": basis, "n_draws": r["n_draws"]}
    blocks = result.get("estimands_avg") if curve == "average" else result.get("estimands")
    blk = _alias(blocks or {}, level)
    if not blk:
        return {"z": None, "lo": None, "hi": None, "status": STATUS_NA, "bound_z": None, "p_left_censored": None,
                "p_right_censored": None, "z_conditional": None, "censored_edge": "", "basis": None, "n_draws": 0}
    s_lo, s_hi = float(blk.get("p_left_censored") or 0), float(blk.get("p_right_censored") or 0)
    st = status_of(s_lo, s_hi)
    cri = blk.get("cri80_z") or [None, None]
    med = blk.get("median_z")
    if st == STATUS_BELOW and glo is not None:
        med = glo
    if st == STATUS_ABOVE and ghi is not None:
        med = ghi
    return {"z": med, "lo": cri[0], "hi": cri[1], "status": st,
            "bound_z": glo if st == STATUS_BELOW else ghi if st == STATUS_ABOVE else None,
            "p_left_censored": s_lo, "p_right_censored": s_hi, "z_conditional": blk.get("median_z_conditional", blk.get("median_z")),
            "censored_edge": censored_edge(s_lo, s_hi, st), "basis": "summary", "n_draws": int(blk.get("n_draws") or 0)}


def level_from_table(result: dict, curve: str, level_fail_rate: float) -> dict:
    """A crossing at any failure-rate level, read from the fit's level table between the two table levels that
    bracket it, linear in the logit of the level, with the bound rule; exact when the level is a table member."""
    lt = result.get("levels_table_avg" if curve == "average" else "levels_table") or {}
    L = [float(x) for x in (lt.get("levels_fail_rate") or [])]
    grid = result.get("grid") or {}
    glo, ghi = grid.get("lo"), grid.get("hi")
    out = {"z": None, "lo": None, "hi": None, "status": STATUS_NA, "p_left_censored": None, "p_right_censored": None}
    if not L:
        return out
    i = bisect.bisect_left(L, level_fail_rate - 1e-12)
    if i < len(L) and abs(L[i] - level_fail_rate) < 1e-9:
        lo_i, hi_i, w = i, i, 0.0
    elif i == 0 or i >= len(L):
        return out
    else:
        lo_i, hi_i = i - 1, i
        lg = lambda p: math.log(p / (1.0 - p))
        w = (lg(level_fail_rate) - lg(L[lo_i])) / (lg(L[hi_i]) - lg(L[lo_i]))

    def ip(name, nd=5):
        col = lt.get(name) or []
        if len(col) <= hi_i or col[lo_i] is None or col[hi_i] is None:
            return None
        return round(float(col[lo_i]) + w * (float(col[hi_i]) - float(col[lo_i])), nd)

    med, lo, hi, pl, pr = ip("median_z"), ip("cri80_lo_z"), ip("cri80_hi_z"), ip("p_left_censored"), ip("p_right_censored")
    st = status_of(pl or 0, pr or 0)
    if st == STATUS_BELOW and glo is not None:
        med = round(float(glo), 5)
    if st == STATUS_ABOVE and ghi is not None:
        med = round(float(ghi), 5)
    return {"z": med, "lo": lo, "hi": hi, "status": st, "p_left_censored": pl, "p_right_censored": pr}


def _summary3(blk):
    blk = blk or {}
    c = blk.get("cri80") or [None, None]
    return blk.get("median"), c[0], c[1]


def row_for(result: dict, arm: str, name: str | None = None, gates: dict | None = None,
            source_sha256_12: str | None = None) -> dict:
    """The crossings table's row for one arm."""
    cfg = result.get("config") or {}
    grid = result.get("grid") or {}
    row = {"arm": arm, "model_name": name or arm}
    basis = None
    for lv in LEVELS_OF_RECORD:
        r = level_read(result, "average", lv)
        basis = basis or r["basis"]
        for s in ("z", "lo", "hi", "status", "bound_z", "p_left_censored", "p_right_censored", "z_conditional", "censored_edge"):
            row[f"{lv}_{s}"] = r[s]
    mt = level_read(result, "median_task", "d99")
    for s in ("z", "lo", "hi", "status", "p_left_censored", "p_right_censored"):
        row[f"d99_median_task_{s}"] = mt[s]
    for lv in EXTRA_LEVELS:
        r = level_read(result, "average", lv)
        for s in ("z", "lo", "hi", "status", "p_left_censored", "p_right_censored"):
            row[f"{lv}_{s}"] = r[s]
    he = level_from_table(result, "average", HARD_END_LEVEL[1])
    for s in ("z", "lo", "hi", "status", "p_left_censored", "p_right_censored"):
        row[f"d1_{s}"] = he[s]
    row["tau"], row["tau_lo"], row["tau_hi"] = _summary3(result.get("tau"))
    row["rho"], row["rho_lo"], row["rho_hi"] = _summary3(result.get("rho_icc") or result.get("rho"))
    row["ell_median"] = (result.get("ell") or {}).get("median")
    g = (gates or {}).get(arm) or {}
    row["crossing_rhat_d50"] = g.get("crossing_rhat_d50")
    row["crossing_ess_d50"] = g.get("crossing_ess_d50")
    row["crossing_rhat_d99"] = g.get("crossing_rhat_d99")
    row["crossing_ess_d99"] = g.get("crossing_ess_d99")
    row["divergences"] = g.get("divergences", (result.get("diagnostics") or {}).get("num_divergences"))
    row["gate"] = g.get("gate")
    row["gates_failed"] = ";".join(g.get("gates_failed") or []) if g else None
    row["n_tasks"] = cfg.get("n_tasks")
    row["grid_lo_z"], row["grid_hi_z"] = grid.get("lo"), grid.get("hi")
    row["m_basis"], row["hsgp_L"] = cfg.get("m_basis"), cfg.get("hsgp_L")
    row["crossing_rule"] = cfg.get("crossing_rule") or "first"
    row["draws_basis"] = basis
    row["engine_sha256_12"] = str(cfg.get("engine_sha256") or "")[:12]
    row["source_sha256_12"] = source_sha256_12
    return row


def table_for(results_dir, names: dict | None = None, gates: dict | None = None, pattern="posterior_summary_*.json") -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(results_dir, pattern))):
        result = load_result(path)
        arm = arm_of(path)
        sha12 = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
        rows.append(row_for(result, arm, (names or {}).get(arm), gates, sha12))
    return rows


def rows_from_files(paths, names=None, gates=None) -> list[dict]:
    rows = []
    for path in paths:
        result = load_result(path)
        arm = arm_of(path)
        sha12 = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
        rows.append(row_for(result, arm, (names or {}).get(arm), gates, sha12))
    return rows


# ------------------------------------------------------------------------------------------------- writing
RULE_IN_WORDS = {
    "curve": "capability D50 and reliability D99 are the crossings of the average-rate curve (the share of attempts "
             "expected to fail at a difficulty) at one half and one in a hundred; the median-task D99 beside",
    "number": "the median over every exported draw of the crossing, a draw below the easiest task counted beyond the "
              "easy end and one beyond the hardest task beyond the hard end; the interval the 10th and 90th "
              "percentiles taken the same way",
    "status": "point, or bound below / bound above when more than half of the draws lie beyond that end (the value "
              "then the easiest or the hardest task used); every arm has a number at every level",
    "levels": "D97, D95 and D90 are the same curve's crossings at 3%, 5% and 10% failure; D1 (99% failure) is read "
              "from the level table between the bracketing levels, linear in the logit of the level",
}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v) if math.isfinite(v) else ""
    return v


def write_table(rows: list[dict], out_dir, label: str | None = None) -> tuple[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cp, jp = out_dir / "crossings.csv", out_dir / "crossings.json"
    with open(cp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in COLUMNS})
    sha = hashlib.sha256(cp.read_bytes()).hexdigest()
    jp.write_text(json.dumps({"label": label or out_dir.name, "n_arms": len(rows), "rule": RULE_IN_WORDS,
                              "csv_sha256": sha, "rows": rows}, indent=1) + "\n", encoding="utf-8")
    return str(cp), sha


def load_crossings(path) -> list[dict]:
    """Read a crossings table (csv or json), this one or an older one, into rows with this table's column names."""
    path = Path(path)
    if path.suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    else:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        new = {}
        for k, v in r.items():
            new[OLD_NAMES.get(k, k)] = v
        if "arm" not in new and "model_id" in r:
            new["arm"] = r["model_id"]
        out.append(new)
    return out


def status_kind(status) -> str:
    """Normalise a status string, this table's or an older one's, to point / bound below / bound above / unavailable."""
    s = str(status or "").lower()
    if s.startswith("bound") and "below" in s:
        return STATUS_BELOW
    if s.startswith("bound") and "above" in s:
        return STATUS_ABOVE
    if s.startswith("point"):
        return STATUS_POINT
    if s.startswith("unresolved"):
        return STATUS_POINT
    return STATUS_NA if not s else s


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit crossings", description="the crossings table from the engine's results")
    ap.add_argument("--results", required=True, help="the directory of posterior_summary_<arm>.json files")
    ap.add_argument("--out-dir", required=True, help="where crossings.csv and crossings.json go")
    ap.add_argument("--names", default=None, help="a JSON map from arm id to the printed name")
    ap.add_argument("--gates", default=None, help="gates.json from `cmr fit gates`, merged per arm")
    ap.add_argument("--label", default=None, help="the fit's name for the json header")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    names = json.loads(Path(args.names).read_text(encoding="utf-8")) if args.names else None
    gates = json.loads(Path(args.gates).read_text(encoding="utf-8")).get("arms") if args.gates else None
    rows = table_for(args.results, names, gates)
    cp, sha = write_table(rows, args.out_dir, args.label)
    n_point = sum(1 for r in rows if r["d99_status"] == STATUS_POINT)
    print(f"crossings: {len(rows)} arms, D99 point on {n_point}; wrote {cp} (sha256 {sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

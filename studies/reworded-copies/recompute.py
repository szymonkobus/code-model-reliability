#!/usr/bin/env python3
"""Recomputes the reworded-copies comparison from the published cells and checks the fold of the identical copies.

Reads ``sets.json`` (the folded copies), ``attribution.jsonl`` (which wave 2 tasks are reworded copies and of which wave 1
task), the published fit's ``cells.csv`` and ``axis.csv``, and this study's ``copies.csv``. Checks that the folded copies
are members of no set and that their parents' published cells carry the copies' attempts; then, for every reworded copy
in the published fit and every arm holding both the copy's and the parent's cell, compares the two pass rates: the
correlation, the share of pairs an exact test cannot tell apart, the share that differ beyond doubt, and the copy's
difficulty against the parent's on the published axis. Exits 1 when a check fails.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

HERE = Path(__file__).resolve().parent
INDISTINGUISHABLE = 0.05   # an exact test above this level cannot tell the two pass counts apart
CLEAR = 0.001              # below this level the two pass counts differ beyond doubt
INFORMATIVE = (0.05, 0.95)   # a pair is informative when the parent's pass rate is neither saturated nor floored
ONE_STEP = 1.0             # one step of difficulty: one logit unit, from a coin-flip task to one failing about three in four


def parent_of(copy_id: str) -> str:
    return copy_id.split("~")[0]


def pearson(xs, ys) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx * syy) ** 0.5 if sxx > 0 and syy > 0 else float("nan")


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    sets = tables.read_sets(data)
    fit = tables.fit_dir(data, args.fit)
    cells = tables.read_cells(fit)
    axis = tables.read_axis(fit)
    attribution = tables.read_attribution(data)
    copies_table = tables.read_csv(HERE / "copies.csv")
    rep = tables.Report()

    # 1. the fold: identical copies are not members; their attempts sit in the parent's published cell
    folded = [c for lst in sets["folded_twins"].values() for c in lst]
    all_members = {t for key in ("wave_1", "wave_2", "wave_2_parked") for t in tables.set_members(sets, key)}
    rep.say(f"published fit: {fit.name}; folded copies in sets.json: {len(folded)} ({ {k: len(v) for k, v in sets['folded_twins'].items()} })")
    rep.check(not any(c in all_members for c in folded), "no folded copy is a member of any set")
    identical_in_table = {r["copy"] for r in copies_table if r["identical"] == "true"}
    rep.check(identical_in_table == set(folded), f"the copies the study found word-identical ({len(identical_in_table)}) are the folded copies")
    arms = sorted({a for a, _ in cells})
    modal_attempts = {}
    wave1 = set(tables.set_members(sets, "wave_1"))
    for arm in arms:
        counts = Counter(n for (a, t), (f, n) in cells.items() if a == arm and t in wave1)
        modal_attempts[arm] = counts.most_common(1)[0][0] if counts else None
    extra = 0; parents_seen = 0
    for c in folded:
        p = parent_of(c)
        rows = [(a, n) for (a, t), (f, n) in cells.items() if t == p]
        if rows:
            parents_seen += 1
            if any(n > modal_attempts[a] for a, n in rows):
                extra += 1
    rep.say(f"parents of folded copies in the published cells: {parents_seen}; parents whose cells carry more than the arm's usual attempts: {extra}")

    # 2. copy against parent, pass rate by pass rate, over the arms holding both cells
    copies = [r for r in attribution if r.get("kind") == "twin" and r.get("set") == "wave_2" and r.get("kept")]
    pairs = []
    for r in copies:
        copy_id, parent = r["task_id"], r["source_task"]
        for arm in arms:
            if (arm, copy_id) in cells and (arm, parent) in cells:
                fc, nc = cells[(arm, copy_id)]
                fp_, np_ = cells[(arm, parent)]
                pc, pp = (nc - fc) / nc, (np_ - fp_) / np_
                p = tables.fisher_exact_p(nc - fc, nc, np_ - fp_, np_)
                pairs.append({"copy": copy_id, "arm": arm, "p_copy": pc, "p_parent": pp, "p": p,
                              "informative": INFORMATIVE[0] <= pp <= INFORMATIVE[1]})
    rep.say()
    rep.say(f"reworded copies in the published fit: {len(copies)}; pairs (copy and parent held by one arm): {len(pairs)} over {len({q['arm'] for q in pairs})} arms")
    inf = [q for q in pairs if q["informative"]]
    for name, group in (("all pairs", pairs), ("informative pairs", inf)):
        if not group:
            continue
        r = pearson([q["p_parent"] for q in group], [q["p_copy"] for q in group])
        indist = sum(q["p"] >= INDISTINGUISHABLE for q in group) / len(group)
        clear = sum(q["p"] < CLEAR for q in group) / len(group)
        gap = statistics.mean(abs(q["p_copy"] - q["p_parent"]) for q in group) * 100
        rep.say(f"  {name:<18} n={len(group):<6} correlation {r:.3f}; indistinguishable {indist:.1%}; differ beyond doubt {clear:.1%}; mean gap {gap:.1f} points")
    clear_by_copy = Counter(q["copy"] for q in pairs if q["p"] < CLEAR)
    rep.say(f"  copies with a pair that differs beyond doubt: {len(clear_by_copy)}; with three or more such pairs: {sum(1 for v in clear_by_copy.values() if v >= 3)}")

    # 3. difficulty: the copy's position against the parent's on the published axis
    dz = []
    for r in copies:
        if r["task_id"] in axis and r["source_task"] in axis:
            dz.append((axis[r["task_id"]], axis[r["source_task"]]))
    if dz:
        rep.say()
        rep.say(f"difficulty on the published axis, {len(dz)} copies: correlation {pearson([b for a, b in dz], [a for a, b in dz]):.3f}; "
                f"median shift {statistics.median(a - b for a, b in dz):+.2f} steps; more than one step away: {sum(abs(a - b) > ONE_STEP for a, b in dz)}; "
                f"more than half a step: {sum(abs(a - b) > ONE_STEP / 2 for a, b in dz)}")

    # 4. the study's own re-run scores, as shipped in copies.csv
    scores = [float(r["rerun_score"]) for r in copies_table if r["rerun_score"] not in ("", "nan")]
    reworded = [float(r["rerun_score"]) for r in copies_table if r["identical"] == "false" and r["rerun_score"] not in ("", "nan")]
    identical = [float(r["rerun_score"]) for r in copies_table if r["identical"] == "true" and r["rerun_score"] not in ("", "nan")]
    rep.say()
    rep.say(f"re-run score (copies.csv): {len(scores)} copies scored; median {statistics.median(scores):.2f}; reworded only {statistics.median(reworded):.2f}; "
            f"word-identical control {statistics.median(identical):.2f} over {len(identical)}")
    added = sum(max(0.0, min(1.0, 1 - s)) / (1 + max(0.0, min(1.0, s))) for s in reworded) if reworded else 0.0
    rep.say(f"independent tasks' worth of the reworded copies, by (1 - s) / (1 + s) summed over scores clipped to [0, 1]: {added:.0f} of {len(reworded)}")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())

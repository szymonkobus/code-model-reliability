#!/usr/bin/env python3
"""Recomputes the rare-failure frame from the published cells and the hand-read categories from this study's cases.

Reads this study's ``cases.csv`` (one row per hand-read case: an arm on a wave 1 task it solves most of the time but
fails 1 to 10 times in 128), the published fit's ``cells.csv``, ``sets.json`` and the published labels. Prints the
cases by category, as cases and as failing attempts, the share of the failing attempts that are the model's own and
the share that trace to the tests or the judge; rebuilds the frame (1 to 10 failures of 128 on a wave 1 task) from the
published cells for every arm the cases cover and reports how the two agree; and gives the share of cases whose task
carries a defect label today. Exits 1 when a check fails.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

HERE = Path(__file__).resolve().parent
ATTEMPTS = 128
RANGE = (1, 10)
TEST_SIDE = {"harness-artifact"}            # the tests or the judge at fault, confirmed case by case
EXTRACTION_SIDE = {"format-extraction"}     # the model's code was right; the step that takes it out of the reply lost it


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    fit = tables.fit_dir(data, args.fit)
    cells = tables.read_cells(fit)
    sets = tables.read_sets(data)
    labels = tables.read_labels(data)
    cases = tables.read_csv(HERE / "cases.csv")
    rep = tables.Report()

    kept_w1 = set(tables.set_members(sets, "wave_1"))
    wave1 = kept_w1 | set(sets["wave_1_originals_excluded_by_label"]["ids"])   # every reviewed wave 1 task: the cases were read before the audit excluded any
    rep.say(f"published fit: {fit.name}; cases: {len(cases)} over {len({r['arm'] for r in cases})} arms")
    rep.check(all(RANGE[0] <= int(r["failures"]) <= RANGE[1] and int(r["attempts"]) == ATTEMPTS and r["task_id"] in wave1 for r in cases),
              "every case is a wave 1 task with 1 to 10 failures of 128")
    on_excluded = sum(1 for r in cases if r["task_id"] not in kept_w1)
    rep.say(f"cases on a wave 1 task the audit later excluded from the measured set: {on_excluded}")
    by_cat_cases = Counter(r["category"] for r in cases)
    by_cat_fails = Counter()
    for r in cases:
        by_cat_fails[r["category"]] += int(r["failures"])
    total_fails = sum(by_cat_fails.values())
    rep.say()
    rep.say(f"{'category':<24}{'cases':>8}{'share':>9}{'failing attempts':>18}{'share':>9}")
    for cat, n in by_cat_cases.most_common():
        rep.say(f"{cat:<24}{n:>8}{n / len(cases):>9.1%}{by_cat_fails[cat]:>18}{by_cat_fails[cat] / total_fails:>9.1%}")
    test_side = sum(by_cat_fails[c] for c in TEST_SIDE) / total_fails
    extraction = sum(by_cat_fails[c] for c in EXTRACTION_SIDE) / total_fails
    rep.say(f"failing attempts: {total_fails}; the model's own {1 - test_side - extraction:.1%}; the extraction step's {extraction:.1%}; the tests' or the judge's {test_side:.1%}")

    # the frame rebuilt from the published cells, per arm the cases cover
    rep.say()
    arms = sorted({r["arm"] for r in cases})
    arms_in_fit = {a for a, _ in cells} & set(arms)
    frame = set(); pooled = 0
    for (a, t), (f, n) in cells.items():
        if a in arms_in_fit and t in kept_w1:
            if n != ATTEMPTS:
                pooled += 1   # the parent of a folded copy carries the copy's attempts too; left aside
            elif RANGE[0] <= f <= RANGE[1]:
                frame.add((a, t))
    still = left = no_cell = arm_out = 0
    for r in cases:
        key = (r["arm"], r["task_id"])
        if r["arm"] not in arms_in_fit:
            arm_out += 1
        elif key not in cells:
            no_cell += 1
        elif key in frame:
            still += 1
        else:
            left += 1
    table_keys = {(r["arm"], r["task_id"]) for r in cases}
    cells_only = len(frame - table_keys)
    rep.say(f"arms of the cases in the published fit: {len(arms_in_fit)} of {len(arms)}; cases of the other arms: {arm_out}")
    rep.say(f"cases whose task is not in the published fit (excluded by the audit): {no_cell}; whose cell pools a folded copy: left aside ({pooled} such cells)")
    rep.say(f"the frame rebuilt from the published cells: {len(frame)} cells in the range; cases still in it {still}; cases whose cell has since left the range {left}; "
            f"cells in the range with no case {cells_only}")
    rep.check(still > 0.8 * (still + left), "at least four in five comparable cases still sit in the range on the published cells")

    # defect labels on the cases' tasks, at the annotation and today
    then = sum(1 for r in cases if r["audit_label"] in ("underspecification", "contradiction"))
    now = sum(1 for r in cases if labels.get(r["task_id"], {}).get("label") in ("underspecification", "contradiction"))
    tasks = {r["task_id"] for r in cases}
    now_tasks = sum(1 for t in tasks if labels.get(t, {}).get("label") in ("underspecification", "contradiction"))
    rep.say()
    rep.say(f"cases on a task with a defect label: {then} at the annotation, {now} by the published labels; "
            f"tasks the cases touch: {len(tasks)}, with a defect label today {now_tasks} ({now_tasks / len(tasks):.0%})")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())

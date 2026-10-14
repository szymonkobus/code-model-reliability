#!/usr/bin/env python3
"""Recomputes what the typing-import cleaning changed and checks the published gpt-5 cells against the cleaned counts.

Reads this study's ``carriers.csv`` (every wave 1 attempt of the two gpt-5 arms that carried an impossible typing
import, with its verdict before and after the cleaning) and ``per_task.csv`` (per arm and task, the failures before
and after), the published fit's ``cells.csv`` and ``data/tasks/wave-1/kept_tasks.json``. Prints the carriers and the
verdicts that changed per arm, on all wave 1 tasks and on the kept ones, and compares the published cell of every
wave 1 task of the two arms with the cleaned failure count. Exits 1 when a check fails.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("gpt-5-mini_batch", "gpt-5-nano_batch")
# What the cleaning changed, as this study recorded it: verdicts fail -> pass on all 542 wave 1 tasks and on the 430 kept
RECORD = {"gpt-5-mini_batch": {"carriers": 222, "changed_all": 169, "changed_kept": 137},
          "gpt-5-nano_batch": {"carriers": 82, "changed_all": 60, "changed_kept": 55}}
# The three wave 1 tasks where a later correction (a float meeting an integer compares within a relative tolerance) moved
# verdicts of these two arms after the cleaning's counts were taken; their published cells differ from the cleaned count.
NUMERIC_TOLERANCE_TASKS = {"Mbpp/14", "Mbpp/458", "Mbpp/93"}


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    fit = tables.fit_dir(data, args.fit)
    cells = tables.read_cells(fit)
    kept = set(tables.read_kept_wave1(data)["tasks"])
    carriers = tables.read_csv(HERE / "carriers.csv")
    per_task = tables.read_csv(HERE / "per_task.csv")
    rep = tables.Report()

    rep.say(f"published fit: {fit.name}")
    rep.say(f"{'arm':<20}{'carriers':>10}{'changed, all tasks':>20}{'changed, kept tasks':>21}{'attempts (542 tasks)':>22}{'share changed':>15}")
    for arm in ARMS:
        rows = [r for r in carriers if r["arm"] == arm]
        changed_all = sum(1 for r in rows if r["verdict_before"] == "fail" and r["verdict_after"] == "pass")
        changed_kept = sum(1 for r in rows if r["verdict_before"] == "fail" and r["verdict_after"] == "pass" and r["task_id"] in kept)
        attempts = sum(int(r["attempts"]) for r in per_task if r["arm"] == arm)
        rep.say(f"{arm:<20}{len(rows):>10}{changed_all:>20}{changed_kept:>21}{attempts:>22}{changed_all / attempts:>15.3%}")
        rec = RECORD[arm]
        rep.check((len(rows), changed_all, changed_kept) == (rec["carriers"], rec["changed_all"], rec["changed_kept"]),
                  f"{arm}: carriers {len(rows)}, changed {changed_all} on all tasks and {changed_kept} on the kept tasks equal the study's record")
    still = Counter(r["note"] for r in carriers if r["verdict_after"] == "fail")
    rep.say(f"carriers still failing after the cleaning, by what remained: {dict(still)}")
    names = Counter(n for r in carriers for n in r["removed_names"].split())
    rep.say(f"names removed, by name: {dict(names.most_common())}")

    rep.say()
    for arm in ARMS:
        same = missing = folded = 0
        differing = []
        for r in per_task:
            if r["arm"] != arm:
                continue
            key = (arm, r["task_id"])
            if key not in cells:
                missing += 1
                continue
            if cells[key][1] != int(r["attempts"]):
                folded += 1   # the published cell pools a folded copy's attempts into the parent's; the counts are not comparable
                continue
            if cells[key][0] == int(r["failures_after"]):
                same += 1
            else:
                differing.append(f"{r['task_id']} cleaned {r['failures_after']} of {r['attempts']}, published {cells[key][0]} of {cells[key][1]}")
        rep.say(f"{arm}: published cells equal to the cleaned count on {same} wave 1 tasks; differ on {len(differing)}; "
                f"parents of a folded copy, pooled, not compared {folded}; not in the published fit {missing} (the tasks not kept)")
        for e in differing:
            rep.say(f"   differs: {e}")
        rep.check(all(e.split()[0] in NUMERIC_TOLERANCE_TASKS for e in differing),
                  f"{arm}: every differing task is one the later numeric-tolerance correction touched")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())

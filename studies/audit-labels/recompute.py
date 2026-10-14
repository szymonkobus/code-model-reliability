#!/usr/bin/env python3
"""Recomputes the task audit's counts from the published labels and checks the kept sets against them.

Reads ``data/tasks/labels/labels.jsonl``, ``labels/label_history.jsonl``, ``sets.json`` and ``wave-1/kept_tasks.json``.
Prints, per set, the number of tasks under each label and the kept count; checks that every member of every set has a
label, that a member is kept exactly when its label is a keep label, that the kept lists hash to the values ``sets.json``
records, that the not-kept lists name the right reasons, and that every task's newest label change ends at its current
label. Exits 1 when a check fails.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

SETS = (("wave_1", "wave 1"), ("wave_2", "wave 2"), ("wave_2_parked", "wave 2 parked"))
LABELS = ("regular", "tricky", "underspecification", "contradiction")


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    sets = tables.read_sets(data)
    labels = tables.read_labels(data)
    changes = tables.read_label_history(data)
    kept_w1 = tables.read_kept_wave1(data)
    rep = tables.Report()

    keep_labels = set(sets["label_rule"]["keep_labels"])
    excluded = sets["wave_1_originals_excluded_by_label"]
    rep.say(f"keep labels: {sorted(keep_labels)}; labelled tasks in the file: {len(labels)}")
    rep.say()
    rep.say(f"{'set':<16}{'reviewed':>9}" + "".join(f"{lab:>20}" for lab in LABELS) + f"{'kept':>7}{'kept share':>12}")
    total_kept = 0
    for key, name in SETS:
        members = tables.set_members(sets, key)
        kept_list = tables.set_kept(sets, key)
        # wave 1's members of record are its kept tasks; the originals the audit excluded are listed beside them, so the
        # reviewed set is both lists together; wave 2 and wave 2 parked list every member, kept or not
        reviewed = members + list(excluded["ids"]) if key == "wave_1" else members
        counts = Counter(labels[t]["label"] for t in reviewed if t in labels)
        missing = [t for t in reviewed if t not in labels]
        kept_by_rule = [t for t in reviewed if t in labels and labels[t]["label"] in keep_labels]
        rep.say(f"{name:<16}{len(reviewed):>9}" + "".join(f"{counts.get(lab, 0):>20}" for lab in LABELS)
                + f"{len(kept_by_rule):>7}{len(kept_by_rule) / len(reviewed):>12.1%}")
        rep.check(not missing, f"{name}: every reviewed task has a label ({len(missing)} missing)")
        rep.check(set(kept_by_rule) == set(kept_list), f"{name}: the kept list equals the reviewed tasks whose label is a keep label")
        rep.check(len(kept_list) == sets["sets"][key]["kept_count"] and len(members) == sets["sets"][key]["count"],
                  f"{name}: the recorded counts ({sets['sets'][key]['count']} members, {sets['sets'][key]['kept_count']} kept) equal the lists")
        rep.check(tables.sha256_sorted(kept_list) == sets["sets"][key]["sha256_sorted_kept"], f"{name}: the kept list's hash equals the recorded one")
        rep.check(tables.sha256_sorted(members) == sets["sets"][key]["sha256_sorted_members"], f"{name}: the member list's hash equals the recorded one")
        if key != "wave_2_parked":
            total_kept += len(kept_list)
    rep.say()
    rep.check(total_kept == sets["wave_1_plus_2"]["kept_count"], f"wave 1+2 kept = {total_kept} (the measured set; recorded {sets['wave_1_plus_2']['kept_count']})")
    rep.check(set(kept_w1["tasks"]) == set(tables.set_kept(sets, "wave_1")) and kept_w1["sha256_sorted"] == tables.sha256_sorted(kept_w1["tasks"]),
              f"wave 1's kept_tasks.json lists the same {kept_w1['count']} tasks and hashes to its recorded value")

    # the lists of tasks not kept, with their reasons
    by_label = Counter(labels[t]["label"] for t in excluded["ids"] if t in labels)
    rep.check(len(excluded["ids"]) == excluded["count"] and dict(by_label) == dict(excluded["by_label"]) and not (set(by_label) & keep_labels),
              f"wave 1: {excluded['count']} reviewed originals excluded, by label {dict(by_label)} (recorded {dict(excluded['by_label'])})")
    for key, name in SETS[1:]:
        rows = sets[f"{key}_members_not_kept"]
        kept_set = set(tables.set_kept(sets, key))
        # a reason reads "<label> (the label rule: ...)": the label is its first word
        rep.check(all(labels[r["task_id"]]["label"] == r["reason"].split(" (")[0] and r["task_id"] not in kept_set for r in rows),
                  f"{name}: the {len(rows)} members not kept carry their label as the reason")

    # the label changes: the newest change of a task ends at its current label; crossings of the keep boundary
    def day(r: dict) -> str:   # the day a change took effect, or the day it was recorded where that is all a row carries
        return r.get("day_applied") or r.get("day_recorded") or ""

    newest: dict[str, dict] = {}
    for r in changes:
        key = r["task_id"]
        if key not in newest or day(r) >= day(newest[key]):
            newest[key] = r
    agree = sum(1 for t, r in newest.items() if t in labels and labels[t]["label"] == r["label_after"])
    rep.check(agree == len(newest), f"label history: {len(changes)} rows on {len(newest)} tasks; the newest row ends at the current label for {agree}")
    moves = [r for r in changes if r["label_before"] and r["label_after"] and r["label_before"] != r["label_after"]]
    confirmations = sum(1 for r in changes if r["label_before"] and r["label_before"] == r["label_after"])
    first = sum(1 for r in changes if not r["label_before"])
    crossings = sum(1 for r in moves if (r["label_before"] in keep_labels) != (r["label_after"] in keep_labels))
    by_set = Counter(r["set"] for r in moves)
    rep.say(f"label changes (a label moved): {len(moves)}, by set {dict(by_set)}; across the keep boundary: {crossings}; "
            f"confirmations (a reading that kept the label): {confirmations}; first labels: {first}")
    in_sets = sum(1 for r in changes if r["set"] != "none")
    rep.say(f"history rows on members of the three sets: {in_sets}; on tasks in no set: {len(changes) - in_sets}")

    # the published fit against the kept sets: a fit is cut from the kept set of its day, so a task set aside later stays in it
    fit = tables.fit_dir(data, args.fit)
    fit_tasks = {t for _, t in tables.read_cells(fit)}
    kept_12 = set(tables.set_kept(sets, "wave_1")) | set(tables.set_kept(sets, "wave_2"))
    set_aside = sorted(fit_tasks - kept_12)
    by_label_aside = Counter(labels[t]["label"] if t in labels else "no label" for t in set_aside)
    rep.say()
    rep.say(f"published fit {fit.name}: {len(fit_tasks)} tasks; kept wave 1+2 tasks of record: {len(kept_12)}; in the fit and since set aside: "
            f"{len(set_aside)} ({dict(by_label_aside)}); kept and not in the fit: {len(kept_12 - fit_tasks)}")
    numbers = data.parent / "docs" / "numbers.json"
    if numbers.exists():
        n = tables.read_json(numbers)
        if all(k in n for k in ("n_tasks_fit", "n_kept_12", "tasks_fit_not_kept")):
            aside = n["tasks_fit_not_kept"]   # a count, or the list of the tasks set aside with their set and label
            aside_ids = sorted(r["task_id"] if isinstance(r, dict) else r for r in aside) if isinstance(aside, list) else None
            agree = (n["n_tasks_fit"], n["n_kept_12"]) == (len(fit_tasks), len(kept_12)) and (
                aside_ids == set_aside if aside_ids is not None else aside == len(set_aside))
            rep.check(agree, f"docs/numbers.json agrees: n_tasks_fit {n['n_tasks_fit']}, n_kept_12 {n['n_kept_12']}, "
                             f"tasks_fit_not_kept {len(aside) if isinstance(aside, list) else aside}")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())

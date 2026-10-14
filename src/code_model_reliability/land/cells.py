"""Verdicts become cells: failures out of attempts per arm and task.

A cell is one arm on one task. Its attempts are the verdict rows of the task; an attempt passes only when its
base status and its plus status are both ``pass``; the failures are the rest. ``time_limit_fails`` counts the
failures the time limit stopped: an attempt whose suite was killed at the set cap (status ``timeout``), and,
where the per-test outcomes are known, an attempt whose every failing test was a time-out. Every cell names the
judging settings its verdicts carry, so cells judged under different settings are never pooled unmarked.

Reads ``verdicts.json`` (composed by ``judgings`` and ``corrections`` where re-judgings or corrections exist) and
optionally ``per_test.jsonl``; writes ``cells.csv`` with the columns ``arm``, ``task_id``, ``failures``,
``attempts``, ``time_limit_fails``, ``judging``.
"""

from __future__ import annotations

import csv
import pathlib
from typing import Any, Iterable

from .passk import attempt_passed

COLUMNS = ("arm", "task_id", "failures", "attempts", "time_limit_fails", "judging")


def time_limited_attempts(rows: list[dict[str, Any]], per_test_rows: Iterable[dict[str, Any]] | None = None) -> set[int]:
    """The attempt indices of a task whose failure the time limit caused."""
    limited = {i for i, r in enumerate(rows) if "timeout" in (r.get("base_status"), r.get("plus_status"))}
    if per_test_rows:
        by_attempt: dict[int, list[dict[str, Any]]] = {}
        for pr in per_test_rows:
            by_attempt.setdefault(pr["attempt"], []).append(pr)
        for attempt, suites in by_attempt.items():
            if attempt >= len(rows) or attempt_passed(rows[attempt]):
                continue
            failing = [s for s in suites if s.get("status") != "pass"]
            if failing and all(s.get("time_outs") and not any(c in "WE" for c in s.get("outcomes", "")) for s in failing):
                limited.add(attempt)
    return limited


def cells_from_verdicts(arm: str, verdicts: dict[str, Any], judging_id: str,
                        per_test_rows: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One cell per task of one arm's verdict file."""
    per_task: dict[str, list[dict[str, Any]]] = {}
    for pr in per_test_rows or ():
        per_task.setdefault(pr["task_id"], []).append(pr)
    cells = []
    for task_id, rows in verdicts["eval"].items():
        passes = sum(1 for r in rows if attempt_passed(r))
        limited = time_limited_attempts(rows, per_task.get(task_id))
        cells.append({
            "arm": arm,
            "task_id": task_id,
            "failures": len(rows) - passes,
            "attempts": len(rows),
            "time_limit_fails": len(limited),
            "judging": judging_id,
        })
    return cells


def write(cells: Iterable[dict[str, Any]], path: str | pathlib.Path) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        for c in cells:
            w.writerow({k: c[k] for k in COLUMNS})
            n += 1
    return n


def read(path: str | pathlib.Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("failures", "attempts", "time_limit_fails"):
            r[k] = int(r[k])
    return rows

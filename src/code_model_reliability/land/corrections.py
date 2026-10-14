"""Corrections to judged verdicts live in a companion file beside them; a judged file is never rewritten.

Two kinds of correction exist. A **continuation**: an answer the output limit cut was run on to completion and
judged again; the completed answer replaces the cut one as the same attempt, with the verdict of the completed
answer, so the two parts are one attempt and the attempt count does not move. A **verdict** correction: an
attempt judged again under a changed comparison or input rule (a float tolerance, a test input removed) with its
new statuses. Each correction names the attempt it corrects by the hash of the solution text that attempt
holds, so a correction written against other verdicts is refused rather than applied.

Reads ``verdicts.json`` and ``corrections.jsonl`` (one JSON object per correction: ``task_id``, ``attempt``,
``kind``, ``solution_sha256`` of the attempt's current text, ``base_status``, ``plus_status``, ``judging`` (the
settings id the new verdict carries), optionally ``new_solution`` for a continuation and ``note``); writes the
companion file by appending, and returns the composed verdicts without touching the judged file.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Iterable

KINDS = ("continuation", "verdict")
STATUSES = ("pass", "fail", "timeout")


def solution_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_corrections(path: str | pathlib.Path) -> list[dict[str, Any]]:
    path = pathlib.Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append_corrections(rows: Iterable[dict[str, Any]], path: str | pathlib.Path) -> int:
    """Add corrections to the companion file; the judged file beside it is not opened."""
    n = 0
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            check(r)
            fh.write(json.dumps(r, sort_keys=True) + "\n")
            n += 1
    return n


def check(row: dict[str, Any]) -> None:
    if row.get("kind") not in KINDS:
        raise ValueError(f"correction kind must be one of {KINDS}: {row.get('kind')!r}")
    for key in ("task_id", "attempt", "solution_sha256", "base_status", "plus_status", "judging"):
        if key not in row:
            raise ValueError(f"correction lacks {key}")
    if row["base_status"] not in STATUSES or row["plus_status"] not in STATUSES:
        raise ValueError("a correction's statuses must be pass, fail or timeout")
    if row["kind"] == "continuation" and "new_solution" not in row:
        raise ValueError("a continuation carries the completed answer as new_solution")


def apply_corrections(verdicts: dict[str, Any], corrections: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """The composed verdicts, the corrections applied and the corrections refused with their reason. The input
    verdicts are not modified; the composed copy carries per corrected row a ``corrected`` block naming the
    kind, the judging and the previous statuses."""
    composed = json.loads(json.dumps(verdicts))
    applied, refused = [], []
    for row in corrections:
        check(row)
        rows = composed["eval"].get(row["task_id"])
        if rows is None or not (0 <= int(row["attempt"]) < len(rows)):
            refused.append({**row, "reason": "no such attempt"})
            continue
        entry = rows[int(row["attempt"])]
        if solution_sha256(entry.get("solution", "")) != row["solution_sha256"]:
            refused.append({**row, "reason": "the attempt holds a different solution text"})
            continue
        previous = {"base_status": entry.get("base_status"), "plus_status": entry.get("plus_status")}
        if row["kind"] == "continuation":
            entry["solution"] = row["new_solution"]
        entry["base_status"] = row["base_status"]
        entry["plus_status"] = row["plus_status"]
        entry["base_fail_tests"] = row.get("base_fail_tests", [])
        entry["plus_fail_tests"] = row.get("plus_fail_tests", [])
        entry["corrected"] = {"kind": row["kind"], "judging": row["judging"], "previous": previous, "note": row.get("note")}
        applied.append(row)
    from .passk import mean_pass_at_k

    composed["pass_at_k"] = {
        suite: {f"pass@{k}": v for k in (1, 10, 100) if (v := mean_pass_at_k(composed, k, suite)) is not None}
        for suite in ("base", "plus")
    }
    return composed, applied, refused

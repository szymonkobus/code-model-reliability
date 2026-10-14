"""pass@k from the verdicts, with the unbiased estimator.

For a task with ``n`` attempts of which ``c`` passed, pass@k is the probability that at least one of ``k``
attempts drawn without replacement passes: ``1 - C(n - c, k) / C(n, k)``. A table's figure is the mean over
tasks. An attempt passes only when both its statuses are ``pass`` (the base tests and the extended tests);
``suite="base"`` gives the base-tests-only figure for comparison with the harness's first block.

Reads ``verdicts.json`` files; writes ``passk.csv`` with the columns ``arm``, ``set``, ``k``, ``pass_at_k``.
"""

from __future__ import annotations

import csv
import math
import pathlib
from typing import Any, Iterable

KS = (1, 10, 100)


def attempt_passed(row: dict[str, Any], suite: str = "plus") -> bool:
    """The published definition: both statuses ``pass``; ``base`` counts the base tests alone."""
    if suite == "base":
        return row.get("base_status") == "pass"
    return row.get("base_status") == "pass" and row.get("plus_status") == "pass"


def pass_at_k(n: int, c: int, k: int) -> float | None:
    """The unbiased estimator; ``None`` when fewer than ``k`` attempts exist."""
    if n < k:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def task_pass_at_k(verdicts: dict[str, Any], k: int, suite: str = "plus") -> dict[str, float | None]:
    """pass@k per task of one verdict file."""
    out: dict[str, float | None] = {}
    for task_id, rows in verdicts["eval"].items():
        n = len(rows)
        c = sum(1 for r in rows if attempt_passed(r, suite))
        out[task_id] = pass_at_k(n, c, k)
    return out


def mean_pass_at_k(verdicts: dict[str, Any], k: int, suite: str = "plus") -> float | None:
    """The mean over tasks; ``None`` when any task has fewer than ``k`` attempts (the harness's rule)."""
    values = list(task_pass_at_k(verdicts, k, suite).values())
    if not values or any(v is None for v in values):
        return None
    return sum(values) / len(values)  # type: ignore[arg-type]


def table(arm: str, set_name: str, verdicts: dict[str, Any], ks: Iterable[int] = KS) -> list[dict[str, Any]]:
    rows = []
    for k in ks:
        value = mean_pass_at_k(verdicts, k)
        if value is not None:
            rows.append({"arm": arm, "set": set_name, "k": k, "pass_at_k": value})
    return rows


def write(rows: Iterable[dict[str, Any]], path: str | pathlib.Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm", "set", "k", "pass_at_k"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "pass_at_k": f"{r['pass_at_k']:.6f}"})

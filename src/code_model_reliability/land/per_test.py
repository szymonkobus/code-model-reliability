"""How alike an arm's failures on a task are, from the per-test outcomes of its failing attempts.

Two failing attempts with the same outcome string failed the same tests in the same way. Per arm and task this
module counts the failing attempts with a known outcome string, the distinct strings, the share of the commonest
string, the collision probability (the chance two failures drawn without replacement share a string, unbiased)
and the entropy of the distribution in bits (with the Miller-Madow correction beside it).

Reads ``per_test.jsonl`` rows (``task_id``, ``attempt``, ``suite``, ``outcomes``); writes ``per_test_summary.csv``
with the columns ``arm``, ``task_id``, ``n_fails``, ``distinct``, ``modal_share``, ``collision``, ``entropy_bits``,
``entropy_bits_corrected``.
"""

from __future__ import annotations

import csv
import math
import pathlib
from collections import Counter
from typing import Any, Iterable

COLUMNS = ("arm", "task_id", "n_fails", "distinct", "modal_share", "collision", "entropy_bits", "entropy_bits_corrected")


def fingerprint(rows_of_attempt: list[dict[str, Any]]) -> str:
    """One string per failing attempt: the base suite's outcomes, a bar, the plus suite's outcomes."""
    by_suite = {r["suite"]: r["outcomes"] for r in rows_of_attempt}
    return by_suite.get("base", "") + "|" + by_suite.get("plus", "")


def statistics(counts: list[int]) -> dict[str, float]:
    n = sum(counts)
    k = len(counts)
    modal = max(counts) / n
    collision = sum(c * (c - 1) for c in counts) / (n * (n - 1)) if n > 1 else 1.0
    entropy = -sum((c / n) * math.log2(c / n) for c in counts)
    corrected = entropy + (k - 1) / (2 * n * math.log(2))
    return {"n_fails": n, "distinct": k, "modal_share": modal, "collision": collision,
            "entropy_bits": entropy, "entropy_bits_corrected": corrected}


def summarise(arm: str, per_test_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_task: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for r in per_test_rows:
        by_task.setdefault(r["task_id"], {}).setdefault(r["attempt"], []).append(r)
    out = []
    for task_id, attempts in by_task.items():
        prints = Counter(fingerprint(rows) for rows in attempts.values())
        stats = statistics(sorted(prints.values()))
        out.append({"arm": arm, "task_id": task_id, **stats})
    return out


def write(rows: Iterable[dict[str, Any]], path: str | pathlib.Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{r[k]:.6f}" if isinstance(r[k], float) else r[k]) for k in COLUMNS})

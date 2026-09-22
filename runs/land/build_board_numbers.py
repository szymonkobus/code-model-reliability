#!/usr/bin/env python3
"""Recompute results/board/board_numbers.jsonl from the per-attempt verdicts in results/per-attempt/.

For every published arm and source benchmark: the number of tasks, the attempts per task (the most common count), and
pass@k for k = 1, 10 and 100 on the base tests and on both test sets, each as the unbiased estimator
1 - C(n-c, k) / C(n, k) over a task's n attempts with c passes, averaged over the arm's tasks (None when every task
has fewer than k attempts). Run from the repository root; writes the table in place.
"""
import csv
import gzip
import json
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results" / "per-attempt"
OUT = ROOT / "results" / "board" / "board_numbers.jsonl"


def passk(c: int, n: int, k: int):
    if n < k:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def main() -> None:
    rows = [{"schema_version": 3,
             "description": "pass@k per published arm and source benchmark, recomputed from results/per-attempt: for each task the number of attempts c of n passing the base tests (base) and both test sets (plus), the unbiased estimator 1 - C(n-c,k)/C(n,k) averaged over the arm's tasks; k = 1, 10, 100",
             "source": "results/per-attempt/wave1_<benchmark>.csv.gz"}]
    for bench in ("humaneval", "mbpp"):
        acc: dict = {}
        with gzip.open(SRC / f"wave1_{bench}.csv.gz", "rt", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                task = acc.setdefault(row["arm_id"], {}).setdefault(row["task_id"], [0, 0, 0])
                task[0] += 1
                task[1] += row["base_status"] == "pass"
                task[2] += row["plus_status"] == "pass"
        for arm_id in sorted(acc):
            tasks = acc[arm_id]
            out = {"arm_id": arm_id, "benchmark": bench, "n_tasks": len(tasks), "n_samples": Counter(v[0] for v in tasks.values()).most_common(1)[0][0]}
            for k in (1, 10, 100):
                for label, idx in (("base", 1), ("plus", 2)):
                    vals = [x for x in (passk(v[idx], v[0], k) for v in tasks.values()) if x is not None]
                    out[f"{label}_pass@{k}"] = round(sum(vals) / len(vals), 6) if vals else None
            rows.append(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    print(f"{OUT}: {len(rows) - 1} rows")


if __name__ == "__main__":
    main()

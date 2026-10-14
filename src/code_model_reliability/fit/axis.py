"""The difficulty scale: one position per task, from the cells of the population of arms.

Definition. The difficulty of a task is the share of attempts that fail on it across the arms of the panel, each
arm counted once: the mean over the panel arms of each arm's failure rate on the task, shrunk by one
pseudo-observation of half a failure and half a pass over the task's total attempts, on the logit scale.
In symbols, for a task with panel arms a = 1..M, f_a failures of n_a attempts, N = sum n_a::

    pbar = (1/M) sum_a f_a / n_a
    q    = (N pbar + 1/2) / (N + 1)
    z    = logit(q) = log(q / (1 - q))

The standard error is the estimator's own: Var(pbar) = (1/M^2) sum_a v_a with v_a the Jeffreys posterior
variance of arm a's rate, (f_a + 1/2)(n_a - f_a + 1/2) / ((n_a + 1)^2 (n_a + 2)), or q(1 - q)/n_a for an arm whose
own data cannot estimate a rate (every attempt failed or every attempt passed); se_q = N/(N + 1) sqrt(Var(pbar));
se_z = se_q / (q(1 - q)). The arms' spread about the mean is part of the quantity, not measurement noise. A
count-based position is reliable within about log(2N + 1) logit of the ends; beyond that the joint fit places
the task through the errors-in-variables term.

The panel. An arm votes on the scale when it has attempts on at least ``COVERAGE_THRESHOLD`` of the set's tasks;
nothing else excludes an arm from voting. Every arm with cells is fitted and placed on the scale whether or not
it votes; an arm that is a fine-tune of another is placed and does not vote. The panel of a published fit is
recorded beside its axis in ``panel.json`` (the threshold, the voters, the arms placed without voting, every
arm's coverage), so the scale can be re-made from the cells.

Reads ``cells.csv`` (arm, task_id, failures, attempts). Writes ``axis.csv`` (task_id, difficulty_z, difficulty_sd,
n_arms, mean_failure_rate, n_attempts) and ``panel.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

COVERAGE_THRESHOLD = 0.9
"""An arm votes on the difficulty scale when it has attempts on at least nine tenths of the set's tasks, so the
scale is set by the arms that saw the whole set and a partly run arm is placed on it without shaping it."""

AXIS_COLUMNS = ("task_id", "difficulty_z", "difficulty_sd", "n_arms", "mean_failure_rate", "n_attempts")


@dataclass(frozen=True)
class Cell:
    arm: str
    task_id: str
    failures: int
    attempts: int


@dataclass(frozen=True)
class TaskDifficulty:
    task_id: str
    z: float
    se: float
    n_arms: int
    n_attempts: int
    mean_failure_rate: float
    se_pooled: float

    @property
    def resolution_logodds(self) -> float:
        return math.log(2 * self.n_attempts + 1)


def read_cells(path) -> list[Cell]:
    """Read ``cells.csv``; columns beyond the four used are ignored; a cell with no attempts is dropped."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = int(row["attempts"])
            if n <= 0:
                continue
            f = int(row["failures"])
            if not 0 <= f <= n:
                raise ValueError(f"cell {row['arm']} / {row['task_id']}: {f} failures of {n} attempts")
            out.append(Cell(row["arm"], row["task_id"], f, n))
    return out


def tasks_of(cells) -> list[str]:
    return sorted({c.task_id for c in cells})


def coverage(cells, tasks=None) -> dict[str, float]:
    """Per arm, the share of the set's tasks it has attempts on."""
    tasks = set(tasks if tasks is not None else tasks_of(cells))
    seen: dict[str, set] = {}
    for c in cells:
        if c.task_id in tasks:
            seen.setdefault(c.arm, set()).add(c.task_id)
    return {a: len(s) / len(tasks) for a, s in sorted(seen.items())}


def voters(cells, tasks=None, threshold=COVERAGE_THRESHOLD, exclude=()) -> list[str]:
    """The arms that vote on the scale: coverage at least ``threshold`` and not in ``exclude`` (fine-tunes)."""
    cov = coverage(cells, tasks)
    return sorted(a for a, s in cov.items() if s >= threshold and a not in set(exclude))


def difficulty(cells, panel) -> dict[str, TaskDifficulty]:
    """The position of every task that at least one panel arm ran, by the definition above."""
    panel = set(panel)
    by_task: dict[str, list[tuple[int, int]]] = {}
    for c in cells:
        if c.arm in panel:
            by_task.setdefault(c.task_id, []).append((c.attempts - c.failures, c.attempts))   # (passes, attempts)
    axis = {}
    for task, vals in sorted(by_task.items()):
        M = len(vals)
        N = sum(n for _, n in vals)
        D_raw = 1.0 - sum(c / n for c, n in vals) / M
        q = (N * D_raw + 0.5) / (N + 1)
        z = math.log(q / (1 - q))
        var_pbar = sum((((n - c) + 0.5) * (c + 0.5) / ((n + 1) ** 2 * (n + 2))) if 0 < (n - c) < n else (q * (1 - q) / n)
                       for c, n in vals) / M ** 2
        se_q = (N / (N + 1)) * math.sqrt(var_pbar)
        se = se_q / (q * (1 - q))
        se_pooled = 1.0 / math.sqrt((N + 2) * q * (1 - q))
        axis[task] = TaskDifficulty(task, z, se, M, N, D_raw, se_pooled)
    return axis


def write_axis_csv(path, axis: dict[str, TaskDifficulty]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(AXIS_COLUMNS)
        for t in sorted(axis):
            a = axis[t]
            w.writerow([t, f"{a.z:.6f}", f"{a.se:.6f}", a.n_arms, f"{a.mean_failure_rate:.6f}", a.n_attempts])


def read_axis_csv(path) -> dict[str, TaskDifficulty]:
    """Read ``axis.csv`` back (an older export with ``z_hat`` and ``se`` columns reads too)."""
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            z = float(row.get("difficulty_z") or row["z_hat"])
            se = float(row.get("difficulty_sd") or row["se"])
            n_arms = int(row.get("n_arms") or row.get("n_arms_holding") or 0)
            n_att = int(row.get("n_attempts") or row.get("n_attempts_total") or 0)
            mfr = float(row["mean_failure_rate"]) if row.get("mean_failure_rate") else float("nan")
            pooled = 1.0 / math.sqrt((n_att + 2) * 0.25) if n_att else float("nan")
            out[row["task_id"]] = TaskDifficulty(row["task_id"], z, se, n_arms, n_att, mfr, pooled)
    return out


def panel_record(cells, voters_list, threshold, tasks=None, excluded=()) -> dict:
    cov = coverage(cells, tasks)
    return {
        "rule": "an arm votes when it has attempts on at least the threshold share of the set's tasks; every arm with "
                "cells is fitted and placed; an arm listed under positioned_only is placed and does not vote",
        "threshold": threshold,
        "n_tasks": len(tasks if tasks is not None else tasks_of(cells)),
        "voters": sorted(voters_list),
        "positioned_only": sorted(a for a in cov if a not in set(voters_list)),
        "excluded_from_voting": sorted(excluded),
        "coverage": {a: round(s, 4) for a, s in cov.items()},
    }


def write_panel(path, record: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


def read_panel(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit axis", description="the difficulty scale from cells")
    ap.add_argument("--cells", required=True, help="cells.csv: arm, task_id, failures, attempts")
    ap.add_argument("--out", required=True, help="axis.csv to write")
    ap.add_argument("--panel-out", default=None, help="panel.json to write beside the axis (default: next to --out)")
    ap.add_argument("--panel", default=None, help="an existing panel.json whose voters are used instead of the coverage rule")
    ap.add_argument("--threshold", type=float, default=COVERAGE_THRESHOLD, help="the coverage share an arm needs to vote")
    ap.add_argument("--no-vote", action="append", default=[], metavar="ARM",
                    help="an arm placed on the scale without voting (a fine-tune of another arm); repeatable")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cells = read_cells(args.cells)
    tasks = tasks_of(cells)
    if args.panel:
        rec = read_panel(args.panel)
        panel = list(rec["voters"])
        threshold = rec.get("threshold", args.threshold)
        excluded = rec.get("excluded_from_voting", [])
    else:
        threshold, excluded = args.threshold, list(args.no_vote)
        panel = voters(cells, tasks, threshold, excluded)
    if not panel:
        print("no arm meets the coverage threshold; no axis written")
        return 1
    axis = difficulty(cells, panel)
    write_axis_csv(args.out, axis)
    panel_out = args.panel_out or str(Path(args.out).with_name("panel.json"))
    write_panel(panel_out, panel_record(cells, panel, threshold, tasks, excluded))
    print(f"axis: {len(axis)} tasks from {len(panel)} voting arms (threshold {threshold}); wrote {args.out} and {panel_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

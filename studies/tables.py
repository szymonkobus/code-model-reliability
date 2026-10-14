"""Readers of the published tables for the study scripts.

Every ``recompute.py`` under ``studies/`` reads the repository's data through this module: the data directory, the
published fit (its cells and difficulty axis), the task sets and their labels, the attribution rows and the arm
registry; plus two small statistics the studies share, an exact test on two pass counts and the Jeffreys logit. The
shapes are those of ``docs/data-contract.md``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAVE1_FOLDERS = ("wave-1", "wave1")
FIT_PARENTS = ("published", "served")


def arg_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--data", default=str(ROOT / "data"), help="the repository's data directory (default: data/ beside studies/)")
    ap.add_argument("--fit", default=None, help="the published fit's directory name when more than one is shipped")
    return ap


def fit_dir(data: Path, name: str | None = None) -> Path:
    """The published fit directory: data/results/published/<fit>/ (an older build spells the parent served)."""
    found = []
    for parent in FIT_PARENTS:
        base = data / "results" / parent
        if base.is_dir():
            found.extend(p for p in sorted(base.iterdir()) if p.is_dir() and (p / "cells.csv").exists())
    if name:
        found = [p for p in found if p.name == name]
    if len(found) != 1:
        raise SystemExit(f"expected one published fit under {data}/results, found {[str(p) for p in found]}; name one with --fit")
    return found[0]


def wave1_dir(data: Path) -> Path:
    for folder in WAVE1_FOLDERS:
        p = data / "tasks" / folder
        if p.is_dir():
            return p
    raise SystemExit(f"no wave 1 folder under {data}/tasks")


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_cells(fit: Path) -> dict[tuple[str, str], tuple[int, int]]:
    """(arm, task_id) -> (failures, attempts) from the published cells."""
    out = {}
    for r in read_csv(fit / "cells.csv"):
        out[(r["arm"], r["task_id"])] = (int(r["failures"]), int(r["attempts"]))
    return out


def read_axis(fit: Path) -> dict[str, float]:
    """task_id -> difficulty in logit units from the published axis."""
    return {r["task_id"]: float(r["difficulty_z"]) for r in read_csv(fit / "axis.csv")}


def read_sets(data: Path) -> dict:
    return read_json(data / "tasks" / "sets.json")


def set_members(sets: dict, key: str) -> list[str]:
    return list(sets["sets"][key]["members"])


def set_kept(sets: dict, key: str) -> list[str]:
    return list(sets["sets"][key]["kept"])


def read_labels(data: Path) -> dict[str, dict]:
    """task_id -> its label row (label, set, justification where it travels)."""
    return {r["task_id"]: r for r in read_jsonl(data / "tasks" / "labels" / "labels.jsonl")}


def read_label_history(data: Path) -> list[dict]:
    return read_jsonl(data / "tasks" / "labels" / "label_history.jsonl")


def read_kept_wave1(data: Path) -> dict:
    return read_json(wave1_dir(data) / "kept_tasks.json")


def read_attribution(data: Path) -> list[dict]:
    return read_jsonl(data / "tasks" / "attribution.jsonl")


def read_registry_arms(data: Path) -> list[dict]:
    """The arm rows of the registry, the header row (the one carrying ``schema``) dropped."""
    return [r for r in read_jsonl(data / "runs" / "registry" / "arms.jsonl") if "schema" not in r]


def sha256_sorted(ids) -> str:
    """The hash of a task list as ``sets.json`` records it: sha256 over the sorted ids joined by line breaks."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def fisher_exact_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided exact test that two pass counts, k1 of n1 and k2 of n2, come from one pass rate."""
    from scipy.stats import fisher_exact

    return float(fisher_exact([[k1, n1 - k1], [k2, n2 - k2]])[1])


def jeffreys_logit(k: float, n: float) -> float:
    """The logit of (k + 1/2) / (n + 1): a rate estimate that stays finite at k = 0 and k = n."""
    import math

    q = (k + 0.5) / (n + 1.0)
    return math.log(q / (1.0 - q))


def pct(x: float, digits: int = 2) -> str:
    return f"{100.0 * x:.{digits}f}%"


class Report:
    """Collects lines to print and problems that make the script exit 1."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.problems: list[str] = []

    def say(self, line: str = "") -> None:
        self.lines.append(line)

    def check(self, ok: bool, what: str) -> bool:
        if not ok:
            self.problems.append(what)
        self.lines.append(("ok   " if ok else "FAIL ") + what)
        return ok

    def finish(self) -> int:
        print("\n".join(self.lines))
        if self.problems:
            print(f"\n{len(self.problems)} check(s) failed")
            return 1
        print("\nall checks passed")
        return 0

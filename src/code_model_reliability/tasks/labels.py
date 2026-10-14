"""The audit labels and their history.

``labels/labels.jsonl`` has one row per reviewed task: ``task_id``, ``set`` (``wave_1``, ``wave_2``,
``wave_2_parked``, or ``none`` for a certified task that is in no set), ``label`` (regular, tricky,
underspecification, contradiction), ``source_round`` (the review round that set the label) and ``justification``
(the reviewer's reason; ``null`` with ``justification_withheld`` true where the reason does not travel).
``labels/label_history.jsonl`` has one row per review-round outcome on a task of the three sets: the task, the set
(``wave_1_not_kept`` for a wave 1 task the audit excluded), the label before and after (equal when the round
confirmed the label), the review round (``null`` with ``settled_by_hand`` true where the label was settled by
hand), the day it was recorded and the day it was applied, and the reason. The wave 1 rows are the audit's own
history; the wave 2 and wave 2 parked rows are the certification pool's, from its archives and its live file.
"""

from __future__ import annotations

from pathlib import Path

from .content import KEEP_LABELS
from .records import iter_jsonl

LABELS = ("regular", "tricky", "underspecification", "contradiction")
LABEL_MEANING = {
    "regular": "statement, reference and tests agree",
    "tricky": "sound, with a subtlety a careless reading misses",
    "underspecification": "the tests require behaviour the statement leaves open",
    "contradiction": "the statement, its examples, the reference or the tests contradict each other",
}


def load_labels(tasks_dir: Path) -> list[dict]:
    return list(iter_jsonl(tasks_dir / "labels" / "labels.jsonl"))


def load_label_history(tasks_dir: Path) -> list[dict]:
    path = tasks_dir / "labels" / "label_history.jsonl"
    return list(iter_jsonl(path)) if path.is_file() else []


def labels_by_task(rows: list[dict]) -> dict[str, str]:
    return {r["task_id"]: r["label"] for r in rows}


def check_labels(rows: list[dict], members: dict[str, frozenset[str]], kept: dict[str, frozenset[str]],
                 keep_labels: tuple[str, ...] = KEEP_LABELS) -> list[str]:
    """Every member has one label from the four; a member is kept exactly when its label is a keep label."""
    problems: list[str] = []
    by_task: dict[str, str] = {}
    for r in rows:
        if r.get("label") not in LABELS:
            problems.append(f"labels: {r.get('task_id')} has an unknown label {r.get('label')!r}")
        if r["task_id"] in by_task:
            problems.append(f"labels: {r['task_id']} appears twice")
        by_task[r["task_id"]] = r.get("label")
    for key, ids in members.items():
        missing = [t for t in ids if t not in by_task]
        if missing:
            problems.append(f"labels: {len(missing)} members of {key} have no label")
        wrong = [t for t in ids if t in by_task and ((by_task[t] in keep_labels) != (t in kept[key]))]
        if wrong:
            problems.append(f"labels: {len(wrong)} members of {key} are kept against their label, e.g. {wrong[0]}")
    return problems

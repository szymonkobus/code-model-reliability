"""The tasks a generation run answers, read in the judge harness's own shape.

A task set is an ordered mapping from task id to task. Each task carries at least ``task_id``, ``prompt`` (the
function signature and docstring the model completes) and ``entry_point`` (the function name the tests call);
the judged content (reference solution, test inputs, expected outputs, tolerance) rides along untouched.

Reads: a JSON-lines file (plain or gzip-compressed) in that shape, such as this repository's wave 2 task parts or a
harness task file; or, by name, the wave 1 task files the harness fetches itself when it is installed.
Writes nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import OrderedDict
from typing import Dict, Iterable

HARNESS_SETS = ("humaneval", "mbpp")
"""The two wave 1 task files, by the harness's names; ``load_tasks`` fetches them through the harness."""

REQUIRED_FIELDS = ("task_id", "prompt", "entry_point")
"""What a task must carry for generation; the judge needs the rest and checks it itself."""


def read_jsonl(path: str) -> Iterable[dict]:
    """Every JSON object in a .jsonl or .jsonl.gz file, in file order; blank lines are skipped."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def load_tasks(source: str, only: Iterable[str] | None = None) -> "OrderedDict[str, dict]":
    """The task set named or stored at ``source``: a harness set name (``humaneval`` or ``mbpp``), a task file, or a
    directory of task parts (every ``*.jsonl`` and ``*.jsonl.gz`` in it, in name order). ``only`` restricts the set
    to the listed task ids, keeping the file's order."""
    if source in HARNESS_SETS:
        tasks = _harness_tasks(source)
    elif os.path.isdir(source):
        tasks = OrderedDict()
        names = sorted(n for n in os.listdir(source) if n.endswith((".jsonl", ".jsonl.gz")))
        for name in names:
            for row in read_jsonl(os.path.join(source, name)):
                tasks[row["task_id"]] = row
    else:
        tasks = OrderedDict((row["task_id"], row) for row in read_jsonl(source))
    for task_id, task in tasks.items():
        missing = [f for f in REQUIRED_FIELDS if f not in task]
        if missing:
            raise ValueError(f"task {task_id!r} lacks {missing}")
    if only is not None:
        keep = set(only)
        tasks = OrderedDict((t, task) for t, task in tasks.items() if t in keep)
    return tasks


def _harness_tasks(name: str) -> "OrderedDict[str, dict]":
    """A wave 1 task file through the harness, which fetches and caches it under its own cache directory."""
    try:
        from evalplus.data import get_human_eval_plus, get_mbpp_plus
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            f"the task set {name!r} comes from the judge harness, which is not installed; install the package's "
            "`judge` extra or pass a task file"
        ) from exc
    getter = {"humaneval": get_human_eval_plus, "mbpp": get_mbpp_plus}[name]
    return OrderedDict(getter().items())


def set_sha256(tasks: Dict[str, dict]) -> str:
    """The identity of a task set for the generation record: sha256 over the sorted task ids, one per line."""
    text = "".join(f"{t}\n" for t in sorted(tasks))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    """sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

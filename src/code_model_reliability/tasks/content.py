"""The identity of a task and of a task set.

A task's identity is the sha256 of its eight judged fields serialised as JSON with sorted keys: the same recipe
every certificate, attribution row and judged cell carries, so a copy of a task can be checked against the record
without the record. A task set's identity is the sha256 of its sorted ids joined by newlines, the recipe
``sets.json`` was written with.

The sets have three spellings, each in its place: wave 1, wave 2 and wave 2 parked in prose; ``wave_1``, ``wave_2``
and ``wave_2_parked`` as the keys of every file and the ``set`` column of every row; ``wave-1``, ``wave-2`` and
``wave-2-parked`` as the folders under ``data/tasks/`` (wave 1's folder holds ids only: its texts come from the judge
harness).
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping

CONTENT_FIELDS: tuple[str, ...] = (
    "task_id",
    "prompt",
    "entry_point",
    "canonical_solution",
    "base_input",
    "plus_input",
    "atol",
    "expected_output",
)
"""The eight judged fields. A field the record lacks hashes as ``null``."""

SET_KEYS: tuple[str, ...] = ("wave_1", "wave_2", "wave_2_parked")
"""The set keys of ``sets.json`` and of the ``set`` column of every row."""

SET_NAMES: dict[str, str] = {"wave_1": "wave 1", "wave_2": "wave 2", "wave_2_parked": "wave 2 parked"}
"""How each set is written in prose."""

SET_DIRS: dict[str, str] = {"wave_2": "wave-2", "wave_2_parked": "wave-2-parked"}
"""The folder under ``data/tasks/`` that holds a set's task text and pointers."""

WAVE_1_DIR = "wave-1"
"""The folder under ``data/tasks/`` with wave 1's kept ids and its judge-side facts; no task text."""

KEEP_LABELS: tuple[str, ...] = ("regular", "tricky")
"""The audit labels that keep a task in the measured sets; the file ``sets.json`` carries the same rule."""


def content_sha256(record: Mapping) -> str:
    """The content hash of a task record: sha256 over the eight judged fields, JSON with sorted keys."""
    payload = {k: record.get(k) for k in CONTENT_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def list_sha256(ids: Iterable[str]) -> str:
    """The identity of a task list: sha256 over the sorted ids joined by newlines, no trailing newline."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def judged_content(record: Mapping) -> dict:
    """The eight judged fields of a record, in the shape the judge reads."""
    return {k: record.get(k) for k in CONTENT_FIELDS}


def set_dir_name(set_key: str) -> str:
    """The folder name of a set that ships text; raises for wave 1, which ships ids only."""
    try:
        return SET_DIRS[set_key]
    except KeyError:
        raise KeyError(f"{set_key} ships no task text; its ids are in sets.json") from None

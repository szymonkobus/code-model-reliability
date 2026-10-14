"""The task records of wave 2 and wave 2 parked: full text in compressed parts, pointers where the text does not
travel.

Each set folder (``wave-2/``, ``wave-2-parked/``) holds ``tasks-part-NN.jsonl.gz`` (one JSON object per line: the
eight judged fields, ``content_sha256``, ``kept_by_audit``, ``io_mode`` and ``provenance``, plus two fields the judge
applies where they exist: ``plus_inputs_removed``, the extended inputs removed before judging, and ``input_shapes``,
the declared shape per argument), ``restricted.jsonl`` (one object per task whose text does not travel: the identity,
the audit flag, ``io_mode``, the provenance, the reason and a pointer sentence) and ``manifest.json`` (the counts,
each part's bytes and sha256, the hash recipe).

``io_mode`` is ``function`` when the tests call the entry point with arguments and ``stdio`` when the program reads
standard input and writes standard output, its output compared as text; a record that predates the field is read as
``function`` unless its entry point is the stdio wrapper.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .content import CONTENT_FIELDS, content_sha256, judged_content, set_dir_name

STDIO_SIGNATURE = "def solve(input_data: str) -> str"
"""The prompt a converted standard-input problem starts with; the fallback for a record without ``io_mode``."""


@dataclass(frozen=True)
class Task:
    """A task with its text: the judged content plus its identity and attribution."""

    record: dict

    @property
    def task_id(self) -> str:
        return self.record["task_id"]

    @property
    def content_sha256(self) -> str:
        return self.record["content_sha256"]

    @property
    def kept_by_audit(self) -> bool:
        return bool(self.record.get("kept_by_audit"))

    @property
    def provenance(self) -> dict:
        return self.record.get("provenance") or {}

    @property
    def io_mode(self) -> str:
        mode = self.record.get("io_mode")
        if mode in ("function", "stdio"):
            return mode
        return "stdio" if (self.record.get("prompt") or "").startswith(STDIO_SIGNATURE) else "function"

    @property
    def plus_inputs_removed(self) -> list:
        """The extended inputs the judge removes before judging (argument lists, matched by value); empty when none."""
        return list(self.record.get("plus_inputs_removed") or [])

    @property
    def input_shapes(self) -> list[str] | None:
        """The declared shape per positional argument, when the inputs are typed before the call; else None."""
        return list(self.record["input_shapes"]) if self.record.get("input_shapes") else None

    def judged(self) -> dict:
        """The eight judged fields, the shape the judge reads."""
        return judged_content(self.record)

    def hash_matches(self) -> bool:
        return content_sha256(self.record) == self.content_sha256


@dataclass(frozen=True)
class Pointer:
    """A task whose text does not travel: identity, audit flag, provenance, the reason and where to rebuild from."""

    record: dict

    @property
    def task_id(self) -> str:
        return self.record["task_id"]

    @property
    def content_sha256(self) -> str:
        return self.record["content_sha256"]

    @property
    def kept_by_audit(self) -> bool:
        return bool(self.record.get("kept_by_audit"))

    @property
    def provenance(self) -> dict:
        return self.record.get("provenance") or {}

    @property
    def reason(self) -> str:
        return self.record.get("reason", "")


def iter_jsonl(path: Path) -> Iterator[dict]:
    """The objects of a JSON-lines file, plain or gzip-compressed."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def set_folder(tasks_dir: Path, set_key: str) -> Path:
    return tasks_dir / set_dir_name(set_key)


def read_manifest(tasks_dir: Path, set_key: str) -> dict:
    return json.loads((set_folder(tasks_dir, set_key) / "manifest.json").read_text(encoding="utf-8"))


def part_paths(tasks_dir: Path, set_key: str) -> list[Path]:
    """The parts in the manifest's order (the manifest is the list of record; the folder may hold nothing else)."""
    folder = set_folder(tasks_dir, set_key)
    manifest = read_manifest(tasks_dir, set_key)
    return [folder / part["file"] for part in manifest.get("parts", [])]


def iter_tasks(tasks_dir: Path, set_key: str, kept_only: bool = False) -> Iterator[Task]:
    """Every task of a set that ships with its text, in part order; ``kept_only`` keeps the audited-in tasks."""
    for path in part_paths(tasks_dir, set_key):
        for rec in iter_jsonl(path):
            task = Task(rec)
            if kept_only and not task.kept_by_audit:
                continue
            yield task


def iter_pointers(tasks_dir: Path, set_key: str) -> Iterator[Pointer]:
    """Every task of a set that ships as a pointer."""
    path = set_folder(tasks_dir, set_key) / "restricted.jsonl"
    if not path.is_file():
        return
    for rec in iter_jsonl(path):
        yield Pointer(rec)


def find_task(tasks_dir: Path, set_key: str, task_id: str) -> Task | Pointer | None:
    for task in iter_tasks(tasks_dir, set_key):
        if task.task_id == task_id:
            return task
    for ptr in iter_pointers(tasks_dir, set_key):
        if ptr.task_id == task_id:
            return ptr
    return None


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_parts(tasks_dir: Path, set_key: str) -> list[str]:
    """Each part's bytes and sha256 against the manifest, and the record fields present. Returns problems."""
    problems: list[str] = []
    folder = set_folder(tasks_dir, set_key)
    manifest = read_manifest(tasks_dir, set_key)
    for part in manifest.get("parts", []):
        path = folder / part["file"]
        if not path.is_file():
            problems.append(f"{set_key}: part {part['file']} is missing")
            continue
        if path.stat().st_size != part.get("bytes"):
            problems.append(f"{set_key}: part {part['file']} has {path.stat().st_size} bytes, the manifest says {part.get('bytes')}")
        if file_sha256(path) != part.get("sha256"):
            problems.append(f"{set_key}: part {part['file']} does not match its manifest sha256")
    for task in iter_tasks(tasks_dir, set_key):
        missing = [k for k in CONTENT_FIELDS if k not in task.record]
        if missing:
            problems.append(f"{set_key}: {task.task_id} lacks {', '.join(missing)}")
            break
    return problems

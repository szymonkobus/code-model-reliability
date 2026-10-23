"""The certificates: one record per task admitted to the pool of new tasks.

``certificates.jsonl`` has one row per certified task, whether or not it is a member of a set: ``task_id``,
``content_sha256`` and ``superseded_prev_sha256`` (the previous hash where the task was re-issued), ``set``
(``frame`` for the pool the two measured sets were drawn from, ``pilot`` for tasks of a pilot that entered neither
set), ``in_frame``, ``status``, ``fit_keep_set`` (eligible for the fits by status and audit label), ``audit_label``
(the label, the review round that set it, and the reviewer's reason where it travels), ``band_aim`` (the difficulty
band the task was aimed at), ``conversion`` (the method and the reference's origin) and ``provenance`` (the upstream
dataset and row, title, URL, licence, rating and tags, or the generator and its settings). Run outcomes are not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .records import iter_jsonl

STATUS_MEANING = {   # the ten values of the certificates' status contract, every one whether or not a task carries it today
    "complete-for-admission": "certified with a complete test set",
    "retracted-to-reserve": "certified, then set aside from the measured pool",
    "withdrawn": "removed after certification",
    "excluded-provisional-tier1": "held out of the measured pool pending a check",
    "excluded-provisional-tier2": "held out of the measured pool pending a lesser check",
    "blocked-tier1-split": "blocked by an unresolved defect-label disagreement",
    "awaiting-components": "certification incomplete",
    "awaiting-label": "certification incomplete: no audit label yet",
    "held-tuple-risk": "held while a type question in its expected outputs was open",
    "held-empty-tests": "no usable tests",
}


def iter_certificates(tasks_dir: Path) -> Iterator[dict]:
    yield from iter_jsonl(tasks_dir / "certificates.jsonl")


def certificate_hashes(tasks_dir: Path) -> dict[str, str]:
    """Task id to its certified content hash."""
    return {c["task_id"]: c["content_sha256"] for c in iter_certificates(tasks_dir) if c.get("content_sha256")}


def check_certificates(tasks_dir: Path, members: dict[str, frozenset[str]]) -> list[str]:
    """Every member of wave 2 and wave 2 parked has a certificate with a content hash; ids are unique."""
    problems: list[str] = []
    seen: set[str] = set()
    hashes: dict[str, str] = {}
    for c in iter_certificates(tasks_dir):
        tid = c.get("task_id")
        if tid in seen:
            problems.append(f"certificates: {tid} appears twice")
        seen.add(tid)
        if c.get("content_sha256"):
            hashes[tid] = c["content_sha256"]
        if c.get("status") not in STATUS_MEANING:
            problems.append(f"certificates: {tid} has an unknown status {c.get('status')!r}")
    for key in ("wave_2", "wave_2_parked"):
        missing = members.get(key, frozenset()) - hashes.keys()
        if missing:
            problems.append(f"certificates: {len(missing)} members of {key} have no certificate with a hash")
    return problems

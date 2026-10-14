"""One reader for the raw replies of every generation back end and for the verdict files.

Three raw-reply shapes exist from the generation paths: ``raw-v1`` (one object per attempt, ``task_id`` and
``solution``, the attempt index implicit in file order), ``records-v2`` (the thinking and runner protocols:
``task_id``, ``sample``, ``answer_raw``, ``think_text``, ``think_finish_reason``, ``closure``) and the API
back ends' records (``task_id``, ``sample``, ``text``, ``stop_reason``). ``iter_raw`` normalises all three to one
record per attempt: ``task_id``, ``attempt``, ``text``, ``think_text``, ``finish``, ``closure``. The generate
stage of this package writes ``raw.jsonl`` in that normalised shape already.

Reads ``raw.jsonl`` files and ``verdicts.json``; writes nothing.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Iterable

SCHEMAS = ("raw-v1", "records-v2", "records-api-v1", "raw")


def _lines(path: str | pathlib.Path) -> Iterable[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def iter_raw(path: str | pathlib.Path, schema: str = "raw") -> Iterable[dict[str, Any]]:
    """The attempts of a raw file as normalised records."""
    if schema == "raw-v1":
        counters: dict[str, int] = {}
        for r in _lines(path):
            t = r["task_id"]
            counters[t] = counters.get(t, -1) + 1
            yield {"task_id": t, "attempt": counters[t], "text": r["solution"], "think_text": None, "finish": None, "closure": None}
    elif schema == "records-v2":
        for r in _lines(path):
            yield {"task_id": r["task_id"], "attempt": r["sample"], "text": r.get("answer_raw", ""),
                   "think_text": r.get("think_text"), "finish": r.get("think_finish_reason"), "closure": r.get("closure")}
    elif schema == "records-api-v1":
        for r in _lines(path):
            yield {"task_id": r["task_id"], "attempt": r.get("sample", 0), "text": r.get("text", ""),
                   "think_text": r.get("think_text"), "finish": r.get("stop_reason"), "closure": None}
    elif schema == "raw":
        for r in _lines(path):
            yield {"task_id": r["task_id"], "attempt": r.get("attempt", 0), "text": r.get("text", ""),
                   "think_text": r.get("think_text"), "finish": r.get("finish_reason"), "closure": r.get("closure")}
    else:
        raise ValueError(f"unknown raw schema {schema!r}; one of {SCHEMAS}")


def load_verdicts(path: str | pathlib.Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_judging(path: str | pathlib.Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

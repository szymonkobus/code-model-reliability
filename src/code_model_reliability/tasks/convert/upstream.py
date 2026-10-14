"""The upstream rows: LeetCodeDataset and LiveCodeBench read from Hugging Face, row by row.

``fetch_leetcode`` streams the two JSON-lines files of newfacade/LeetCodeDataset and keeps the columns the converter
reads; ``fetch_livecodebench`` streams the six release slices of livecodebench/code_generation_lite (newest first)
and keeps the LeetCode rows that name a function (the stdin problems have no joinable reference). Each row carries
``_row`` (file and line) and ``_fetched_at``; the LeetCodeDataset rows double as the references the join reads. A
dataset revision can be pinned so that a fetch reads the rows as they stood at a commit of the dataset repository.

Needs the ``huggingface_hub`` package (``pip install huggingface_hub``); nothing else.
"""

from __future__ import annotations

import datetime
import io
import json
import os
from pathlib import Path
from typing import Iterator

LEETCODE_FILES = ("LeetCodeDataset-train.jsonl", "LeetCodeDataset-test.jsonl")
LEETCODE_COLUMNS = ["task_id", "question_id", "difficulty", "tags", "problem_description", "starter_code",
                    "estimated_date", "prompt", "completion", "entry_point", "input_output"]
LIVECODEBENCH_FILES = ("test6.jsonl", "test5.jsonl", "test4.jsonl", "test3.jsonl", "test2.jsonl", "test.jsonl")
LIVECODEBENCH_COLUMNS = ["question_title", "question_content", "platform", "question_id", "contest_id", "contest_date",
                         "starter_code", "difficulty", "public_test_cases", "private_test_cases", "metadata"]


def _dataset_path(repo: str, filename: str, revision: str | None) -> str:
    return "datasets/%s%s/%s" % (repo, "@" + revision if revision else "", filename)


def stream_jsonl(fs, path: str, keep: list[str] | None = None) -> Iterator[dict]:
    """A Hugging Face-hosted JSON-lines file, row by row, each row with ``_row`` naming its file and line."""
    with fs.open(path, "rb") as fh:
        for i, line in enumerate(io.TextIOWrapper(fh, encoding="utf-8")):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if keep:
                row = {k: row.get(k) for k in keep}
            row["_row"] = "%s#%d" % (os.path.basename(path).split("@")[-1], i)
            yield row


def _filesystem():
    from huggingface_hub import HfFileSystem
    return HfFileSystem()


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def fetch_leetcode(out: Path, revision: str | None = None, slugs: set[str] | None = None) -> int:
    """Write the LeetCodeDataset rows (all, or only the given slugs) to ``out``; returns the row count."""
    fs = _filesystem()
    fetched_at = _stamp()
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for filename in LEETCODE_FILES:
            for row in stream_jsonl(fs, _dataset_path("newfacade/LeetCodeDataset", filename, revision), LEETCODE_COLUMNS):
                if slugs is not None and row.get("task_id") not in slugs:
                    continue
                row["_fetched_at"] = fetched_at
                fh.write(json.dumps(row, default=str) + "\n")
                n += 1
    return n


def fetch_livecodebench(out: Path, revision: str | None = None, slugs: set[str] | None = None) -> tuple[int, int]:
    """Write the LiveCodeBench LeetCode rows that name a function (all, or only the given slugs) to ``out``; returns
    the rows kept and the rows skipped for having no joinable reference."""
    from .livecodebench import slugify
    fs = _filesystem()
    fetched_at = _stamp()
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = skipped = 0
    with open(out, "w", encoding="utf-8") as fh:
        for filename in LIVECODEBENCH_FILES:
            for row in stream_jsonl(fs, _dataset_path("livecodebench/code_generation_lite", filename, revision), LIVECODEBENCH_COLUMNS):
                meta = {}
                try:
                    meta = json.loads(row.get("metadata") or "{}")
                except ValueError:
                    pass
                if (row.get("platform") or "").lower() != "leetcode" or not meta.get("func_name"):
                    skipped += 1
                    continue
                if slugs is not None and slugify(row.get("question_title")) not in slugs:
                    continue
                row["_func_name"] = meta["func_name"]
                row.pop("metadata", None)
                row["_fetched_at"] = fetched_at
                fh.write(json.dumps(row, default=str) + "\n")
                kept += 1
    return kept, skipped


def references_by_slug(leetcode_rows_path: Path) -> dict[str, dict]:
    """The LeetCodeDataset rows by slug, as the LiveCodeBench join reads them."""
    refs: dict[str, dict] = {}
    with open(leetcode_rows_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                refs[row["task_id"]] = row
    return refs

"""What a generation run writes, and how an interrupted run resumes.

Per set and arm, in one output directory:

- ``samples.jsonl`` — one object per attempt, ``{"task_id", "solution"}``, in task order and attempt order within
  a task: the program after extraction, the shape the judge reads (the harness's own samples shape).
- ``raw.jsonl`` — one object per attempt as the model returned it: ``task_id``, ``attempt``, ``text``,
  ``finish_reason`` (``stop``, ``length`` or ``refusal``), ``tokens`` (output tokens where the back end reports
  them) and, for the thinking forms, ``think_text``, ``think_tokens``, ``answer_tokens`` and ``closure`` (how the
  thinking closed). A ``provider`` object carries what an API returned beside the text (the model string it
  served, its stop reason, its token usage, the batch id).
- ``generation.json`` — every setting the attempts were produced under (see ``GenerationRecord``).

The two line files are written together, one attempt at a time, each line flushed, so a run that is killed leaves
at most one unpaired line. On resume the files are repaired: a torn last line is dropped, the longer file is cut to
the shorter one's length, and the attempts already present per task are counted so generation continues from
there. Nothing is ever rewritten in place: a completed run is final, and a correction lands beside it.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
from collections import Counter
from typing import Dict, Iterable, Optional

SAMPLES = "samples.jsonl"
RAW = "raw.jsonl"
GENERATION = "generation.json"

FINISH_REASONS = ("stop", "length", "refusal")
"""The one vocabulary for why an answer ended: the model stopped, the output limit cut it, or the provider refused."""


def normalise_finish_reason(reason: Optional[str]) -> str:
    """Every back end's end-of-output word mapped to the three words above; an unknown word is ``stop``."""
    r = (reason or "").lower()
    if r in ("length", "max_tokens", "max_output_tokens"):
        return "length"
    if r in ("refusal", "content_filter", "safety", "recitation"):
        return "refusal"
    return "stop"


def today() -> str:
    """The day, written year-month-day; the one date a generation record carries."""
    return _dt.date.today().isoformat()


@dataclasses.dataclass
class GenerationRecord:
    """Every setting an attempt was produced under; written as ``generation.json`` beside the attempts."""

    arm: str
    task_set: str
    task_set_sha256: str
    n_tasks: int
    attempts_per_task: int
    model_id: str
    model_revision: Optional[str]
    form: str
    protocol: str
    protocol_version: str
    backend: str
    prompt_style: str
    sampling: dict
    output_limit: Optional[int]
    thinking_budget: Optional[int]
    answer_budget: Optional[int]
    max_model_len: Optional[int]
    stops: list
    harness_commit: str
    instruction: str
    extractor: dict
    pins: dict
    seed: Optional[int]
    started: str
    finished: Optional[str] = None
    notes: dict = dataclasses.field(default_factory=dict)

    def write(self, out_dir: str) -> None:
        with open(os.path.join(out_dir, GENERATION), "w", encoding="utf-8") as fh:
            json.dump(dataclasses.asdict(self), fh, indent=1, ensure_ascii=False)
            fh.write("\n")

    @classmethod
    def read(cls, out_dir: str) -> "GenerationRecord":
        with open(os.path.join(out_dir, GENERATION), encoding="utf-8") as fh:
            return cls(**json.load(fh))


def _trim_torn_line(path: str) -> bool:
    """Drop a last line that is not whole JSON (a write the kill interrupted); restore a missing final newline.
    Returns whether a line was dropped."""
    if not os.path.exists(path):
        return False
    with open(path, "rb") as fh:
        data = fh.read()
    lines = data.splitlines(keepends=True)
    if not lines:
        return False
    last = lines[-1]
    try:
        json.loads(last.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        os.truncate(path, len(data) - len(last))
        return True
    if not last.endswith(b"\n"):
        with open(path, "ab") as fh:
            fh.write(b"\n")
    return False


def _line_count(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


def _truncate_to_lines(path: str, n: int) -> None:
    with open(path, "rb") as fh:
        offset = 0
        for _ in range(n):
            offset += len(fh.readline())
    os.truncate(path, offset)


def repair(out_dir: str) -> dict:
    """Make the two line files whole and paired after an interruption: torn last lines dropped, both cut to their
    common length. Returns what was done, for the log."""
    samples = os.path.join(out_dir, SAMPLES)
    raw = os.path.join(out_dir, RAW)
    done = {"torn_samples": _trim_torn_line(samples), "torn_raw": _trim_torn_line(raw)}
    n_s, n_r = _line_count(samples), _line_count(raw)
    if n_s != n_r:
        n = min(n_s, n_r)
        if os.path.exists(samples):
            _truncate_to_lines(samples, n)
        if os.path.exists(raw):
            _truncate_to_lines(raw, n)
        done["cut_to"] = n
    return done


def attempts_done(out_dir: str) -> Counter:
    """How many attempts each task already has in ``raw.jsonl`` (after ``repair``)."""
    counts: Counter = Counter()
    path = os.path.join(out_dir, RAW)
    if not os.path.exists(path):
        return counts
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                counts[json.loads(line)["task_id"]] += 1
    return counts


def read_rows(path: str) -> Iterable[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


class AttemptWriter:
    """Appends one attempt at a time to ``samples.jsonl`` and ``raw.jsonl`` together."""

    def __init__(self, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        self.out_dir = out_dir
        self.repaired = repair(out_dir)
        self.done = attempts_done(out_dir)
        self._samples = open(os.path.join(out_dir, SAMPLES), "a", encoding="utf-8")
        self._raw = open(os.path.join(out_dir, RAW), "a", encoding="utf-8")

    def write(self, task_id: str, attempt: int, solution: str, text: str, finish_reason: str, **extra) -> None:
        """One attempt: the extracted program to the samples file, the model's text and its record to the raw file.
        ``extra`` carries the thinking fields, the token count and the provider block."""
        raw_row = {
            "task_id": task_id,
            "attempt": attempt,
            "text": text,
            "finish_reason": normalise_finish_reason(finish_reason),
        }
        raw_row.update({k: v for k, v in extra.items() if v is not None})
        sample_line = json.dumps({"task_id": task_id, "solution": solution}, ensure_ascii=False) + "\n"
        raw_line = json.dumps(raw_row, ensure_ascii=False) + "\n"
        self._samples.write(sample_line)
        self._raw.write(raw_line)
        self._samples.flush()
        self._raw.flush()
        self.done[task_id] += 1

    def close(self) -> None:
        self._samples.close()
        self._raw.close()

    def __enter__(self) -> "AttemptWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def check_counts(out_dir: str, tasks: Dict[str, dict], attempts_per_task: int) -> None:
    """Fail unless the samples file holds exactly ``attempts_per_task`` attempts for every task of the set and no
    other task; run before judging, which does not check counts itself."""
    counts: Counter = Counter(r["task_id"] for r in read_rows(os.path.join(out_dir, SAMPLES)))
    extra = sorted(set(counts) - set(tasks))
    if extra:
        raise ValueError(f"samples hold tasks outside the set: {extra[:5]}")
    bad = {t: counts.get(t, 0) for t in tasks if counts.get(t, 0) != attempts_per_task}
    if bad:
        raise ValueError(f"tasks with an attempt count other than {attempts_per_task}: {dict(list(bad.items())[:5])}")

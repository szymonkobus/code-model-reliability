"""Several judgings of the same attempts become one set of verdicts: the newest judging of a task wins.

An arm's attempts may be judged more than once: a whole file again under new settings, or the tasks a setting
change touched. Each judging is its own verdict file beside the first (``verdicts.json``, ``verdicts.1.json``,
``verdicts.2.json`` and so on, each with its ``judging.N.json``), and nothing is ever rewritten. ``compose``
takes the judgings oldest to newest and, task by task, keeps the newest judging that judged the task; a judging
of a task is accepted only when it judged the same attempts (the same solution texts in the same order), so a
re-judging of other programs can never pose as a correction. The composed verdicts carry, per task, the id of
the judging that won.

Reads the verdict files of one arm; writes nothing (the composed verdicts go to ``cells``).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

_NUMBERED = re.compile(r"^verdicts(?:\.(\d+))?\.json$")


def solution_hashes(rows: list[dict[str, Any]]) -> list[str]:
    return [hashlib.sha256(r.get("solution", "").encode("utf-8")).hexdigest()[:16] for r in rows]


def judging_files(arm_dir: str | pathlib.Path) -> list[tuple[pathlib.Path, pathlib.Path | None]]:
    """The verdict files of an arm directory with their judging records, oldest (unnumbered) to newest."""
    arm_dir = pathlib.Path(arm_dir)
    found = []
    for p in arm_dir.iterdir():
        m = _NUMBERED.match(p.name)
        if m:
            n = int(m.group(1)) if m.group(1) else 0
            record = arm_dir / ("judging.json" if n == 0 else f"judging.{n}.json")
            found.append((n, p, record if record.exists() else None))
    return [(p, r) for _, p, r in sorted(found)]


def compose(judgings: list[tuple[dict[str, Any], str]]) -> tuple[dict[str, Any], dict[str, str]]:
    """``judgings`` are ``(verdicts, judging_id)`` pairs oldest to newest; returns the composed verdicts and, per
    task, the id of the judging whose verdicts stand. Raises on a re-judging of different attempts."""
    if not judgings:
        raise ValueError("no judgings to compose")
    base, base_id = judgings[0]
    composed = {"date": base.get("date"), "hash": base.get("hash"), "eval": {}, "pass_at_k": {}}
    won: dict[str, str] = {}
    for task_id, rows in base["eval"].items():
        composed["eval"][task_id] = list(rows)
        won[task_id] = base_id
    for verdicts, judging_id in judgings[1:]:
        for task_id, rows in verdicts["eval"].items():
            if task_id not in composed["eval"]:
                composed["eval"][task_id] = list(rows)
                won[task_id] = judging_id
                continue
            if solution_hashes(rows) != solution_hashes(composed["eval"][task_id]):
                raise ValueError(f"re-judging of {task_id} under {judging_id} judged different attempts")
            composed["eval"][task_id] = list(rows)
            won[task_id] = judging_id
    from .passk import mean_pass_at_k

    composed["pass_at_k"] = {
        suite: {f"pass@{k}": v for k in (1, 10, 100) if (v := mean_pass_at_k(composed, k, suite)) is not None}
        for suite in ("base", "plus")
    }
    return composed, won


def compose_directory(arm_dir: str | pathlib.Path) -> tuple[dict[str, Any], dict[str, str]]:
    """``compose`` over the verdict files found in an arm directory."""
    pairs = []
    for verdict_path, record_path in judging_files(arm_dir):
        with open(verdict_path, encoding="utf-8") as fh:
            verdicts = json.load(fh)
        judging_id = "unknown"
        if record_path is not None:
            with open(record_path, encoding="utf-8") as fh:
                judging_id = json.load(fh).get("settings_id", "unknown")
        pairs.append((verdicts, judging_id))
    return compose(pairs)

"""The outcome of every test for an attempt, where a verdict says only pass or fail.

The judge's verdict files carry one status per suite and the first failing test. This module writes, per failing
attempt and suite, the outcome string over every test (``P`` pass, ``W`` wrong, ``T`` time-out, ``E`` exception,
``A`` not run), either as the judge records it while judging every test, or by re-running the failing attempts
of an existing verdict file under the same settings. Two attempts with the same outcome string failed the same
tests in the same way; the land stage counts the distinct strings per arm and task.

Reads a task file (or harness set), a samples file and a ``verdicts.json``; writes ``per_test.jsonl``, one JSON
object per failing attempt and suite: ``task_id``, ``attempt``, ``suite`` (``base`` or ``plus``), ``outcomes``,
``time_outs`` (the indices of the tests stopped by the limit), ``status``.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Iterable

from . import execute
from .settings import JudgingSettings, memory_limit_bytes


def row(task_id: str, attempt: int, suite: str, result: execute.SuiteResult) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "attempt": attempt,
        "suite": suite,
        "status": result.status,
        "outcomes": result.outcomes,
        "time_outs": result.time_outs,
        "killed_at_cap": result.killed_at_cap,
    }


def write(rows: Iterable[dict[str, Any]], path: str | pathlib.Path) -> int:
    path = pathlib.Path(path)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
            n += 1
    return n


def read(path: str | pathlib.Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def rerun_failing(problems: dict[str, dict[str, Any]], expected: dict[str, dict[str, Any]], verdicts: dict[str, Any],
                  settings: JudgingSettings, completion_form: bool = False) -> list[dict[str, Any]]:
    """Re-run every failing attempt of ``verdicts`` on every test of the suite it failed, under ``settings``, and
    return the per-test rows. The judged program is rebuilt from the verdict's own solution text."""
    memory = memory_limit_bytes(settings)
    rows: list[dict[str, Any]] = []
    for task_id, attempts in verdicts["eval"].items():
        p = problems[task_id]
        exp = expected[task_id]
        for i, a in enumerate(attempts):
            program = execute.judged_program(p["prompt"], a["solution"], settings.leading_imports is not None,
                                             completion_form and settings.typing_prelude is not None)
            for suite in ("base", "plus"):
                if a.get(f"{suite}_status") == execute.PASS:
                    continue
                result = execute.run_suite(
                    p["kind"], p["entry_point"], program, p[f"{suite}_input"], exp[suite], exp[f"{suite}_time"],
                    p["atol"], floor_s=settings.time_limit_floor_s, factor=settings.time_limit_factor,
                    set_cap_s=settings.set_cap_s, memory_bytes=memory, stdin_stdout=p["stdin_stdout"],
                    stop_at_first=False,
                )
                rows.append(row(task_id, i, suite, result))
    return rows

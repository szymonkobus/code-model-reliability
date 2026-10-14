"""A deterministic stand-in for a model: an answer per task and attempt, decided by a seeded rule.

The stand-in returns one of four answers for a task, so a judged fixture carries passes, failures of each kind
and the cases the judge's rules decide:

- ``correct``: the task's reference solution under the prompt;
- ``variant``: a correct answer that only passes under the judge's rules (the prompt's imports not repeated, an
  exact integer where the reference returns a float, an output text with a trailing newline);
- ``wrong``: an answer with a wrong output on some test;
- ``slow``: an answer that sleeps past the per-test time limit on one test.

The kind is chosen from the sha256 of the task id, the attempt index and the seed, so the same arguments give the
same answer on every machine. Reads and writes nothing.
"""

from __future__ import annotations

import hashlib

KINDS = ("correct", "correct", "correct", "variant", "variant", "wrong", "wrong", "slow")


def kind_of(task_id: str, attempt: int, seed: int = 0) -> str:
    digest = hashlib.sha256(f"{task_id}|{attempt}|{seed}".encode("utf-8")).hexdigest()
    return KINDS[int(digest[:8], 16) % len(KINDS)]


def answer(task: dict, attempt: int, seed: int = 0) -> str:
    """The stand-in's program for one attempt: a whole program in the samples' ``solution`` shape."""
    kind = kind_of(task["task_id"], attempt, seed)
    answers = task["fixture_answers"]
    return answers[kind]


def samples(tasks: list[dict], attempts: int, seed: int = 0) -> list[dict]:
    """The samples file's rows for a fixture set: ``attempts`` answers per task, in task and attempt order."""
    rows = []
    for task in tasks:
        for i in range(attempts):
            rows.append({"task_id": task["task_id"], "solution": answer(task, i, seed)})
    return rows

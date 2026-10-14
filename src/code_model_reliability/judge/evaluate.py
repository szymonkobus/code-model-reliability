"""Judging a samples file against a task set: a verdict per attempt, the settings pinned beside them.

``judge`` reads the tasks (a task file in the contract's shape or a harness set by name), applies the input rules
the settings name, computes the expected outputs from the reference solutions, then runs every attempt of the
samples file on the base tests and on the extended tests in a pool of workers, each attempt in its own sandboxed
child. It writes:

- ``verdicts.json`` in the harness's own output shape: ``eval`` maps a task id to its attempts in file order,
  each with ``base_status``, ``plus_status`` (``pass``, ``fail`` or ``timeout``), the first failing input of each
  suite, and the solution text as judged; ``pass_at_k`` recomputed from the verdicts with the unbiased estimator;
  ``hash`` the task set's hash; ``date`` the day;
- ``judging.json``: the settings record and its id, the harness commit, the set and its hash, the attempts and
  tasks counted, the attempts the time limit stopped per task, and what the input rules did;
- ``per_test.jsonl`` when asked: the outcome of every test for every failing attempt.

An attempt passes only when both statuses are ``pass``. Reads ``samples.jsonl`` (one JSON object per attempt,
``task_id`` and ``solution``, in task order and attempt order) and the task source; writes the three files above
into the output directory.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Iterable

from . import execute, per_test, settings as settings_module, tasks as tasks_module
from .settings import CURRENT, JudgingSettings, memory_limit_bytes

_WORK: dict[str, Any] = {}  # the problems and expected outputs, inherited by the forked workers


def read_samples(path: str | pathlib.Path) -> Iterable[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _judge_attempt(args: tuple) -> dict[str, Any]:
    task_id, attempt, solution, every_test = args
    p = _WORK["problems"][task_id]
    exp = _WORK["expected"][task_id]
    s: JudgingSettings = _WORK["settings"]
    program = execute.judged_program(p["prompt"], solution, s.leading_imports is not None,
                                     _WORK["completion_form"] and s.typing_prelude is not None)
    out: dict[str, Any] = {"task_id": task_id, "attempt": attempt, "solution": solution}
    for suite in ("base", "plus"):
        result = execute.run_suite(
            p["kind"], p["entry_point"], program, p[f"{suite}_input"], exp[suite], exp[f"{suite}_time"], p["atol"],
            floor_s=s.time_limit_floor_s, factor=s.time_limit_factor, set_cap_s=s.set_cap_s,
            memory_bytes=_WORK["memory"], stdin_stdout=p["stdin_stdout"], stop_at_first=not every_test,
        )
        out[suite] = {"status": result.status, "outcomes": result.outcomes, "time_outs": result.time_outs,
                      "killed_at_cap": result.killed_at_cap, "failing": result.failing_tests}
    return out


def pass_at_k_table(eval_block: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, float]]:
    """The harness's ``pass_at_k`` block, recomputed from the verdicts: per suite the mean over tasks of the
    unbiased estimator for k in 1, 10, 100 where every task has at least k attempts."""
    from ..land.passk import pass_at_k

    out: dict[str, dict[str, float]] = {}
    for suite in ("base", "plus"):
        table: dict[str, float] = {}
        for k in (1, 10, 100):
            values = []
            for rows in eval_block.values():
                n = len(rows)
                if n < k:
                    values = []
                    break
                if suite == "base":
                    c = sum(1 for r in rows if r["base_status"] == execute.PASS)
                else:
                    c = sum(1 for r in rows if r["base_status"] == execute.PASS and r["plus_status"] == execute.PASS)
                values.append(pass_at_k(n, c, k))
            if values:
                table[f"pass@{k}"] = sum(values) / len(values)
        out[suite] = table
    return out


def judge(tasks, samples: str | pathlib.Path, out_dir: str | pathlib.Path, settings: JudgingSettings = CURRENT,
          *, workers: int | None = None, every_test: bool = True, per_test_rows: bool = False,
          completion_form: bool = False, cache_dir: str | pathlib.Path | None = None) -> dict[str, Any]:
    """Judge ``samples`` over ``tasks`` under ``settings``; returns the judging record written beside the verdicts.

    ``every_test`` runs every test of a suite (the per-test outcomes are then complete); ``False`` stops a suite
    at its first failing test, as the harness does by default. ``completion_form`` applies the typing prelude the
    settings name. ``cache_dir`` keeps the expected outputs between judgings of the same tasks.
    """
    from . import reference

    execute.set_start_method_fork()
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    probs = tasks_module.load_problems(tasks)
    rules_done = tasks_module.prepare(probs, settings)
    expected = {tid: reference.expected_outputs(p, cache_dir) for tid, p in probs.items()}
    _WORK.update(problems=probs, expected=expected, settings=settings, memory=memory_limit_bytes(settings),
                 completion_form=completion_form)
    jobs: list[tuple] = []
    counts: dict[str, int] = {}
    for sample in read_samples(samples):
        tid = sample["task_id"]
        if tid not in probs:
            print(f"samples carry a task the set does not: {tid}", file=sys.stderr)
            continue
        if "solution" in sample:
            solution = sample["solution"]
        else:
            solution = probs[tid]["prompt"] + sample["completion"]
        jobs.append((tid, counts.get(tid, 0), solution, every_test))
        counts[tid] = counts.get(tid, 0) + 1
    n_workers = workers or settings.workers
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for r in pool.map(_judge_attempt, jobs, chunksize=1):
            results.append(r)
    order = {tid: i for i, tid in enumerate(probs)}
    results.sort(key=lambda r: (order[r["task_id"]], r["attempt"]))
    eval_block: dict[str, list[dict[str, Any]]] = {tid: [] for tid in probs if tid in counts}
    stopped_by_limit: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for r in results:
        tid = r["task_id"]
        p = probs[tid]
        entry = {"task_id": tid, "solution": r["solution"]}
        limited = False
        for suite in ("base", "plus"):
            res = r[suite]
            entry[f"{suite}_status"] = res["status"]
            failing = res["failing"]
            entry[f"{suite}_fail_tests"] = [p[f"{suite}_input"][failing[0]]] if failing and res["status"] != execute.PASS else []
            if res["status"] == execute.TIMEOUT or (res["status"] != execute.PASS and res["time_outs"] and
                                                    all(c in "TPA" for c in res["outcomes"])):
                limited = True
            if per_test_rows and res["status"] != execute.PASS:
                rows.append({"task_id": tid, "attempt": r["attempt"], "suite": suite, "status": res["status"],
                             "outcomes": res["outcomes"], "time_outs": res["time_outs"],
                             "killed_at_cap": res["killed_at_cap"]})
        if limited:
            stopped_by_limit[tid] = stopped_by_limit.get(tid, 0) + 1
        eval_block[tid].append(entry)
    verdicts = {
        "date": datetime.date.today().isoformat(),
        "hash": tasks_module.set_hash(probs),
        "eval": eval_block,
        "pass_at_k": pass_at_k_table(eval_block),
    }
    with open(out_dir / "verdicts.json", "w", encoding="utf-8") as fh:
        json.dump(verdicts, fh)
    source_name = str(tasks) if str(tasks) in tasks_module.HARNESS_SETS else pathlib.Path(str(tasks)).name
    record = settings_module.describe(
        settings,
        task_source=source_name,
        set_hash=verdicts["hash"],
        n_tasks=len(eval_block),
        n_attempts=len(results),
        every_test=every_test,
        completion_form=completion_form,
        input_rules=rules_done,
        stopped_by_time_limit=stopped_by_limit,
        reference=settings.reference,
    )
    with open(out_dir / "judging.json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    if per_test_rows:
        per_test.write(rows, out_dir / "per_test.jsonl")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmr judge", description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", required=True, help="a task file (.jsonl or .jsonl.gz) or a harness set: humaneval, mbpp")
    parser.add_argument("--samples", required=True, help="samples.jsonl: one attempt per line, task_id and solution")
    parser.add_argument("--out", required=True, help="the output directory for verdicts.json, judging.json and per_test.jsonl")
    parser.add_argument("--settings", default=CURRENT.name, choices=sorted(settings_module.RECORDS))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--first-fail", action="store_true", help="stop a suite at its first failing test instead of running every test")
    parser.add_argument("--per-test", action="store_true", help="also write per_test.jsonl for the failing attempts")
    parser.add_argument("--completion-form", action="store_true", help="the attempts are a base model's completions: apply the typing prelude")
    parser.add_argument("--cache", default=None, help="a directory for the expected outputs, reused between judgings")
    args = parser.parse_args(argv)
    record = judge(args.tasks, args.samples, args.out, settings_module.RECORDS[args.settings], workers=args.workers,
                   every_test=not args.first_fail, per_test_rows=args.per_test, completion_form=args.completion_form,
                   cache_dir=args.cache)
    print(json.dumps({k: record[k] for k in ("settings_id", "n_tasks", "n_attempts", "stopped_by_time_limit")}))
    return 0

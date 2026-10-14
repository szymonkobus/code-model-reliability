"""The expected outputs of a task and the reference's time per test, computed from the reference solution.

For every test input the task's reference solution is run on the prompt plus the reference body, and its return
value and its elapsed time are kept: the values are what an attempt's outputs are compared with, the times set
the per-test limits. Each reference runs in a forked child, so whatever it changes in the process (a raised
recursion limit, a decimal context, a random seed, a replaced output stream) dies with the child instead of
reaching the judge or the next reference. For the harness's tasks whose outputs are only checked for being
``None`` or not, the expected value is that flag, as in the harness.

Reads nothing on disk. Writes, when a cache directory is given, one JSON file per task content hash, so a
second judging of the same tasks reuses the values and the times.

No ``from __future__ import annotations`` here either: the reference is compiled with ``dont_inherit`` so that
this module's flags never reach it (see ``execute``).
"""

import copy
import hashlib
import json
import multiprocessing
import pathlib
import time
from typing import Any

from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS

METHOD = "isolated"


def _reference_key(problem: dict[str, Any]) -> str:
    text = json.dumps(
        {k: problem.get(k) for k in ("task_id", "prompt", "canonical_solution", "entry_point", "base_input", "plus_input")},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_reference(code: str, inputs, entry_point: str, output_not_none: bool, conn) -> None:
    try:
        exec_globals: dict = {}
        exec(compile(code, "<reference>", "exec", dont_inherit=True), exec_globals)
        fn = exec_globals[entry_point]
        values, times = [], []
        for inp in inputs:
            inp = copy.deepcopy(inp)
            start = time.time()
            value = fn(*inp)
            times.append(time.time() - start)
            values.append(value is not None if output_not_none else value)
        conn.send(("ok", (values, times)))
    except BaseException as e:  # a reference that fails is a defect of the task, reported by the caller
        conn.send(("error", repr(e)[:500]))
    finally:
        conn.close()


def _in_child(code: str, inputs, entry_point: str, output_not_none: bool):
    ctx = multiprocessing.get_context("fork")
    rx, tx = ctx.Pipe(duplex=False)
    child = ctx.Process(target=_run_reference, args=(code, inputs, entry_point, output_not_none, tx))
    child.start()
    tx.close()
    try:
        status, value = rx.recv()
    except EOFError:
        status, value = "error", "the reference's process ended without a result"
    child.join()
    if status != "ok":
        raise RuntimeError(f"reference solution failed: {value}")
    return value


def expected_outputs(problem: "dict[str, Any]", cache_dir: "str | pathlib.Path | None" = None) -> "dict[str, Any]":
    """``{"base": values, "base_time": seconds, "plus": values, "plus_time": seconds}`` for one problem."""
    key = _reference_key(problem)
    cache_file = pathlib.Path(cache_dir) / f"{key}.json" if cache_dir else None
    if cache_file and cache_file.exists():
        with open(cache_file, encoding="utf-8") as fh:
            cached = json.load(fh)
        if cached.get("key") == key:
            return cached["expected"]
    code = problem["prompt"] + problem["canonical_solution"]
    not_none = problem["kind"] == "mbpp" and problem["entry_point"] in MBPP_OUTPUT_NOT_NONE_TASKS
    base, base_time = _in_child(code, problem["base_input"], problem["entry_point"], not_none)
    plus, plus_time = _in_child(code, problem["plus_input"], problem["entry_point"], not_none)
    expected = {"base": base, "base_time": base_time, "plus": plus, "plus_time": plus_time}
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = cache_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"key": key, "expected": expected}, fh, default=_json_default)
            tmp.replace(cache_file)
        except (TypeError, ValueError):
            pass  # an expected value JSON cannot carry (a set, a complex number) is recomputed next time
    return expected


def _json_default(value):
    raise TypeError(f"not JSON: {type(value).__name__}")

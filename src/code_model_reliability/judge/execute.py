"""Running one attempt against one suite of tests in the harness's sandbox, with an outcome per test.

This is the harness's evaluation of one program (its ``untrusted_check`` and ``unsafe_execute`` at the pinned
commit) written out with the comparison rule of ``compare`` in place of the bare ``==``, and with every test's
outcome recorded (the harness records a pass-or-fail flag). The program runs in a forked child under the
harness's own guard (a memory limit, destructive calls disabled, input and output swallowed, a temporary
working directory); each test gets its own time limit; the whole suite is killed at the set cap.

Outcomes per test: ``P`` pass, ``W`` wrong output, ``T`` time-out, ``E`` exception, ``A`` not run (the attempt
stopped at an earlier failure or was killed at the set cap). The attempt's status on the suite is the harness's:
``pass`` when every test passed, ``timeout`` when the child was killed at the set cap, ``fail`` otherwise.

Reads and writes nothing on disk; the child communicates through shared memory.

This module deliberately carries no ``from __future__ import annotations``: ``exec`` compiles the judged program
with the calling module's future flags, and deferred annotations would let a program whose signature names an
undefined type pass where the harness fails it at definition. The program is compiled with ``dont_inherit``
as well, so no flag of this module reaches it.
"""

import dataclasses
import multiprocessing
import os
import time
from typing import Any, Sequence

from evalplus.eval.utils import TimeoutException, create_tempdir, reliability_guard, swallow_io, time_limit

from . import compare

PASS, FAIL, TIMEOUT = "pass", "fail", "timeout"

_OUTCOME_CODES = {0: "A", 1: "P", 2: "W", 3: "T", 4: "E"}
_SUCCESS, _FAILED, _UNKNOWN = 0, 1, 3


@dataclasses.dataclass
class SuiteResult:
    """One attempt on one suite: the status, the outcome per test, and the per-test limits and elapsed times of
    the tests that failed on time (for the record of what the limit stopped)."""

    status: str
    outcomes: str
    time_limits: "list[float]"
    elapsed: "list[float | None]"
    set_cap_s: float
    killed_at_cap: bool

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def time_outs(self) -> "list[int]":
        return [i for i, c in enumerate(self.outcomes) if c == "T"]

    @property
    def failing_tests(self) -> "list[int]":
        return [i for i, c in enumerate(self.outcomes) if c in ("W", "T", "E")]


def time_limits_for(reference_times: Sequence[float], floor_s: float, factor: float) -> "list[float]":
    """The per-test limits: the floor, or the factor times the reference's own time on the test when larger."""
    return [max(floor_s, factor * t) for t in reference_times]


def _run_in_child(kind, entry_point, program, inputs, expected, limits, atol, stdin_stdout, stop_at_first,
                  memory_bytes, status, outcomes, elapsed, progress):
    """The judged program, in the forked child: define it, call it on every test, compare, record."""
    with create_tempdir():
        # These are needed to clean the temporary directory up after the guard disables them.
        import os as _os
        import shutil as _shutil

        rmtree, rmdir, chdir = _shutil.rmtree, _os.rmdir, _os.chdir
        reliability_guard(maximum_memory_bytes=memory_bytes)
        perf = time.perf_counter
        try:
            exec_globals: dict = {}
            code = compile(program, "<attempt>", "exec", dont_inherit=True)
            with swallow_io():
                exec(code, exec_globals)
                fn = exec_globals[entry_point]
            for i, inp in enumerate(inputs):
                t0 = perf()
                try:
                    with time_limit(limits[i]):
                        with swallow_io():
                            out = fn(*inp)
                    matched, atol = compare.outputs_match(kind, entry_point, out, expected[i], atol, inp, stdin_stdout)
                    outcomes[i] = 1 if matched else 2
                except TimeoutException:
                    outcomes[i] = 3
                except BaseException:
                    outcomes[i] = 4
                elapsed[i] = perf() - t0
                progress.value += 1
                if outcomes[i] != 1 and stop_at_first:
                    break
            status.value = _SUCCESS
        except BaseException:
            status.value = _FAILED
        _shutil.rmtree, _os.rmdir, _os.chdir = rmtree, rmdir, chdir


def run_suite(kind: str, entry_point: str, program: str, inputs: Sequence, expected: Sequence,
              reference_times: Sequence[float], atol: float, *, floor_s: float, factor: float, set_cap_s: "float | None",
              memory_bytes: "int | None", stdin_stdout: bool = False, stop_at_first: bool = False) -> SuiteResult:
    """Judge one program on one suite. ``inputs`` and ``expected`` are aligned lists; ``reference_times`` are the
    reference's seconds per test, which set the limits with the floor and the factor; ``set_cap_s`` caps the whole
    suite's limit where a record carries one, ``None`` leaves the summed limits alone."""
    limits = time_limits_for(reference_times, floor_s, factor)
    cap = (min(set_cap_s, sum(limits)) if set_cap_s is not None else sum(limits)) + 1.0
    if not stop_at_first:
        cap += 1.0  # the harness's extra second for collecting every test's outcome
    n = len(inputs)
    # Shared slots without a lock: the child is the only writer and the parent reads only after the child has
    # exited; a lock a dying child held at the kill would leave the parent waiting on it forever.
    status = multiprocessing.Value("i", _UNKNOWN, lock=False)
    progress = multiprocessing.Value("i", 0, lock=False)
    outcomes = multiprocessing.Array("b", [0] * n, lock=False)
    elapsed = multiprocessing.Array("d", [0.0] * n, lock=False)
    ctx = multiprocessing.get_context("fork")
    child = ctx.Process(
        target=_run_in_child,
        args=(kind, entry_point, program, list(inputs), list(expected), limits, atol, stdin_stdout, stop_at_first,
              memory_bytes, status, outcomes, elapsed, progress),
    )
    child.start()
    child.join(timeout=cap + 1.0)
    killed = False
    if child.is_alive():
        child.terminate()
        time.sleep(0.1)
    if child.is_alive():
        child.kill()
        time.sleep(0.1)
    if status.value == _UNKNOWN:
        killed = True
    codes = "".join(_OUTCOME_CODES[outcomes[i]] for i in range(n))
    if killed:
        result_status = TIMEOUT
    elif status.value == _SUCCESS and all(c == "P" for c in codes) and len(codes) == n:
        result_status = PASS
    else:
        result_status = FAIL
    per_test_elapsed = [elapsed[i] if outcomes[i] != 0 else None for i in range(n)]
    return SuiteResult(result_status, codes, limits, per_test_elapsed, cap, killed)


def judged_program(prompt: str, solution: str, leading_imports: bool, typing_prelude: bool) -> str:
    """The text the judge executes for one attempt under the import rules."""
    from .leading_imports import apply as apply_imports, apply_typing

    if typing_prelude:
        return apply_typing(prompt, solution, with_imports=leading_imports)
    if leading_imports:
        return apply_imports(prompt, solution)
    return solution


def set_start_method_fork() -> None:
    """The sandbox forks the judged child so it inherits the loaded modules; set once per process."""
    if multiprocessing.get_start_method(allow_none=True) not in (None, "fork"):
        raise RuntimeError("the judge needs the fork start method")
    if multiprocessing.get_start_method(allow_none=True) is None:
        multiprocessing.set_start_method("fork")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

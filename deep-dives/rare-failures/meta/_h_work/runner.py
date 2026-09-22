"""Sandboxed per-task executor for group H verification.

Reads a JSON payload on stdin:
  {prompt, canonical_solution, entry_point, atol, base_input, plus_input,
   shapes: {shape_id: code}}
Computes expected outputs from prompt+canonical_solution (deepcopied inputs),
then executes each shape in prompt context against every base+plus input with
evalplus unsafe_execute compare semantics (exact ==; atol/1e-6 allclose with
rtol 1e-7 and type/length asserts for floats; find_zero special oracle).
Sandbox: evalplus reliability_guard (4GB RLIMIT_AS), temp cwd, swallowed IO,
10s alarm per call, socket disabled, PYTHONHASHSEED=0 (set by driver).
Shapes with >5 timeouts abort remaining inputs.

Emits result JSON on the real stdout.
"""
import copy
import json
import sys

import numpy as np

from evalplus.eval import is_floats, query_maximum_memory_bytes
from evalplus.eval._special_oracle import _poly
from evalplus.eval.utils import (
    TimeoutException,
    create_tempdir,
    reliability_guard,
    swallow_io,
    time_limit,
)

CALL_TIMEOUT = 10  # seconds, per call


def compare(out, exp, entry_point, atol, inp):
    """evalplus unsafe_execute humaneval compare. Returns updated atol.
    Raises AssertionError on mismatch (caller counts it)."""
    exact_match = out == exp
    if entry_point == "find_zero":
        assert abs(_poly(*inp, out)) <= atol
        return atol
    if atol == 0 and is_floats(exp):
        atol = 1e-6  # enforce atol for float comparison
    if not exact_match and atol != 0:
        # explicitly set rtol=1e-07 to match np.testing.assert_allclose defaults
        assert type(out) == type(exp)
        if isinstance(exp, (list, tuple)):
            assert len(out) == len(exp)
        assert np.allclose(out, exp, rtol=1e-07, atol=atol)
    else:
        assert exact_match
    return atol


def main():
    payload = json.loads(sys.stdin.read())
    real_stdout = sys.stdout

    prompt = payload["prompt"]
    canonical = payload["canonical_solution"]
    entry_point = payload["entry_point"]
    task_atol = payload["atol"]
    inputs = [("base", inp) for inp in payload["base_input"]] + [
        ("plus", inp) for inp in payload["plus_input"]
    ]
    shapes = payload["shapes"]

    result = {"expected_errors": 0, "skipped_inputs": [], "shapes": {}}

    with create_tempdir():
        import os
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        chdir = os.chdir
        reliability_guard(maximum_memory_bytes=query_maximum_memory_bytes())
        import socket

        socket.socket = None  # no network

        # ---- ground truth from prompt + canonical_solution ----
        expected = []  # (ok, value)
        try:
            gt_globals = {}
            with swallow_io():
                exec(prompt + canonical, gt_globals)
            gt_fn = gt_globals[entry_point]
            for idx, (_, inp) in enumerate(inputs):
                try:
                    with time_limit(CALL_TIMEOUT):
                        with swallow_io():
                            val = gt_fn(*copy.deepcopy(inp))
                    expected.append((True, val))
                except BaseException:
                    expected.append((False, None))
                    result["expected_errors"] += 1
                    result["skipped_inputs"].append(idx)
        except BaseException as e:
            result["gt_exec_error"] = repr(e)
            expected = [(False, None)] * len(inputs)

        # ---- each shape ----
        for sid, code in shapes.items():
            sres = {
                "exec_error": None,
                "n_inputs": len(inputs),
                "n_run": 0,
                "n_pass": 0,
                "n_mismatch": 0,
                "n_crash": 0,
                "n_timeout": 0,
                "n_skipped_gt": 0,
                "aborted_after": None,
                "first_mismatch": None,
                "first_crash": None,
                "first_timeout": None,
            }
            result["shapes"][sid] = sres
            exec_globals = {}
            try:
                with swallow_io():
                    exec(prompt, exec_globals)
                    exec(code, exec_globals)
                fn = exec_globals[entry_point]
            except BaseException as e:
                sres["exec_error"] = repr(e)
                continue

            atol = task_atol
            for idx, (split, inp) in enumerate(inputs):
                ok, exp = expected[idx]
                if not ok:
                    sres["n_skipped_gt"] += 1
                    continue
                if sres["n_timeout"] > 5:
                    sres["aborted_after"] = idx
                    break
                sres["n_run"] += 1
                # call
                try:
                    with time_limit(CALL_TIMEOUT):
                        with swallow_io():
                            out = fn(*copy.deepcopy(inp))
                except TimeoutException:
                    sres["n_timeout"] += 1
                    if sres["first_timeout"] is None:
                        sres["first_timeout"] = {"split": split, "input": repr(inp)[:200]}
                    continue
                except BaseException as e:
                    sres["n_crash"] += 1
                    if sres["first_crash"] is None:
                        sres["first_crash"] = {
                            "split": split,
                            "input": repr(inp)[:200],
                            "error": repr(e)[:200],
                        }
                    continue
                # compare
                try:
                    atol = compare(out, exp, entry_point, atol, inp)
                except BaseException:
                    sres["n_mismatch"] += 1
                    if sres["first_mismatch"] is None:
                        sres["first_mismatch"] = {
                            "split": split,
                            "input": repr(inp)[:200],
                            "expected": repr(exp)[:200],
                            "got": repr(out)[:200],
                        }
                    continue
                sres["n_pass"] += 1

        shutil.rmtree = rmtree
        os.rmdir = rmdir
        os.chdir = chdir

    print(json.dumps(result), file=real_stdout)


if __name__ == "__main__":
    main()

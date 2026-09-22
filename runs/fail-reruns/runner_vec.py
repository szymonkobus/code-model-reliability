"""Per-(task) executor emitting FULL per-input outcome vectors.

Derived from rare-failures/meta/_j_work/runner.py (census semantics kept
bit-for-bit: prompt-context exec, 10s alarm/call, RLIMIT_AS via
EVALPLUS_MAX_MEMORY_BYTES/default 4GB, PYTHONHASHSEED=0 set by driver,
evalplus compare incl. special oracles, >5-timeouts abort). Changes:
  1. per-input outcome vector per shape: string of
     P=pass M=mismatch C=crash T=timeout S=skipped-gt A=aborted(not run)
  2. guarded repr (big-payload lane: never repr() objects with huge reprs)
  3. wall-time per shape recorded.
Payload adds optional "input_limit_bytes" (guard threshold, default 1MB).
"""
import re as _re
import copy
import json
import sys
import time

_TIME = time.time          # private refs: judged code may mutate shared modules
_JSON_DUMPS = json.dumps   # (e.g. time.time = None); the runner must not depend on them

import numpy as np

from evalplus.data.mbpp import mbpp_deserialize_inputs
from evalplus.eval import is_floats, query_maximum_memory_bytes
from evalplus.eval._special_oracle import (
    MBPP_OUTPUT_NOT_NONE_TASKS,
    MBPP_OUTPUT_SET_EQ_TASKS,
    _digit_distance_nums,
    _poly,
    _surface_Area,
)
from evalplus.eval.utils import (
    TimeoutException,
    create_tempdir,
    reliability_guard,
    swallow_io,
    time_limit,
)

CALL_TIMEOUT = 10  # seconds, per call (census harness semantics)


def safe_repr(obj, cap=200):
    """repr truncated WITHOUT materializing huge reprs for big containers."""
    try:
        if isinstance(obj, (list, tuple, set, dict)) and len(obj) > 50:
            it = list(obj.items())[:5] if isinstance(obj, dict) else list(obj)[:5]
            return f'<{type(obj).__name__} len={len(obj)} head={repr(it)[:cap]}>'
        return repr(obj)[:cap]
    except Exception:
        return '<unreprable>'


def compare_humaneval(out, exp, entry_point, atol, inp):
    exact_match = out == exp
    if entry_point == "find_zero":
        assert abs(_poly(*inp, out)) <= atol
        return atol
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if not exact_match and atol != 0:
        assert type(out) == type(exp)
        if isinstance(exp, (list, tuple)):
            assert len(out) == len(exp)
        assert np.allclose(out, exp, rtol=1e-07, atol=atol)
    else:
        assert exact_match
    return atol


def compare_mbpp(out, exp, entry_point, atol, inp):
    exact_match = out == exp
    if "are_equivalent" == entry_point:
        exact_match = exact_match or True
    elif "sum_div" == entry_point:
        exact_match = exact_match or out == 0
    elif "surface_Area" == entry_point:
        exact_match = exact_match or abs(out - _surface_Area(*inp)) <= atol
    elif "digit_distance_nums" == entry_point:
        exact_match = exact_match or out == _digit_distance_nums(*inp)
    elif entry_point in MBPP_OUTPUT_SET_EQ_TASKS:
        exact_match = set(out) == set(exp)
    elif entry_point in MBPP_OUTPUT_NOT_NONE_TASKS:
        if isinstance(out, bool):
            exact_match = out == exp
        else:
            exact_match = exp == (out is not None)
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if not exact_match and atol != 0:
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

    benchmark = payload["benchmark"]
    prompt = payload["prompt"]
    canonical = payload["canonical_solution"]
    entry_point = payload["entry_point"]
    task_atol = payload["atol"]
    compare = compare_humaneval if benchmark == "humaneval" else compare_mbpp
    output_not_none = (benchmark == "mbpp"
                       and entry_point in MBPP_OUTPUT_NOT_NONE_TASKS)
    base_input = payload["base_input"]
    plus_input = payload["plus_input"]
    if benchmark == "mbpp":
        tid = payload["task_id"]
        base_input = mbpp_deserialize_inputs(tid, base_input)
        plus_input = mbpp_deserialize_inputs(tid, plus_input)
    inputs = [("base", inp) for inp in base_input] + [
        ("plus", inp) for inp in plus_input
    ]
    shapes = payload["shapes"]

    # judge's imports-at-check transform (ONE shared implementation, repo file
    # preamble_transform.py shipped next to this runner): when the payload
    # carries preamble_rule, the executed program is apply(prompt, code) —
    # the prompt's leading import block + `from builtins import *` + code —
    # exactly as the judge grades it (single exec of the concatenated string).
    preamble_rule = payload.get("preamble_rule")
    if preamble_rule:
        import preamble_transform as _pt
        assert _pt.RULE == preamble_rule, f"preamble rule mismatch: {_pt.RULE} != {preamble_rule}"
        import hashlib as _hl
        transform_sha = _hl.sha256(open(_pt.__file__, "rb").read()).hexdigest()
    else:
        transform_sha = None
    result = {"expected_errors": 0, "skipped_inputs": [], "n_inputs": len(inputs),
              "n_base": len(payload["base_input"]),
              "semantics": (("preamble-v" + _re.match(r"leading-imports-v([0-9.]+)-", preamble_rule).group(1))
                            if preamble_rule and _re.match(r"leading-imports-v([0-9.]+)-", preamble_rule)
                            else ("preamble-" + preamble_rule if preamble_rule else "standalone-v2")),
              "inputs": payload.get("inputs_version", "original"),
              "transform_sha256": transform_sha,   # exact transform version the shapes ran under
              "shapes": {}}

    with create_tempdir():
        import os
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        chdir = os.chdir
        reliability_guard(maximum_memory_bytes=query_maximum_memory_bytes())
        import socket

        socket.socket = None  # no network
        try:

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
                        if output_not_none:
                            val = val is not None
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
              try:
                t_sh = _TIME()
                vec = []
                sres = {"exec_error": None, "vector": None, "wall_s": None,
                        "n_timeout": 0, "first_mismatch": None, "first_crash": None,
                        "first_timeout": None}
                result["shapes"][sid] = sres
                exec_globals = {}
                try:
                    with time_limit(CALL_TIMEOUT):
                        with swallow_io():
                            program = _pt.apply(prompt, code) if preamble_rule else code
                            exec(program, exec_globals)  # standalone exec of the judged program
                    fn = exec_globals[entry_point]
                except BaseException as e:
                    sres["exec_error"] = repr(e)[:300]
                    sres["wall_s"] = round(_TIME() - t_sh, 3)
                    continue

                atol = task_atol
                aborted = False
                for idx, (split, inp) in enumerate(inputs):
                    ok, exp = expected[idx]
                    if not ok:
                        vec.append("S")
                        continue
                    if aborted or sres["n_timeout"] > 5:
                        aborted = True
                        vec.append("A")
                        continue
                    try:
                        with time_limit(CALL_TIMEOUT):
                            with swallow_io():
                                out = fn(*copy.deepcopy(inp))
                    except TimeoutException:
                        sres["n_timeout"] += 1
                        vec.append("T")
                        if sres["first_timeout"] is None:
                            sres["first_timeout"] = {"split": split,
                                                     "input": safe_repr(inp)}
                        continue
                    except BaseException as e:
                        vec.append("C")
                        if sres["first_crash"] is None:
                            sres["first_crash"] = {"split": split,
                                                   "input": safe_repr(inp),
                                                   "error": repr(e)[:200]}
                        continue
                    try:
                        atol = compare(out, exp, entry_point, atol, inp)
                    except BaseException:
                        vec.append("M")
                        if sres["first_mismatch"] is None:
                            sres["first_mismatch"] = {"split": split,
                                                      "input": safe_repr(inp),
                                                      "expected": safe_repr(exp),
                                                      "got": safe_repr(out)}
                        continue
                    vec.append("P")
                sres["vector"] = "".join(vec)
                sres["wall_s"] = round(_TIME() - t_sh, 3)
              except BaseException as e:  # stray exception outside the per-call guards
                result["shapes"].pop(sid, None)
                result.setdefault("stray_errors", []).append({"shape": sid, "error": repr(e)[:200]})
                continue

        finally:
            # ALWAYS restore before tempdir teardown (a raising body used to
            # leave os.rmdir=None and the cleanup TypeError masked the cause);
            # free the (potentially huge) GT first so rmtree can allocate.
            expected = None
            exec_globals = None
            import gc
            gc.collect()
            shutil.rmtree = rmtree
            os.rmdir = rmdir
            os.chdir = chdir

    print(_JSON_DUMPS(result), file=real_stdout)


if __name__ == "__main__":
    main()

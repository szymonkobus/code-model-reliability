#!/usr/bin/env python3
import hashlib, inspect, numbers, sys, textwrap
ERA = "compare-numeric-tolerant-v2"; KNOB = "numeric-tolerant-v2"; RTOL = 1e-9
import numpy as _np
import evalplus.eval as _ev
import compare_normalize_patch as _v1

def _is_float(x): return isinstance(x, numbers.Real) and not isinstance(x, numbers.Integral) and not isinstance(x, bool)
def _is_int(x): return isinstance(x, numbers.Integral) and not isinstance(x, bool)

def num_eq(a, b, depth=0):
    if depth > 8: return a == b
    if (_is_float(a) and isinstance(b, numbers.Real) and not isinstance(b, bool)) or (_is_float(b) and isinstance(a, numbers.Real) and not isinstance(a, bool)):
        try: return bool(_np.isclose(float(a), float(b), rtol=RTOL, atol=0.0))
        except Exception: return a == b
    if _is_int(a) and _is_int(b): return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b): return False
        return all(num_eq(x, y, depth + 1) for x, y in zip(a, b))
    return a == b

def num_eq_exactfirst(a, b):
    try:
        if a == b: return True
    except Exception: pass
    return num_eq(a, b)

IMPL = "exactfirst-v1"

def apply():
    _v1.apply()   # normalized-v1 first: subclasses/numpy scalars → plain builtins, then the tolerant compare on the exact branch
    src = getattr(_ev, "_UNSAFE_EXECUTE_SRC", None) or textwrap.dedent(inspect.getsource(_ev.unsafe_execute))
    # the MAIN exact branch carries normalized-v1's call (v1 always applies first); the second `exact_match = out == exp` in the source is the
    # Mbpp OUTPUT_NOT_NONE special oracle's bool branch and stays exact
    needle = 'out = globals()["_norm_out"](out); exact_match = out == exp'
    assert src.count(needle) == 1, f"compare_numeric_patch: exact-branch needle found {src.count(needle)} times — evalplus/compare_normalize source changed, needs a look"
    new_src = src.replace(needle, 'out = globals()["_norm_out"](out); exact_match = globals()["_num_eq"](out, exp)')
    _ev._num_eq = num_eq_exactfirst; _ev._UNSAFE_EXECUTE_SRC = new_src
    _ev._num_eq_impl = IMPL
    exec(compile(new_src, "<compare_numeric_patch:unsafe_execute>", "exec"), vars(_ev))
    return ERA, hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16]

def _selftest():
    assert num_eq(752629165542741114880, 7.526291655427412e+20) and num_eq(7.526291655427412e+20, 752629165542741114880)
    assert num_eq(10**24, 1e24) and num_eq(1e200, 10**200) and num_eq([1, 2.0000000001], [1, 2]) and not num_eq([1, 2.001], [1, 2])
    assert not num_eq(10**24, 10**24 + 1) and not num_eq(2**53 + 1, 2**53) and num_eq(3, 3) and not num_eq(3, 4)
    assert num_eq("a", "a") and not num_eq("a", "b") and num_eq([1, [2, 3.0]], [1, [2, 3]]) and not num_eq([1, 2], [1, 2, 3]) and num_eq(True, True) and not num_eq(True, 1.0000001)
    assert num_eq(0.1 + 0.2, 0.3) and not num_eq(0.1, 0.10001)
    for x, y in ((752629165542741114880, 7.526291655427412e+20), ([1, 2.0000000001], [1, 2]), ([1, 2.001], [1, 2]), (10**24, 10**24 + 1), ("a", "b"), ([float("nan")], [float("nan")]), (float("inf"), float("inf")), (-0.0, 0.0)):
        assert num_eq_exactfirst(x, y) == num_eq(x, y), (x, y)
    import time as _t; big = [float(i) * 1.5 for i in range(10**6)]; t0 = _t.time(); assert num_eq_exactfirst(big, list(big)); assert _t.time() - t0 < 2.0, "exact-first path too slow"
    era, sha = apply(); assert "_num_eq" in _ev._UNSAFE_EXECUTE_SRC and "_norm_out" in _ev._UNSAFE_EXECUTE_SRC
    # end-to-end through untrusted_check: an integer answer against a float reference on an atol-0 problem passes; a wrong one fails
    r = _ev.untrusted_check("mbpp", "def f(l, b, h):\n    return l * b * h // 2\n", [[123456789, 987654321, 12345]], "f", expected=[7.526291655427412e+20], atol=0, ref_time=[0.01], fast_check=False, min_time_limit=1.0, gt_time_limit_factor=4.0)
    r2 = _ev.untrusted_check("mbpp", "def f(l, b, h):\n    return l * b * h // 2 + 10**12\n", [[123456789, 987654321, 12345]], "f", expected=[7.526291655427412e+20], atol=0, ref_time=[0.01], fast_check=False, min_time_limit=1.0, gt_time_limit_factor=4.0)
    r3 = _ev.untrusted_check("mbpp", "def f(n):\n    return 10 ** n\n", [[24]], "f", expected=[1e24], atol=0, ref_time=[0.01], fast_check=False, min_time_limit=1.0, gt_time_limit_factor=4.0)
    assert r[0] == "pass" and r2[0] == "fail" and r3[0] == "pass", (r[0], r2[0], r3[0])
    print(f'{{"selftest": "ok", "era": "{era}", "sha": "{sha}", "rtol": {RTOL}}}')

if __name__ == "__main__":
    if "--selftest" in sys.argv: _selftest()
    else: print(f'{{"era": "{ERA}", "knob": "{KNOB}", "sha": "{hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16]}"}}')

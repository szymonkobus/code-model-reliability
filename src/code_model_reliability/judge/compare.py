"""The comparison rule: when an attempt's output on one test counts as the expected output.

The harness compares with ``out == exp`` and, for float-valued tasks, a tolerance. Three additions make that
comparison depend on the value alone:

- the returned value is first **normalised** to plain builtins (a float subclass to float, a Counter to dict, a
  numpy scalar or array to int, float or list), so equality is decided by the builtins' own ``__eq__`` and never
  by a method the judged program defined; a value of a non-builtin type is unequal to everything;
- **numbers** compare with a relative tolerance of ``RTOL`` where a float meets a number (elementwise through
  lists and tuples of equal length); two integers compare exactly at any size; everything else compares with
  ``==``. An exact ``==`` is tried first, so a huge equal container is not walked in Python;
- a **stdin-stdout task** (a program reading its input text and returning its output text) compares the two
  texts after the same canonicalisation the expected outputs were produced with: line ends to ``\\n``, trailing
  whitespace stripped from each line, trailing blank lines dropped.

``outputs_match`` is the whole rule for one test: the normalisation and the number comparison, the harness's
special oracles for its own tasks (a set comparison, a not-None check, two numeric oracles), the harness's
float-tolerance branch, and the canonical stdout comparison. Reads and writes nothing.
"""

from __future__ import annotations

import numbers
from typing import Any

import numpy as np
from evalplus.eval import is_floats
from evalplus.eval._special_oracle import (
    MBPP_OUTPUT_NOT_NONE_TASKS,
    MBPP_OUTPUT_SET_EQ_TASKS,
    _digit_distance_nums,
    _poly,
    _surface_Area,
)

RTOL = 1e-9
"""Relative tolerance where a float meets a number: double rounding sits near 1e-16, so 1e-9 forgives rounding
and nothing a seven-digit answer could hide; an integer pair is never forgiven by one."""

RULE = "normalised-values, float tolerance 1e-9, canonical stdout"


class _Unequal:
    """Stands in for a returned value of a non-builtin type: unequal to everything, unusable in the tolerance branch."""

    __slots__ = ()

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __hash__(self):
        return 0

    def __bool__(self):
        return False

    def __repr__(self):
        return "<non-builtin return value>"

    def __iter__(self):
        raise TypeError("non-builtin return value")

    def __len__(self):
        raise TypeError("non-builtin return value")


UNEQUAL = _Unequal()
_SCALARS = (int, float, str, bool, bytes, complex, type(None))


def _plain(value) -> bool:
    """True for an exact builtin scalar, or an exact builtin container whose every element is plain."""
    t = type(value)
    if t in _SCALARS:
        return True
    if t is list or t is tuple or t is set or t is frozenset:
        return all(type(x) in _SCALARS or _plain(x) for x in value)
    if t is dict:
        return all((type(k) in _SCALARS or _plain(k)) and (type(v) in _SCALARS or _plain(v)) for k, v in value.items())
    return False


def normalize(value):
    """The value as plain builtins; a plain value is returned as is, a non-builtin object becomes ``UNEQUAL``."""
    if _plain(value):
        return value
    t = type(value)
    if t is list:
        return [normalize(x) for x in value]
    if t is tuple:
        return tuple(normalize(x) for x in value)
    if t is dict:
        return {normalize(k): normalize(v) for k, v in value.items()}
    if t is set or t is frozenset:
        return t(normalize(x) for x in value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, complex):
        return complex(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bytes):
        return bytes(value)
    if isinstance(value, dict):
        return {normalize(k): normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(x) for x in value]
    if isinstance(value, tuple):
        return tuple(normalize(x) for x in value)
    if isinstance(value, (set, frozenset)):
        return set(normalize(x) for x in value)
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, numbers.Complex):
        return complex(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist) and type(value).__module__.split(".")[0] == "numpy":
        try:
            return normalize(tolist())
        except Exception:
            return UNEQUAL
    return UNEQUAL


def _is_float(x) -> bool:
    return isinstance(x, numbers.Real) and not isinstance(x, numbers.Integral) and not isinstance(x, bool)


def _is_int(x) -> bool:
    return isinstance(x, numbers.Integral) and not isinstance(x, bool)


def numbers_equal(a, b, depth: int = 0) -> bool:
    """Equality with the float tolerance: tolerant where a float meets a number, exact for two integers,
    elementwise through lists and tuples of equal length, ``==`` for everything else."""
    if depth > 8:
        return a == b
    a_real = isinstance(a, numbers.Real) and not isinstance(a, bool)
    b_real = isinstance(b, numbers.Real) and not isinstance(b, bool)
    if (_is_float(a) and b_real) or (_is_float(b) and a_real):
        try:
            return bool(np.isclose(float(a), float(b), rtol=RTOL, atol=0.0))
        except Exception:
            return a == b
    if _is_int(a) and _is_int(b):
        return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(numbers_equal(x, y, depth + 1) for x, y in zip(a, b))
    return a == b


def values_equal(out, exp) -> bool:
    """``numbers_equal`` with an exact ``==`` tried first: an exact match is a tolerant match in every branch, and
    the exact comparison of a huge container runs in C where the recursive one would take minutes."""
    try:
        if out == exp:
            return True
    except Exception:
        pass
    return numbers_equal(out, exp)


def stdout_canonical(text: str) -> str:
    """The canonical form of an output text: CR LF and lone CR to LF, every line stripped of trailing whitespace,
    trailing blank lines dropped (so no final newline); leading whitespace, interior blank lines and case stay."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def outputs_match(kind: str, entry_point: str, out: Any, exp: Any, atol: float, inp, stdin_stdout: bool = False):
    """Whether ``out`` counts as ``exp`` on one test; returns ``(matched, atol)`` because the harness's float rule
    sets the tolerance to 1e-6 on the first float-valued test and keeps it for the attempt's later tests.

    ``kind`` is the harness's dataset kind (``humaneval`` for function tasks with a single reference, ``mbpp`` for
    the tasks with the special oracles); ``inp`` is the test's argument list, read by two oracles.
    """
    out = normalize(out)
    exact = values_equal(out, exp) or (
        stdin_stdout and isinstance(out, str) and isinstance(exp, str) and stdout_canonical(out) == stdout_canonical(exp)
    )
    if kind == "mbpp":
        if entry_point == "are_equivalent":
            exact = True
        elif entry_point == "sum_div":
            exact = exact or out == 0
        elif entry_point == "surface_Area":
            exact = exact or abs(out - _surface_Area(*inp)) <= atol
        elif entry_point == "digit_distance_nums":
            exact = exact or out == _digit_distance_nums(*inp)
        elif entry_point in MBPP_OUTPUT_SET_EQ_TASKS:
            exact = set(out) == set(exp)
        elif entry_point in MBPP_OUTPUT_NOT_NONE_TASKS:
            exact = out == exp if isinstance(out, bool) else exp == (out is not None)
    if kind == "humaneval" and entry_point == "find_zero":
        return abs(_poly(*inp, out)) <= atol, atol
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if not exact and atol != 0:
        if type(out) is not type(exp):
            return False, atol
        if isinstance(exp, (list, tuple)) and len(out) != len(exp):
            return False, atol
        return bool(np.allclose(out, exp, rtol=1e-07, atol=atol)), atol
    return bool(exact), atol

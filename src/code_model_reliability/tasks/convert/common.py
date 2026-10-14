"""What the two converters share: the literal parsers, the JSON-stability and float rules, the multi-answer screen,
the docstring escape and the sandboxed reference check.

A converted task is accepted only when the reference solution reproduces every kept expected output in an isolated
subprocess; the content it produces is byte-for-byte what the published pointer tasks were built from, so a rebuilt
record's content hash can be checked against the certified one.
"""

from __future__ import annotations

import ast
import json
import math
import re
import subprocess
import sys
from typing import Any

MIN_TESTS = 5
"""A task needs at least this many literal tests (examples and dataset tests together) to be converted."""

PER_TEST_TIMEOUT_S = 10.0
"""The reference's time limit per input at conversion time (generous: the judge applies its own limits later)."""

MEMORY_LIMIT_BYTES = 1536 * 1024 * 1024
"""The reference subprocess's address-space limit."""

OUTPUT_CAP = 4_000_000
"""A reference output longer than this is cut (a runaway print guard)."""

# A statement that lets a solver return any of several answers has no exact oracle; such a problem is routed out
# as "needs-human". Strong phrases flag wherever they stand; weak phrases flag outside the Examples and Note sections
# and yield to an adjacent tie-break clause ("...the lexicographically smallest"), which restores a unique answer.
# Letter-case licensing alone ("YES in any case") does not route a problem out.
_ANY_STRONG = [
    r"\b(?:print|output)\s+any\b(?!\s*(?:extra|additional|other|whitespace|space|leading|trailing))",
    r"\bany of them\b",
    r"\bany one of them\b",
    r"\bany of (?:these|those)\b",
    r"\bany of the (?:possible|valid|correct)?\s*(?:answers|solutions)\b",
    r"\bany such (?:answer|solution|sequence|array|string|arrangement|permutation|order(?:ing)?|pair|set|tree|graph|way)\b",
    r"\bany valid (?:answer|solution|sequence|array|string|arrangement|permutation|order(?:ing)?|pair|set|construction)\b",
    r"\bany (?:correct|possible) (?:answer|solution)\b",
    r"\b(?:answer|solution)s?\s+(?:is|are)\s+not\s+(?:necessarily\s+)?unique\b",
    r"\b(?:print|output)[^.\n]{0,80}\bin any order\b",
]
_ANY_WEAK = [
    r"\bif (?:there (?:are|exist)|it has)\s+(?:multiple|several|more than one)\b",
    r"\b(?:multiple|several)\s+(?:possible\s+)?(?:answers|solutions)\b",
]
# benchmark statements say "return ..." where contest statements say "print"
_ANY_RETURN = [
    r"\breturn[^.\n]{0,80}\bin any order\b",
    r"\breturn any\b(?!\s*(?:thing))",
    r"\bin any order\b",
]
_TIEBREAK_RE = re.compile(
    r"smallest|largest|lexicograph|minim(?:um|al|ize)|maxim(?:um|al|ize)|earliest|latest|shortest|longest|unique", re.I
)
_EX_HDR_RE = re.compile(r"^[ \t]*Examples?[ \t]*$", re.M)
_NOTE_RE = re.compile(r"^[ \t]*Note[ \t]*$", re.M)
_ANY_STRONG_RES = [re.compile(p, re.I) for p in _ANY_STRONG]
_ANY_WEAK_RES = [re.compile(p, re.I) for p in _ANY_WEAK]
_ANY_RETURN_RES = [re.compile(p, re.I) for p in _ANY_RETURN]


def _context(text: str, m: re.Match) -> str:
    lo = max(0, m.start() - 30)
    return "...%s..." % text[lo:m.end() + 30].replace("\n", " ").strip()


def _before_examples_and_note(description: str) -> str:
    """The statement cut at its Examples or Note heading, whichever comes first."""
    if not description:
        return ""
    cut = len(description)
    for rx in (_EX_HDR_RE, _NOTE_RE):
        m = rx.search(description)
        if m:
            cut = min(cut, m.start())
    return description[:cut]


def multi_answer_phrase(description: str) -> str | None:
    """The phrase that makes a statement multi-answer, with its context, or None when the statement has one answer."""
    text = description or ""
    for rx in _ANY_STRONG_RES:
        m = rx.search(text)
        if m:
            return _context(text, m)
    main = _before_examples_and_note(text)
    for rx in _ANY_WEAK_RES:
        m = rx.search(main)
        if m and not _TIEBREAK_RE.search(main[m.end():m.end() + 120]):
            return _context(main, m)
    for rx in _ANY_RETURN_RES:
        m = rx.search(text)
        if m:
            return _context(text, m)
    return None


def json_stable(value: Any) -> bool:
    """True when a value survives a JSON round-trip unchanged (the record is JSON lines)."""
    try:
        return json.loads(json.dumps(value)) == value
    except (TypeError, ValueError):
        return False


def has_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, (list, tuple)):
        return any(has_float(x) for x in value)
    if isinstance(value, dict):
        return any(has_float(x) for x in list(value.keys()) + list(value.values()))
    return False


def has_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return any(has_nonfinite(x) for x in value)
    if isinstance(value, dict):
        return any(has_nonfinite(x) for x in list(value.keys()) + list(value.values()))
    return False


_PY_LITERAL_FIX = (("true", "True"), ("false", "False"), ("null", "None"))


def parse_literal(text: str) -> Any:
    """``ast.literal_eval`` with the leniency LeetCode's JSON needs: true, false and null read as Python literals."""
    s = (text or "").strip()
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        pass
    t = s
    for a, b in _PY_LITERAL_FIX:
        t = re.sub(r"\b%s\b" % a, b, t)
    return ast.literal_eval(t)   # raises on a value that is not a literal


def parse_call_arguments(text: str, param_order: list[str]) -> list:
    """A LeetCode input string, ``nums = [3,3], target = 6`` or positional, as the argument list in parameter order.
    Raises on a value that is not a literal."""
    tree = ast.parse("_f(%s)" % text, mode="eval")
    call = tree.body
    if call.args and not call.keywords:
        return [ast.literal_eval(a) for a in call.args]
    kw = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
    if set(kw) != set(param_order):
        raise ValueError("keyword arguments %s do not match the parameters %s" % (sorted(kw), param_order))
    return [kw[p] for p in param_order]


def sanitize_doc(text: str) -> str:
    """The statement as it can stand inside a triple-quoted docstring."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


_CHILD_SOURCE = r'''
import json, signal, sys, resource, time

spec = json.load(sys.stdin)
try:
    resource.setrlimit(resource.RLIMIT_AS, (spec["mem_bytes"], spec["mem_bytes"]))
except (ValueError, OSError):
    pass

class _Timeout(Exception):
    pass

def _alarm(signum, frame):
    raise _Timeout()

signal.signal(signal.SIGALRM, _alarm)
namespace = {"__name__": "__conv__"}
try:
    exec(compile(spec["full_code"], "<task>", "exec"), namespace)
    fn = namespace[spec["entry_point"]]
except BaseException as e:
    print(json.dumps({"fatal": "%s: %s" % (type(e).__name__, e)}), flush=True)
    sys.exit(0)

for i, args in enumerate(spec["inputs"]):
    t0 = time.perf_counter()
    try:
        signal.setitimer(signal.ITIMER_REAL, spec["timeout"])
        out = fn(*args)
        signal.setitimer(signal.ITIMER_REAL, 0)
        if not isinstance(out, str):
            out = repr(out)
        if len(out) > spec["output_cap"]:
            out = out[:spec["output_cap"]]
        print(json.dumps({"i": i, "ok": True, "out": out, "t": round(time.perf_counter() - t0, 4)}), flush=True)
    except BaseException as e:
        signal.setitimer(signal.ITIMER_REAL, 0)
        err = "Timeout" if isinstance(e, _Timeout) else type(e).__name__
        print(json.dumps({"i": i, "ok": False, "err": err, "t": round(time.perf_counter() - t0, 4)}), flush=True)
'''


def run_reference(full_code: str, entry_point: str, inputs: list, timeout: float = PER_TEST_TIMEOUT_S) -> tuple[dict, str | None]:
    """Run the entry point on every input in an isolated subprocess with a memory limit and a per-input time limit.
    Returns the results by input index and a fatal error when the program did not even load."""
    spec = {"full_code": full_code, "entry_point": entry_point, "inputs": inputs, "timeout": timeout,
            "mem_bytes": MEMORY_LIMIT_BYTES, "output_cap": OUTPUT_CAP}
    budget = min(600, 30 + timeout * len(inputs) * 1.5)
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", _CHILD_SOURCE], input=json.dumps(spec),
                              capture_output=True, text=True, timeout=budget)
        out = proc.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
    results, fatal = {}, None
    for line in out.splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "fatal" in r:
            fatal = r["fatal"]
        else:
            results[r["i"]] = r
    return results, fatal


def run_and_compare(full_code: str, entry_point: str, inputs: list, expected: list,
                    timeout: float = PER_TEST_TIMEOUT_S) -> tuple[bool, list[int], list[str], float]:
    """The reference against the expected values. Returns (all equal, mismatching indices, errors, slowest input in
    seconds). A result that is not a string comes back as its repr and is compared after ``literal_eval``."""
    results, fatal = run_reference(full_code, entry_point, inputs, timeout)
    if fatal:
        return False, [], ["fatal: %s" % fatal[:120]], 0.0
    mismatches, errors, slowest = [], [], 0.0
    for i in range(len(inputs)):
        r = results.get(i)
        if r is None or not r.get("ok"):
            errors.append("test %d: %s" % (i, (r or {}).get("err", "missing")))
            continue
        slowest = max(slowest, r.get("t", 0))
        got_raw = r["out"]
        try:
            got = ast.literal_eval(got_raw)
        except (ValueError, SyntaxError):
            got = got_raw   # a plain string return
        if got != expected[i]:
            mismatches.append(i)
    return (not mismatches and not errors), mismatches, errors, slowest


def read_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path, rows) -> int:
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n

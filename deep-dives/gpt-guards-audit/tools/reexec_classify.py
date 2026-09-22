#!/usr/bin/env python3
"""Mechanical first-pass classification of a failed attempt by re-running the
extracted solution on the FIRST failing input the judge recorded.

Not a re-judge: verdicts stay as judged. This only asks WHY the attempt failed:
  import_crash      module-level exec fails (ImportError/SyntaxError/NameError...)
                    subtype impossible_typing_import when `from typing import int`-like
  entry_missing     module loads but the entry point is not defined
  guard_raise       the entry raises from an explicit `raise` statement in the model's
                    own code (a deliberate guard); message + guard line recorded
  incidental_raise  the entry raises but not from an explicit raise (a bug hit by the input)
  timeout           the call exceeds the per-call timeout
  wrong_value       the call returns a value different from the canonical solution's
  matches_canonical returns the canonical value on the recorded input (judge-side or
                    tolerance question; flagged for a manual look)
  no_failing_input  judge recorded a fail without an input (e.g. base-fail with no test)
Runs the model code in a subprocess with an address-space cap and SIGALRM timeout.
"""
import json, os, signal, subprocess, sys, tempfile, traceback, ast, re

WORKER = r'''
import json, signal, sys, io, contextlib, resource, traceback, math
resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
class CallTimeout(BaseException): pass
def _alarm(*a): raise CallTimeout()
signal.signal(signal.SIGALRM, _alarm)

def deep_eq(a, b, atol):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b and type(a) == type(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) or isinstance(b, float) or atol:
            try: return abs(a - b) <= max(atol or 1e-6, 1e-6 * max(1.0, abs(a), abs(b)))
            except Exception: return a == b
        return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(deep_eq(x, y, atol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_eq(a[k], b[k], atol) for k in a)
    return a == b

def run(job):
    res = {}
    g = {"__name__": "__solmod__"}
    src = job["program"]
    try:
        signal.alarm(10)
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src, "<sol>", "exec"), g)
        signal.alarm(0)
    except CallTimeout:
        return {"stage": "module_timeout"}
    except BaseException as e:
        signal.alarm(0)
        return {"stage": "module_error", "exc": type(e).__name__, "msg": str(e)[:300]}
    fn = g.get(job["entry"])
    if fn is None:
        return {"stage": "entry_missing"}
    if job.get("inputs") is None:
        return {"stage": "no_input"}
    inp = job["inputs"]
    try:
        signal.alarm(10)
        with contextlib.redirect_stdout(io.StringIO()):
            out = fn(*inp)
            if hasattr(out, "__iter__") and not isinstance(out, (list, str, dict, tuple, set, bytes)):
                out = list(out)
        signal.alarm(0)
    except CallTimeout:
        return {"stage": "timeout"}
    except BaseException as e:
        signal.alarm(0)
        tb = traceback.extract_tb(e.__traceback__)
        sol_frames = [f for f in tb if f.filename == "<sol>"]
        last = sol_frames[-1] if sol_frames else None
        line_txt = None
        if last is not None:
            lines = src.splitlines()
            if 1 <= last.lineno <= len(lines):
                line_txt = lines[last.lineno - 1].strip()
        return {"stage": "raised", "exc": type(e).__name__, "msg": str(e)[:300],
                "line": line_txt, "lineno": last.lineno if last else None,
                "explicit_raise": bool(line_txt and line_txt.startswith("raise")),
                "depth_in_sol": len(sol_frames)}
    exp = job.get("expected")
    try:
        got_json = json.loads(json.dumps(out, default=repr))
    except BaseException:
        got_json = repr(out)[:300]
    if exp is None:
        return {"stage": "returned", "got": got_json}
    try:
        same = deep_eq(out, exp["value"], job.get("atol"))
    except BaseException:
        same = False
    return {"stage": "returned", "got": got_json, "matches_canonical": same,
            "type_got": type(out).__name__, "type_exp": exp.get("type")}

import ast
for line in sys.stdin:
    job = json.loads(line)
    if job.get("inputs_repr") is not None:
        job["inputs"] = ast.literal_eval(job["inputs_repr"])
    if job.get("expected_repr") is not None and job.get("expected") is not None:
        job["expected"]["value"] = ast.literal_eval(job["expected_repr"])
    try:
        r = run(job)
    except BaseException as e:
        r = {"stage": "worker_error", "exc": type(e).__name__}
    r["key"] = job["key"]
    sys.stdout.write(json.dumps(r, default=repr) + "\n"); sys.stdout.flush()
'''

IMPOSSIBLE_TYPING = re.compile(r"from\s+typing\s+import\s+[^\n]*\b(int|float|str|bool|Integer|Integral|list|dict|set|tuple|complex)\b")

def classify(result, program):
    st = result.get("stage")
    if st == "module_error":
        sub = "impossible_typing_import" if (result.get("exc") == "ImportError" and IMPOSSIBLE_TYPING.search(program)) else result.get("exc")
        return "import_crash", sub
    if st == "module_timeout": return "timeout", "module"
    if st == "entry_missing": return "entry_missing", None
    if st == "no_input": return "no_failing_input", None
    if st == "timeout": return "timeout", "call"
    if st == "raised":
        if result.get("explicit_raise"): return "guard_raise", result.get("exc")
        return "incidental_raise", result.get("exc")
    if st == "returned":
        if result.get("matches_canonical"): return "matches_canonical", None
        return "wrong_value", None
    return "unresolved", st

def run_jobs(jobs, python=sys.executable):
    """jobs: list of dicts with key, program, entry, inputs (list or None), expected ({'value','type'} or None), atol."""
    out = {}
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as wf:
        wf.write(WORKER); wpath = wf.name
    try:
        # run in chunks so a wedged worker does not block everything
        CH = 200
        for i in range(0, len(jobs), CH):
            chunk = jobs[i:i+CH]
            with tempfile.TemporaryFile("w+") as fin, tempfile.TemporaryFile("w+") as fout, tempfile.TemporaryFile("w+") as ferr:
                for j in chunk:
                    jj = dict(j)
                    if jj.get('inputs') is not None: jj['inputs_repr'] = repr(jj['inputs'])
                    if jj.get('expected') is not None: jj['expected_repr'] = repr(jj['expected']['value'])
                    fin.write(json.dumps(jj, default=repr) + "\n")
                fin.flush(); fin.seek(0)
                p = subprocess.Popen([python, wpath], stdin=fin, stdout=fout, stderr=ferr, start_new_session=True)
                try:
                    p.wait(timeout=20 * len(chunk) + 30)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL); p.wait()
                fout.seek(0)
                for line in fout:
                    try: r = json.loads(line)
                    except Exception: continue
                    out[r["key"]] = r
            for j in chunk:
                if j["key"] not in out:
                    out[j["key"]] = {"stage": "worker_lost", "key": j["key"]}
    finally:
        os.unlink(wpath)
    return out

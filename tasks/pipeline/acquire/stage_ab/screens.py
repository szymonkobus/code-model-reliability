#!/usr/bin/env python3
"""Verdicts: "pass" | "flag" | "no-data" (screen has no evidence for this task).

Run on one task:   python3 screens.py --task HumanEval/6
Run on the pool:   python3 screens.py --all            (slow; Stage A driver
                   backtest.py is the intended entry point)
"""

import argparse
import ast
import copy
import csv
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys

# ---------------------------------------------------------------- constants

HOME = os.environ.get("EVALPLUS_HOME", os.path.expanduser("~"))
DATA_FILES = {
    "humaneval": os.path.join(HOME, ".cache/evalplus/HumanEvalPlus-v0.1.10.jsonl"),
    "mbpp": os.path.join(HOME, ".cache/evalplus/MbppPlus-v0.2.0.jsonl"),
}
FAIL_MATRIX = "results/per-task/fail_counts_matrix.csv"

STRONG_MODELS = [
    "claude-sonnet-5",
    "claude-sonnet-5-thinking",
    "deepseek-ai/DeepSeek-R1-0528",
    "deepseek-ai/DeepSeek-V3.2",
    "deepseek-ai/DeepSeek-V3.2-Thinking",
    "Qwen/Qwen3-32B-Thinking",
]
STRONG_FAIL_THRESHOLD = 0.99   # per-model fail rate that counts as "fails"

TIMEOUT_S = 1.0                # production per-test base time limit
RUNTIME_MARGIN = 10            # reference must be 10x faster than timeout
PAYLOAD_LIMIT = 1_000_000      # 1 MB flag on serialized inputs+outputs
PER_INPUT_TIMEOUT = 1.0        # runner SIGALRM per call
BATCH_TIMEOUT = 180            # hard cap per runner subprocess
RECURSION_PROBE_LIMIT = 260    # audit recursion limit (runner floor ~40)
RECURSION_PROBE_INPUTS = 20
CMP_INPUT_CAP = 300            # determinism/trivial comparison subset
MUTANT_INPUT_CAP = 60
MAX_MUTANTS = 16
MUTATION_KILL_MIN = 0.90       # suite must kill >=90% of mutants
MIN_TESTS = 5                  # coverage filter: >=5 tests ...
MIN_DISTINCT_OUTPUTS = 2       # ... producing >=2 distinct outputs
SEED = 20260826

KNOWN_MISSPELLINGS = {
    "seperate", "lenght", "recieve", "occurence", "occurences", "begining",
    "maximun", "minimun", "triangl", "adress", "charater", "charecter",
    "divisable", "divisble", "seperated", "consequtive", "concatinate",
    "substract", "postion", "runing", "smalest", "largst", "compair",
}

BANNED_MODULES = {"socket", "requests", "urllib", "http", "subprocess",
                  "random", "secrets"}
BANNED_CALLS = {"open", "input", "exec", "eval"}
BANNED_ATTRS = {("time", "time"), ("time", "clock"), ("time", "perf_counter"),
                ("datetime", "now"), ("datetime", "today"), ("date", "today"),
                ("os", "system"), ("os", "remove"), ("os", "popen"),
                ("random", "random"), ("random", "randint"),
                ("random", "choice"), ("random", "shuffle")}

# ------------------------------------------------------------------ runner
# Executed in a child process (python3 screens.py --runner). Reads one JSON
# spec on stdin: {entry_point, inputs, atol, per_input_timeout,
# candidates: [{name, code, recursion_limit?, input_indices?}]}
# Emits one JSON line per candidate as soon as it finishes, so a hard crash
# (segfault on deep C recursion, etc.) loses only the remaining candidates.


def _normalize(obj, atol):
    """Canonical, hash-seed-independent serialization of a return value."""
    if isinstance(obj, bool):
        return "b:%r" % obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return "f:nan"
        if atol and atol > 0:
            nd = max(0, -int(math.floor(math.log10(atol))))
            return "f:%s" % round(obj, nd)
        return "f:%r" % obj
    if isinstance(obj, int):
        return "i:%r" % obj
    if isinstance(obj, str):
        return "s:%r" % obj
    if obj is None:
        return "none"
    if isinstance(obj, (list, tuple)):   # list/tuple equal, as in production
        return "l:[%s]" % ",".join(_normalize(x, atol) for x in obj)
    if isinstance(obj, (set, frozenset)):
        return "set:{%s}" % ",".join(
            sorted(_normalize(x, atol) for x in obj))
    if isinstance(obj, dict):
        items = sorted((_normalize(k, atol), _normalize(v, atol))
                       for k, v in obj.items())
        return "d:{%s}" % ",".join("%s=%s" % kv for kv in items)
    return "o:%r" % (obj,)


def runner_main():
    import contextlib
    import io
    import signal
    import time

    spec = json.load(sys.stdin)
    inputs = spec["inputs"]
    ep = spec["entry_point"]
    atol = spec.get("atol") or 0
    per_t = spec.get("per_input_timeout", PER_INPUT_TIMEOUT)

    class _Timeout(Exception):
        pass

    def _alarm(signum, frame):
        raise _Timeout()

    signal.signal(signal.SIGALRM, _alarm)
    base_limit = sys.getrecursionlimit()

    for cand in spec["candidates"]:
        rec = {"name": cand["name"], "fatal": None, "results": []}
        gl = {"__name__": "__cand__"}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                signal.setitimer(signal.ITIMER_REAL, 10.0)
                exec(compile(cand["code"], "<cand>", "exec"), gl)
                signal.setitimer(signal.ITIMER_REAL, 0)
            fn = gl.get(ep)
            if not callable(fn):
                raise KeyError("entry point %r not defined" % ep)
        except BaseException as e:  # noqa: BLE001 - candidate code
            signal.setitimer(signal.ITIMER_REAL, 0)
            rec["fatal"] = "%s: %s" % (type(e).__name__, e)
            print(json.dumps(rec), flush=True)
            continue

        rl = cand.get("recursion_limit")
        if rl:
            sys.setrecursionlimit(rl)
        idxs = cand.get("input_indices")
        if idxs is None:
            idxs = range(len(inputs))
        for i in idxs:
            try:
                args = copy.deepcopy(inputs[i])
            except Exception:
                args = inputs[i]
            t0 = time.perf_counter()
            try:
                signal.setitimer(signal.ITIMER_REAL, per_t)
                with contextlib.redirect_stdout(io.StringIO()):
                    out = fn(*args)
                signal.setitimer(signal.ITIMER_REAL, 0)
                rec["results"].append(
                    {"i": i, "ok": True, "out": _normalize(out, atol),
                     "t": round(time.perf_counter() - t0, 6)})
            except BaseException as e:  # noqa: BLE001 - candidate code
                signal.setitimer(signal.ITIMER_REAL, 0)
                err = "Timeout" if isinstance(e, _Timeout) else type(e).__name__
                rec["results"].append(
                    {"i": i, "ok": False, "err": err,
                     "t": round(time.perf_counter() - t0, 6)})
        if rl:
            sys.setrecursionlimit(base_limit)
        print(json.dumps(rec), flush=True)


def run_candidates(task, candidates, per_input_timeout=PER_INPUT_TIMEOUT,
                   hashseed=0):
    """Run candidate solutions in a child process; tolerate hard crashes."""
    spec = {
        "entry_point": task["entry_point"],
        "inputs": task["_inputs"],
        "atol": task.get("atol") or 0,
        "per_input_timeout": per_input_timeout,
        "candidates": candidates,
    }
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed))
    out, timed_out = "", False
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--runner"],
            input=json.dumps(spec), capture_output=True, text=True,
            timeout=BATCH_TIMEOUT, env=env)
        out = proc.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        timed_out = True
    recs = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            recs[r["name"]] = r
        except json.JSONDecodeError:
            continue
    for cand in candidates:
        if cand["name"] not in recs:
            recs[cand["name"]] = {
                "name": cand["name"],
                "fatal": "batch-timeout" if timed_out else "runner-crash",
                "results": []}
    return recs


# ------------------------------------------------------------- pool loading


def load_pool():
    """Return {task_id: task-dict} for the full 542-task pool."""
    pool = {}
    for bench, path in DATA_FILES.items():
        with open(path) as f:
            for line in f:
                t = json.loads(line)
                t["_benchmark"] = bench
                t["_inputs"] = list(t.get("base_input") or []) + \
                    list(t.get("plus_input") or [])
                t["_n_base"] = len(t.get("base_input") or [])
                t["_full_code"] = t["prompt"] + t["canonical_solution"]
                pool[t["task_id"]] = t
    return pool


def load_fail_matrix():
    """{task_id: {model: (fails, n)}} — task ids like 'HumanEval/29'."""
    m = {}
    with open(FAIL_MATRIX) as f:
        for r in csv.DictReader(f):
            m.setdefault(r["task"], {})[r["model"]] = (
                int(r["fails"]), int(r["n"]))
    return m

# -------------------------------------------------------------- exec bundle


class Ctx:
    """Shared context: pool-wide indexes plus per-task cached executions."""

    def __init__(self, pool, fail_matrix=None):
        self.pool = pool
        self.fail_matrix = fail_matrix if fail_matrix is not None \
            else load_fail_matrix()
        self._exec = {}
        self._dup_index = None

    def dup_index(self):
        if self._dup_index is None:
            by_prompt, by_sol = {}, {}
            for tid, t in self.pool.items():
                pk = _norm_text(t["prompt"])
                sk = _norm_text(t["canonical_solution"])
                by_prompt.setdefault(pk, []).append(tid)
                by_sol.setdefault(sk, []).append(tid)
            self._dup_index = (by_prompt, by_sol)
        return self._dup_index

    def get_exec(self, task):
        tid = task["task_id"]
        if tid not in self._exec:
            self._exec[tid] = _execute_task(task)
        return self._exec[tid]


def _norm_text(s):
    return hashlib.sha256(re.sub(r"\s+", "", s).lower().encode()).hexdigest()


def _trivial_candidates(ep):
    exprs = ["None", "(args[0] if args else None)", "[]", "0", "''",
             "False", "True"]
    return [{"name": "trivial:%s" % e,
             "code": "def %s(*args, **kw):\n    return %s\n" % (ep, e)}
            for e in exprs]


# --- mutation generation (oracle screen: catches non-oracle test suites) ---

_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
             ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add,
             ast.Div: ast.Mult, ast.FloorDiv: ast.Div, ast.Mod: ast.Add}


def generate_mutants(full_code, max_mutants=MAX_MUTANTS, seed=SEED):
    """One-site AST mutants of the reference solution. Returns [(name, src)]."""
    try:
        tree = ast.parse(full_code)
    except SyntaxError:
        return []
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in _CMP_SWAP:
                    sites.append(("cmp", node, k))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            sites.append(("bin", node, None))
        elif isinstance(node, ast.BoolOp):
            sites.append(("bool", node, None))
        elif (isinstance(node, ast.Constant) and type(node.value) is int
              and not isinstance(node.value, bool)):
            sites.append(("int", node, None))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append(("not", node, None))
    rng = random.Random(seed)
    if len(sites) > max_mutants:
        sites = rng.sample(sites, max_mutants)
    mutants = []
    orig_norm = re.sub(r"\s+", "", full_code)
    for j, (kind, node, k) in enumerate(sites):
        saved = None
        if kind == "cmp":
            saved = node.ops[k]
            node.ops[k] = _CMP_SWAP[type(saved)]()
        elif kind == "bin":
            saved = node.op
            node.op = _BIN_SWAP[type(saved)]()
        elif kind == "bool":
            saved = node.op
            node.op = ast.Or() if isinstance(saved, ast.And) else ast.And()
        elif kind == "int":
            saved = node.value
            node.value = saved + 1
        try:
            if kind == "not":
                # fresh copy where the `not X` node is replaced by `X`
                src = ast.unparse(_ReplaceNode(node, node.operand).visit(
                    ast.parse(full_code)))
            else:
                src = ast.unparse(tree)
        except Exception:
            src = None
        # restore
        if kind == "cmp":
            node.ops[k] = saved
        elif kind in ("bin", "bool"):
            node.op = saved
        elif kind == "int":
            node.value = saved
        if src and re.sub(r"\s+", "", src) != orig_norm:
            mutants.append(("mutant:%d:%s" % (j, kind), src))
    return mutants


class _ReplaceNode(ast.NodeTransformer):
    """Replace the node equal (by position+type) to `target` with `repl`."""

    def __init__(self, target, repl):
        self._pos = (getattr(target, "lineno", None),
                     getattr(target, "col_offset", None))
        self._repl = repl

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and \
                (node.lineno, node.col_offset) == self._pos:
            return node.operand
        return node


def _execute_task(task):
    """Run canonical (x2 hash seeds), recursion probe, trivials, mutants."""
    n = len(task["_inputs"])
    rng = random.Random(SEED)
    cmp_idx = sorted(rng.sample(range(n), min(n, CMP_INPUT_CAP))) if n else []
    mut_idx = sorted(rng.sample(cmp_idx, min(len(cmp_idx), MUTANT_INPUT_CAP)))
    # recursion probe on the largest inputs (deep recursion bites there)
    by_size = sorted(range(n), key=lambda i: -len(repr(task["_inputs"][i])))
    rec_idx = sorted(by_size[:RECURSION_PROBE_INPUTS])

    code = task["_full_code"]
    batch1 = [{"name": "canonical", "code": code},
              {"name": "recursion_probe", "code": code,
               "recursion_limit": RECURSION_PROBE_LIMIT,
               "input_indices": rec_idx}]
    r1 = run_candidates(task, batch1, hashseed=0)
    r2 = run_candidates(
        task, [{"name": "canonical", "code": code, "input_indices": cmp_idx}],
        hashseed=1)
    triv = run_candidates(
        task, [dict(c, input_indices=cmp_idx)
               for c in _trivial_candidates(task["entry_point"])])
    mutants = generate_mutants(code)
    mut = run_candidates(
        task, [{"name": name, "code": src, "input_indices": mut_idx}
               for name, src in mutants],
        per_input_timeout=0.5) if mutants else {}
    return {"run1": r1.get("canonical"),
            "recursion": r1.get("recursion_probe"),
            "run2": r2.get("canonical"),
            "trivials": triv,
            "mutants": mut,
            "n_mutants": len(mutants),
            "cmp_idx": cmp_idx, "mut_idx": mut_idx, "rec_idx": rec_idx}


def _outmap(rec):
    return {r["i"]: r.get("out") for r in rec["results"] if r["ok"]}

# ------------------------------------------------------------------ screens
# Each screen: (task, ctx) -> {"screen","verdict","reason"}


def _res(name, verdict, reason=""):
    return {"screen": name, "verdict": verdict, "reason": reason}


def screen_reference_self_test(task, ctx):
    """Stage 0: reference solution passes its own tests (runs clean on
    every recorded input, no exception / timeout)."""
    r = ctx.get_exec(task)["run1"]
    if r["fatal"]:
        return _res("reference_self_test", "flag",
                    "canonical failed to load: %s" % r["fatal"])
    bad = [x for x in r["results"] if not x["ok"]]
    if bad:
        return _res("reference_self_test", "flag",
                    "canonical raised on %d/%d inputs (e.g. input %d: %s)"
                    % (len(bad), len(r["results"]), bad[0]["i"], bad[0]["err"]))
    if len(r["results"]) < len(task["_inputs"]):
        return _res("reference_self_test", "flag",
                    "canonical run incomplete (%d/%d inputs; batch timeout)"
                    % (len(r["results"]), len(task["_inputs"])))
    return _res("reference_self_test", "pass",
                "canonical clean on all %d inputs" % len(r["results"]))


def screen_determinism(task, ctx):
    """Stage 0: test results identical across repeated runs (two runs under
    different hash seeds; normalized outputs must match)."""
    ex = ctx.get_exec(task)
    o1, o2 = _outmap(ex["run1"]), _outmap(ex["run2"])
    common = [i for i in ex["cmp_idx"] if i in o1 and i in o2]
    if not common:
        return _res("determinism", "no-data", "no comparable outputs")
    diff = [i for i in common if o1[i] != o2[i]]
    if diff:
        return _res("determinism", "flag",
                    "outputs differ across runs on %d/%d inputs (first: %d)"
                    % (len(diff), len(common), diff[0]))
    return _res("determinism", "pass",
                "identical outputs across 2 runs on %d inputs" % len(common))


def screen_payload_size(task, ctx):
    """Stage 0: test inputs + expected outputs over 1MB are flagged."""
    size = sum(len(repr(x)) for x in task["_inputs"])
    size += sum(len(o) for o in _outmap(ctx.get_exec(task)["run1"]).values())
    if size > PAYLOAD_LIMIT:
        return _res("payload_size", "flag",
                    "serialized inputs+outputs = %.1f MB (> 1 MB)"
                    % (size / 1e6))
    return _res("payload_size", "pass", "payload %.0f KB" % (size / 1e3))


def screen_runtime_margin(task, ctx):
    """Stage 0: reference must run >=10x faster than the timeout."""
    r = ctx.get_exec(task)["run1"]
    times = [x["t"] for x in r["results"] if x["ok"]]
    if not times:
        return _res("runtime_margin", "no-data", "canonical never ran clean")
    worst = max(times)
    if worst > TIMEOUT_S / RUNTIME_MARGIN:
        return _res("runtime_margin", "flag",
                    "slowest reference input %.3fs > %.2fs (timeout/%d)"
                    % (worst, TIMEOUT_S / RUNTIME_MARGIN, RUNTIME_MARGIN))
    return _res("runtime_margin", "pass", "worst input %.4fs" % worst)


def screen_recursion_depth(task, ctx):
    """Stage 0: recursion depth audit — reference needing deep recursion
    (RecursionError at an audit limit the default judge exceeds) is flagged."""
    ex = ctx.get_exec(task)
    probe = ex["recursion"]
    if probe is None or probe["fatal"]:
        return _res("recursion_depth", "no-data",
                    "probe unavailable: %s"
                    % (probe["fatal"] if probe else "missing"))
    ok1 = {r["i"] for r in ex["run1"]["results"] if r["ok"]}
    hits = [r for r in probe["results"]
            if not r["ok"] and r["err"] == "RecursionError" and r["i"] in ok1]
    if hits:
        return _res("recursion_depth", "flag",
                    "RecursionError at audit limit %d on %d probe inputs "
                    "(clean at default limit) — deep recursion"
                    % (RECURSION_PROBE_LIMIT, len(hits)))
    return _res("recursion_depth", "pass",
                "no deep recursion on %d largest inputs"
                % len(probe["results"]))


def _contains_float(norm_str):
    return "f:" in norm_str


def screen_float_tolerance(task, ctx):
    """Stage 0: tasks returning floats need an explicit tolerance policy."""
    outs = _outmap(ctx.get_exec(task)["run1"])
    has_float = any(_contains_float(o) for o in outs.values())
    atol = task.get("atol") or 0
    if has_float and not atol:
        return _res("float_tolerance", "flag",
                    "outputs contain floats but atol=0 (exact float compare)")
    return _res("float_tolerance", "pass",
                "floats=%s atol=%s" % (has_float, atol))


_WORD_RE = re.compile(r"[a-z]+")


def screen_name_wellformedness(task, ctx):
    """Stage 0: entry point / prompt well-formedness — valid identifier,
    defined by the reference, present in the prompt, conventional casing,
    no known misspellings; prompt parses and is non-trivial."""
    ep = task["entry_point"]
    problems = []
    if not ep.isidentifier():
        problems.append("entry point %r is not a valid identifier" % ep)
    try:
        tree = ast.parse(task["_full_code"])
        defined = {n.name for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef)}
        if ep not in defined:
            problems.append("reference never defines %r" % ep)
    except SyntaxError as e:
        problems.append("prompt+canonical does not parse: %s" % e)
    if ep not in task["prompt"]:
        problems.append("entry point %r absent from prompt" % ep)
    if re.search(r"_[A-Z]", ep) or (ep != ep.lower() and "_" in ep):
        problems.append("mixed camelCase/underscore name %r" % ep)
    bad_words = sorted(set(_WORD_RE.findall(ep.lower())) & KNOWN_MISSPELLINGS)
    if bad_words:
        problems.append("known misspelling token(s) %s in name" % bad_words)
    if len(task["prompt"].strip()) < 30:
        problems.append("prompt under 30 chars")
    if problems:
        return _res("name_wellformedness", "flag", "; ".join(problems))
    return _res("name_wellformedness", "pass", "entry point %r clean" % ep)


def screen_duplicates(task, ctx):
    """Stage 0: duplicates are removed — flag tasks sharing a normalized
    prompt or normalized reference solution with another pool task."""
    by_prompt, by_sol = ctx.dup_index()
    tid = task["task_id"]
    twins = set(by_prompt[_norm_text(task["prompt"])]) | \
        set(by_sol[_norm_text(task["canonical_solution"])])
    twins.discard(tid)
    if twins:
        return _res("duplicates", "flag",
                    "shares prompt/solution with %s" % sorted(twins)[:3])
    return _res("duplicates", "pass", "no duplicate in pool")


def screen_trivial_solutions(task, ctx):
    """Stage 0 (degenerate-test detection): trivial do-nothing solutions
    must fail the tests — flag if any constant/identity stub matches the
    reference output on every compared input."""
    ex = ctx.get_exec(task)
    ref = _outmap(ex["run1"])
    idx = [i for i in ex["cmp_idx"] if i in ref]
    if not idx:
        return _res("trivial_solutions", "no-data", "no reference outputs")
    for name, rec in ex["trivials"].items():
        if rec["fatal"]:
            continue
        outs = _outmap(rec)
        if all(outs.get(i) == ref[i] for i in idx):
            return _res("trivial_solutions", "flag",
                        "%s passes all %d compared inputs" % (name, len(idx)))
    return _res("trivial_solutions", "pass",
                "all %d trivial stubs rejected" % len(ex["trivials"]))


def screen_output_diversity(task, ctx):
    """Stage 1 coverage filter: >=5 tests producing >=2 distinct outputs;
    a suite whose expected outputs are all identical is degenerate."""
    ref = _outmap(ctx.get_exec(task)["run1"])
    if not ref:
        return _res("output_diversity", "no-data", "no reference outputs")
    distinct = len(set(ref.values()))
    if len(task["_inputs"]) < MIN_TESTS:
        return _res("output_diversity", "flag",
                    "only %d tests (< %d)" % (len(task["_inputs"]), MIN_TESTS))
    if distinct < MIN_DISTINCT_OUTPUTS:
        return _res("output_diversity", "flag",
                    "all %d expected outputs identical" % len(ref))
    return _res("output_diversity", "pass",
                "%d tests, %d distinct outputs" % (len(ref), distinct))


def screen_io_purity(task, ctx):
    """Stage 0: tests may not touch network, filesystem, randomness, or the
    clock — AST scan of the reference for banned imports/calls."""
    try:
        tree = ast.parse(task["_full_code"])
    except SyntaxError:
        return _res("io_purity", "no-data", "code does not parse")
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += ["import %s" % a.name for a in node.names
                     if a.name.split(".")[0] in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in BANNED_MODULES:
                hits.append("from %s import ..." % node.module)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BANNED_CALLS:
                hits.append("%s()" % f.id)
            elif isinstance(f, ast.Attribute) and \
                    isinstance(f.value, ast.Name) and \
                    (f.value.id, f.attr) in BANNED_ATTRS:
                hits.append("%s.%s()" % (f.value.id, f.attr))
    if hits:
        return _res("io_purity", "flag",
                    "impure constructs: %s" % sorted(set(hits)))
    return _res("io_purity", "pass", "no network/fs/random/clock use")


def screen_mutation_adequacy(task, ctx):
    """Stage 1 oracle check: the suite must catch >=90% of plausibly wrong
    solutions — approximated by one-site AST mutants of the reference; a
    mutant is 'caught' if any compared input distinguishes it (different
    output, exception, or timeout). Equivalent mutants inflate flags; this
    is the expected-noisiest screen and is reported separately."""
    ex = ctx.get_exec(task)
    if ex["n_mutants"] == 0:
        return _res("mutation_adequacy", "no-data",
                    "no mutation sites in reference")
    ref = _outmap(ex["run1"])
    idx = [i for i in ex["mut_idx"] if i in ref]
    if not idx:
        return _res("mutation_adequacy", "no-data", "no reference outputs")
    killed = total = 0
    survivors = []
    for name, rec in ex["mutants"].items():
        total += 1
        if rec["fatal"]:
            killed += 1
            continue
        ok_out = _outmap(rec)
        # killed = any compared input where the mutant crashed, timed out,
        # went missing (batch crash), or returned a different output
        if any(i not in ok_out or ok_out[i] != ref[i] for i in idx):
            killed += 1
        else:
            survivors.append(name)
    rate = killed / total
    if rate < MUTATION_KILL_MIN:
        return _res("mutation_adequacy", "flag",
                    "suite kills %d/%d mutants (%.0f%% < %.0f%%); "
                    "survivors: %s"
                    % (killed, total, 100 * rate, 100 * MUTATION_KILL_MIN,
                       survivors[:3]))
    return _res("mutation_adequacy", "pass",
                "suite kills %d/%d mutants" % (killed, total))


def screen_strong_model_unanimous_failure(task, ctx):
    """Stage 2/4 behavioral screen: a task every strong model fails
    (>=99% fail rate each) is label-suspect until reviewed. Uses the
    recorded 128-attempt failure-count matrix."""
    row = ctx.fail_matrix.get(task["task_id"])
    if not row:
        return _res("strong_model_unanimous_failure", "no-data",
                    "task absent from fail_counts_matrix.csv")
    rates = {m: row[m][0] / row[m][1] for m in STRONG_MODELS if m in row}
    if not rates:
        return _res("strong_model_unanimous_failure", "no-data",
                    "no strong-panel models in matrix for this task")
    if all(r >= STRONG_FAIL_THRESHOLD for r in rates.values()):
        return _res("strong_model_unanimous_failure", "flag",
                    "all %d strong models fail >=%.0f%% (rates: %s)"
                    % (len(rates), 100 * STRONG_FAIL_THRESHOLD,
                       {m.split("/")[-1]: round(v, 3)
                        for m, v in rates.items()}))
    return _res("strong_model_unanimous_failure", "pass",
                "best strong model fails %.1f%%" % (100 * min(rates.values())))


MECHANICAL_SCREENS = [
    screen_reference_self_test,
    screen_determinism,
    screen_payload_size,
    screen_runtime_margin,
    screen_recursion_depth,
    screen_float_tolerance,
    screen_name_wellformedness,
    screen_duplicates,
    screen_trivial_solutions,
    screen_output_diversity,
    screen_io_purity,
]
ORACLE_SCREENS = [
    screen_mutation_adequacy,
    screen_strong_model_unanimous_failure,
]
ALL_SCREENS = MECHANICAL_SCREENS + ORACLE_SCREENS


def run_all_screens(task, ctx):
    return [screen(task, ctx) for screen in ALL_SCREENS]

# --------------------------------------------------------------------- cli


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runner", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--task", help="single task id, e.g. HumanEval/6")
    ap.add_argument("--all", action="store_true", help="run on full pool")
    args = ap.parse_args()

    if args.runner:
        runner_main()
        return
    pool = load_pool()
    ctx = Ctx(pool)
    if args.task:
        tids = [args.task]
    elif args.all:
        tids = sorted(pool)
    else:
        ap.error("give --task ID or --all")
    for tid in tids:
        for r in run_all_screens(pool[tid], ctx):
            print("%-12s %-32s %-7s %s"
                  % (tid, r["screen"], r["verdict"], r["reason"]))


if __name__ == "__main__":
    main()

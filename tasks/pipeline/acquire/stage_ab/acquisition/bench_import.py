#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyarrow>=15", "huggingface_hub>=0.23"]
# ///
"""LiveCodeBench v6 is handled by a separate join pass (it ships no
reference solutions; references are joined from LeetCodeDataset /
open-r1 submissions) — not in this file yet.

House record shape mirrors convert.py's contract (consumed unmodified by
../screens.py): {task_id, prompt, entry_point, canonical_solution,
base_input, plus_input, atol, expected_output, provenance, conversion}.
Typed argument lists / return values are native to the screens
normalizer; everything stored must survive a JSON round-trip, and a
candidate converts ONLY if the reference reproduces every kept expected
value in a sandboxed subprocess (reusing convert.run_reference).
"""

import argparse
import ast
import base64
import json
import math
import os
import re
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import convert as houseconv   # run_reference, detect_any_of_them, canon

MIN_TESTS = 5

# benchmark statements say "return ..." where contest ones say "print"
_BENCH_ANY_RES = [re.compile(p, re.I) for p in (
    r"\breturn[^.\n]{0,80}\bin any order\b",
    r"\breturn any\b(?!\s*(?:thing))",
    r"\bin any order\b",
)]


def bench_any_of_them(description):
    rec = {"statement": {"description": description or "",
                         "output_format": None, "note": None}}
    hit = houseconv.detect_any_of_them(rec)
    if hit and hit[0] == "multi":
        return hit[1]
    for rx in _BENCH_ANY_RES:
        m = rx.search(description or "")
        if m:
            return houseconv._ctx(description, m)
    return None


BASE_PROMOTE_K = 2


def ensure_base(base_in, base_exp, plus_in, plus_exp, warnings):
    if not base_in and len(plus_in) > BASE_PROMOTE_K:
        base_in[:] = plus_in[:BASE_PROMOTE_K]
        base_exp[:] = plus_exp[:BASE_PROMOTE_K]
        del plus_in[:BASE_PROMOTE_K]
        del plus_exp[:BASE_PROMOTE_K]
        warnings.append("base_input = first %d official tests promoted "
                        "(no statement examples extractable)"
                        % BASE_PROMOTE_K)
    if not base_in or not plus_in:
        raise ValueError("empty base_input or plus_input after split "
                         "(base %d, plus %d)" % (len(base_in), len(plus_in)))


def _json_ok(v):
    try:
        json.dumps(v, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _json_stable(v):
    """True if v survives a JSON round-trip unchanged (house jsonl safety)."""
    try:
        return json.loads(json.dumps(v)) == v
    except (TypeError, ValueError):
        return False


def _has_float(v):
    if isinstance(v, float):
        return True
    if isinstance(v, (list, tuple)):
        return any(_has_float(x) for x in v)
    if isinstance(v, dict):
        return any(_has_float(x) for x in list(v.keys()) + list(v.values()))
    return False


def _has_nonfinite(v):
    if isinstance(v, float):
        return not math.isfinite(v)
    if isinstance(v, (list, tuple)):
        return any(_has_nonfinite(x) for x in v)
    if isinstance(v, dict):
        return any(_has_nonfinite(x)
                   for x in list(v.keys()) + list(v.values()))
    return False


_PY_LITERAL_FIX = (("true", "True"), ("false", "False"), ("null", "None"))


def parse_literal(s):
    """ast.literal_eval with LeetCode-JSON leniency (true/false/null)."""
    s = (s or "").strip()
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        pass
    t = s
    for a, b in _PY_LITERAL_FIX:
        t = re.sub(r"\b%s\b" % a, b, t)
    return ast.literal_eval(t)      # raises on genuine non-literals


def parse_kwarg_call(s, param_order):
    """LeetCode input string 'nums = [3,3], target = 6' -> positional list
    ordered by param_order. Raises on non-literal values."""
    tree = ast.parse("_f(%s)" % s, mode="eval")
    call = tree.body
    if call.args and not call.keywords:
        return [ast.literal_eval(a) for a in call.args]
    kw = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
    if set(kw) != set(param_order):
        raise ValueError("kwargs %s != params %s" % (sorted(kw),
                                                     param_order))
    return [kw[p] for p in param_order]


def run_and_compare(full_code, entry_point, inputs, expected, timeout=10.0):
    """Sandbox-run entry_point on inputs; compare to expected values.
    Returns (ok_all, mismatches, errors, max_t). Child returns repr() for
    non-str results; compare via literal_eval when possible."""
    saved = houseconv.ENTRY_POINT
    houseconv.ENTRY_POINT = entry_point
    try:
        res, fatal = houseconv.run_reference(full_code, inputs, timeout)
    finally:
        houseconv.ENTRY_POINT = saved
    if fatal:
        return False, [], ["fatal: %s" % fatal[:120]], 0.0
    mism, errs, tmax = [], [], 0.0
    for i in range(len(inputs)):
        r = res.get(i)
        if r is None or not r.get("ok"):
            errs.append("test %d: %s" % (i, (r or {}).get("err", "missing")))
            continue
        tmax = max(tmax, r.get("t", 0))
        got_raw = r["out"]
        exp = expected[i]
        try:
            got = ast.literal_eval(got_raw)
        except (ValueError, SyntaxError):
            got = got_raw          # plain string return
        if got != exp:
            mism.append(i)
    return (not mism and not errs), mism, errs, tmax


# ------------------------------------------------------------- leetcode

_CONSTRAINTS_HDR_RE = re.compile(r"Constraints:?", re.I)
_LOST_SUP_RE = re.compile(r"\b10(1[0-8]|[2-9])\b")


def repair_lost_superscripts(desc):
    """Return (repaired_text, n_repairs)."""
    m = _CONSTRAINTS_HDR_RE.search(desc or "")
    if not m:
        return desc, 0
    head, block = desc[:m.start()], desc[m.start():]
    stop = re.search(r"\n\s*(?:Follow[- ]up|Note)\b", block)
    tail = ""
    if stop:
        block, tail = block[:stop.start()], block[stop.start():]
    fixed, n = _LOST_SUP_RE.subn(r"10^\1", block)
    return head + fixed + tail, n


LC_EXAMPLE_RE = re.compile(
    r"Input:?\s*(.+?)\s*Output:?\s*(.+?)(?=\s*(?:Explanation|Example|"
    r"Constraints|Note|Follow-up|$))", re.S)
STRUCT_TYPES_RE = re.compile(
    r"\b(ListNode|TreeNode|Node|GraphNode)\b")


def leetcode_signature(starter_code, fname):
    """Return (param_names, def_line) from the starter's Solution method.
    LeetCode starters ship the method with an EMPTY body, which ast.parse
    rejects — extract the def header by bracket matching and parse
    'header: pass' instead when needed."""
    try:
        tree = ast.parse(starter_code)
    except (SyntaxError, IndentationError):
        i = starter_code.find("def %s" % fname)
        if i < 0:
            raise ValueError("def %s not found in starter" % fname)
        depth = 0
        j = i
        while j < len(starter_code):
            ch = starter_code[j]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                break
            j += 1
        header = re.sub(r"\s+", " ", starter_code[i:j + 1])
        tree = ast.parse("%s\n    pass" % header)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            params = [a.arg for a in node.args.args if a.arg != "self"]
            src = ast.unparse(node)
            header = src.split("\n", 1)[0]          # def f(self, ...) ...:
            header = header.replace("(self, ", "(").replace("(self)", "()")
            return params, header
    raise ValueError("method %s not found in starter" % fname)


# power forms FIRST: a plain-digits alternative would match the "10" of
# "10^9" and stop (measured: 55 false positives on the live scan)
_NUM = r"(?:-?\d[\d,]*\s*\*\s*10\^\d+|10\^\d+|-?\d[\d,]*(?!\s*\^))"
# either side may be SYMBOLIC (another parameter, e.g. "1 <= k <= m" — audit
# wave-2, leetcode/properties-graph k=0): the numeric side is still checked
# and a symbolic side is skipped.
_SYM = r"[A-Za-z_]\w*(?:\.length)?"
_BOUND_RE = re.compile(
    r"(" + _NUM + r"|" + _SYM + r")\s*(<=|<)\s*([A-Za-z_]\w*)\s*(<=|<)\s*(" + _NUM + r"|" + _SYM + r")")


def _num(tok):
    tok = tok.replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(-?\d+)\*10\^(\d+)", tok)
    if m:
        return int(m.group(1)) * 10 ** int(m.group(2))
    m = re.fullmatch(r"10\^(\d+)", tok)
    if m:
        return 10 ** int(m.group(1))
    return int(tok)


def scalar_bound_violations(desc, params, inputs):
    """Class 2a for LeetCode (audit wave-2, calculate-delayed-arrival-time:
    plus input arrivalTime=24 vs the stated 1 <= arrivalTime < 24). Parse
    Constraints lines of the form `lo <= name <= hi` / `lo <= name < hi`
    for SCALAR int parameters and check each input; reported as WARNINGS."""
    ci = desc.find("Constraints")
    if ci < 0:
        return []
    block = desc[ci:]
    bounds = {}
    # constraint lines may spell the parameter in a different case
    # (dataset text: "1 <= arrivaltime < 24" for arrivalTime)
    by_lower = {p.lower(): p for p in params}
    for m in _BOUND_RE.finditer(block):
        lo, op1, name, op2, hi = m.groups()
        pname = by_lower.get(name.lower())
        if pname:
            def _side(tok):
                try:
                    return _num(tok)
                except ValueError:
                    return None      # symbolic side: not checked
            lo_v, hi_v = _side(lo), _side(hi)
            if lo_v is None and hi_v is None:
                continue
            bounds[pname] = (lo_v, op1, op2, hi_v, lo.strip(), hi.strip())
    if not bounds:
        return []
    out = []
    for i, args in enumerate(inputs):
        for name, val in zip(params, args):
            if name not in bounds or isinstance(val, bool) or not isinstance(val, int):
                continue
            lo, op1, op2, hi, lo_txt, hi_txt = bounds[name]
            ok_lo = True if lo is None else ((val >= lo) if op1 == "<=" else (val > lo))
            ok_hi = True if hi is None else ((val <= hi) if op2 == "<=" else (val < hi))
            if not (ok_lo and ok_hi):
                out.append("input %d: %s=%s violates stated %s %s %s %s %s"
                           % (i, name, val, lo_txt, op1, name, op2, hi_txt))
    return out[:8]


_STAR_IMPORT_RE = re.compile(r"^from\s+([A-Za-z_][\w.]*)\s+import\s+\*\s*$", re.M)


def bind_star_modules(preamble):
    """LeetCode's real prelude binds module names; the dataset header only
    star-imports them, so `heapq.heappop(...)` raises NameError under our
    judge (audit wave-2, take-gifts-from-the-richest-pile: 26 attempts).
    Add `import X` for every `from X import *` that lacks a plain import."""
    mods = _STAR_IMPORT_RE.findall(preamble or "")
    add = [m for m in dict.fromkeys(mods)
           if not re.search(r"^import\s+%s\b" % re.escape(m), preamble, re.M)]
    if not add:
        return preamble, 0
    lines = (preamble or "").splitlines()
    last_import = -1
    for i, l in enumerate(lines):
        if re.match(r"^(import|from)\s", l):
            last_import = i
        elif l.strip() and not l.lstrip().startswith("#"):
            break
    ins = ["import %s" % m for m in add]
    if last_import < 0:
        return "\n".join(ins + lines) + "\n", len(add)
    lines[last_import + 1:last_import + 1] = ins
    return "\n".join(lines) + "\n", len(add)


_RET_ANN_RE_T = r"def\s+%s\s*\([^)]*\)\s*->\s*([^:\n]+):"


def return_annotation_forbids_none(starter_code, fname):
    """True when the starter's return annotation is present and cannot be
    None (no Optional/None/Any/object in it). Absent annotation -> False."""
    m = re.search(_RET_ANN_RE_T % re.escape(fname), starter_code or "")
    if not m:
        return False
    ann = m.group(1).strip()
    return not re.search(r"\b(Optional|None|Any|object)\b", ann)


_HELPER_NAMES = ("ListNode", "TreeNode", "list_node", "tree_node", "is_same_list", "is_same_tree")


def trim_unused_helpers(preamble, starter_code, completion):
    """LeetCodeDataset's prelude carries ListNode/TreeNode classes plus four
    list/tree helpers (60 of its 76 lines). Structure-typed signatures are
    rejected at intake, so no converted task can use them, yet completion-
    style arms echo the whole prompt and lose ~450 tokens of budget to dead
    code (task-audit wave-3, lcb/find-special-substring-of-length-k). Cut the
    preamble at the first helper definition when neither the starter nor the
    completion names a helper; imports and `inf = float('inf')` stay.
    Returns (preamble, chars_trimmed)."""
    text = (starter_code or "") + "\n" + (completion or "")
    if any(n in text for n in _HELPER_NAMES):
        return preamble, 0
    m = re.search(r"^class (?:ListNode|TreeNode)\b", preamble or "", re.M)
    if not m:
        return preamble, 0
    kept = preamble[:m.start()].rstrip() + "\n"
    return kept, len(preamble) - len(kept)


def convert_leetcode(rec):
    m = {"source": "leetcode"}
    desc = rec.get("problem_description") or ""
    slug = rec.get("task_id")

    anyof = bench_any_of_them(desc)
    m["any_of_them"] = anyof
    if anyof:
        return ("needs-human", "any-of-them statement (multi-answer): "
                "exact oracle unsound. Matched: %s" % anyof[:140], None, m)
    if STRUCT_TYPES_RE.search(rec.get("starter_code") or ""):
        return ("rejected", "structure-typed signature (ListNode/TreeNode) "
                "— not literal-representable", None, m)

    ep = (rec.get("entry_point") or "").strip()
    fname = ep.split(".")[-1].split("(")[0]
    try:
        params, header = leetcode_signature(rec["starter_code"], fname)
    except (ValueError, SyntaxError) as e:
        return "needs-human", "starter parse failed: %s" % e, None, m

    completion = rec.get("completion") or ""
    if "class Solution" not in completion:
        return ("needs-human", "completion is not a Solution class", None, m)

    # plus set: dataset input_output pairs
    plus_in, plus_exp, dropped = [], [], 0
    seen_args = set()   # exact duplicate inputs (audit wave-2: 8 of 90 on
    ret_forbids_none = return_annotation_forbids_none(rec.get("starter_code") or "", fname)
    dropped_none = 0
    for io in rec.get("input_output") or []:
        try:
            args = parse_kwarg_call(io["input"], params)
            exp = parse_literal(io["output"])
        except (ValueError, SyntaxError, KeyError):
            dropped += 1
            continue
        if exp is None and ret_forbids_none:
            dropped_none += 1
            continue
        if _has_nonfinite(args) or _has_nonfinite(exp):
            return ("rejected", "non-finite float (NaN/inf) in tests — "
                    "does not JSON-round-trip / self-compares false",
                    None, m)
        if not _json_stable(args) or not _json_stable(exp):
            dropped += 1
            continue
        akey = json.dumps(args, sort_keys=True)
        if akey in seen_args:
            dropped += 1
            continue
        seen_args.add(akey)
        plus_in.append(args)
        plus_exp.append(exp)

    # base set: examples parsed out of the statement text
    base_in, base_exp, ex_bad = [], [], 0
    for mm in LC_EXAMPLE_RE.finditer(desc):
        try:
            args = parse_kwarg_call(mm.group(1), params)
            exp = parse_literal(mm.group(2))
        except (ValueError, SyntaxError):
            ex_bad += 1
            continue
        if not _json_stable(args) or not _json_stable(exp):
            ex_bad += 1
            continue
        key = json.dumps(args)
        drop = None
        for j, a in enumerate(plus_in):
            if json.dumps(a) == key:
                drop = j
                break
        if drop is not None:
            del plus_in[drop], plus_exp[drop]
        base_in.append(args)
        base_exp.append(exp)
    m.update(n_base=len(base_in), n_plus=len(plus_in),
             n_dropped_nonliteral=dropped, n_example_parse_fail=ex_bad,
             n_dropped_none_expected=dropped_none)

    if len(base_in) + len(plus_in) < MIN_TESTS:
        return ("rejected", "only %d literal tests" %
                (len(base_in) + len(plus_in)), None, m)
    if any(_has_float(v) for v in base_exp + plus_exp):
        return ("rejected", "float expected values: atol=0 exact equality "
                "is the pinned judge semantics; "
                "tolerance-defined tasks cannot ride the pinned judge",
                None, m)
    warnings = []
    if dropped_none:
        warnings.append("dropped %d dataset IO pair(s) whose expected output "
                        "is None against a return annotation that excludes "
                        "None (reference fell through: guarantee-violating "
                        "inputs, out of domain by construction)" % dropped_none)
    try:
        ensure_base(base_in, base_exp, plus_in, plus_exp, warnings)
    except ValueError as e:
        return "rejected", str(e), None, m

    desc, n_sup = repair_lost_superscripts(desc)
    m["superscripts_repaired"] = n_sup
    preamble, n_trim = trim_unused_helpers((rec.get("prompt") or "").rstrip(),
                                           rec.get("starter_code"), completion)
    m["preamble_trimmed_chars"] = n_trim
    preamble, n_bound = bind_star_modules(preamble.rstrip())
    m["star_modules_bound"] = n_bound
    prompt = "%s\n%s\n    \"\"\"%s\n    \"\"\"\n" % (
        preamble.rstrip(), header,
        houseconv._sanitize_doc(desc).replace("\n", "\n    "))
    call_args = ", ".join(params)
    body_lines = ["    %s" % l if l.strip() else ""
                  for l in completion.split("\n")]
    canonical = "\n".join(body_lines).rstrip() + (
        "\n    return Solution().%s(%s)\n" % (fname, call_args))

    inputs = base_in + plus_in
    expected = base_exp + plus_exp
    sbv = scalar_bound_violations(desc, params, inputs)
    m["scalar_bound_violations"] = len(sbv)
    warnings.extend("domain-sentence violation (class 2a): %s" % v for v in sbv)
    ok, mism, errs, tmax = run_and_compare(prompt + canonical, fname,
                                           inputs, expected)
    m.update(ref_max_test_s=tmax)
    if not ok:
        return ("needs-human", "reference mismatch/err on %d/%d tests (%s)"
                % (len(mism) + len(errs), len(inputs),
                   "; ".join(errs[:3]) or "value mismatch"), None, m)

    if tmax > 0.1:
        warnings.append("reference slowest test %.2fs exceeds house "
                        "runtime margin (0.10s)" % tmax)
    task = {
        "task_id": "leetcode/%s" % slug,
        "prompt": prompt,
        "entry_point": fname,
        "canonical_solution": canonical,
        "base_input": base_in,
        "plus_input": plus_in,
        "atol": 0,
        "expected_output": {"base": base_exp, "plus": plus_exp},
        "provenance": {
            "problem_key": slug,
            "source_dataset": "newfacade/LeetCodeDataset",
            "source_row": rec.get("_row"),
            "title": slug, "rating": None,
            "difficulty": rec.get("difficulty"),
            "tags": rec.get("tags"),
            "url": "https://leetcode.com/problems/%s/" % slug,
            "license": "apache-2.0 (dataset card) over LeetCode material",
            "dates": {"source_date": rec.get("estimated_date"),
                      "fetched": rec.get("_fetched_at")},
            "time_limit_s": None, "duplicate_of": None,
        },
        "conversion": {"method": "leetcode-solution-wrap",
                       "reference": {"origin": "dataset completion"},
                       "tests_dropped_at_fetch": 0,
                       "tests_dropped_at_budget": dropped,
                       "sample_tests_extracted": len(base_in),
                       "superscripts_repaired": n_sup,
                       "layout_pin": "",
                       "warnings": warnings},
    }
    return "converted", "reference exact on %d tests" % len(inputs), task, m


# -------------------------------------------------------------- evoeval

def _extract_assert_tests(test_src, entry_point):
    """Pull literal (args, expected) pairs from `assert f(...) == lit` /
    `assert candidate(...) == lit` lines. Returns (pairs, n_skipped)."""
    pairs, skipped = [], 0
    seen_pairs = set()
    try:
        tree = ast.parse(test_src)
    except SyntaxError:
        return [], -1
    names = {entry_point, "candidate"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        t = node.test
        if not (isinstance(t, ast.Compare) and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq)):
            skipped += 1
            continue
        call, lit = t.left, t.comparators[0]
        if not isinstance(call, ast.Call):
            call, lit = lit, call
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in names and not call.keywords):
            skipped += 1
            continue
        try:
            args = [ast.literal_eval(a) for a in call.args]
            exp = ast.literal_eval(lit)
        except (ValueError, SyntaxError):
            skipped += 1
            continue
        if _json_stable(args) and _json_stable(exp):
            key = json.dumps([args, exp], sort_keys=True)
            if key in seen_pairs:          # duplicate assert (lbpp/106 plus 5 == plus 4)
                skipped += 1
                continue
            seen_pairs.add(key)
            pairs.append((args, exp))
        else:
            skipped += 1
    return pairs, skipped


def _extract_evalplus_lists(test_src):
    try:
        tree = ast.parse(test_src)
    except SyntaxError:
        return None
    found = {}
    nodes = list(ast.walk(tree))
    for node in nodes:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if name not in ("inputs", "outputs", "results", "ref_output",
                        "expected_output"):
            continue
        v = node.value
        try:
            found[name] = ast.literal_eval(v)
            continue
        except (ValueError, SyntaxError, TypeError):
            pass
        if isinstance(v, ast.ListComp) and len(v.generators) == 1:
            it = v.generators[0].iter
            try:
                strs = ast.literal_eval(it)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(strs, list) and all(isinstance(s, str)
                                              for s in strs):
                args_lists = []
                for s in strs:
                    try:
                        args_lists.append(ast.literal_eval("[%s]" % s))
                    except (ValueError, SyntaxError, TypeError,
                            MemoryError):
                        args_lists.append(None)     # keep alignment
                found[name] = args_lists
    ins = found.get("inputs")
    outs = found.get("outputs", found.get("results",
                     found.get("ref_output", found.get("expected_output"))))
    if isinstance(ins, list) and isinstance(outs, list) \
            and len(ins) == len(outs) and ins:
        return [(i if isinstance(i, list) else [i], o)
                for i, o in zip(ins, outs) if i is not None]
    return None


_DOCTEST_RE = re.compile(r">>>\s*([A-Za-z_]\w*\(.*\))[ \t]*\n\s*([^\n>]+)")


def _doctest_pairs(prompt, entry_point):
    pairs = []
    for call_s, exp_s in _DOCTEST_RE.findall(prompt):
        try:
            call = ast.parse(call_s, mode="eval").body
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == entry_point and not call.keywords):
                continue
            args = [ast.literal_eval(a) for a in call.args]
            exp = ast.literal_eval(exp_s.strip())
        except (ValueError, SyntaxError):
            continue
        if _json_ok(args) and _json_ok(exp):
            pairs.append((args, exp))
    return pairs


_UNIQUE_RE = re.compile(r"\b(?:unique|distinct|no duplicates?)\b", re.I)
_POSITIVE_RE = re.compile(r"\bpositive (?:integers?|numbers?|values?)\b", re.I)


def domain_sentence_violations(prompt, inputs):
    """Class 2a (audit wave-2, evoeval/difficult_13): the prose states a
    domain ('positive integers and unique') that the GT plus inputs
    violate. Two mechanical shapes only — duplicates in a list argument
    when the docstring says unique/distinct; non-positive ints in a list
    argument when it says positive — reported as WARNINGS (canonical and
    tests stay self-consistent; the label decides). Format sentences
    (tool_use_59) are not mechanically checkable."""
    doc = re.sub(r"\s+", " ", prompt)
    want_unique = bool(_UNIQUE_RE.search(doc))
    want_positive = bool(_POSITIVE_RE.search(doc))
    if not (want_unique or want_positive):
        return []
    out = []
    for i, args in enumerate(inputs):
        for a in args:
            if isinstance(a, list) and a and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in a):
                if want_unique and len(set(a)) != len(a):
                    out.append("input %d: prose says unique/distinct but a list argument has duplicates" % i)
                if want_positive and any(x <= 0 for x in a):
                    out.append("input %d: prose says positive but a list argument has a non-positive value" % i)
    return out[:8]


def convert_evoeval(rec):
    m = {"source": "evoeval"}
    ep = rec["entry_point"]
    prompt, canonical = rec["prompt"], rec["canonical_solution"]

    anyof = bench_any_of_them(prompt)
    m["any_of_them"] = anyof
    if anyof:
        return ("needs-human", "any-of-them statement: %s" % anyof[:140],
                None, m)

    # EvoEval prompts end at the closing docstring quotes with no newline;
    # normalize so prompt + canonical_solution is executable (house contract)
    if not prompt.endswith("\n"):
        prompt += "\n"

    pairs = _extract_evalplus_lists(rec.get("test") or "")
    if pairs is None:
        pairs, skipped = _extract_assert_tests(rec.get("test") or "", ep)
        m["n_assert_skipped"] = skipped
    base_pairs = _doctest_pairs(prompt, ep)
    seen = {json.dumps(a) for a, _ in base_pairs}
    plus_pairs = [(a, e) for a, e in pairs if json.dumps(a) not in seen]
    m.update(n_base=len(base_pairs), n_plus=len(plus_pairs))
    allp = base_pairs + plus_pairs
    if len(allp) < MIN_TESTS:
        return ("needs-human", "only %d literal tests extractable"
                % len(allp), None, m)
    if any(_has_nonfinite(a) or _has_nonfinite(e) for a, e in allp):
        return ("rejected", "non-finite float (NaN/inf) in tests", None, m)
    if any(_has_float(e) for _, e in allp):
        return ("rejected", "float expected values: atol=0 is the pinned "
                "house semantics; tolerance tasks route out", None, m)

    base_in = [a for a, _ in base_pairs]; base_exp = [e for _, e in base_pairs]
    plus_in = [a for a, _ in plus_pairs]; plus_exp = [e for _, e in plus_pairs]
    evo_warnings = []
    try:
        ensure_base(base_in, base_exp, plus_in, plus_exp, evo_warnings)
    except ValueError as e:
        return "rejected", str(e), None, m
    inputs = base_in + plus_in
    expected = base_exp + plus_exp
    dv = domain_sentence_violations(prompt, inputs)
    m["domain_sentence_violations"] = len(dv)
    evo_warnings.extend("domain-sentence violation (class 2a): %s" % d for d in dv)
    ok, mism, errs, tmax = run_and_compare(prompt + canonical, ep,
                                           inputs, expected)
    m["ref_max_test_s"] = tmax
    if not ok:
        return ("needs-human", "canonical mismatch/err on %d/%d (%s)"
                % (len(mism) + len(errs), len(inputs),
                   "; ".join(errs[:3]) or "value mismatch"), None, m)

    task = {
        "task_id": "evoeval/%s_%s" % (rec.get("_config", "x"),
                                      rec["task_id"].split("/")[-1]),
        "prompt": prompt,
        "entry_point": ep,
        "canonical_solution": canonical,
        "base_input": base_in,
        "plus_input": plus_in,
        "atol": 0,
        "expected_output": {"base": base_exp, "plus": plus_exp},
        "provenance": {
            "problem_key": rec["task_id"],
            "source_dataset": "evoeval/EvoEval_%s" % rec.get("_config"),
            "source_row": rec.get("_row"),
            "title": ep, "rating": None,
            "difficulty": rec.get("_config"),
            "tags": ["evoeval", rec.get("_config")],
            "url": "https://huggingface.co/datasets/evoeval/EvoEval_%s"
                   % rec.get("_config"),
            "license": "apache-2.0",
            "dates": {"source_date": "2024-03",
                      "fetched": rec.get("_fetched_at")},
            "time_limit_s": None, "duplicate_of": None,
        },
        "conversion": {"method": "evoeval-native",
                       "reference": {"origin": "dataset canonical_solution"},
                       "tests_dropped_at_fetch": 0,
                       "tests_dropped_at_budget": 0,
                       "sample_tests_extracted": len(base_pairs),
                       "layout_pin": "",
                       "warnings": evo_warnings},
    }
    return "converted", "canonical exact on %d tests" % len(inputs), task, m


# ----------------------------------------------------------------- lbpp

def _lbpp_decode(s):
    """LBPP columns are base64(zlib(pickle)) per the dataset's own loader;
    payloads are plain str / list-of-str objects."""
    import pickle
    raw = zlib.decompress(base64.b64decode(s))
    v = pickle.loads(raw) if raw[:1] == b"\x80" else raw.decode()
    # payloads are JSON-encoded strings/lists inside the pickle
    if isinstance(v, str) and v[:1] in ("\"", "["):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def convert_lbpp(rec):
    m = {"source": "lbpp"}
    instr = rec.get("instruction") or ""
    anyof = bench_any_of_them(instr)
    m["any_of_them"] = anyof
    if anyof:
        return ("needs-human", "any-of-them statement: %s" % anyof[:140],
                None, m)
    try:
        completion = _lbpp_decode(rec["completion"])
        test_list = _lbpp_decode(rec["test_list"])
        if isinstance(test_list, str):
            test_list = json.loads(test_list)
    except Exception as e:
        return "needs-human", "decode failed: %s" % e, None, m

    sig = (rec.get("signature") or "").strip().rstrip(":")
    fmatch = re.match(r"def\s+([A-Za-z_]\w*)", sig)
    if not fmatch:
        return "needs-human", "unparseable signature", None, m
    fname = fmatch.group(1)

    try:
        tree = ast.parse(completion)
    except SyntaxError as e:
        return "needs-human", "completion does not parse: %s" % e, None, m
    fn = None
    imports, helpers = [], []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            fn = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(node))
        elif isinstance(node, ast.If) and getattr(
                getattr(node.test, "left", None), "id", "") == "__name__":
            continue                       # drop __main__ guards
        else:
            # helper defs/classes/constants: nest them inside the solve
            # body (closure scoping keeps them resolvable)
            helpers.append(node)
    if fn is None:
        return ("needs-human", "completion shape unsupported (no target "
                "fn)", None, m)
    m["n_inlined_helpers"] = len(helpers)

    pairs, skipped = _extract_assert_tests("\n".join(test_list), fname)
    m.update(n_tests=len(pairs), n_assert_skipped=skipped)
    if len(pairs) < MIN_TESTS:
        return ("needs-human", "only %d literal tests (%d asserts "
                "non-literal)" % (len(pairs), skipped), None, m)
    if any(_has_nonfinite(a) or _has_nonfinite(e) for a, e in pairs):
        return ("rejected", "non-finite float (NaN/inf) in tests", None, m)
    if any(_has_float(e) for _, e in pairs):
        return ("rejected", "float expected values: atol=0 is the pinned "
                "house semantics; tolerance tasks route out", None, m)

    body_src = "\n".join(ast.unparse(n) for n in helpers + fn.body)
    body = "".join("    %s\n" % l if l.strip() else "\n"
                   for l in body_src.split("\n"))
    preamble = ("\n".join(imports) + "\n\n") if imports else ""
    prompt = "%s%s:\n    \"\"\"%s\n    \"\"\"\n" % (
        preamble, sig,
        houseconv._sanitize_doc(instr).replace("\n", "\n    "))

    inputs = [a for a, _ in pairs]
    expected = [e for _, e in pairs]
    ok, mism, errs, tmax = run_and_compare(prompt + body, fname,
                                           inputs, expected)
    m["ref_max_test_s"] = tmax
    if not ok:
        return ("needs-human", "reference mismatch/err on %d/%d (%s)"
                % (len(mism) + len(errs), len(inputs),
                   "; ".join(errs[:3]) or "value mismatch"), None, m)

    task = {
        "task_id": "lbpp/%s" % rec["task_id"].split("/")[-1],
        "prompt": prompt,
        "entry_point": fname,
        "canonical_solution": body,
        "base_input": inputs[:2],
        "plus_input": inputs[2:],
        "atol": 0,
        "expected_output": {"base": expected[:2], "plus": expected[2:]},
        "provenance": {
            "problem_key": rec["task_id"],
            "source_dataset": "CohereLabs/lbpp#python",
            "source_row": rec.get("_row"),
            "title": rec.get("title"), "rating": None,
            "difficulty": None,
            "tags": rec.get("categories"),
            "url": "https://huggingface.co/datasets/CohereLabs/lbpp",
            "license": "apache-2.0",
            "dates": {"source_date": "2024-06",
                      "fetched": rec.get("_fetched_at")},
            "time_limit_s": None, "duplicate_of": None,
        },
        "conversion": {"method": "lbpp-body-extract",
                       "reference": {"origin": "dataset completion"},
                       "tests_dropped_at_fetch": 0,
                       "tests_dropped_at_budget": 0,
                       "sample_tests_extracted": 0,
                       "layout_pin": "",
                       "warnings": ["base_input = first 2 tests (no "
                                    "marked statement examples in LBPP)"]},
    }
    return "converted", "reference exact on %d tests" % len(inputs), task, m


# -------------------------------------------------------------- lcb join

def _slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def _lcb_tests(raw):
    """Decode LCB test case field: JSON list, possibly wrapped in
    base64+zlib+pickle for large private suites."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        pass
    import pickle
    v = pickle.loads(zlib.decompress(base64.b64decode(raw)))
    return json.loads(v) if isinstance(v, str) else v


def _lcb_parse_io(t, n_params):
    """LCB functional IO: input = one JSON literal per line (positional
    args), output = one JSON literal."""
    lines = [l for l in (t.get("input") or "").split("\n") if l.strip()]
    if len(lines) != n_params:
        raise ValueError("arg count %d != %d params"
                         % (len(lines), n_params))
    args = [json.loads(l) for l in lines]
    exp = json.loads(t.get("output"))
    return args, exp


def make_convert_lcb(lcd_map):
    def convert_lcb(rec):
        m = {"source": "lcb"}
        desc = rec.get("question_content") or ""
        anyof = bench_any_of_them(desc)
        m["any_of_them"] = anyof
        if anyof:
            return ("needs-human", "any-of-them statement: %s"
                    % anyof[:140], None, m)
        slug = _slugify(rec.get("question_title"))
        ref = lcd_map.get(slug)
        if ref is None:
            return ("needs-human", "no joinable reference (slug %s not in "
                    "LeetCodeDataset; likely post-map problem)" % slug,
                    None, m)
        fname = rec.get("_func_name")
        try:
            params, header = leetcode_signature(
                rec.get("starter_code") or ref["starter_code"], fname)
        except (ValueError, SyntaxError) as e:
            return "needs-human", "starter parse failed: %s" % e, None, m
        completion = ref.get("completion") or ""
        if "class Solution" not in completion:
            return "needs-human", "joined completion not a Solution class", \
                None, m

        base_in, base_exp, plus_in, plus_exp, dropped = [], [], [], [], 0
        try:
            pub = _lcb_tests(rec.get("public_test_cases"))
            priv = _lcb_tests(rec.get("private_test_cases"))
        except Exception as e:
            return "needs-human", "test decode failed: %s" % e, None, m
        for tset, ins, exps in ((pub, base_in, base_exp),
                                (priv, plus_in, plus_exp)):
            for t in tset:
                if (t.get("testtype") or "functional") != "functional":
                    dropped += 1
                    continue
                try:
                    args, exp = _lcb_parse_io(t, len(params))
                except (ValueError, TypeError) as e:
                    dropped += 1
                    continue
                if not _json_stable(args) or not _json_stable(exp):
                    dropped += 1
                    continue
                ins.append(args)
                exps.append(exp)
        m.update(n_base=len(base_in), n_plus=len(plus_in),
                 n_dropped=dropped)
        if len(base_in) + len(plus_in) < MIN_TESTS:
            return ("rejected", "only %d usable tests"
                    % (len(base_in) + len(plus_in)), None, m)
        if any(_has_nonfinite(v) for v in
               base_in + plus_in + base_exp + plus_exp):
            return ("rejected", "non-finite float (NaN/inf) in tests",
                    None, m)
        if any(_has_float(v) for v in base_exp + plus_exp):
            return ("rejected", "float expected values: atol=0 is the "
                    "pinned judge semantics; tolerance tasks route out",
                    None, m)
        lcb_warnings = []
        try:
            ensure_base(base_in, base_exp, plus_in, plus_exp, lcb_warnings)
        except ValueError as e:
            return "rejected", str(e), None, m

        prompt = "%s\n%s\n    \"\"\"%s\n    \"\"\"\n" % (
            (ref.get("prompt") or "").rstrip(), header,
            houseconv._sanitize_doc(desc).replace("\n", "\n    "))
        body_lines = ["    %s" % l if l.strip() else ""
                      for l in completion.split("\n")]
        canonical = "\n".join(body_lines).rstrip() + (
            "\n    return Solution().%s(%s)\n" % (fname, ", ".join(params)))
        inputs = base_in + plus_in
        expected = base_exp + plus_exp
        ok, mism, errs, tmax = run_and_compare(prompt + canonical, fname,
                                               inputs, expected)
        m["ref_max_test_s"] = tmax
        if not ok:
            return ("needs-human", "joined reference mismatch/err on "
                    "%d/%d (%s)" % (len(mism) + len(errs), len(inputs),
                                    "; ".join(errs[:3]) or "value mismatch"),
                    None, m)
        task = {
            "task_id": "lcb/%s" % slug,
            "prompt": prompt,
            "entry_point": fname,
            "canonical_solution": canonical,
            "base_input": base_in,
            "plus_input": plus_in,
            "atol": 0,
            "expected_output": {"base": base_exp, "plus": plus_exp},
            "provenance": {
                "problem_key": slug,
                "source_dataset": "livecodebench/code_generation_lite#v6",
                "source_row": rec.get("_row"),
                "title": rec.get("question_title"), "rating": None,
                "difficulty": rec.get("difficulty"),
                "tags": ["livecodebench"],
                "url": "https://leetcode.com/problems/%s/" % slug,
                "license": "cc (dataset card) over LeetCode material",
                "dates": {"source_date": rec.get("contest_date"),
                          "fetched": rec.get("_fetched_at")},
                "time_limit_s": None, "duplicate_of": None,
                "reference_joined_from": "newfacade/LeetCodeDataset",
                "reference_source": "newfacade/LeetCodeDataset@%s" % slug,
            },
            "conversion": {"method": "lcb-functional-join",
                           "reference": {"origin":
                                         "LeetCodeDataset completion "
                                         "(joined by slug)",
                                         "reference_source":
                                         "newfacade/LeetCodeDataset@%s"
                                         % slug,
                                         "reproduce_check":
                                         "exact on %d/%d kept tests"
                                         % (len(inputs), len(inputs))},
                           "tests_dropped_at_fetch": dropped,
                           "tests_dropped_at_budget": 0,
                           "sample_tests_extracted": len(base_in),
                           "layout_pin": "",
                           "warnings": lcb_warnings},
        }
        return ("converted", "joined reference exact on %d tests"
                % len(inputs), task, m)
    return convert_lcb


# ------------------------------------------------------------------ fetch

def _stream_jsonl(fs, path, keep=None):
    """Stream a HF-hosted jsonl file row by row (memory-bounded)."""
    import io
    with fs.open(path, "rb") as f:
        for i, line in enumerate(io.TextIOWrapper(f, encoding="utf-8")):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if keep:
                r = {k: r.get(k) for k in keep}
            r["_row"] = "%s#%d" % (os.path.basename(path), i)
            yield r


def fetch(source, limit, out):
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem
    import datetime
    fs = HfFileSystem()
    fetched_at = datetime.datetime.now(datetime.timezone.utc)\
        .isoformat(timespec="seconds")
    rows = []
    if source == "leetcode":
        cols = ["task_id", "question_id", "difficulty", "tags",
                "problem_description", "starter_code", "estimated_date",
                "prompt", "completion", "entry_point", "input_output"]
        for path in ("datasets/newfacade/LeetCodeDataset/"
                     "LeetCodeDataset-train.jsonl",
                     "datasets/newfacade/LeetCodeDataset/"
                     "LeetCodeDataset-test.jsonl"):
            rows.extend(_stream_jsonl(fs, path, keep=cols))
        # full slug->reference sidecar for the LCB v6 join (LCB ships no
        # solutions; this map is its only reference source)
        map_path = os.path.join(os.path.dirname(out) or ".",
                                "leetcode_solutions_map.jsonl")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(map_path, "w") as f:
            for r in rows:
                f.write(json.dumps({k: r.get(k) for k in
                                    ("task_id", "question_id",
                                     "starter_code", "completion",
                                     "entry_point", "prompt",
                                     "estimated_date")}) + "\n")
        print("[bench-fetch] wrote %d-row solutions map -> %s"
              % (len(rows), map_path), flush=True)
        # Easy-weighted, freshest-first within difficulty (contamination
        # bookkeeping favors recent problems; Easy fills the sub-2% band)
        rows.sort(key=lambda r: (r.get("estimated_date") or ""),
                  reverse=True)
        quota = {"Easy": limit // 2, "Medium": (limit * 3) // 10,
                 "Hard": limit - limit // 2 - (limit * 3) // 10}
        sel, cnt = [], {}
        for r in rows:
            d = r.get("difficulty")
            if cnt.get(d, 0) < quota.get(d, 0):
                cnt[d] = cnt.get(d, 0) + 1
                sel.append(r)
        rows = sel
        print("[bench-fetch] leetcode: %s" % cnt, flush=True)
    elif source == "evoeval":
        for cfg in ("difficult", "creative", "subtle", "combine",
                    "tool_use"):
            path = "datasets/evoeval/EvoEval_%s/test.jsonl" % cfg
            for r in _stream_jsonl(fs, path):
                r["_config"] = cfg
                rows.append(r)
        print("[bench-fetch] evoeval: %d rows" % len(rows), flush=True)
    elif source == "lcb":
        # LiveCodeBench v6, freshest slices first (contest_date is the
        # contamination field this source exists for). No solutions ship;
        # references are joined at convert time from the LeetCodeDataset
        # completion map. stdin-type (atcoder/codeforces) rows carry no
        # joinable reference -> recorded + skipped here.
        keep = ["question_title", "question_content", "platform",
                "question_id", "contest_id", "contest_date", "starter_code",
                "difficulty", "public_test_cases", "private_test_cases",
                "metadata"]
        n_stdin = 0
        for fname in ("test6.jsonl", "test5.jsonl", "test4.jsonl",
                      "test3.jsonl", "test2.jsonl", "test.jsonl"):
            if limit and len(rows) >= limit:
                break
            path = ("datasets/livecodebench/code_generation_lite/%s"
                    % fname)
            for r in _stream_jsonl(fs, path, keep=keep):
                meta = {}
                try:
                    meta = json.loads(r.get("metadata") or "{}")
                except ValueError:
                    pass
                if r.get("platform", "").lower() != "leetcode" \
                        or not meta.get("func_name"):
                    n_stdin += 1
                    continue
                r["_func_name"] = meta["func_name"]
                r.pop("metadata", None)
                rows.append(r)
                if limit and len(rows) >= limit:
                    break
        print("[bench-fetch] lcb: %d functional leetcode rows kept, "
              "%d stdin/other skipped (no joinable reference)"
              % (len(rows), n_stdin), flush=True)
    elif source == "lbpp":
        files = sorted(fs.glob(
            "datasets/CohereLabs/lbpp/python/*.parquet"))
        for path in files:
            with fs.open(path, "rb") as f:
                t = pq.read_table(f)
            for i, r in enumerate(t.to_pylist()):
                r["_row"] = "%s#%d" % (os.path.basename(path), i)
                rows.append(r)
        print("[bench-fetch] lbpp: %d rows" % len(rows), flush=True)
    else:
        raise SystemExit("unknown source %s" % source)
    if limit and source != "leetcode":
        rows = rows[:limit]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            r["_fetched_at"] = fetched_at
            f.write(json.dumps(r, default=str) + "\n")
    print("[bench-fetch] wrote %d -> %s" % (len(rows), out), flush=True)


# ---------------------------------------------------------------- convert

CONVERTERS = {"leetcode": convert_leetcode, "evoeval": convert_evoeval,
              "lbpp": convert_lbpp}


def convert_main(inp, outdir, limit=None, aux=None, ids=None):
    os.makedirs(outdir, exist_ok=True)
    tasks_path = os.path.join(outdir, "tasks_converted.jsonl")
    report_path = os.path.join(outdir, "conversion_report.jsonl")
    done = set()
    counts = {"converted": 0, "needs-human": 0, "rejected": 0}
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add(r["cand_id"])
                    counts[r["status"]] += 1
                except Exception:
                    pass
    recs = []
    with open(inp) as f:
        for line in f:
            recs.append(json.loads(line))
    if ids:
        want = set(ids)
        recs = [r for r in recs if str(r.get("task_id")).split("/")[-1] in want
                or _slugify(r.get("question_title") or "") in want
                or ("%s_%s" % (r.get("_config"), str(r.get("task_id")).split("/")[-1])) in want]
    if limit:
        recs = recs[:limit]
    src = "lcb" if "lcb" in os.path.basename(inp) else \
          "leetcode" if "leetcode" in inp.lower() else \
          "evoeval" if "evoeval" in inp else "lbpp"
    if src == "lcb":
        lcd_map = {}
        with open(aux or os.path.join(os.path.dirname(inp),
                                      "leetcode_solutions_map.jsonl")) as f:
            for line in f:
                r = json.loads(line)
                lcd_map[r["task_id"]] = r
        conv = make_convert_lcb(lcd_map)
    else:
        conv = CONVERTERS[src]
    with open(tasks_path, "a") as tf, open(report_path, "a") as rf:
        for n, rec in enumerate(recs, 1):
            key = rec.get("task_id") or _slugify(
                rec.get("question_title") or "row-%d" % n)
            cand_id = "%s/%s" % (src, str(key).split("/")[-1])
            if cand_id in done:
                continue
            t1 = time.time()
            try:
                status, reason, task, metrics = conv(rec)
            except Exception as e:
                status, reason, task = "needs-human", \
                    "converter crashed: %s: %s" % (type(e).__name__, e), None
                metrics = {}
            counts[status] += 1
            if task:
                tf.write(json.dumps(task) + "\n")
                tf.flush()
            rf.write(json.dumps({
                "cand_id": cand_id, "source": src, "status": status,
                "reason": reason, "elapsed_s": round(time.time() - t1, 1),
                "metrics": metrics}) + "\n")
            rf.flush()
            print("[bench-convert] %3d/%d %-40s %-11s %s"
                  % (n, len(recs), cand_id, status, reason[:70]),
                  flush=True)
    print("[bench-convert] yield: %s of %d" % (counts, len(recs)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--source", required=True,
                   choices=("leetcode", "evoeval", "lbpp", "lcb"))
    f.add_argument("--limit", type=int, default=None)
    f.add_argument("--out", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--in", dest="inp", required=True)
    c.add_argument("--outdir", required=True)
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--aux", default=None,
                   help="lcb: path to leetcode_solutions_map.jsonl")
    c.add_argument("--ids", nargs="*", default=None,
                   help="convert only these ids (slug / EvoEval index / "
                   "<config>_<n>)")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.source, args.limit, args.out)
    else:
        convert_main(args.inp, args.outdir, args.limit, args.aux, args.ids)


if __name__ == "__main__":
    main()

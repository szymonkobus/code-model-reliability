#!/usr/bin/env python3
"""Consistency-contract verifier for paraphrase twins (mechanical part).

Verdict per twin: pass | fail(reasons). Semantic drift beyond these checks
is the audit's job by design.

Usage: python3 verify_twins.py --twins twins.jsonl --report report.jsonl
"""

import argparse
import ast
import re
import json
import os
import re
import subprocess
import sys
import tempfile

HOME = os.environ.get("EVALPLUS_HOME", os.path.expanduser("~"))
DATA_FILES = {
    "humaneval": os.path.join(HOME, ".cache/evalplus/HumanEvalPlus-v0.1.10.jsonl"),
    "mbpp": os.path.join(HOME, ".cache/evalplus/MbppPlus-v0.2.0.jsonl"),
}

DOCTEST_RUNNER = r"""
import doctest, json, sys
src = sys.stdin.read()
payload = json.loads(src)
g = {}
try:
    exec(payload["code"], g)
except Exception as e:
    print(json.dumps({"status": "exec-error", "detail": str(e)[:200]})); sys.exit(0)
parser = doctest.DocTestParser()
test = parser.get_doctest(payload["doc"], g, "twin", None, 0)
runner = doctest.DocTestRunner(verbose=False)
runner.run(test)
print(json.dumps({"status": "ran", "attempted": runner.tries,
                  "failed": runner.failures}))
"""


def load_pool():
    pool = {}
    for bench, path in DATA_FILES.items():
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                r["_benchmark"] = bench
                pool[r["task_id"]] = r
    return pool


def sig_dump(prompt, entry_point):
    try:
        tree = ast.parse(prompt)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == entry_point:
            return ast.dump(node.args) + "|" + ast.dump(node.returns) \
                if node.returns else ast.dump(node.args) + "|None"
    return "NOT-FOUND"


def example_lines(prompt):
    """Doctest lines (>>> + their expected-output lines) and assert lines."""
    lines = prompt.splitlines()
    out = []
    in_doct = False
    for ln in lines:
        s = ln.strip()
        if s.startswith(">>>"):
            out.append(s)
            in_doct = True
        elif in_doct and s and not s.startswith(('"""', "'''")):
            out.append(s)
            in_doct = False
        elif s.startswith("assert "):
            out.append(s)
            in_doct = False
        else:
            in_doct = False
    return out


def run_doctests(code, doc, timeout=30):
    try:
        p = subprocess.run(
            [sys.executable, "-c", DOCTEST_RUNNER],
            input=json.dumps({"code": code, "doc": doc}),
            capture_output=True, text=True, timeout=timeout)
        return json.loads(p.stdout.strip() or '{"status":"empty"}')
    except Exception as e:
        return {"status": "runner-error", "detail": str(e)[:200]}


def docstring_of(prompt):
    # whole prompt text works for the doctest parser (it scans for >>>)
    return prompt


CONSTRAINT_WORDS = [
    "tuple", "tuples", "list", "lists", "set", "sets", "dict", "dictionary",
    "single character", "single-character", "individual character", "one character",
    "non-empty", "nonempty", "non-negative", "nonnegative", "positive", "negative",
    "integer", "integers", "float", "floats", "string", "strings", "boolean",
    "distinct", "unique", "sorted", "ascending", "descending", "at least", "at most",
    "exactly", "always", "never", "guaranteed", "valid", "lowercase", "uppercase",
    "ascii", "digit", "digits", "letter", "letters", "whole number",
    "counts", "numbers", "amounts", "scores", "prices", "ages", "names", "words",
    "keys", "ids", "measurements", "readings", "totals", "quantities",
    "temperatures", "weights", "characters", "numeric", "numerical",
    "pair", "pairs", "pairing", "paired", "couple", "couples", "two-element",
    "three-element", "triple", "triples", "triplet", "triplets", "quadruple",
    "2-tuple", "3-tuple", "two values", "three values", "two items", "three items",
    "two numbers", "three numbers", "each with a", "one entry and", "entry and a",
]


TYPE_HINT_SYNONYMS = {  # a parent stating a type via annotation/name has "said" the word
    r"\bstr\b": " string strings ", r"\bint\b": " integer integers whole number ",
    r"\bfloat\b": " float floats ", r"\bbool\b": " boolean ", r"\blist\b": " list lists ",
    r"\btuple\b": " tuple tuples ", r"\bdict\b": " dict dictionary ", r"\bset\b": " set sets ",
}


def new_constraint_words(src_prompt, twin_prompt):
    import re as _re
    s, t = src_prompt.lower(), twin_prompt.lower()
    for pat, syn in TYPE_HINT_SYNONYMS.items():
        if _re.search(pat, s):
            s += syn
    found = []
    for w in CONSTRAINT_WORDS:
        pat = r"\b" + _re.escape(w) + r"\b"
        if _re.search(pat, t) and not _re.search(pat, s):
            found.append(w)
    return found


def paraphrase_distance(src_prompt, twin_prompt):
    import difflib
    a = re.sub(r"\s+", " ", twin_prompt.strip()); b = re.sub(r"\s+", " ", src_prompt.strip())
    return {"identical": a == b, "ratio": round(difflib.SequenceMatcher(None, a, b).ratio(), 4)}


NEAR_PARAPHRASE = 0.90


def verify(twin, src):
    reasons = []
    warnings = []
    bench = src["_benchmark"]
    pd = paraphrase_distance(src["prompt"], twin["prompt"])
    if pd["identical"]:
        reasons.append("paraphrase: prompt identical to parent modulo whitespace (no rewording)")
    elif pd["ratio"] >= NEAR_PARAPHRASE:
        warnings.append(f"paraphrase-near: ratio {pd['ratio']} >= {NEAR_PARAPHRASE} (re-render with another style)")
    # constraint-introduction check (see CONSTRAINT_WORDS)
    intro = new_constraint_words(src["prompt"], twin["prompt"])
    if intro:
        reasons.append(f"new-constraint-words: {intro}")

    skip = {"prompt", "task_id", "provenance", "conversion"}
    for k in src:
        if k.startswith("_") or k in skip:
            continue
        if twin.get(k) != src[k]:
            reasons.append(f"inherit:{k} differs")

    try:
        ast.parse(twin["prompt"])
    except SyntaxError as e:
        reasons.append(f"compiles: {e}")

    if bench == "humaneval":
        s_sig = sig_dump(src["prompt"], src["entry_point"])
        t_sig = sig_dump(twin["prompt"], src["entry_point"])
        if t_sig != s_sig:
            reasons.append(f"signature: src={bool(s_sig)} twin_sig_differs_or_missing")

    src_ex = example_lines(src["prompt"])
    twin_norm = "\n".join(l.strip() for l in twin["prompt"].splitlines())
    missing = [e for e in src_ex if e not in twin_norm]
    if missing:
        reasons.append(f"examples: {len(missing)}/{len(src_ex)} missing: {missing[:3]}")

    # execution witness: doctests behave identically on src vs twin
    if bench == "humaneval":
        code = src["prompt"] + src["canonical_solution"]
    else:
        code = "\n".join(src["canonical_solution"]) if isinstance(
            src["canonical_solution"], list) else src["canonical_solution"]
    r_src = run_doctests(code, docstring_of(src["prompt"]))
    r_twin = run_doctests(code, docstring_of(twin["prompt"]))
    if r_src.get("status") == "ran" and r_twin.get("status") == "ran":
        if (r_twin["attempted"], r_twin["failed"]) != (r_src["attempted"], r_src["failed"]):
            reasons.append(
                f"doctest: src {r_src['failed']}/{r_src['attempted']} fail "
                f"vs twin {r_twin['failed']}/{r_twin['attempted']}")
    elif r_src.get("status") != r_twin.get("status"):
        reasons.append(f"doctest-status: src={r_src.get('status')} twin={r_twin.get('status')}")

    return {
        "task_id": twin["task_id"],
        "source_task_id": src["task_id"],
        "verdict": "pass" if not reasons else "fail",
        "reasons": reasons,
        "warnings": warnings,
        "paraphrase_ratio": pd["ratio"],
        "doctest_src": r_src, "doctest_twin": r_twin,
        "n_examples_src": len(src_ex),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twins", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    pool = load_pool()
    n_pass = n_fail = 0
    with open(args.twins) as f, open(args.report, "w") as rep:
        for line in f:
            twin = json.loads(line)
            src = pool[twin["provenance"]["source_task_id"]]
            v = verify(twin, src)
            rep.write(json.dumps(v) + "\n")
            n_pass += v["verdict"] == "pass"
            n_fail += v["verdict"] == "fail"
            print(f"{v['task_id']}: {v['verdict']}" +
                  (f" {v['reasons']}" if v["reasons"] else ""))
    print(f"total: {n_pass} pass, {n_fail} fail")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()

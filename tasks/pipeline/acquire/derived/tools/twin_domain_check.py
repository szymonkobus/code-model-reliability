#!/usr/bin/env python3
"""Facts per argument (recursive over the top container):
  container kinds, element arities (for tuple/list elements), element kinds,
  lengths (min/max), presence of empty containers, sign classes of ints,
  presence of non-int numerics, presence of multi-char / empty strings.
Claims recognised (regex families, twin-only vocabulary):
  arity (pair/couple/two-element/2-tuple -> arity 2; triple/three-element -> 3)
  single-character elements; non-empty; positive/non-negative/negative;
  integer-only / numeric-only; strings-only; distinct/unique elements; sorted.
Usage: python3 tools/twin_domain_check.py --twins a.jsonl ... --out report.json
"""
import argparse
import json
import os
import re
import sys
import time

HOME = os.environ.get("EVALPLUS_HOME", os.path.expanduser("~"))
DATA = [f"{HOME}/.cache/evalplus/HumanEvalPlus-v0.1.10.jsonl",
        f"{HOME}/.cache/evalplus/MbppPlus-v0.2.0.jsonl"]

CLAIMS = {
    "arity2": r"\b(pairs?|pairing|paired|couples?|two-element|2-tuples?|two values|two items|two numbers|each (\w+ )?(with|and) (a|an|one) \w+)\b",
    "arity3": r"\b(triples?|triplets?|three-element|3-tuples?|three values|three items|three numbers)\b",
    "single_char": r"\b(single[- ]character|individual characters?|one character|single letters?)\b",
    "non_empty": r"\b(non-?empty|at least one (element|item|value|entry))\b",
    "positive": r"\b(positive|strictly positive)\b",
    "non_negative": r"\b(non-?negative)\b",
    "integers_only": r"\b(integers?|whole numbers?)\b",
    "numeric_only": r"\b(numbers?|numeric|numerical|amounts|scores|totals|quantities)\b",
    "strings_only": r"\b(strings?|words|names|texts?)\b",
    "distinct": r"\b(distinct|unique|no duplicates?|without duplicates?)\b",
    "sorted": r"\b(sorted|ascending order|descending order|in (?:ascending|descending|increasing|decreasing) order)\b",
}


def kind(v):
    if isinstance(v, bool): return "bool"
    if isinstance(v, int): return "int"
    if isinstance(v, float): return "float"
    if isinstance(v, str): return "str"
    if v is None: return "none"
    if isinstance(v, list): return "list"
    if isinstance(v, dict): return "dict"
    return type(v).__name__


def facts_for_arg(values):
    f = {"kinds": set(), "elem_arities": set(), "elem_kinds": set(), "has_empty": False,
         "has_nonpos": False, "has_neg": False, "has_nonint": False, "has_multichar": False,
         "has_dup_elems": False, "has_unsorted": False, "n": len(values)}
    for v in values:
        f["kinds"].add(kind(v))
        if isinstance(v, (list, str)):
            if len(v) == 0: f["has_empty"] = True
            if isinstance(v, str) and len(v) != 1: f["has_multichar"] = True
        if isinstance(v, list):
            def leaves(x):
                if isinstance(x, list):
                    for y in x:
                        yield from leaves(y)
                else:
                    yield x
            ek = {kind(e) for e in leaves(v)}; f["elem_kinds"] |= ek
            for e in v:
                if isinstance(e, list): f["elem_arities"].add(len(e))
                if isinstance(e, str) and len(e) != 1: f["has_multichar"] = True
                if isinstance(e, int) and not isinstance(e, bool):
                    if e <= 0: f["has_nonpos"] = True
                    if e < 0: f["has_neg"] = True
                if isinstance(e, (float, str, list, dict)): f["has_nonint"] = True
            try:
                if len(set(map(json.dumps, v))) != len(v): f["has_dup_elems"] = True
                if any(isinstance(e, (int, float)) for e in v) and v != sorted(v) and v != sorted(v, reverse=True):
                    f["has_unsorted"] = True
            except Exception:
                pass
        if isinstance(v, int) and not isinstance(v, bool):
            if v <= 0: f["has_nonpos"] = True
            if v < 0: f["has_neg"] = True
        if isinstance(v, (float, str)): f["has_nonint"] = True
    return f


def contradictions(claim_set, facts):
    out = []
    if "arity2" in claim_set and facts["elem_arities"] and facts["elem_arities"] != {2}:
        out.append(f"claims pairs; element arities in tests: {sorted(facts['elem_arities'])}")
    if "arity3" in claim_set and facts["elem_arities"] and facts["elem_arities"] != {3}:
        out.append(f"claims triples; element arities in tests: {sorted(facts['elem_arities'])}")
    if "single_char" in claim_set and facts["has_multichar"]:
        out.append("claims single-character elements; tests hold multi-char/empty strings")
    if "non_empty" in claim_set and facts["has_empty"]:
        out.append("claims non-empty; tests include an empty input")
    if "positive" in claim_set and facts["has_nonpos"]:
        out.append("claims positive; tests include zero/negative values")
    if "non_negative" in claim_set and facts["has_neg"]:
        out.append("claims non-negative; tests include negatives")
    if "integers_only" in claim_set and facts["has_nonint"] and "list" in facts["kinds"]:
        out.append("claims integers; tests include non-int elements")
    if "numeric_only" in claim_set and facts["elem_kinds"] and not facts["elem_kinds"] <= {"int", "float", "bool"}:
        out.append(f"claims numeric elements; test element kinds: {sorted(facts['elem_kinds'])}")
    if "strings_only" in claim_set and facts["elem_kinds"] and not facts["elem_kinds"] <= {"str"}:
        out.append(f"claims string elements; test element kinds: {sorted(facts['elem_kinds'])}")
    if "distinct" in claim_set and facts["has_dup_elems"]:
        out.append("LOW-CONFIDENCE (word may describe the output): claims distinct elements; tests include duplicates")
    if "sorted" in claim_set and facts["has_unsorted"]:
        out.append("LOW-CONFIDENCE (word may describe the output): claims sorted input; tests include unsorted lists")
    return out


INPUT_CUES = r"\b(given|takes?|taking|receives?|accepts?|input|inputs|passed|argument|parameter|provided|supplied|hand(?:ed|s)?|is a|are a|as a|consist(?:s|ing)? of|stored as|records?|list of|tuple of)\b"
OUTPUT_CUES = r"\b(returns?|returning|result|results|output|outputs|produces?|producing|yields?|gives? back|hands? back|splits? (?:it |them )?(?:up )?into|into|sorts?|answer|computed|report)\b"


def input_claims(src_prompt, twin_prompt, names):
    import re as _re
    sp, tp = src_prompt.lower(), twin_prompt.lower()
    name_pat = "|".join(_re.escape(n.lower()) for n in (names or []) if len(n) > 1)
    in_pat = INPUT_CUES + (r"|\b(" + name_pat + r")\b" if name_pat else "")
    claims = set()
    for sent in _re.split(r"(?<=[.;:!?])\s+|\n\s*\n", tp):
        for c, pat in CLAIMS.items():
            m = _re.search(pat, sent)
            if not m or _re.search(pat, sp):
                continue
            pos = m.start()
            d_in = min((abs(x.start() - pos) for x in _re.finditer(in_pat, sent)), default=None)
            d_out = min((abs(x.start() - pos) for x in _re.finditer(OUTPUT_CUES, sent)), default=None)
            weak = c in ("sorted", "distinct")  # both audited cases described the OUTPUT
            if weak:
                if d_in is not None and (d_out is None or d_in < d_out):
                    claims.add(c)      # positive input evidence required
            elif d_in is None and d_out is None:
                claims.add(c)          # no cue: keep (conservative)
            elif d_out is None or (d_in is not None and d_in <= d_out):
                claims.add(c)          # nearer to an input cue
            # else: about the output -> not a claim on the input
    return claims


def arg_names(prompt, entry_point):
    import ast
    try:
        tree = ast.parse(prompt + "    pass\n")
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == entry_point:
            return [a.arg for a in n.args.args]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twins", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--withdrawals", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out/withdrawals.jsonl"))
    args = ap.parse_args()
    src = {}
    for p in DATA:
        for line in open(p):
            r = json.loads(line); src[r["task_id"]] = r
    withdrawn = set()
    if os.path.exists(args.withdrawals):
        withdrawn = {json.loads(l).get("task_id") for l in open(args.withdrawals)}
    flagged, n, seen = [], 0, set()
    for path in args.twins:
        for line in open(path):
            t = json.loads(line)
            if t["task_id"] in withdrawn or t["task_id"] in seen: continue
            seen.add(t["task_id"]); n += 1
            s = src[t["provenance"]["source_task_id"]]
            inputs = s["base_input"] + s["plus_input"]
            names = arg_names(s["prompt"], s["entry_point"]) or [f"arg{i}" for i in range(len(inputs[0]) if inputs else 0)]
            claims = input_claims(s["prompt"], t["prompt"], names)
            if not claims: continue
            hits = []
            for i in range(len(inputs[0]) if inputs else 0):
                f = facts_for_arg([a[i] for a in inputs if i < len(a)])
                for c in contradictions(claims, f):
                    hits.append({"arg": names[i] if i < len(names) else f"arg{i}", "contradiction": c})
            if hits:
                flagged.append({"task_id": t["task_id"], "source": s["task_id"], "dial": t["provenance"]["dial"]["style"],
                                "claims": sorted(claims), "contradictions": hits})
    out = {"_meta": {"contract": "Twin prose claims contradicted by the parent's own graded inputs (high-precision successor to the vocabulary sweep). A flag here is a candidate CONTRADICTION; verify by reading.",
                     "check": "tools/twin_domain_check.py", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
           "n_live": n, "n_flagged": len(flagged), "flagged": flagged}
    with open(args.out + ".tmp", "w") as f:
        json.dump(out, f, indent=1)
    os.replace(args.out + ".tmp", args.out)
    print(json.dumps({"n_live": n, "n_flagged": len(flagged),
                      "ids": [x["task_id"] for x in flagged]}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Mechanical derivation, grounded in the task's own text: the prompt's doctest
`>>> f(...)` calls are typed Python literals. For each argument, infer a type
shape from every example literal (tuple/list/set/frozenset/dict containers,
nested), unify across examples, and cross-check by (a) scanning the prose for
per-argument container words and (b) running the canonical on the typed
inputs (must not raise; outputs compared to the JSON-list run).

Usage: python3 tools/derive_input_types.py --tasks a.jsonl b.jsonl --out map.json
"""

import argparse
import ast
import copy
import json
import re
import subprocess
import sys


def shape_of(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if v is None:
        return "None"
    if isinstance(v, (list, set, frozenset)):
        kind = type(v).__name__
        inner = sorted({shape_of(x) for x in v})
        return f"{kind}[{unify(inner)}]"
    if isinstance(v, tuple):
        inner = [shape_of(x) for x in v]
        if inner and len(set(inner)) == 1 and len(inner) > 2:
            return f"tuple[{inner[0]},...]"
        return "tuple[" + ",".join(inner) + "]" if inner else "tuple[]"
    if isinstance(v, dict):
        ks = sorted({shape_of(k) for k in v}); vs = sorted({shape_of(x) for x in v.values()})
        return f"dict[{unify(ks)},{unify(vs)}]"
    return "any"


def unify(shapes):
    shapes = sorted(set(shapes))
    if len(shapes) > 1 and "any" in shapes:
        shapes = [x for x in shapes if x != "any"]  # unknown absorbed by the concrete
    if not shapes:
        return "any"
    if len(shapes) == 1:
        return shapes[0]
    if set(shapes) <= {"int", "bool"}:
        return "int"
    if set(shapes) <= {"int", "float", "bool"}:
        return "float"
    # containers of same kind with differing inner: unify inner
    kinds = {s.split("[")[0] for s in shapes}
    if len(kinds) == 1 and "[" in shapes[0]:
        k = kinds.pop()
        inners = [s[len(k) + 1:-1] for s in shapes]
        if k == "tuple":
            return "tuple[any,...]"
        return f"{k}[{unify(inners)}]"
    return "any"


def example_calls(prompt, entry_point):
    calls = []
    lines = prompt.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith(">>>") and entry_point + "(" in s:
            expr = s[3:].strip()
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("..."):
                expr += " " + lines[j].strip()[3:].strip()
                j += 1
            i = j
        else:
            i += 1
            continue
        if True:
            try:
                node = ast.parse(expr, mode="eval").body
            except SyntaxError:
                continue
            if isinstance(node, ast.Call):
                try:
                    calls.append([ast.literal_eval(a) for a in node.args])
                except Exception:
                    continue
    return calls


def arg_names(prompt, entry_point):
    try:
        tree = ast.parse(prompt + "    pass\n")
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == entry_point:
            return [a.arg for a in n.args.args]
    return None


CONTAINER_WORDS = {"tuple": "tuple", "tuples": "tuple", "set": "set", "sets": "set",
                   "frozenset": "frozenset", "frozensets": "frozenset",
                   "list": "list", "lists": "list", "dict": "dict"}


def prose_hints(prompt, name):
    """container words within ~60 chars of the argument name in the prose."""
    hints = set()
    for m in re.finditer(r"\b" + re.escape(name) + r"\b", prompt):
        win = prompt[max(0, m.start() - 60): m.end() + 60].lower()
        for w, c in CONTAINER_WORDS.items():
            if re.search(r"\b" + w + r"\b", win):
                hints.add(c)
    return sorted(hints)


def to_typed(v, shape):
    """Convert a JSON-loaded value to the declared shape (recursive)."""
    if shape in ("int", "str", "bool", "float", "None", "any"):
        return v
    m = re.match(r"^(list|set|frozenset|tuple|dict)\[(.*)\]$", shape)
    if not m:
        return v
    kind, inner = m.group(1), m.group(2)
    if kind == "dict":
        return v
    if kind == "tuple":
        if inner.endswith(",...") or inner == "":
            t = inner[:-4] if inner.endswith(",...") else "any"
            return tuple(to_typed(x, t) for x in v)
        parts = split_top(inner)
        if len(parts) == len(v):
            return tuple(to_typed(x, t) for x, t in zip(v, parts))
        return tuple(to_typed(x, parts[0] if parts else "any") for x in v)
    conv = {"list": list, "set": set, "frozenset": frozenset}[kind]
    return conv(to_typed(x, inner) for x in v)


def split_top(s):
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


RUNNER = r"""
import json, sys, copy
sys.path.insert(0, %r)
from derive_input_types import to_typed
p = json.loads(sys.stdin.read())
g = {}
exec(p["code"], g)
fn = g[p["ep"]]
res = {"list_errs": 0, "typed_errs": 0, "diff": 0, "n": 0}
for args in p["inputs"]:
    res["n"] += 1
    typed = [to_typed(copy.deepcopy(a), s) for a, s in zip(args, p["shapes"])]
    o1 = o2 = None; e1 = e2 = False
    try: o1 = repr(fn(*copy.deepcopy(args)))
    except Exception: e1 = True
    try: o2 = repr(fn(*typed))
    except Exception: e2 = True
    res["list_errs"] += e1; res["typed_errs"] += e2
    if not e1 and not e2 and o1 != o2: res["diff"] += 1
print(json.dumps(res))
"""


OVERRIDES = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    ovp = os.path.join(here, "..", "tracker", "declared_input_types_overrides.json")
    if os.path.exists(ovp):
        OVERRIDES.update(json.load(open(ovp))["overrides"])

    out = {}
    for path in args.tasks:
        for line in open(path):
            r = json.loads(line)
            ep = r["entry_point"]
            names = arg_names(r["prompt"], ep)
            calls = example_calls(r["prompt"], ep)
            if not names:
                out[r["task_id"]] = {"status": "ambiguous", "reason": "signature unparsable"}
                continue
            per_arg = {}
            for i, name in enumerate(names):
                shapes = [shape_of(c[i]) for c in calls if i < len(c)]
                shape = unify(shapes) if shapes else "any"
                hints = prose_hints(r["prompt"], name)
                container = shape.split("[")[0] if "[" in shape else None
                status = "declared"
                note = ""
                # a prose container word is EXPLAINED if it appears at any
                # nesting level of the derived shape (list[tuple[...]] explains
                # both 'list' and 'tuple'); only unexplained typed words flag
                unexplained = [h for h in hints if h in ("tuple", "set", "frozenset")
                               and h not in shape]
                scalar = shape in ("int", "str", "bool", "float", "None")
                if scalar:
                    unexplained = []  # a literal scalar in the examples settles it; 'set' is English here
                if shape == "any" and hints:
                    status = "ambiguous"; note = f"no example literal; prose mentions {hints}"
                elif unexplained:
                    status = "ambiguous"; note = f"prose near '{name}' mentions {unexplained} not seen in example shape {shape}"
                elif "[any]" in shape and any(h in ("tuple", "set", "frozenset") for h in hints):
                    status = "ambiguous"; note = f"empty-container examples only; prose mentions {hints}"
                per_arg[name] = {"shape": shape, "prose_hints": hints, "status": status}
                if note:
                    per_arg[name]["note"] = note
            shapes = [per_arg[n]["shape"] for n in names]
            code = r["prompt"] + "\n" + r["canonical_solution"]
            inputs = r["base_input"] + r["plus_input"]
            chk = {"status": "skipped"}
            try:
                p = subprocess.run([sys.executable, "-c", RUNNER % here],
                                   input=json.dumps({"code": code, "ep": ep, "inputs": inputs, "shapes": shapes}),
                                   capture_output=True, text=True, timeout=300)
                chk = json.loads(p.stdout.strip())
            except Exception as e:
                chk = {"status": "runner-error", "detail": str(e)[:120]}
            # owner curation of ambiguity flags (justified per task)
            ov = OVERRIDES.get(r["task_id"], {})
            for name, o in ov.items():
                if name in per_arg and per_arg[name]["status"] == "ambiguous":
                    per_arg[name]["status"] = o["status"]
                    per_arg[name]["curated"] = o["justification"]
            # ambiguous args stay converter no-ops: their shape is reported but not applied
            applied = [per_arg[n]["shape"] if per_arg[n]["status"] == "declared" else "any" for n in names]
            needs_typing = any("tuple" in s or "set" in s for s in applied)
            out[r["task_id"]] = {
                "entry_point": ep, "arg_names": names, "args": per_arg,
                "shapes": applied, "shapes_derived": shapes,
                "applies_to": ["base_input", "plus_input"],
                "needs_typed_inputs": needs_typing,
                "status": "ambiguous" if any(a["status"] == "ambiguous" for a in per_arg.values()) else "declared",
                "canonical_check": chk,
            }
    import hashlib, time
    n = len(out); amb = sum(1 for v in out.values() if v.get("status") == "ambiguous")
    typed = sorted(k for k, v in out.items() if v.get("needs_typed_inputs"))
    body = json.dumps(out, sort_keys=True)
    out["_meta"] = {
        "contract": ("Declared INPUT types for generated pool tasks ("
                     "the prompt's declared argument types are the grading contract). Derived from each prompt's doctest "
                     "literals; owner-curated where prose was English rather than a type (declared_input_types_overrides.json). "
                     "Consumers apply to_typed(value, shape) per positional arg to base_input and plus_input when "
                     "needs_typed_inputs is true; shape 'any' is a no-op. No task text or test is rewritten."),
        "shape_language": "int|str|bool|float|None|any | list[T] | tuple[T1,T2,...] | tuple[T,...] | set[T] | frozenset[T] | dict[K,V] (nested)",
        "converter": "acquisition-derived/tools/derive_input_types.py::to_typed",
        "counts": {"tasks": n, "needs_typed_inputs": len(typed), "ambiguous": amb},
        "typed_task_ids": typed,
    }
    out["_stamp"] = {"written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "content_sha256": hashlib.sha256(body.encode()).hexdigest()}
    with open(args.out + ".tmp", "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    import os as _os
    _os.replace(args.out + ".tmp", args.out)
    print(f"tasks {n} | need typed inputs {len(typed)} | ambiguous {amb} -> {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse, ast, glob, json, os, re, string, sys

# ---------------------------------------------------------------- bound expressions
_TOK = re.compile(r"\s*(\d[\d,]*|\^|\*|\+|-|\(|\))")

def _eval_bound(txt):
    """Evaluate a bound expression such as '2^31 - 1', '5 * 10^4', '-10^9', '1000'. None if not numeric."""
    t = txt.strip().replace(" ", " ")
    if not re.fullmatch(r"[-\d\s\^\*\+\(\),]+", t) or not re.search(r"\d", t):
        return None
    try:
        expr = t.replace(",", "").replace("^", "**")
        node = ast.parse(expr, mode="eval")
        for n in ast.walk(node):
            if not isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Pow, ast.USub)):
                return None
            if isinstance(n, ast.Constant) and not isinstance(n.value, int):
                return None
        v = eval(compile(node, "<bound>", "eval"), {"__builtins__": {}}, {})
        return v if isinstance(v, int) else None
    except Exception:
        return None

# ---------------------------------------------------------------- signature
def parse_signature(prompt, entry_point):
    """Return [(name, annotation_text)] of the entry point's def line."""
    m = re.search(r"^def\s+%s\s*\((.*?)\)\s*(?:->.*?)?:\s*$" % re.escape(entry_point), prompt, re.M | re.S)
    if not m:
        return []
    inner = m.group(1)
    params, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            params.append(cur); cur = ""
        else:
            cur += ch
    if cur.strip():
        params.append(cur)
    out = []
    for p in params:
        p = p.strip()
        if p in ("self",) or not p:
            continue
        name, ann = (p.split(":", 1) + [""])[:2]
        name = name.strip().split("=")[0].strip()
        out.append((name, ann.split("=")[0].strip()))
    return out

def type_ok(val, ann):
    a = ann.replace(" ", "")
    if a in ("int",):
        return isinstance(val, int) and not isinstance(val, bool)
    if a == "str":
        return isinstance(val, str)
    if a == "bool":
        return isinstance(val, bool)
    if a == "float":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    m = re.fullmatch(r"(?:List|list)\[(.*)\]", a)
    if m:
        return isinstance(val, list) and all(type_ok(x, m.group(1)) for x in val)
    if a.startswith("Optional["):
        return val is None or type_ok(val, a[len("Optional["):-1])
    return True  # unknown annotation: not checked

# ---------------------------------------------------------------- constraints block
def constraints_block(prompt):
    i = prompt.find("Constraints")
    if i < 0:
        return ""
    block = prompt[i:]
    stop = re.search(r"\n\s*(?:Follow[- ]up|Note)\b", block)
    if stop:
        block = block[:stop.start()]
    block = block.split('"""')[0]
    return block

# power forms FIRST (the same lesson as bench_import.py: plain digits would match the "2" of "2^31 - 1")
_NUMX = r"-?\s*(?:\d[\d,]*\s*\*\s*10\^\d+|10\^\d+|2\^\d+|\d[\d,]*(?!\s*\^))(?:\s*[-+]\s*(?:10\^\d+|2\^\d+|\d+))?"
_SYMX = r"(?:\d+\s*\*\s*)?[A-Za-z_]\w*(?:\[[^\]]*\])*(?:\.length|\.size\(\))?(?:\s*[-+]\s*\d+)?"
_SIDE = r"(" + _NUMX + r"|" + _SYMX + r")"
_NAME1 = r"[A-Za-z_]\w*(?:\[[^\]]*\])*(?:\.length|\.size\(\))?"
_NAMES = r"(" + _NAME1 + r"(?:\s*,\s*" + _NAME1 + r")*)"
_BOUND = re.compile(_SIDE + r"\s*(<=|<)\s*" + _NAMES + r"\s*(<=|<)\s*" + _SIDE)
_BOUND3 = re.compile(r"^\s*" + _SIDE + r"\s*(<=|<)\s*(" + _NAME1 + r")\s*(<=|<)\s*(" + _NAME1 + r")\s*(<=|<)\s*" + _SIDE + r"\s*$")
_BOUND_ONE = re.compile(r"^\s*(" + _NAME1 + r")\s*(<=|<|>=|>)\s*" + _SIDE + r"\s*$")
_TERM = r"(?:" + _NUMX + r"|" + _SYMX + r")"
_EQCHAIN = re.compile(r"^\s*(" + _TERM + r")(?:\s*==\s*(" + _TERM + r"))+\s*$")
_SUBJECTS = r"(" + _NAME1 + r"(?:\s*(?:,|and)\s*" + _NAME1 + r")*)"
_CHARSET = re.compile(r"^\s*" + _SUBJECTS + r"\s+(?:only\s+)?(?:consists?|contains?|comprises?|is\s+made\s+up|are\s+made\s+up)\s+(?:only\s+)?(?:of\s+)?(.*?)\s*$", re.I)
_ELEMSET = re.compile(r"^\s*" + _SUBJECTS + r"\s+(?:is|are)\s+(?:either\s+|one\s+of\s+)?((?:(?:'[^']*'|\"[^\"]*\"|-?\d+)\s*(?:,\s*|\s+or\s+|,\s*or\s+)?)+)\s*$", re.I)
_SORTED = re.compile(r"^\s*(" + _NAME1 + r")\s+(?:is|are)\s+(?:sorted\s+)?(?:in\s+)?(non-decreasing|non-increasing|ascending|descending|strictly\s+increasing|strictly\s+decreasing|increasing|decreasing)(?:\s+order)?\s*$", re.I)
_UNIQUE = re.compile(r"^\s*(?:(?:all\s+(?:the\s+)?|the\s+)?(?:elements|integers|values|numbers|characters|strings|words)\s+(?:of|in)\s+" + _SUBJECTS + r"\s+are\s+(?:unique|distinct|different)|(" + _NAME1 + r")\s+(?:contains|consists\s+of|has)\s+(?:only\s+)?(?:unique|distinct)\s+)", re.I)
_PARITY = re.compile(r"^\s*(" + _NAME1 + r")\s+is\s+(even|odd)\s*$", re.I)

def _charset(phrase):
    p = phrase.lower().rstrip(".")
    allowed = set()
    known = False
    if re.search(r"lower-?case", p):
        allowed |= set(string.ascii_lowercase); known = True
    if re.search(r"upper-?case", p):
        allowed |= set(string.ascii_uppercase); known = True
    if re.search(r"\b(?:english\s+)?(?:letters|characters|alphabets)\b", p) and not re.search(r"lower-?case|upper-?case", p):
        allowed |= set(string.ascii_letters); known = True
    if "digit" in p or "numeric" in p:
        allowed |= set(string.digits); known = True
    if re.search(r"\bspaces?\b", p):
        allowed.add(" "); known = True
    if "printable ascii" in p:
        allowed |= set(chr(c) for c in range(32, 127)); known = True
    for q in re.findall(r"'([^']*)'|\"([^\"]*)\"", phrase):
        v = q[0] or q[1]
        if v:
            allowed |= set(v); known = True
    residue = re.sub(r"'[^']*'|\"[^\"]*\"", "", p)
    residue = re.sub(r"one\s+of\s+the\s+following|following|lower-?case|upper-?case|english|letters|alphabets|digits|digit|spaces|space|and|or|only|the|characters|character|printable|ascii|numeric|:|,|/|\.|\s", "", residue)
    if residue.strip():
        return None
    return allowed if known else None

def _split_names(txt):
    return [x.strip() for x in re.split(r"\s*(?:,|\band\b)\s*", txt) if x.strip()]

def _parse_values(txt):
    vals = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"|(-?\d+)", txt):
        if m.group(3) is not None:
            vals.append(int(m.group(3)))
        else:
            vals.append(m.group(1) if m.group(1) is not None else m.group(2))
    residue = re.sub(r"'[^']*'|\"[^\"]*\"|-?\d+|,|\bor\b|\beither\b|\s", "", txt)
    return vals if not residue else None

def parse_constraints(prompt, params):
    """Return (predicates, skipped_lines). A predicate: (text, fn(args_by_name) -> list of why)."""
    block = constraints_block(prompt)
    names = [n for n, _ in params]
    lower = {n.lower(): n for n in names}
    preds, skipped = [], []
    dims = {}
    lines = [re.sub(r"[​ ]", " ", l).strip().rstrip(".").strip() for l in block.split("\n")[1:]]
    lines = [l for l in lines if re.search(r"[A-Za-z0-9]", l)]
    block_quoted = set()
    for q in re.findall(r"'([^']*)'|\"([^\"]*)\"", block):
        block_quoted |= set(q[0] or q[1])
    for l in lines:
        m = _EQCHAIN.match(l)
        if m:
            terms = [t.strip() for t in re.split(r"\s*==\s*", l.strip())]
            for t in terms:
                mm = re.fullmatch(r"([A-Za-z_]\w*)((?:\[[^\]]*\])*)\.length", t)
                if mm and mm.group(1).lower() in lower:
                    for v in terms:
                        if re.fullmatch(r"[A-Za-z_]\w*", v) and v.lower() not in lower:
                            dims[v] = (lower[mm.group(1).lower()], mm.group(2).count("["))

    def resolve(tok, args):
        """Numeric value of a side, or the value/length a symbolic side names; None if unknown."""
        v = _eval_bound(tok)
        if v is not None:
            return v
        t = tok.strip()
        m = re.fullmatch(r"(?:(\d+)\s*\*\s*)?([A-Za-z_]\w*)((?:\[[^\]]*\])*)(\.length|\.size\(\))?(\s*[-+]\s*\d+)?", t)
        if not m:
            return None
        mul, base, idx, ln, off = m.groups()
        vals = term_values(base + (idx or "") + (ln or ""), args)
        if not vals or len(set(vals)) != 1:
            return None
        val = vals[0]
        if mul:
            val *= int(mul)
        if off:
            val += int(off.replace(" ", ""))
        return val

    def term_values(t, args):
        t = t.strip()
        v = _eval_bound(t)
        if v is not None:
            return [v]
        m = re.fullmatch(r"(?:(\d+)\s*\*\s*)?([A-Za-z_]\w*)((?:\[[^\]]*\])*)(\.length|\.size\(\))?(\s*[-+]\s*\d+)?", t)
        if not m:
            return None
        mul, base, idx, ln, off = m.groups()
        subs = re.findall(r"\[([^\]]*)\]", idx or "")
        depth = len(subs)
        if base.lower() in lower:
            a = args.get(lower[base.lower()])
            vals = [a]
            for sub in subs:
                nv = []
                lit = re.fullmatch(r"\s*(-?\d+)\s*", sub)
                for x in vals:
                    if not isinstance(x, list):
                        return None
                    if lit:                      # a literal index names one element of each list
                        k = int(lit.group(1))
                        if -len(x) <= k < len(x):
                            nv.append(x[k])
                        else:
                            return None          # the list is too short for the index: not this predicate's call
                    else:
                        nv.extend(x)
                vals = nv
            if ln:
                out = []
                for x in vals:
                    if isinstance(x, (list, str)):
                        out.append(len(x))
                    else:
                        return None
                vals = out
        elif base in dims and depth == 0 and not ln:
            arr, d = dims[base]
            a = args.get(arr)
            for _ in range(d):
                a = a[0] if isinstance(a, list) and a else None
            if not isinstance(a, list):
                return None
            vals = [len(a)]
        else:
            return None
        if mul or off:
            out = []
            for x in vals:
                if isinstance(x, bool) or not isinstance(x, int):
                    return None
                y = x * int(mul) if mul else x
                y = y + int(off.replace(" ", "")) if off else y
                out.append(y)
            vals = out
        return vals

    def bound_pred(lo, op1, nm, op2, hi, text):
        def fn(args):
            lo_v = resolve(lo, args) if lo is not None else None
            hi_v = resolve(hi, args) if hi is not None else None
            vals = term_values(nm, args)
            if vals is None or (lo_v is None and hi_v is None):
                return []
            for v in vals:
                if isinstance(v, bool):
                    continue
                if isinstance(v, float):
                    return ["%s=%r is not an integer" % (nm, v)]
                if not isinstance(v, int):
                    continue
                ok_lo = True if lo_v is None else (v >= lo_v if op1 == "<=" else v > lo_v)
                ok_hi = True if hi_v is None else (v <= hi_v if op2 == "<=" else v < hi_v)
                if not (ok_lo and ok_hi):
                    return ["%s=%s outside %s" % (nm, v, text)]
            return []
        return fn

    for l in lines:
        m = _EQCHAIN.match(l)
        if m:
            terms = [t.strip() for t in re.split(r"\s*==\s*", l.strip())]
            def mkeq(terms=terms, text=l):
                def fn(args):
                    allv = []
                    for t in terms:
                        vals = term_values(t, args)
                        if vals is None:
                            return []
                        allv.extend(vals)
                    if len(set(allv)) > 1:
                        return ["values %s do not satisfy %s" % (sorted(set(allv))[:4], text)]
                    return []
                return fn
            preds.append((l, mkeq())); continue
        m = _BOUND3.match(l)
        if m:
            lo, op1, a, op2, b, op3, hi = m.groups()
            preds.append((l, bound_pred(lo, op1, a, op3, hi, l)))
            preds.append((l, bound_pred(lo, op1, b, op3, hi, l)))
            preds.append((l, bound_pred(a, op2, b, "<=", None, l)))
            continue
        handled = False
        for m in _BOUND.finditer(l):
            lo, op1, names_txt, op2, hi = m.groups()
            for nm in _split_names(names_txt):
                preds.append((l, bound_pred(lo, op1, nm, op2, hi, l))); handled = True
        if handled:
            continue
        m = _BOUND_ONE.match(l)
        if m:
            nm, op, side = m.groups()
            if op in ("<=", "<"):
                preds.append((l, bound_pred(None, "<=", nm, op, side, l)))
            else:
                preds.append((l, bound_pred(side, "<=" if op == ">=" else "<", nm, "<=", None, l)))
            continue
        m = _ELEMSET.match(l)
        if m:
            subjects = _split_names(m.group(1)); vals = _parse_values(m.group(2))
            if vals is not None and all(re.match(r"[A-Za-z_]\w*", x).group(0).lower() in lower for x in subjects):
                def mke(subjects=subjects, allowed=set(vals), text=l):
                    def fn(args):
                        for nm in subjects:
                            tv = term_values(nm, args)
                            if tv is None:
                                continue
                            for v in tv:
                                if isinstance(v, (list, dict)):
                                    return []
                                if v not in allowed:
                                    return ["%s=%s is not among %s" % (nm, json.dumps(v)[:20], text)]
                        return []
                    return fn
                preds.append((l, mke())); continue
        m = _CHARSET.match(l)
        if m:
            subjects = _split_names(m.group(1))
            if all(re.match(r"[A-Za-z_]\w*", x).group(0).lower() in lower for x in subjects):
                allowed = _charset(m.group(2))
                if allowed is None:
                    skipped.append(l); continue
                allowed = allowed | block_quoted
                def mkc(subjects=subjects, allowed=allowed, text=l):
                    def fn(args):
                        for nm in subjects:
                            tv = term_values(nm if "[" in nm else nm + "[i]", args) if isinstance(args.get(lower.get(re.match(r"[A-Za-z_]\w*", nm).group(0).lower())), list) else term_values(nm, args)
                            if tv is None:
                                continue
                            for sv in tv:
                                if isinstance(sv, str) and not set(sv) <= allowed:
                                    return ["%s has characters outside the stated set: %r" % (nm, "".join(sorted(set(sv) - allowed))[:20])]
                        return []
                    return fn
                preds.append((l, mkc())); continue
        m = _SORTED.match(l)
        if m and re.match(r"[A-Za-z_]\w*", m.group(1)).group(0).lower() in lower:
            kind = re.sub(r"\s+", " ", m.group(2).lower())
            def mks(nm=m.group(1), kind=kind, text=l):
                def fn(args):
                    tv = term_values(nm, args)
                    if tv is None or len(tv) != 1 or not isinstance(tv[0], list):
                        return []
                    a = tv[0]
                    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in a):
                        return []
                    pairs = list(zip(a, a[1:]))
                    ok = {"non-decreasing": all(x <= y for x, y in pairs), "ascending": all(x <= y for x, y in pairs),
                          "increasing": all(x <= y for x, y in pairs), "strictly increasing": all(x < y for x, y in pairs),
                          "non-increasing": all(x >= y for x, y in pairs), "descending": all(x >= y for x, y in pairs),
                          "decreasing": all(x >= y for x, y in pairs), "strictly decreasing": all(x > y for x, y in pairs)}.get(kind, True)
                    return [] if ok else ["%s is not %s" % (nm, text)]
                return fn
            preds.append((l, mks())); continue
        m = _UNIQUE.match(l)
        if m and (m.group(1) or m.group(2)):
            subjects = _split_names(m.group(1) or m.group(2))
            if all(re.match(r"[A-Za-z_]\w*", x).group(0).lower() in lower for x in subjects):
                def mku(subjects=subjects, text=l):
                    def fn(args):
                        for nm in subjects:
                            tv = term_values(nm, args)
                            if tv is None or len(tv) != 1 or not isinstance(tv[0], list):
                                return []
                            a = tv[0]
                            if len(set(json.dumps(x) for x in a)) != len(a):
                                return ["%s has repeated elements against %s" % (nm, text)]
                        return []
                    return fn
                preds.append((l, mku())); continue
        m = _PARITY.match(l)
        if m and re.match(r"[A-Za-z_]\w*", m.group(1)).group(0).lower() in lower:
            def mkp(nm=m.group(1), par=m.group(2).lower(), text=l):
                def fn(args):
                    tv = term_values(nm, args)
                    if tv is None:
                        return []
                    for v in tv:
                        if isinstance(v, int) and not isinstance(v, bool) and (v % 2 == 0) != (par == "even"):
                            return ["%s=%s is not %s" % (nm, v, par)]
                    return []
                return fn
            preds.append((l, mkp())); continue
        skipped.append(l)
    return preds, skipped

def screen(prompt, entry_point, inputs):
    params = parse_signature(prompt, entry_point)
    preds, skipped = parse_constraints(prompt, params)
    viol = []
    for i, args in enumerate(inputs):
        if len(args) != len(params):
            continue
        by = {n: v for (n, _), v in zip(params, args)}
        why = []
        for (n, ann), v in zip(params, args):
            if ann and not type_ok(v, ann):
                why.append("%s=%s is not of the stated type %s" % (n, json.dumps(v)[:40], ann))
        for text, fn in preds:
            try:
                why.extend(fn(by))
            except Exception as e:  # a predicate that cannot read these args does not decide
                pass
        if why:
            viol.append({"where": "input %d" % i, "args": json.dumps(args)[:120], "why": why[:4]})
    return viol, [t for t, _ in preds], skipped

# ---------------------------------------------------------------- probe
def probe():
    INC = "tasks/build/training-pool/incoming/lcds"
    REP = "tasks/build/training-pool/checkers/train-check-lcds-1/tools/domain_report.json"
    checker = json.load(open(REP))
    tot_rec = tot_inp = flagged_rec = flagged_inp = 0
    n_preds = n_skipped = 0
    caught = missed = extra = 0
    missed_ex, extra_ex = [], []
    per_rec = {}
    for f in sorted(glob.glob(INC + "/*.json")):
        d = json.load(open(f))
        inputs = list(d["base_input"]) + list(d["plus_input"])
        viol, preds, skipped = screen(d["prompt"], d["entry_point"], inputs)
        tot_rec += 1; tot_inp += len(inputs); n_preds += len(preds); n_skipped += len(skipped)
        if viol:
            flagged_rec += 1; flagged_inp += len(viol)
        per_rec[d["task_id"]] = {"n_inputs": len(inputs), "violations": viol, "constraints_evaluated": preds, "constraints_skipped": skipped}
        ch = checker.get(d["task_id"])
        if ch is not None:
            nb = len(d["base_input"])
            mine = {int(v["where"].split()[1]) for v in viol}
            theirs = set()
            for v in ch["violations"]:
                m = re.fullmatch(r"(base|plus)\[(\d+)\]", v["where"])
                if m:
                    theirs.add(int(m.group(2)) + (0 if m.group(1) == "base" else nb))
            c = len(mine & theirs); caught += c
            m_ = theirs - mine; missed += len(m_)
            e_ = mine - theirs; extra += len(e_)
            for i in sorted(m_)[:2]:
                why = [v["why"] for v in ch["violations"] if v["where"] in ("base[%d]" % i, "plus[%d]" % (i - nb))]
                missed_ex.append((d["task_id"].split("/")[1], json.dumps(inputs[i])[:50], (why[0] if why else [""])[0][:70]))
            for i in sorted(e_)[:2]:
                why = [v["why"] for v in viol if v["where"] == "input %d" % i]
                extra_ex.append((d["task_id"].split("/")[1], json.dumps(inputs[i])[:50], (why[0] if why else [""])[0][:70]))
    print("landed records %d, inputs %d; screen flags %d records / %d inputs; constraint lines evaluated %d, skipped %d"
          % (tot_rec, tot_inp, flagged_rec, flagged_inp, n_preds, n_skipped))
    print("against train-check-lcds-1's 60 records: caught %d of their %d flagged inputs, missed %d; flagged %d inputs they did not" % (caught, caught + missed, missed, extra))
    print("--- missed (theirs, not mine), sample:")
    for x in missed_ex[:14]: print("   ", x)
    print("--- extra (mine, not theirs), sample:")
    for x in extra_ex[:14]: print("   ", x)
    out = "tasks/build/acquire/conv-leetcode/landing/domain_screen_probe.json"
    with open(out + ".part", "w") as f:
        json.dump(per_rec, f, indent=0)
    os.replace(out + ".part", out)
    print("per-record probe written:", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    if a.probe:
        probe()

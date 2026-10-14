#!/usr/bin/env python3
import argparse, ast, difflib, hashlib, os, shutil, sys

OLD_MD5 = "702106b1"

EDITS = [
    ('def parse_kwarg_call(s, param_order):\n'
     '    """LeetCode input string \'nums = [3,3], target = 6\' -> positional list\n'
     '    ordered by param_order. Raises on non-literal values."""\n'
     '    tree = ast.parse("_f(%s)" % s, mode="eval")\n'
     '    call = tree.body\n'
     '    if call.args and not call.keywords:\n'
     '        return [ast.literal_eval(a) for a in call.args]\n'
     '    kw = {k.arg: ast.literal_eval(k.value) for k in call.keywords}\n'
     '    if set(kw) != set(param_order):\n'
     '        raise ValueError("kwargs %s != params %s" % (sorted(kw),\n'
     '                                                     param_order))\n'
     '    return [kw[p] for p in param_order]\n',
     'def parse_kwarg_call(s, param_order, positional_fallback=False):\n'
     '    """LeetCode input string \'nums = [3,3], target = 6\' -> positional list\n'
     '    ordered by param_order. Raises on non-literal values. With\n'
     '    positional_fallback (statement examples only), keyword names that do\n'
     '    not match the parameters are taken in the order written when the count\n'
     '    matches (LeetCode renamed parameters after some statements were\n'
     '    written: "edgeList" vs edges, "ops" vs operations; the reference run\n'
     '    remains the check)."""\n'
     '    tree = ast.parse("_f(%s)" % s, mode="eval")\n'
     '    call = tree.body\n'
     '    if call.args and not call.keywords:\n'
     '        return [ast.literal_eval(a) for a in call.args]\n'
     '    kw = {k.arg: ast.literal_eval(k.value) for k in call.keywords}\n'
     '    if set(kw) != set(param_order):\n'
     '        if positional_fallback and not call.args and len(kw) == len(param_order):\n'
     '            return [ast.literal_eval(k.value) for k in call.keywords]\n'
     '        raise ValueError("kwargs %s != params %s" % (sorted(kw),\n'
     '                                                     param_order))\n'
     '    return [kw[p] for p in param_order]\n'),
    ('    base_in, base_exp, ex_bad = [], [], 0\n'
     '    for mm in LC_EXAMPLE_RE.finditer(desc):\n'
     '        try:\n'
     '            args = parse_kwarg_call(mm.group(1), params)\n',
     '    base_in, base_exp, ex_bad = [], [], 0\n'
     '    ex_renamed = 0\n'
     '    for mm in LC_EXAMPLE_RE.finditer(desc):\n'
     '        try:\n'
     '            args = parse_kwarg_call(mm.group(1), params, positional_fallback=True)\n'
     '            kwnames = re.findall(r"(?:^|,)\\s*([A-Za-z_]\\w*)\\s*=", mm.group(1))\n'
     '            if kwnames and set(kwnames) != set(params):\n'
     '                ex_renamed += 1\n'),
    ('    m.update(n_base=len(base_in), n_plus=len(plus_in),\n'
     '             n_dropped_nonliteral=dropped, n_example_parse_fail=ex_bad,\n'
     '             n_dropped_none_expected=dropped_none,\n'
     '             n_dropped_error_output=dropped_error)\n',
     '    m.update(n_base=len(base_in), n_plus=len(plus_in),\n'
     '             n_dropped_nonliteral=dropped, n_example_parse_fail=ex_bad,\n'
     '             n_dropped_none_expected=dropped_none,\n'
     '             n_dropped_error_output=dropped_error,\n'
     '             example_kwargs_renamed=ex_renamed)\n'),
]


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("--out", default=""); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check and not a.out:
        sys.exit("REFUSED: give --out <staged path> or --check")
    raw = open(a.src, "rb").read()
    if not md5(raw).startswith(OLD_MD5):
        sys.exit("REFUSED: %s has md5 %s, not %s..." % (a.src, md5(raw), OLD_MD5))
    src = raw.decode("utf-8"); new = src
    for i, (o, n) in enumerate(EDITS, 1):
        c = new.count(o)
        if c != 1:
            sys.exit("REFUSED: edit %d anchor occurs %d times, not once:\n%s" % (i, c, o[:200]))
        new = new.replace(o, n)
    ast.parse(new)
    print("".join(difflib.unified_diff(src.splitlines(True), new.splitlines(True), "bench_import.py (%s)" % md5(raw)[:8], "patched")))
    print("patched md5 %s | %d -> %d bytes | %d edits" % (md5(new.encode("utf-8")), len(raw), len(new.encode("utf-8")), len(EDITS)))
    if a.check:
        print("--check: nothing written"); return
    if os.path.abspath(a.out) == os.path.abspath(a.src):
        sys.exit("REFUSED: --out is the source itself")
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    shutil.copymode(a.src, tmp); os.replace(tmp, a.out)
    print("staged:", a.out, "md5", md5(open(a.out, "rb").read()))


if __name__ == "__main__":
    main()

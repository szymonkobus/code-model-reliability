#!/usr/bin/env python3
import argparse, ast, difflib, hashlib, os, shutil, sys

OLD_MD5 = "47a45d6a"

EDITS = [
    ('def canon(s):\n'
     '    lines = [l.rstrip() for l in (s or "").replace("\\r\\n", "\\n")\n'
     '             .replace("\\r", "\\n").split("\\n")]\n'
     '    while lines and lines[-1] == "":\n'
     '        lines.pop()\n'
     '    return "\\n".join(lines)\n',
     'def canon(s):\n'
     '    lines = [l.rstrip() for l in (s or "").replace("\\r\\n", "\\n")\n'
     '             .replace("\\r", "\\n").split("\\n")]\n'
     '    while lines and lines[-1] == "":\n'
     '        lines.pop()\n'
     '    return "\\n".join(lines)\n'
     '\n'
     '\n'
     'def fold(s):\n'
     '    """The canonical form with the empty lines removed: a CodeChef sample\n'
     '    printed with blank lines between its lines then matches its stored test\n'
     '    (train-check-taco-gen1-1, 25 Sep 2026; six records of gen_batch_0001-0003\n'
     '    had no example kind and promoted official tests to base)."""\n'
     '    return "\\n".join(l for l in canon(s).split("\\n") if l.strip() != "")\n'),
    ('    ex_set = set(example_inputs)\n'
     '    n_ex = 0\n',
     '    ex_set = set(example_inputs)\n'
     '    ex_folded = {fold(x) for x in example_inputs if fold(x)}\n'
     '    n_ex = 0\n'
     '    n_ex_fold = 0\n'),
    ('        kind = "example" if sig[0] in ex_set else "official"\n',
     '        if sig[0] in ex_set:\n'
     '            kind = "example"\n'
     '        elif ex_folded and fold(sig[0]) in ex_folded:\n'
     '            kind = "example"        # the sample with its blank lines folded\n'
     '            n_ex_fold += 1\n'
     '        else:\n'
     '            kind = "official"\n'),
    ('            "n_line_lists_joined": n_joined,\n',
     '            "n_line_lists_joined": n_joined,\n'
     '            "n_example_by_fold": n_ex_fold,\n'),
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
    print("".join(difflib.unified_diff(src.splitlines(True), new.splitlines(True), "fetch_taco.py (%s)" % md5(raw)[:8], "patched")))
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

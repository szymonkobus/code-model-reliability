#!/usr/bin/env python3
import argparse, ast, difflib, hashlib, os, shutil, sys

OLD_MD5 = "b39f946e"

EDITS = [
    ('    return "\\n".join(l for l in canon(s).split("\\n") if l.strip() != "")\n',
     '    return "\\n".join(l for l in canon(s).split("\\n") if l.strip() != "")\n'
     '\n'
     '\n'
     '_STDIN_HDR = re.compile(r"^\\s*STDIN\\b", re.I)\n'
     '_DASHES = re.compile(r"^\\s*-{2,}(?:\\s+-{2,})*\\s*$")\n'
     '\n'
     '\n'
     'def block_forms(block):\n'
     '    """The forms of a statement example block a stored test may equal: the\n'
     '    block folded, and — for HackerRank\'s two-column sample ("STDIN  Function"\n'
     '    header, a dashes line, then each input line beside an annotation, as on\n'
     '    taco/18090 and taco/4614; train-check-taco-gen7-1, 25 Sep 2026) — the fold\n'
     '    of its left column, each line cut at its first run of two or more spaces."""\n'
     '    forms = {fold(block)}\n'
     '    lines = canon(block).split("\\n")\n'
     '    if lines and _STDIN_HDR.match(lines[0]):\n'
     '        body = lines[1:]\n'
     '        if body and _DASHES.match(body[0]):\n'
     '            body = body[1:]\n'
     '        left = [re.split(r"\\s{2,}", l.strip(), maxsplit=1)[0] for l in body if l.strip()]\n'
     '        if left:\n'
     '            forms.add(fold("\\n".join(left)))\n'
     '    forms.discard("")\n'
     '    return forms\n'),
    ('    ex_folded = {fold(x) for x in example_inputs if fold(x)}\n',
     '    ex_folded = set()\n'
     '    for x in example_inputs:\n'
     '        if x:\n'
     '            ex_folded |= block_forms(x)   # the fold, and the left column of a two-column sample\n'),
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

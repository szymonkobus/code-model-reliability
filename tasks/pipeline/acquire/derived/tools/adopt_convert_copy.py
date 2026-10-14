#!/usr/bin/env python3
import argparse, ast, difflib, hashlib, os, re, shutil, sys

TRAILERS = ["compared exactly, character for character", "in this casing", "An efficient algorithm is required: the time limit"]
BANNED = re.compile(r"\b(judge[sd]?|grader[s]?|runner[s]?|harness|autograder)\b", re.I)


def md5(b):
    return hashlib.md5(b).hexdigest()


def top_defs(tree):
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record"); ap.add_argument("candidate")
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True)
    ap.add_argument("--expect-defs", default="")
    ap.add_argument("--check", action="store_true"); ap.add_argument("--diff-sha256", default="")
    a = ap.parse_args()
    if not a.check and not a.diff_sha256:
        sys.exit("REFUSED: give --check first, then --diff-sha256 <sha> of the diff you read")
    rb, cb = open(a.record, "rb").read(), open(a.candidate, "rb").read()
    if not md5(rb).startswith(a.old):
        sys.exit("REFUSED: record md5 %s is not %s..." % (md5(rb), a.old))
    if not md5(cb).startswith(a.new):
        sys.exit("REFUSED: candidate md5 %s is not %s..." % (md5(cb), a.new))
    rs, cs = rb.decode("utf-8"), cb.decode("utf-8")
    tree = ast.parse(cs)
    want = {d for d in a.expect_defs.split(",") if d}
    missing = want - top_defs(tree)
    if missing:
        sys.exit("REFUSED: expected top-level definitions missing from the candidate: %s" % sorted(missing))
    for t in TRAILERS:
        if t not in cs:
            sys.exit("REFUSED: trailer sentence of record missing from the candidate: %r" % t)
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and BANNED.search(n.value) and "os._exit" not in n.value]
    if bad:
        sys.exit("REFUSED: judge/grader/runner words in string literals: %r" % bad[:5])
    diff = "".join(difflib.unified_diff(rs.splitlines(True), cs.splitlines(True),
                                        "convert.py (%s)" % md5(rb)[:8], "candidate (%s)" % md5(cb)[:8]))
    dsha = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    if a.check:
        print(diff)
        print("diff sha256 %s | +%d -%d lines | %d -> %d bytes" % (dsha, added, removed, len(rb), len(cb)))
        print("--check: nothing written")
        return
    if dsha != a.diff_sha256:
        sys.exit("REFUSED: the diff now (sha256 %s) is not the one read (%s): something moved" % (dsha, a.diff_sha256))
    keep = os.path.join(os.path.dirname(a.record) or ".", "convert.%s.py" % md5(rb)[:8])
    if not os.path.exists(keep):
        shutil.copy2(a.record, keep)
    tmp = a.record + ".tmp"
    with open(tmp, "wb") as f:
        f.write(cb)
    shutil.copymode(a.record, tmp)
    os.replace(tmp, a.record)
    back = open(a.record, "rb").read()
    if md5(back) != md5(cb):
        sys.exit("FAILED: re-read md5 %s != %s" % (md5(back), md5(cb)))
    print("adopted: %s md5 %s (+%d -%d lines) | predecessor kept: %s md5 %s"
          % (a.record, md5(back), added, removed, keep, md5(open(keep, "rb").read())))


if __name__ == "__main__":
    main()

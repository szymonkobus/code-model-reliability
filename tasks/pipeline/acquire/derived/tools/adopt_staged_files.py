#!/usr/bin/env python3
import argparse, hashlib, os, shutil


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", action="append", required=True); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    plan = []
    for p in a.pair:
        s, r, want = p.split(":")
        if not md5(s).startswith(want):
            raise SystemExit("REFUSED: staged %s has md5 %s, not the witnessed %s..." % (s, md5(s), want))
        if not os.path.exists(r):
            raise SystemExit("REFUSED: record %s does not exist" % r)
        plan.append((s, r))
        print("%s (%s) -> %s (was %s)" % (s, md5(s)[:8], r, md5(r)[:8]))
    if a.check:
        print("--check: nothing written"); return
    for s, r in plan:
        base, ext = os.path.splitext(os.path.basename(r))
        keep = os.path.join(os.path.dirname(r) or ".", "%s.%s%s" % (base, md5(r)[:8], ext))
        if not os.path.exists(keep):
            shutil.copy2(r, keep)
        tmp = r + ".tmp"
        shutil.copyfile(s, tmp)
        shutil.copymode(r, tmp)
        os.replace(tmp, r)
        if md5(r) != md5(s):
            raise SystemExit("FAILED: %s re-read md5 %s != %s" % (r, md5(r), md5(s)))
        print("adopted %s md5 %s | predecessor %s" % (r, md5(r), keep))


if __name__ == "__main__":
    main()

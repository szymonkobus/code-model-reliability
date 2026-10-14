#!/usr/bin/env python3
import glob, importlib.util, json, sys


def load(path):
    spec = importlib.util.spec_from_file_location("convert_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_raw(pattern, want):
    found = {}
    for fn in sorted(glob.glob(pattern)):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                if not any(('"taco/%s"' % i) in line for i in want):
                    continue
                rec = json.loads(line)
                cid = rec.get("cand_id", "")
                for i in want:
                    if cid == "taco/%s" % i and i not in found:
                        found[i] = (fn, rec)
        if len(found) == len(want):
            break
    return found


def main():
    path, pattern, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
    src = open(path, encoding="utf-8").read()
    if '__name__ == "__main__"' not in src and "__name__ == '__main__'" not in src:
        sys.exit("REFUSED: %s has no main guard; importing it would run it" % path)
    mod = load(path)
    for i, (fn, rec) in sorted(find_raw(pattern, ids).items(), key=lambda kv: ids.index(kv[0])):
        governs = mod.case_grant_governs_output(rec)
        expected = [t.get("expected", t.get("output", "")) for t in rec.get("tests", [])]
        pin = mod.case_pin_text(expected, mod.statement_text(rec)) if governs else ""
        print("taco/%s (%s): governs_output=%s | pin=%r" % (i, fn.rsplit("/", 1)[-1], governs, pin[:160]))
    missing = [i for i in ids if i not in find_raw(pattern, ids)]
    if missing:
        print("not found under the glob:", missing)


if __name__ == "__main__":
    main()

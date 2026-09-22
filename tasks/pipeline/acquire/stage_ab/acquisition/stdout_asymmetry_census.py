#!/usr/bin/env python3
"""Stored expected = canon(official output): CRLF->LF, per-line rstrip, trailing
blank lines dropped. The judge historically stripped only whole-output
trailing whitespace from a text's output, so an attempt can flip only on
inputs where canon(official) != official.rstrip() (per-line trailing
spaces, CR characters, interior blank-line structure). Both lists are
emitted: changed_any (canon != raw) and changed_beyond_whole_strip
(canon != raw.rstrip()). Positions are given as base/plus index and as the
flat base+plus index. Kept tests that did not come from the candidate's
official list (statement examples attached at conversion) are reported as
unmatched, with their count.
"""
import argparse, hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # canon

CAND_ID_RE = re.compile(r'"cand_id":\s*"([^"]+)"')


def key(s):
    return hashlib.sha1(convert.canon(s or "").encode("utf-8", "replace")).hexdigest()


def kinds(raw):
    k = []
    if "\r" in raw:
        k.append("cr")
    lf = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = lf.split("\n")
    if any(l != l.rstrip() for l in lines):
        k.append("trailing-space-lines")
    body = lines[:]
    while body and body[-1] == "":
        body.pop()
    if len(lines) - len(body) > 1:
        k.append("trailing-blank-lines")
    if not raw.endswith("\n"):
        k.append("no-final-newline")
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="live task file with base/plus inputs + expecteds (survivors dump)")
    ap.add_argument("--cands", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tasks = {}
    with open(a.tasks) as fh:
        for line in fh:
            if line.strip():
                t = json.loads(line)
                tasks[t["task_id"]] = t
    wanted = set(tasks)
    found = {}
    for path in a.cands:
        with open(path) as fh:
            for line in fh:
                m = CAND_ID_RE.search(line[:400])
                if not m or m.group(1) not in wanted or m.group(1) in found:
                    continue
                cand = json.loads(line)
                by_key = {}
                for t in cand.get("tests") or []:
                    by_key.setdefault(key(t.get("input") or ""), t.get("output") or "")
                found[m.group(1)] = by_key
    n_rows = 0
    with open(a.out, "w") as out:
        for tid in sorted(tasks):
            t = tasks[tid]
            inputs = [("base", i, x[0]) for i, x in enumerate(t["base_input"])] + \
                     [("plus", i, x[0]) for i, x in enumerate(t["plus_input"])]
            expected = list(t["expected_output"]["base"]) + list(t["expected_output"]["plus"])
            by_key = found.get(tid)
            row = {"task_id": tid, "n_base": len(t["base_input"]), "n_plus": len(t["plus_input"]),
                   "n_inputs": len(inputs), "candidate_found": by_key is not None,
                   "unmatched_inputs": [], "changed_any": [], "changed_beyond_whole_strip": [],
                   "stored_equals_canon_official": None}
            if by_key is not None:
                mism = 0
                for flat, ((pos, idx, inp), exp) in enumerate(zip(inputs, expected)):
                    k = key(inp)
                    if k not in by_key:
                        row["unmatched_inputs"].append({"pos": pos, "index": idx, "flat": flat})
                        continue
                    raw = by_key[k]
                    c = convert.canon(raw)
                    if c != convert.canon(exp):
                        mism += 1
                    if c != raw:
                        row["changed_any"].append({"pos": pos, "index": idx, "flat": flat, "kinds": kinds(raw)})
                    if c != raw.rstrip():
                        row["changed_beyond_whole_strip"].append({"pos": pos, "index": idx, "flat": flat, "kinds": kinds(raw)})
                row["stored_equals_canon_official"] = (mism == 0)
            row["asymmetry_input_indices"] = [x["flat"] for x in row["changed_beyond_whole_strip"]]
            row["n_asymmetry"] = len(row["asymmetry_input_indices"])
            out.write(json.dumps(row) + "\n")
            n_rows += 1
    rows = [json.loads(l) for l in open(a.out)]
    print("CENSUS_SUMMARY tasks %d | candidate found %d | tasks with any normalization change %d | tasks with change beyond whole-output strip %d | inputs beyond whole strip %d of %d | tasks with unmatched (statement-example) inputs %d | stored != canon(official) anywhere: %d" % (
        len(rows), sum(1 for r in rows if r["candidate_found"]), sum(1 for r in rows if r["changed_any"]),
        sum(1 for r in rows if r["changed_beyond_whole_strip"]), sum(len(r["changed_beyond_whole_strip"]) for r in rows),
        sum(r["n_inputs"] for r in rows), sum(1 for r in rows if r["unmatched_inputs"]),
        sum(1 for r in rows if r["stored_equals_canon_official"] is False)), flush=True)


if __name__ == "__main__":
    main()

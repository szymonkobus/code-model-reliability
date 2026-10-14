#!/usr/bin/env python3
"""Each record file is one JSON line ending in "}\\n" (json.dumps with the
default separators, as the landing wrote it). The insertion is the text
', "contract": ""' before the final "}" — so a text diff of the file shows
the single JSON line changed and nothing else, and the change to that line is
exactly the inserted key. Verified per file before anything is written:
  - the file is exactly one line ending in "}\\n";
  - the record has no "contract" key already;
  - after == before[:-2] + ', "contract": ""' + "}\\n"  (character-exact:
    the diff is the inserted text and nothing else);
  - json.loads(after) == json.loads(before) + {"contract": ""};
  - the certifier's eight-field content sha256 (sha256 of json.dumps of
    {task_id, prompt, entry_point, canonical_solution, base_input, plus_input,
    atol, expected_output} with sort_keys) is IDENTICAL before and after.
A file failing any check stops the run (nothing of it written) and is named.

Log row per file: file, list, bytes_before, bytes_after, bytes_added,
content_sha256_before, content_sha256_after, sha_unchanged, diff_lines
(1: the one JSON line), inserted_text, file_sha256_before/after.

The manifests of lists 0040–0048 record each new and replaced FILE sha256 as
landed; --apply adds "new_file_sha256_after_contract_field" and
"replaced_file_sha256_after_contract_field" beside them (content shas are
untouched, the batch lists' own sha256 do not change — the paths are the same).

Usage: python3 add_contract_field.py --lists 0014-0048 [--apply]
"""

import argparse
import datetime
import hashlib
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KNOW = os.path.join(os.path.dirname(HERE), "knowledge")
INCOMING = "tasks/build/training-pool/incoming"
INSERT = ', "contract": ""'
CONTENT_FIELDS = ("task_id", "prompt", "entry_point", "canonical_solution",
                  "base_input", "plus_input", "atol", "expected_output")


def content_sha(rec):
    return hashlib.sha256(json.dumps({k: rec.get(k) for k in CONTENT_FIELDS},
                                     sort_keys=True).encode()).hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def prepare(path, lst):
    before = open(path, "rb").read()
    text = before.decode("utf-8")
    if text.count("\n") != 1 or not text.endswith("}\n") or not text.startswith("{"):
        raise SystemExit("STOP %s: not a single JSON line ending in }\\n" % path)
    rec = json.loads(text)
    if "contract" in rec:
        raise SystemExit("STOP %s: already carries a contract field (%r)"
                         % (path, rec["contract"]))
    after_text = text[:-2] + INSERT + "}\n"
    if after_text != text[:-2] + INSERT + text[-2:]:
        raise SystemExit("STOP %s: insertion is not character-exact" % path)
    new = json.loads(after_text)
    expect = dict(rec)
    expect["contract"] = ""
    if new != expect:
        raise SystemExit("STOP %s: parsed record differs beyond the added key" % path)
    sha_b, sha_a = content_sha(rec), content_sha(new)
    if sha_b != sha_a:
        raise SystemExit("STOP %s: content sha moved" % path)
    after = after_text.encode("utf-8")
    if len(after) - len(before) != len(INSERT.encode("utf-8")):
        raise SystemExit("STOP %s: byte delta is not the inserted text" % path)
    return after, {"file": os.path.relpath(path, INCOMING), "list": lst,
                   "bytes_before": len(before), "bytes_after": len(after),
                   "bytes_added": len(after) - len(before),
                   "content_sha256_before": sha_b, "content_sha256_after": sha_a,
                   "sha_unchanged": sha_b == sha_a, "diff_lines": 1,
                   "inserted_text": INSERT,
                   "file_sha256_before": sha256_bytes(before),
                   "file_sha256_after": sha256_bytes(after)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lists", default="0014-0048")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.lists.split("-"))
    plan, per_list = [], {}
    seen = set()
    for n in range(lo, hi + 1):
        lst = "taco_batch_%04d" % n
        lp = os.path.join(INCOMING, lst + ".txt")
        if not os.path.exists(lp):
            continue
        k = 0
        for line in open(lp):
            p = line.strip()
            if not p:
                continue
            if p in seen:
                raise SystemExit("STOP: %s listed twice" % p)
            seen.add(p)
            after, row = prepare(p, lst)
            plan.append((p, after, row))
            k += 1
        per_list[lst] = k
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_path = os.path.join(KNOW, "contract_field_addition%s.jsonl"
                            % ("" if a.apply else ".dry"))
    print("%s: %d files in %d lists verified (%s); total bytes added %d"
          % ("APPLY" if a.apply else "DRY", len(plan), len(per_list), a.lists,
             sum(r["bytes_added"] for _, _, r in plan)))
    for lst, k in per_list.items():
        print("  %s %d" % (lst, k))
    if not a.apply:
        with open(log_path, "w") as f:
            for _, _, row in plan:
                f.write(json.dumps(dict(row, prepared_at=stamp, applied=False)) + "\n")
        print("prepared only; log %s" % log_path)
        return
    for p, after, row in plan:
        d = os.path.dirname(p)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
        with os.fdopen(fd, "wb") as f:
            f.write(after)
        os.replace(tmp, p)
        if sha256_bytes(open(p, "rb").read()) != row["file_sha256_after"]:
            raise SystemExit("STOP %s: written bytes differ from the plan" % p)
    with open(log_path, "a") as f:
        for _, _, row in plan:
            f.write(json.dumps(dict(row, applied_at=stamp, applied=True)) + "\n")
    # manifests: the file shas as they stand now, beside the as-landed ones
    by_file = {os.path.basename(p): row for p, _, row in plan}
    for n in range(lo, hi + 1):
        mp = os.path.join(INCOMING, "taco_batch_%04d.manifest.jsonl" % n)
        if not os.path.exists(mp):
            continue
        rows = [json.loads(l) for l in open(mp) if l.strip()]
        for m in rows:
            for key in ("new_file", "replaced_file"):
                r = by_file.get(m.get(key))
                if r:
                    m[key + "_sha256_after_contract_field"] = r["file_sha256_after"]
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=INCOMING)
        with os.fdopen(fd, "w") as f:
            f.write("".join(json.dumps(m) + "\n" for m in rows))
        os.replace(tmp, mp)
    print("applied; log %s" % log_path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import glob, hashlib, json, os, sys
INCOMING = "tasks/build/training-pool/incoming"
FIELDS = ["task_id", "prompt", "entry_point", "canonical_solution", "base_input", "plus_input", "atol", "expected_output"]
RULE = "the certifier's (training_certify.py CONTENT_FIELDS): sha256 of json.dumps sort_keys=True, default separators, over task_id, prompt, entry_point, canonical_solution, base_input, plus_input, atol, expected_output"

def cert_sha(rec):
    return hashlib.sha256(json.dumps({k: rec.get(k) for k in FIELDS}, sort_keys=True).encode()).hexdigest()

added = same = 0
shas = {}
for path in sorted(glob.glob(os.path.join(INCOMING, "lcds", "lcds__*.json"))):
    rec = json.load(open(path))
    h = cert_sha(rec)
    shas[os.path.basename(path)] = h
    if rec.get("content_sha256") == h:
        same += 1
        continue
    rec["content_sha256"] = h
    rec["content_sha256_rule"] = RULE
    part = path + ".part"
    with open(part, "w") as f:
        json.dump(rec, f)
    os.replace(part, path)
    added += 1
rows_touched = 0
for rp in sorted(glob.glob(os.path.join(INCOMING, "lcds_batch_*.report.jsonl"))):
    rows = [json.loads(l) for l in open(rp)]
    changed = False
    for r in rows:
        fn = r.get("file")
        if fn and fn in shas and r.get("content_sha256") != shas[fn]:
            r["content_sha256"] = shas[fn]; changed = True; rows_touched += 1
    if changed:
        with open(rp + ".part", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        os.replace(rp + ".part", rp)
print("records: added %d, already present %d; report rows updated %d" % (added, same, rows_touched))

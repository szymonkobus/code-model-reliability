#!/usr/bin/env python3
"""Usage: python3 entity_scan.py [--lists 0001-0030]"""

import argparse
import json
import os
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KNOW = os.path.join(os.path.dirname(HERE), "knowledge")
INCOMING = "tasks/build/training-pool/incoming"
ENTITY = re.compile(r"&gt;|&lt;|&amp;|&quot;|&#\d+;")
FIELDS = ("prompt", "base_input", "plus_input", "expected_output")


def scan_record(rec):
    hits = {}
    example = None
    for f in FIELDS:
        v = rec.get(f)
        text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        ms = list(ENTITY.finditer(text or ""))
        if ms:
            hits[f] = len(ms)
            if example is None:
                m = ms[0]
                example = {"field": f, "context":
                           text[max(0, m.start() - 60):m.end() + 40].replace("\n", " ")}
    return hits, example


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lists", default="0001-0030")
    a = ap.parse_args()
    lo, hi = a.lists.split("-")
    per_list, records = {}, []
    for n in range(int(lo), int(hi) + 1):
        name = "taco_batch_%04d" % n
        lp = os.path.join(INCOMING, name + ".txt")
        if not os.path.exists(lp):
            continue
        form = "?"
        rp = os.path.join(INCOMING, name + ".report.jsonl")
        if os.path.exists(rp):
            first = open(rp).readline().strip()
            if first:
                form = json.loads(first).get("form", "?")
        stats = {"form": form, "records_scanned": 0, "records_with_entities": 0,
                 "places_by_field": {f: 0 for f in FIELDS},
                 "records_by_field": {f: 0 for f in FIELDS}}
        for line in open(lp):
            p = line.strip()
            if not p or not os.path.exists(p):
                continue
            rec = json.load(open(p))
            stats["records_scanned"] += 1
            hits, example = scan_record(rec)
            if hits:
                stats["records_with_entities"] += 1
                for f, k in hits.items():
                    stats["places_by_field"][f] += k
                    stats["records_by_field"][f] += 1
                records.append({"task_id": rec["task_id"], "list": name, "form": form,
                                "fields": hits, "n_places": sum(hits.values()),
                                "example": example,
                                "kinds": sorted({m.group(0) for f in FIELDS for m in
                                                 ENTITY.finditer(
                                                     rec.get(f) if isinstance(rec.get(f), str)
                                                     else json.dumps(rec.get(f), ensure_ascii=False))})})
        per_list[name] = stats
    out = {"scanned_at_lists": a.lists, "pattern": ENTITY.pattern,
           "fields": list(FIELDS), "per_list": per_list, "records": records,
           "totals": {"records_with_entities": len(records),
                      "lists_scanned": len(per_list),
                      "records_scanned": sum(s["records_scanned"] for s in per_list.values())}}
    os.makedirs(KNOW, exist_ok=True)
    path = os.path.join(KNOW, "entity_scan.json")
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=KNOW)
    with os.fdopen(fd, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    print("%-16s %-28s %8s %8s   prompt base plus expected" % ("list", "form", "scanned", "with"))
    for name, s in per_list.items():
        rb = s["records_by_field"]
        print("%-16s %-28s %8d %8d   %6d %4d %4d %8d" % (
            name, s["form"], s["records_scanned"], s["records_with_entities"],
            rb["prompt"], rb["base_input"], rb["plus_input"], rb["expected_output"]))
    print("total records with entities: %d of %d; written %s"
          % (len(records), out["totals"]["records_scanned"], path))
    for r in records[:6]:
        print("  e.g. %-12s %s %s | %s" % (r["task_id"], r["list"], r["fields"],
                                          (r["example"] or {}).get("context", "")[:100]))


if __name__ == "__main__":
    main()

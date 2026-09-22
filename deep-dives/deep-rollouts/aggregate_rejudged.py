#!/usr/bin/env python3
"""Scans runs/regrade/rejudge-dr-<rep>-<tag>-<jobid>/samples.eval_results.json
(the in-knob authoritative scoring pass per repeat). Emits per (task, rep):
  {"task_id","benchmark","rep","fails","n"}
Deduplicates: if a rep has several rejudge scratches, keeps the newest jobid.

Usage: python3 aggregate_rejudged.py <base-dir> <out-dir>
"""
import glob
import json
import os
import re
import sys

base, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
TAG2BENCH = {"he": "humaneval", "mbpp": "mbpp"}

best = {}
for p in glob.glob(f"{base}/runs/regrade/rejudge-dr-*/samples.eval_results.json"):
    m = re.search(r"rejudge-dr-(d\d+)-(he|mbpp)-(\d+)/", p)
    if not m:
        continue
    rep, tag, jobid = m.group(1), m.group(2), int(m.group(3))
    key = (rep, tag)
    if key not in best or jobid > best[key][0]:
        best[key] = (jobid, p)

rows_by_bench = {"humaneval": [], "mbpp": []}
for (rep, tag), (jobid, p) in sorted(best.items()):
    bench = TAG2BENCH[tag]
    try:
        ev = json.load(open(p))["eval"]
    except Exception as e:
        print(f"SKIP {p}: {e}", file=sys.stderr)
        continue
    for tid, samples in ev.items():
        fails = sum(1 for s in samples
                    if not (s.get("base_status") == "pass"
                            and s.get("plus_status") == "pass"))
        rows_by_bench[bench].append(
            {"task_id": tid, "benchmark": bench, "rep": rep,
             "fails": fails, "n": len(samples), "jobid": jobid})

for bench, rows in rows_by_bench.items():
    out = f"{outdir}/aggrj_{bench}.jsonl"
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    reps = sorted({r["rep"] for r in rows})
    print(f"{bench}: {len(reps)} re-judged reps ({','.join(reps)}) -> {out}")

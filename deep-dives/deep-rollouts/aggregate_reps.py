#!/usr/bin/env python3
import glob
import json
import os
import sys

base, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
STEM = "Qwen--Qwen3-4B_vllm_temp_0.8"

for bench in ("humaneval", "mbpp"):
    rows = []
    for evp in sorted(glob.glob(f"{base}/runs-repd*/{bench}/{STEM}.eval_results.json")):
        rep = evp.split("/runs-rep")[1].split("/")[0]   # e.g. 'd02'
        try:
            ev = json.load(open(evp))["eval"]
        except Exception as e:
            print(f"SKIP {evp}: {e}", file=sys.stderr)
            continue
        for tid, samples in ev.items():
            fail_idx = [i for i, s in enumerate(samples)
                        if not (s.get("base_status") == "pass"
                                and s.get("plus_status") == "pass")]
            rows.append({"task_id": tid, "benchmark": bench, "rep": rep,
                         "fails": len(fail_idx), "n": len(samples),
                         "fail_idx": fail_idx})
    out = f"{outdir}/agg_{bench}.jsonl"
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    reps = sorted({r["rep"] for r in rows})
    print(f"{bench}: {len(rows)} task-rep rows across {len(reps)} reps -> {out}")

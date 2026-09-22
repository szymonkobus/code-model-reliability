#!/usr/bin/env python3
"""Join the hand labels (drawn on the v6 sample) to the FINAL reader's classes: a labelled row that the final
reader no longer flags is reported as resolved. Writes results/label_rejoin.json."""
import json, glob, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
labels = [json.loads(l) for l in open(os.path.join(HERE, "results", "handlabels.jsonl"))]
spec = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, "results", "handlabel_specimens.jsonl"))}
ids = {r["id"] for r in labels}
now = {}
for fn in glob.glob(os.path.join(HERE, "results", "cells", "*.flags.jsonl")):
    for line in open(fn):
        r = json.loads(line)
        aid = f"{r['arm']}|{r['bench']}|{r['task_id']}|{r['sample']}"
        if aid in ids: now[aid] = r["class"]
out = collections.Counter()
rows = []
for r in labels:
    old = spec[r["id"]]["class"]; new = now.get(r["id"], "SAME")
    out[(old, new, r["label"])] += 1
    rows.append({"id": r["id"], "label": r["label"], "class_v6": old, "class_final": new})
json.dump({"rows": rows, "transitions": {f"{a}->{b}|{l}": v for (a, b, l), v in out.items()}}, open(os.path.join(HERE, "results", "label_rejoin.json"), "w"), indent=1)
for (a, b, l), v in sorted(out.items()): print(f"{v:3d} {a:28s} -> {b:28s} {l}")

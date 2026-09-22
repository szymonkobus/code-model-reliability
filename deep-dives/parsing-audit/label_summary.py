#!/usr/bin/env python3
"""Precision per class from hand labels (results/handlabels.jsonl: {id, label, note}) joined to specimens.
Labels: MISPARSE-VERDICT | MISPARSE-NEUTRAL | MODEL-SIDE | READER-ERROR. Wilson 95% intervals."""
import json, os, math, collections
HERE = os.path.dirname(os.path.abspath(__file__))
spec = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, "results", "handlabel_specimens.jsonl"))}
labels = [json.loads(l) for l in open(os.path.join(HERE, "results", "handlabels.jsonl"))]
def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)
by = collections.defaultdict(collections.Counter)
for r in labels:
    s = spec[r["id"]]; by[(s["class"], "pass" if s["pass"] else "fail")][r["label"]] += 1
out = {}
for k, c in sorted(by.items()):
    n = sum(c.values()); mp = c["MISPARSE-VERDICT"] + c["MISPARSE-NEUTRAL"]
    lo, hi = wilson(mp, n)
    out[f"{k[0]}|{k[1]}"] = {"n": n, "labels": dict(c), "misparse_share": mp / n, "wilson95": [lo, hi]}
    print(f"{k[0]:28s} {k[1]:4s} n={n:3d} misparse={mp/n:5.2f} [{lo:.2f},{hi:.2f}] {dict(c)}")
json.dump({"n_labels": len(labels), "by_class": out}, open(os.path.join(HERE, "results", "label_summary.json"), "w"), indent=1)

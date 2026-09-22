#!/usr/bin/env python3
"""Aggregate results/shapes/*.json (board cells + pool units) -> results/shapes_summary.json."""
import json, glob, os, collections
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "results", "shapes")
board = collections.Counter(); pool = collections.Counter(); per_arm = collections.defaultdict(collections.Counter); cells = 0; units = 0
for fn in glob.glob(os.path.join(D, "*.json")):
    d = json.load(open(fn))
    if os.path.basename(fn).startswith("pool__"):
        units += 1
        for k in ("rows", "p1", "data_bound", "error"): pool[k] += d.get(k, 0)
    else:
        cells += 1; arm = d["cell"].split("|")[0]
        for k in ("p1", "p1_fail", "p1_artifact_lost_def", "p1_fail_and_lost_def", "data_bound", "data_bound_fail", "error"):
            v = d.get(k, 0); v = v if isinstance(v, int) else 0
            board[k] += v; per_arm[arm][k] += v
        # scanned-row count: the per-cell reader summary (the scan file's "rows" key held the flagged list in this run)
        sfn = os.path.join(HERE, "results", "cells", d["cell"].replace("|", "__") + ".summary.json")
        if os.path.exists(sfn): board["rows"] += json.load(open(sfn))["n_seen"]
out = {"generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
       "definitions": {"p1": "top-level assignment to the entry-point name BEFORE a correctly named def in the same reply (pinned stage-2 keeps the first claimant)",
                       "data_bound": "entry-point name bound only to data (literal / non-callable), no def of that name in the reply"},
       "board_cells": cells, "board": dict(board), "pool_units": units, "pool": dict(pool),
       "per_arm_p1": {a: c["p1"] for a, c in sorted(per_arm.items()) if c["p1"]},
       "per_arm_data_bound": {a: c["data_bound"] for a, c in sorted(per_arm.items()) if c["data_bound"]}}
json.dump(out, open(os.path.join(HERE, "results", "shapes_summary.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("board_cells", "board", "pool_units", "pool")}, indent=0))

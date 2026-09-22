#!/usr/bin/env python3
"""Per task: where the prompt's doctest example inputs sit —
  clean     all examples in base_input
  plus      none in base, at least one in plus_input
  split     some in base, the rest in plus/untested
  untested  examples parse but sit in neither base nor plus
  none      no parseable doctest call in the prompt
Usage: python3 tools/weak_base_census.py --tasks gen/targeted_*.jsonl --out tracker/targeted_weak_base_census.json
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from derive_input_types import example_calls  # noqa: E402


def classify(rec):
    calls = example_calls(rec["prompt"], rec["entry_point"])
    if not calls:
        return "none", 0, 0, 0
    ex = {json.dumps(list(c)) for c in calls}
    base = {json.dumps(list(b)) for b in rec["base_input"]}
    plus = {json.dumps(list(p)) for p in rec["plus_input"]}
    in_base, in_plus = len(ex & base), len(ex & plus)
    if in_base == len(ex):
        cls = "clean"
    elif in_base == 0 and in_plus > 0:
        cls = "plus"
    elif in_base > 0:
        cls = "split"
    else:
        cls = "untested"
    return cls, len(ex), in_base, in_plus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    per_task, totals = {}, {"clean": 0, "plus": 0, "split": 0, "untested": 0, "none": 0}
    for path in args.tasks:
        for line in open(path):
            r = json.loads(line)
            if r.get("provenance", {}).get("channel") != "targeted":
                continue
            cls, n_ex, in_base, in_plus = classify(r)
            per_task[r["task_id"]] = {"examples_in": cls, "n_examples": n_ex,
                                      "n_in_base": in_base, "n_in_plus": in_plus,
                                      "n_base_inputs": len(r["base_input"]),
                                      "generator": r["provenance"].get("generator")}
            totals[cls] += 1
    body = json.dumps(per_task, sort_keys=True)
    out = {
        "_meta": {
            "contract": ("Per-task location of the prompt's doctest example inputs (base/plus) for Targeted records; "
                         "consumed by the pool pages' targeted_weak_base disclosure. Schema: tasks{task_id: {examples_in: "
                         "clean|plus|split|untested|none, n_examples, n_in_base, n_in_plus, n_base_inputs, generator}}, "
                         "totals{class: count}, n. Weak base = plus|untested|none (a program failing the prompt's own examples can pass base)."),
            "producer": "tasks/pipeline/acquire/weak_base_census.py",
            "root_cause": "scale-1 generator took the first 3 generated inputs as base; v1.1 generator sets base = docstring examples",
        },
        "_stamp": {"written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "content_sha256": hashlib.sha256(body.encode()).hexdigest()},
        "n": len(per_task),
        "totals": totals,
        "weak_base_total": totals["plus"] + totals["untested"] + totals["none"],
        "tasks": per_task,
    }
    with open(args.out + ".tmp", "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    os.replace(args.out + ".tmp", args.out)
    print(json.dumps({"n": out["n"], "totals": totals, "weak_base_total": out["weak_base_total"]}))


if __name__ == "__main__":
    main()

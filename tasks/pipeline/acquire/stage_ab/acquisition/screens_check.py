#!/usr/bin/env python3
"""Acquisition step 3 (verification): feed converted tasks through the
the admission screens (../screens.py) unmodified, proving the records
are shape-compatible with them.

The strong-model screen reports no-data (no fail matrix rows exist for new
tasks yet) — expected. runtime_margin / payload_size flags on hard contest
tasks are real screen verdicts, reported, not suppressed.

Usage:
  python3 screens_check.py --tasks artifacts/smoke/tasks_converted.jsonl
"""

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCREENS_PATH = os.path.join(HERE, "..", "screens.py")


def load_screens():
    spec = importlib.util.spec_from_file_location("screens", SCREENS_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["screens"] = mod   # subprocess runner path uses __file__
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True,
                    help="tasks_converted.jsonl from convert.py")
    ap.add_argument("--out", default=None,
                    help="verdicts jsonl (default alongside input)")
    args = ap.parse_args()

    S = load_screens()
    pool = {}
    with open(args.tasks) as f:
        for line in f:
            t = json.loads(line)
            t["_benchmark"] = "acquisition"
            t["_inputs"] = list(t.get("base_input") or []) + \
                list(t.get("plus_input") or [])
            t["_n_base"] = len(t.get("base_input") or [])
            t["_full_code"] = t["prompt"] + t["canonical_solution"]
            pool[t["task_id"]] = t
    if not pool:
        print("no tasks to check")
        return

    ctx = S.Ctx(pool, fail_matrix={})   # no recorded attempts for new tasks
    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.tasks)),
        "screen_verdicts.jsonl")
    n_flag = 0
    with open(out_path, "w") as f:
        for tid in sorted(pool):
            for r in S.run_all_screens(pool[tid], ctx):
                f.write(json.dumps({"task_id": tid, **r}) + "\n")
                mark = "FLAG " if r["verdict"] == "flag" else ""
                if r["verdict"] == "flag":
                    n_flag += 1
                print("%-28s %-32s %-7s %s%s"
                      % (tid, r["screen"], r["verdict"], mark,
                         r["reason"][:80]), flush=True)
    print("\n%d tasks x %d screens, %d flags -> %s"
          % (len(pool), len(S.ALL_SCREENS), n_flag, out_path))


if __name__ == "__main__":
    main()

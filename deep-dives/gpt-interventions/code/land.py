#!/usr/bin/env python3
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from habits import detect
from evalplus.data import get_human_eval_plus, get_mbpp_plus
from evalplus.sanitize import sanitize
stage = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else f"gpt-interventions-{stage}.completions.jsonl"
ds = {"humaneval": get_human_eval_plus(), "mbpp": get_mbpp_plus()}
rows = [json.loads(l) for l in open(src) if l.strip()]
out_s = os.path.join(HERE, "..", "data", f"{stage}_samples.jsonl")
out_h = os.path.join(HERE, "..", "data", f"{stage}_habits.json")
habits = {}
with open(out_s, "w") as f:
    for r in rows:
        tid = r["task_id"]; board = tid.split("~")[0]
        b = "humaneval" if board.startswith("HumanEval") else "mbpp"
        ep = ds[b][board]["entry_point"]
        text = r.get("text") or ""
        sol = sanitize(text, entrypoint=ep)
        f.write(json.dumps({"task_id": tid, "board_task": board, "solution": sol}) + "\n")
        h = detect(text, ep)
        h.update({"finish_reason": r.get("finish_reason"), "output_tokens": r.get("output_tokens"),
                  "reasoning_tokens": r.get("reasoning_tokens"), "empty_solution": not sol.strip(),
                  "intervention": tid.split("~")[1] if "~" in tid else None})
        habits[tid] = h
json.dump(habits, open(out_h, "w"), indent=1)
print(f"{len(rows)} rows -> {out_s}; habits -> {out_h}")
for tid, h in habits.items():
    flags = [k for k in ["impossible_import", "guard_raise", "stdin", "entry_missing", "empty_solution"] if h[k]]
    print(f"{tid:<22} finish={h['finish_reason']} out_tok={h['output_tokens']} flags={flags}")

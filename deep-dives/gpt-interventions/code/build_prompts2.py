#!/usr/bin/env python3
"""Build a follow-up round's prompt file (one line per attempt) from data/design2.json + data/interventions2.json.
Row: {task_id, messages, model, params, n=1}; task_id = <task>~<candidate>[~nano]~a<k>.
A round is a list of blocks: {arm, candidates, tasks (key into design2 or a list), attempts, attempt_offset,
controls_attempts, controls_offset}. Round 1 (pre-blocks form) is kept readable by the legacy branch.
Usage: build_prompts2.py <round>
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "..", "data")
from evalplus.data import get_human_eval_plus, get_mbpp_plus
design = json.load(open(f"{D}/design2.json")); cands = json.load(open(f"{D}/interventions2.json"))
INSTR = "Please provide a self-contained Python script that solves the following problem in a markdown code block:"
ds = {"humaneval": get_human_eval_plus(), "mbpp": get_mbpp_plus()}
def prob(t): return ds["humaneval" if t.startswith("HumanEval") else "mbpp"][t]
def user_msg(t, sid):
    c = cands[sid]; body = f"```\n{prob(t)['prompt'].strip()}\n```\n"
    if c["mode"] in ("none", "system"): return f"{INSTR}\n{body}"
    if c["mode"] == "replace_instruction": return f"{c['text']}\n{body}"
    return f"{INSTR}\n{body}{c['text']}\n"
def messages(t, sid):
    c = cands[sid]
    if c["mode"] == "system": return [{"role": "system", "content": c["text"]}, {"role": "user", "content": user_msg(t, sid)}]
    return [{"role": "user", "content": user_msg(t, sid)}]
rnd = sys.argv[1]; r = design["rounds"][rnd]
blocks = r.get("blocks") or [{"arm": r["arm"], "candidates": r["candidates"], "tasks": r["tasks"], "attempts": r["attempts"], "attempt_offset": 0, "controls_attempts": r["controls_attempts"], "controls_offset": 0}]
rows = []; seen = set()
for b in blocks:
    tasks = design[b["tasks"]] if isinstance(b["tasks"], str) else b["tasks"]
    model = design["models"][b["arm"]]; tag = "" if b["arm"] == "gpt-5-mini" else "~nano"
    for sid in b["candidates"]:
        for t in tasks:
            for k in range(b.get("attempt_offset", 0), b.get("attempt_offset", 0) + b["attempts"]):
                tid = f"{t}~{sid}{tag}~a{k}"; assert tid not in seen, tid; seen.add(tid)
                rows.append({"task_id": tid, "messages": messages(t, sid), "model": model, "params": design["params"], "n": 1})
        for t in design["controls"]:
            for k in range(b.get("controls_offset", 0), b.get("controls_offset", 0) + b["controls_attempts"]):
                tid = f"{t}~{sid}{tag}~a{k}"; assert tid not in seen, tid; seen.add(tid)
                rows.append({"task_id": tid, "messages": messages(t, sid), "model": model, "params": design["params"], "n": 1})
out = f"{D}/prompts_{rnd}.jsonl"; tmp = out + ".tmp"
with open(tmp, "w") as f:
    for x in rows: f.write(json.dumps(x) + "\n")
os.replace(tmp, out)
from collections import Counter
print(f"{len(rows)} requests -> {out}; by model {dict(Counter(x['model'] for x in rows))}")

#!/usr/bin/env python3
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
from evalplus.data import get_human_eval_plus, get_mbpp_plus
design = json.load(open(os.path.join(HERE, "..", "data", "design.json")))
inter = json.load(open(os.path.join(HERE, "..", "data", "interventions.json")))
INSTR = "Please provide a self-contained Python script that solves the following problem in a markdown code block:"
ds = {"humaneval": get_human_eval_plus(), "mbpp": get_mbpp_plus()}
def prob(t): return ds["humaneval" if t.startswith("HumanEval") else "mbpp"][t]
def user_msg(t, iid):
    base = f"{INSTR}\n```\n{prob(t)['prompt'].strip()}\n```\n"
    text = inter[iid]["text"]
    return base + text.strip() + "\n"
stage = sys.argv[1]
rows = []
def add(t, iid, rep=None, model=None, arm_tag=None):
    tid = f"{t}~{iid}" + (f"~r{rep}" if rep else "") + (f"~{arm_tag}" if arm_tag else "")
    rows.append({"task_id": tid, "messages": [{"role": "user", "content": user_msg(t, iid)}],
                 "model": model or design["model_id"], "params": design["params"], "n": 1})
if stage == "stage1":
    s = design["stage1"]
    for iid in s["interventions"]:
        for t in design["trap_tasks"]: add(t, iid)
        for t in design["control_tasks"]: add(t, iid)
        for t in s["repeat_tasks"]:
            for k in range(1, s["repeats_per_intervention"] + 1): add(t, iid, rep=k)
else:
    s2 = design["stage2"]
    for arm in ["gpt-5-mini", "gpt-5-nano"]:
        a = s2[arm]
        for t in a["tasks"]:
            add(t, a["intervention"], model=a["model_id"], arm_tag=None if arm == "gpt-5-mini" else "nano")
    assert len(rows) == s2["calls"], (len(rows), s2["calls"])
out = os.path.join(HERE, "..", "data", f"prompts_{stage}.jsonl")
tmp = out + ".tmp"
with open(tmp, "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
os.replace(tmp, out)
print(f"{len(rows)} requests -> {out}")

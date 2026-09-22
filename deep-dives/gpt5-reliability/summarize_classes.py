#!/usr/bin/env python3
import json, os
from collections import defaultdict

D = "deep-dives/gpt5-reliability"

def page_class(r):
    c, sub = r["class"], r["detail"].get("subtype", "")
    if r.get("subcause") == "generator_strip":
        return "harness_generator_strip"
    if r.get("subcause") == "extraction_other":
        return "harness_extraction_other"
    if r.get("subcause") == "raw_empty_truncation":
        return "model_no_output"
    if r.get("subcause") == "model_no_def":
        return "model_other_crash"
    if c == "import_crash":
        return "model_typing_import" if sub == "typing_builtin" else "model_other_crash"
    if c == "guard_raise":
        return "style_guard_raise"
    if c == "other_raise":
        return "model_other_raise"
    if c == "wrong_value":
        return "model_wrong_value"
    if c in ("timeout", "timeout_module"):
        return "model_timeout"
    return "unresolved_reexec"

rows = [json.loads(l) for l in open(f"{D}/classified_fails.jsonl")]
out = {"by_model": {}, "by_model_kept": {}, "per_task": defaultdict(dict),
       "n_rows": len(rows)}
for r in rows:
    pc = page_class(r)
    kept = r.get("rank") is not None
    for scope, cond in (("by_model", True), ("by_model_kept", kept)):
        if not cond:
            continue
        d = out[scope].setdefault(r["model"], defaultdict(int))
        d[pc] += 1
        d["_total"] += 1
    if kept:
        k = f'{r["model"]}|{r["benchmark"]}|{r["task"]}'
        t = out["per_task"].setdefault(k, defaultdict(int))
        t[pc] += 1
        t["_rank"] = r["rank"]
        t["_difficulty_pct"] = r["difficulty_pct"]

out["per_task"] = {k: dict(v) for k, v in out["per_task"].items()}
out["by_model"] = {k: dict(v) for k, v in out["by_model"].items()}
out["by_model_kept"] = {k: dict(v) for k, v in out["by_model_kept"].items()}
with open(f"{D}/class_summary.json", "w") as f:
    json.dump(out, f, indent=1)
for scope in ("by_model", "by_model_kept"):
    print(scope)
    for m, d in out[scope].items():
        print(" ", m, {k: v for k, v in sorted(d.items())})

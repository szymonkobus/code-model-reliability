#!/usr/bin/env python3
"""Worst easy tasks per gpt-5 arm from gpt5-reliability's classified failures."""
import json, os, collections
D = "deep-dives/gpt5-reliability/classified_fails.jsonl"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "worst_tasks.json")
EASY = 20.0
rows = [json.loads(l) for l in open(D)]
per = collections.defaultdict(lambda: collections.Counter())
meta = {}
for r in rows:
    if r.get("rank") is None or r.get("difficulty_pct") is None:  # not kept / no difficulty
        continue
    if r["difficulty_pct"] >= EASY:
        continue
    key = (r["model"], r["benchmark"], r["task"])
    per[key][r["class"]] += 1
    per[key]["_n_fail"] += 1
    meta[key] = {"difficulty_pct": r["difficulty_pct"], "rank": r["rank"]}
out = {}
for arm in ["gpt-5-mini", "gpt-5-nano"]:
    tasks = []
    for (m, b, t), c in per.items():
        if m != arm: continue
        d = dict(c); n = d.pop("_n_fail")
        tasks.append({"task": t, "benchmark": b, "n_fail_of_128": n,
                      "difficulty_pct": meta[(m, b, t)]["difficulty_pct"],
                      "classes": dict(sorted(d.items(), key=lambda kv: -kv[1]))})
    tasks.sort(key=lambda x: -x["n_fail_of_128"])
    total = sum(x["n_fail_of_128"] for x in tasks)
    top10 = sum(x["n_fail_of_128"] for x in tasks[:10])
    out[arm] = {"easy_fail_total": total, "easy_tasks_with_failures": len(tasks),
                "top10_share": round(top10 / total, 3) if total else None,
                "top10_fails": top10, "tasks": tasks}
json.dump(out, open(OUT, "w"), indent=1)
for arm, o in out.items():
    print(f"{arm}: {o['easy_fail_total']} easy failures on {o['easy_tasks_with_failures']} tasks; top-10 carry {o['top10_fails']} ({o['top10_share']:.0%})")
    for x in o["tasks"][:16]:
        print(f"  {x['task']:<14} {x['n_fail_of_128']:>3}/128  diff {x['difficulty_pct']:5.1f}%  {x['classes']}")

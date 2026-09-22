#!/usr/bin/env python3
"""Join judge verdicts, habit flags and the 128-attempt baselines into data/results.json.

Per intervention (and per arm): the attempts on trap tasks, how many failed, how many would be
expected to fail without the instruction (the sum of the tasks' baseline failure rates, one per
attempt), the control attempts, and the text-habit counts against their baseline rates.
Also the probability of seeing at most the observed number of trap failures if the instruction
did nothing (exact Poisson-binomial over the attempts' baseline rates) — one honest line on power.
"""
import json, os, itertools, glob
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "..", "data")
J = lambda n: json.load(open(os.path.join(D, n)))
design, inter, base = J("design.json"), J("interventions.json"), J("baseline_habits.json")
stages = sorted(os.path.basename(p)[:-len("_judge.json")] for p in glob.glob(os.path.join(D, "stage*_judge.json")))
rows = []
for s in stages:
    judge = {r["task_id"]: r for r in J(f"{s}_judge.json")["results"]}
    habits = J(f"{s}_habits.json")
    for tid, jr in judge.items():
        parts = tid.split("~"); task, iid = parts[0], parts[1]
        arm = "gpt-5-nano" if "nano" in parts[2:] else "gpt-5-mini"
        b = base[arm][task]
        kind = "control" if task in design["control_tasks"] else "trap"
        h = habits[tid]
        rows.append({"stage": s, "task_id": tid, "task": task, "arm": arm, "intervention": iid, "kind": kind,
                     "pass": jr["pass"], "base_status": jr["base_status"], "plus_status": jr["plus_status"],
                     "baseline_fail_of_128": b["fail"], "baseline_fail_rate": b["fail"] / b["n"],
                     "habits": {k: h[k] for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]},
                     "baseline_habits_of_128": {k: b[k] for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]},
                     "output_tokens": h["output_tokens"], "reasoning_tokens": h.get("reasoning_tokens")})

def poisson_binomial_cdf(ps, k):
    """P(X <= k) where X = sum of independent Bernoulli(p_i)."""
    dist = [1.0]
    for p in ps:
        nd = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nd[i] += v * (1 - p); nd[i + 1] += v * p
        dist = nd
    return sum(dist[: k + 1])

summary = {}
for arm in ["gpt-5-mini", "gpt-5-nano"]:
    for iid in inter:
        if iid == "not_tested": continue
        rs = [r for r in rows if r["arm"] == arm and r["intervention"] == iid]
        if not rs: continue
        trap = [r for r in rs if r["kind"] == "trap"]; ctrl = [r for r in rs if r["kind"] == "control"]
        ps = [r["baseline_fail_rate"] for r in trap]
        obs = sum(not r["pass"] for r in trap)
        hab = {}
        for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]:
            hab[k] = {"observed": sum(r["habits"][k] for r in trap),
                      "expected_from_baseline": round(sum(r["baseline_habits_of_128"][k] / 128 for r in trap), 2),
                      "attempts": len(trap)}
        summary.setdefault(arm, {})[iid] = {
            "name": inter[iid]["name"], "trap_attempts": len(trap), "trap_failures": obs,
            "trap_expected_failures_without_instruction": round(sum(ps), 2),
            "trap_fail_rate": round(obs / len(trap), 3) if trap else None,
            "trap_baseline_fail_rate": round(sum(ps) / len(ps), 3) if ps else None,
            "p_at_most_observed_if_no_effect": round(poisson_binomial_cdf(ps, obs), 4),
            "control_attempts": len(ctrl), "control_failures": sum(not r["pass"] for r in ctrl),
            "failed_tasks": [r["task_id"] for r in trap + ctrl if not r["pass"]],
            "tasks": sorted({r["task"] for r in trap}),
            "habits": hab,
        }
# baseline habit rates on the ten mini trap tasks (for the figure's habit panel)
out = {"generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "stages": stages, "calls_used": len(rows), "summary": summary, "rows": rows}
json.dump(out, open(os.path.join(D, "results.json"), "w"), indent=1)
for arm, d in summary.items():
    for iid, s in d.items():
        print(f"{arm} {iid} ({s['name']}): trap {s['trap_failures']}/{s['trap_attempts']} failed, expected {s['trap_expected_failures_without_instruction']} without it (p<= {s['p_at_most_observed_if_no_effect']}); controls {s['control_failures']}/{s['control_attempts']} failed; habits " +
              ", ".join(f"{k} {v['observed']} vs {v['expected_from_baseline']}" for k, v in s["habits"].items()))
        if s["failed_tasks"]: print("   failed:", s["failed_tasks"])

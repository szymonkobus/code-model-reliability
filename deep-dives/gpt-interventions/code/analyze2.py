#!/usr/bin/env python3
"""Follow-up analysis (short universal instructions). Joins every round's judge verdicts, habit flags and the
128-attempt baselines into data/results2.json: per arm and candidate, trap attempts and failures, the failures
expected from the record for the same attempts, control attempts and failures, habit counts, a per-task table,
and the probability of at most the observed trap failures if the candidate did nothing (Poisson-binomial)."""
import json, os, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "..", "data")
J = lambda n: json.load(open(os.path.join(D, n)))
d2, cands, base = J("design2.json"), J("interventions2.json"), J("baseline_habits.json")
controls = set(d2["controls"]); medium = set(d2.get("medium_tasks", [])) | set(d2.get("medium_tasks_nano", []))
rounds = sorted(os.path.basename(p)[:-len("_judge.json")] for p in glob.glob(os.path.join(D, "round*_judge.json")))
rows = []
for rd in rounds:
    judge = {r["task_id"]: r for r in J(f"{rd}_judge.json")["results"]}; habits = J(f"{rd}_habits.json")
    for tid, jr in judge.items():
        parts = tid.split("~"); task, sid = parts[0], parts[1]
        arm = "gpt-5-nano" if "nano" in parts else "gpt-5-mini"
        b = base[arm][task]; h = habits[tid]
        rows.append({"round": rd, "task_id": tid, "task": task, "arm": arm, "candidate": sid, "kind": "control" if task in controls else ("medium" if task in medium else "trap"),
                     "pass": jr["pass"], "baseline_fail_of_128": b["fail"], "baseline_fail_rate": b["fail"] / b["n"],
                     "habits": {k: h[k] for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]},
                     "baseline_habits_of_128": {k: b[k] for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]},
                     "output_tokens": h["output_tokens"], "reasoning_tokens": h.get("reasoning_tokens")})
def pb_cdf(ps, k):
    dist = [1.0]
    for p in ps:
        nd = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist): nd[i] += v * (1 - p); nd[i + 1] += v * p
        dist = nd
    return sum(dist[:k + 1])
summary = {}
for arm in ["gpt-5-mini", "gpt-5-nano"]:
    for sid in cands:
        rs = [r for r in rows if r["arm"] == arm and r["candidate"] == sid]
        if not rs: continue
        trap = [r for r in rs if r["kind"] == "trap"]; ctrl = [r for r in rs if r["kind"] == "control"]; med = [r for r in rs if r["kind"] == "medium"]
        ps = [r["baseline_fail_rate"] for r in trap]; obs = sum(not r["pass"] for r in trap)
        per_task = {}
        for r in trap + ctrl + med:
            d = per_task.setdefault(r["task"], {"attempts": 0, "fails": 0, "baseline_fail_of_128": r["baseline_fail_of_128"], "kind": r["kind"], "rounds": set()})
            d["attempts"] += 1; d["fails"] += int(not r["pass"]); d["rounds"].add(r["round"])
        for d in per_task.values(): d["rounds"] = sorted(d["rounds"])
        hab = {k: {"observed": sum(r["habits"][k] for r in trap), "expected_from_record": round(sum(r["baseline_habits_of_128"][k] / 128 for r in trap), 1), "attempts": len(trap)}
               for k in ["impossible_import", "guard_raise", "stdin", "entry_missing"]}
        summary.setdefault(arm, {})[sid] = {
            "name": cands[sid]["name"], "kind": cands[sid]["kind"], "mode": cands[sid]["mode"], "words": len(cands[sid]["text"].split()) if cands[sid]["mode"] == "append" else None,
            "rounds": sorted({r["round"] for r in rs}), "tasks": sorted({r["task"] for r in trap}),
            "trap_attempts": len(trap), "trap_failures": obs, "trap_expected_failures_from_record": round(sum(ps), 1),
            "trap_fail_share": round(obs / len(trap), 3) if trap else None, "trap_record_fail_share": round(sum(ps) / len(ps), 3) if ps else None,
            "p_at_most_observed_if_no_effect": round(pb_cdf(ps, obs), 4) if trap else None,
            "control_attempts": len(ctrl), "control_failures": sum(not r["pass"] for r in ctrl),
            "medium_attempts": len(med), "medium_failures": sum(not r["pass"] for r in med),
            "medium_expected_failures_from_record": round(sum(r["baseline_fail_rate"] for r in med), 1),
            "habits": hab, "per_task": per_task,
            "mean_output_tokens": round(sum(r["output_tokens"] or 0 for r in rs) / len(rs)) if rs else None}
out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rounds": rounds, "calls": len(rows), "summary": summary, "rows": rows}
json.dump(out, open(os.path.join(D, "results2.json"), "w"), indent=1)
for arm, d in summary.items():
    print(arm)
    for sid, s in d.items():
        print(f"  {sid} {s['name'][:52]:<52} trap {s['trap_failures']:>2}/{s['trap_attempts']:<3} exp {s['trap_expected_failures_from_record']:>5}  p<= {s['p_at_most_observed_if_no_effect']}  ctrl {s['control_failures']}/{s['control_attempts']}  med {s['medium_failures']}/{s['medium_attempts']} exp {s['medium_expected_failures_from_record']}  raise {s['habits']['guard_raise']['observed']}/{s['habits']['guard_raise']['expected_from_record']}  imp {s['habits']['impossible_import']['observed']}/{s['habits']['impossible_import']['expected_from_record']}  tok {s['mean_output_tokens']}")

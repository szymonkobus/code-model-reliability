#!/usr/bin/env python3
import json, glob, os, sys, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results")
# usage: pool_by_task.py [FLAGS_DIR [OUT_NAME [LABEL]]]  (defaults: results/pool, pool_by_task, the API models)
FLAGS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(R, "pool")
OUTNAME = sys.argv[2] if len(sys.argv) > 2 else "pool_by_task"
LABEL = sys.argv[3] if len(sys.argv) > 3 else "the API models (gemini-3.5-flash-lite, gemini-3.6-flash, gpt-5-mini, gpt-5-nano; the 2026-09-02 pool run, about 40% of the API replies on the new tasks)"
task_cert = {}
for f in glob.glob(os.path.join(R, "bridge_v4", "*.json")):
    d = json.load(open(f)); cert = d["file"].split("-certshard_")[1]
    for t in d.get("by_task", {}): task_cert[t] = "certshard_" + cert
cert_tasks = collections.Counter(task_cert.values())
unit_size = {}
for f in glob.glob(os.path.join(FLAGS, "*.summary.json")):
    s = json.load(open(f)); unit_size[s["unit"]] = s["n_seen"]
flag = collections.defaultdict(collections.Counter)          # (task, arm) -> class counts
for f in glob.glob(os.path.join(FLAGS, "*.flags.jsonl")):
    for line in open(f):
        r = json.loads(line); arm = r["unit"].split("__")[0]
        flag[(r["task_id"], arm)][r["class"]] += 1
rows = {}
for unit, n in unit_size.items():
    arm, cert = unit.split("__", 1)
    tasks = [t for t, c in task_cert.items() if c == cert]
    if not tasks: continue
    per = n / len(tasks)
    for t in tasks:
        row = rows.setdefault(t, {"task_id": t, "attempts": 0, "misparse": 0, "diff_entry": 0, "by_arm": {}})
        c = flag.get((t, arm), {})
        mp = c.get("LOST-ENTRY", 0) + c.get("HELPER-DROP", 0); de = c.get("DIFF-ENTRY", 0)
        row["attempts"] += per; row["misparse"] += mp; row["diff_entry"] += de
        row["by_arm"][arm] = {"attempts": round(per), "misparse": mp, "diff_entry": de}
out = []
for r in rows.values():
    r["attempts"] = round(r["attempts"]); r["misparse_pct"] = round(100 * r["misparse"] / r["attempts"], 2) if r["attempts"] else None
    out.append(r)
out.sort(key=lambda r: (-(r["misparse_pct"] or 0), -r["misparse"]))
def n_at(th): return sum(1 for r in out if (r["misparse_pct"] or 0) >= th)
summary = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "units": len(unit_size), "tasks_covered": len(out),
           "attempts": sum(r["attempts"] for r in out), "misparse": sum(r["misparse"] for r in out), "diff_entry": sum(r["diff_entry"] for r in out),
           "tasks_misparse_ge_5pct": n_at(5), "tasks_misparse_ge_10pct": n_at(10), "tasks_misparse_ge_25pct": n_at(25), "by_task": out}
want = {l.strip() for l in open(os.path.join(R, "pool_audit_first_tasks.txt")) if l.strip()} if os.path.exists(os.path.join(R, "pool_audit_first_tasks.txt")) else set()
hit = [r for r in out if r["task_id"] in want and r["misparse"] > 0]
summary["audit_first_intersection"] = {"list_size": len(want), "seen": sum(1 for r in out if r["task_id"] in want), "with_misparse": len(hit),
                                       "tasks": [{k: r[k] for k in ("task_id", "attempts", "misparse", "misparse_pct", "diff_entry")} for r in hit]}
summary["scope"] = LABEL; summary["source"] = FLAGS
json.dump(summary, open(os.path.join(R, OUTNAME + ".json"), "w"), indent=1)
_flag_rows = sum(1 for f in glob.glob(os.path.join(FLAGS, "*.summary.json")) for _ in [0]) and sum(json.load(open(f)).get("n_seen", 0) for f in glob.glob(os.path.join(FLAGS, "*.summary.json")))
L = [f"# Which new tasks had answers the pinned extractor did not judge (the answer or a needed helper dropped): {LABEL.split(' (')[0]}",
     f"Built {summary['generated_at']} from {FLAGS}: {summary['units']} units, {summary['attempts']:,} replies of {LABEL}.",
     f"Denominator: {summary['attempts']:,} covered replies, counted per task and arm from the certshard task map (normally 128 per task and arm); the run itself saw {_flag_rows:,} replies, so {_flag_rows - summary['attempts']:,} replies of tasks outside that map are not covered here.",
     "Misparse = the function the model wrote, or a helper it needs, was not in the judged code; an earlier version judged while the model wrote another later is listed apart (different version). Not re-judged.",
     "", f"- tasks covered: {summary['tasks_covered']:,}; misparsed replies: {summary['misparse']:,} of {summary['attempts']:,} ({100*summary['misparse']/summary['attempts']:.2f}%); different version: {summary['diff_entry']:,}",
     f"- tasks with 5%+ of covered API replies misparsed: {summary['tasks_misparse_ge_5pct']}; 10%+: {summary['tasks_misparse_ge_10pct']}; 25%+: {summary['tasks_misparse_ge_25pct']}",
     "", "## Tasks where at least 10% of covered replies were misparsed", "| task | replies covered | misparsed | share | different version | arms covered |", "|---|---:|---:|---:|---:|---|"]
for r in out:
    if (r["misparse_pct"] or 0) >= 10: L.append(f"| {r['task_id']} | {r['attempts']} | {r['misparse']} | {r['misparse_pct']}% | {r['diff_entry']} | {', '.join(sorted(r['by_arm']))} |")
ai = summary["audit_first_intersection"]
L += ["", f"## Intersection with the tasks-to-audit-first list ({ai['list_size']} tasks; {ai['seen']} covered; {ai['with_misparse']} with at least one misparsed reply)", "| task | replies covered | misparsed | share | different version |", "|---|---:|---:|---:|---:|"]
for r in ai["tasks"]: L.append(f"| {r['task_id']} | {r['attempts']} | {r['misparse']} | {r['misparse_pct']}% | {r['diff_entry']} |")
L += ["", f"Per arm per task: results/{OUTNAME}.json. Source rows: {FLAGS}/*.flags.jsonl (reader v7 vs the pinned extractor's stored solution)."]
open(os.path.join(R, OUTNAME + ".md"), "w").write("\n".join(L) + "\n")
print({k: v for k, v in summary.items() if k not in ("by_task", "audit_first_intersection")}); print(ai["list_size"], ai["seen"], ai["with_misparse"])
for r in out[:12]: print(f"{r['task_id'][:50]:50s} {r['attempts']:6d} {r['misparse']:5d} {r['misparse_pct']!s:>6s} {r['diff_entry']:5d} {sorted(r['by_arm'])}")
print("--- audit-first hits"); 
for r in ai["tasks"][:15]: print(f"{r['task_id'][:50]:50s} {r['attempts']:6d} {r['misparse']:5d} {r['misparse_pct']!s:>6s} {r['diff_entry']:5d}")

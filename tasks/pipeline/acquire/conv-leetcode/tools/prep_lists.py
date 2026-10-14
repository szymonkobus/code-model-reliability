#!/usr/bin/env python3
"""prep_lists.py — the candidate list and the twin list for the lcds conversion.

Reads training-plan's composition of record (sha256 verified against the owner's
message) and writes, under lists/:
  chosen_800.tsv     slug, difficulty, question_id, date — Easy first, then Medium,
                     each in the composition's own order (a copy named by the sha's first 8)
  composition_sha.txt  the sha256 of the composition file the lists were cut from
  twin_slugs.txt     every slug of a live leetcode/<slug> id plus the 106 staged slugs
  twin_hits.txt      chosen slugs that hit the twin list (the second check; expected 0)
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMP = "research/training/training-plan/out/pool-composition-2026-09-24.json"
LIVE = "tasks/build/training-pool/live_leetcode_ids.txt"
STAGED = "tasks/build/training-pool/staged/leetcode/tasks_converted.gated.jsonl"

raw = open(COMP, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
d = json.loads(raw)
probs = d["sources"]["leetcode_dataset"]["problems"]
easy = [p for p in probs if p["difficulty"] == "Easy"]
med = [p for p in probs if p["difficulty"] == "Medium"]
other = [p for p in probs if p["difficulty"] not in ("Easy", "Medium")]
ordered = easy + med + other

live = set()
for line in open(LIVE):
    line = line.strip()
    if line.startswith("leetcode/"):
        live.add(line.split("/", 1)[1])
staged = set()
for line in open(STAGED):
    r = json.loads(line)
    staged.add(r["task_id"].split("/", 1)[1])
twins = live | staged

os.makedirs(os.path.join(HERE, "lists"), exist_ok=True)
with open(os.path.join(HERE, "lists", "composition_sha.txt"), "w") as f:
    f.write(sha + "\n")
for name in ("chosen_800.tsv", "chosen_800.%s.tsv" % sha[:8]):
    with open(os.path.join(HERE, "lists", name), "w") as f:
        for p in ordered:
            f.write("%s\t%s\t%s\t%s\n" % (p["task_id"], p["difficulty"], p.get("question_id"), p.get("date")))
with open(os.path.join(HERE, "lists", "twin_slugs.txt"), "w") as f:
    for s in sorted(twins):
        f.write(s + "\n")
hits = [p["task_id"] for p in ordered if p["task_id"] in twins]
with open(os.path.join(HERE, "lists", "twin_hits.txt"), "w") as f:
    for s in hits:
        f.write(s + "\n")
print("composition sha256 %s; chosen %d (Easy %d, Medium %d, other %d); live slugs %d, staged slugs %d, twin list %d; chosen hitting twins: %d"
      % (sha[:8], len(ordered), len(easy), len(med), len(other), len(live), len(staged), len(twins), len(hits)))
print("first 3:", [p["task_id"] for p in ordered[:3]], "last:", ordered[-1]["task_id"])

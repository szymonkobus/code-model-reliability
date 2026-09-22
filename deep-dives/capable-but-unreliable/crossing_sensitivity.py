# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""How many tasks set an arm's 1% crossing? For each measurable arm:
the number of kept tasks at or below its reliability crossing (in
difficulty) on which it fails at least once in 128 attempts — these are
the failures the 1% level is read from — and the share of its failing
attempts that sit on them. Writes data/crossing_sensitivity.json."""
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
D = HERE / "data"
def inv_logit(z): return 1 / (1 + math.exp(-z))
diff = {}
for row in csv.DictReader(open(D / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])
counts = defaultdict(dict)
for row in csv.DictReader(open(D / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))
rj = json.load(open(D / "residuals.json"))
per = {}
for m, v in rj["models"].items():
    if v.get("residual") is None or m not in counts:
        continue
    rel_d = inv_logit(v["rel"][1])                # crossing, as a difficulty
    below = [t for t in counts[m] if diff.get(t, 1) <= rel_d]
    failed = [t for t in below if counts[m][t][0] < counts[m][t][1]]
    fails_below = sum(counts[m][t][1] - counts[m][t][0] for t in failed)
    fails_all = sum(counts[m][t][1] - counts[m][t][0] for t in counts[m])
    per[m] = {"crossing_difficulty": rel_d, "tasks_at_or_below": len(below),
              "tasks_failed_at_or_below": len(failed), "failing_attempts_at_or_below": fails_below,
              "share_of_all_failing_attempts": fails_below / fails_all if fails_all else 0.0}
n = np.array([p["tasks_failed_at_or_below"] for p in per.values()])
out = {"n_arms": len(per), "tasks_failed_at_or_below_median": float(np.median(n)),
       "tasks_failed_at_or_below_p25": float(np.percentile(n, 25)),
       "tasks_failed_at_or_below_p75": float(np.percentile(n, 75)),
       "share_of_failing_attempts_median": float(np.median([p["share_of_all_failing_attempts"] for p in per.values()])),
       "per_arm": per}
json.dump(out, open(D / "crossing_sensitivity.json", "w"), indent=1)
print(f"{len(per)} arms: tasks failed at/below the 1% crossing — median {out['tasks_failed_at_or_below_median']:.0f} "
      f"(IQR {out['tasks_failed_at_or_below_p25']:.0f}-{out['tasks_failed_at_or_below_p75']:.0f}); "
      f"they carry a median {out['share_of_failing_attempts_median']:.1%} of an arm's failing attempts")

# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""H2: trap-task susceptibility.

A "trap task" here: an easy-band kept task (pooled difficulty < 20%)
that trips many configurations at once — operationalized on the CURRENT
46-config board as >=12 of the other 45 configs failing >=2 of 128
attempts (leave-the-model-out, so a model's own failures never make its
own trap list). Scale mirrors rare-failures' 6-of-22 finding.

Traits per model (per benchmark and combined):
  trap_rate   failing attempts on trap tasks / attempts on trap tasks
  trap_share  share of the model's easy-band failing attempts on traps
Tests:
  R^2 vs the panel residual; cross-benchmark stability of trap_rate.
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EASY = 0.20
TRIP_FAILS = 2
TRIP_CONFIGS = 12

diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])

counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))

models = sorted(counts)
easy_tasks = [t for t in diff if diff[t] < EASY
              and any(t in counts[m] for m in models)]

# per task: which configs trip it
trippers = {t: {m for m in models
                if t in counts[m]
                and counts[m][t][1] - counts[m][t][0] >= TRIP_FAILS}
            for t in easy_tasks}

resid_json = json.load(open(HERE / "data" / "residuals.json"))
perb = json.load(open(HERE / "data" / "per_benchmark_residuals.json"))

rows = {}
for m in models:
    traps_m = [t for t in easy_tasks
               if len(trippers[t] - {m}) >= TRIP_CONFIGS]
    out = {}
    for scope, pred in [("comb", lambda t: True),
                        ("he", lambda t: t.startswith("HumanEval")),
                        ("mbpp", lambda t: t.startswith("Mbpp"))]:
        ts = [t for t in traps_m if pred(t) and t in counts[m]]
        fa = sum(counts[m][t][1] - counts[m][t][0] for t in ts)
        at = sum(counts[m][t][1] for t in ts)
        easy_f = sum(counts[m][t][1] - counts[m][t][0]
                     for t in easy_tasks if pred(t) and t in counts[m])
        out[f"trap_rate_{scope}"] = fa / at if at else None
        out[f"trap_share_{scope}"] = fa / easy_f if easy_f else None
        out[f"n_traps_{scope}"] = len(ts)
    rows[m] = out

n_traps_global = len([t for t in easy_tasks
                      if len(trippers[t]) >= TRIP_CONFIGS])
print(f"easy tasks {len(easy_tasks)}, global trap tasks (>= {TRIP_CONFIGS} "
      f"of 46 trip): {n_traps_global}")


def corr(pairs):
    x, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    return np.corrcoef(x, y)[0, 1], len(pairs)


# vs combined residual
for trait in ["trap_rate_comb", "trap_share_comb"]:
    pairs = [(rows[m][trait], resid_json["models"][m]["residual"])
             for m in models if rows[m][trait] is not None
             and resid_json["models"][m].get("residual") is not None]
    r, n = corr(pairs)
    print(f"{trait} vs combined residual: r={r:.3f} R2={r*r:.3f} n={n}")

# vs per-benchmark residuals
for scope, res in [("he", perb["he"]), ("mbpp", perb["mbpp"])]:
    pairs = [(rows[m][f"trap_rate_{scope}"], res[m])
             for m in models if m in res
             and rows[m][f"trap_rate_{scope}"] is not None]
    r, n = corr(pairs)
    print(f"trap_rate_{scope} vs {scope} residual: r={r:.3f} R2={r*r:.3f} "
          f"n={n}")

# cross-pool stability of the trait itself
pairs = [(rows[m]["trap_rate_he"], rows[m]["trap_rate_mbpp"])
         for m in models
         if rows[m]["trap_rate_he"] is not None
         and rows[m]["trap_rate_mbpp"] is not None]
r, n = corr(pairs)
print(f"trap_rate stability: corr(HE, MBPP) = {r:.3f} n={n}")

# and of the general easy-band failure rate, for comparison
gen = {}
for m in models:
    for scope, pred in [("he", lambda t: t.startswith("HumanEval")),
                        ("mbpp", lambda t: t.startswith("Mbpp"))]:
        f = sum(counts[m][t][1] - counts[m][t][0]
                for t in easy_tasks if pred(t) and t in counts[m])
        a = sum(counts[m][t][1] for t in easy_tasks
                if pred(t) and t in counts[m])
        gen.setdefault(m, {})[scope] = f / a if a else None
pairs = [(math.log1p(1000 * gen[m]["he"]), math.log1p(1000 * gen[m]["mbpp"]))
         for m in models
         if gen[m].get("he") is not None and gen[m].get("mbpp") is not None]
r, n = corr(pairs)
print(f"log easy-band failure rate stability: corr(HE, MBPP) = {r:.3f} n={n}")

json.dump(rows, open(HERE / "data" / "trap_traits.json", "w"), indent=1)

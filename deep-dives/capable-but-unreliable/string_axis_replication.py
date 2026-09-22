# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Replication attempt for the string-manipulation clash axis.

The exploratory finding (clash_axes.py): splitting easy tasks by
prompt-keyword 'stringy' decorrelates models' residuals across sides
(0.32 vs 0.59 random-split null, z=-2.5). Replications here, each
designed to be as independent as the data allows:

 R1. Different operationalization: 'solution-stringy' = the canonical
     solution actually calls string methods / string ops, regardless
     of prompt wording. Overlap with prompt-stringy reported.
 R2. Within-benchmark: run the prompt-stringy split inside HumanEval+
     only and inside MBPP+ only (the original was stratified-combined;
     if the axis is real it should show in each pool separately).
 R3. Capability-adjusted breadth sanity check (unrelated to strings,
     riding the run): residualize breadth on capability first, then
     corr2 with the residual — does breadth survive as a trait rather
     than capability leakage?
"""

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EASY = 0.20
N_NULL = 300
rng = np.random.default_rng(77)

diff = {}
for row in csv.DictReader(open(HERE / "data" / "task_difficulty.csv")):
    if row["panel"] == "combined":
        diff[row["task_id"]] = float(row["difficulty"])
counts = defaultdict(dict)
for row in csv.DictReader(open(HERE / "data" / "counts.csv")):
    if row["kept"] == "1":
        counts[row["model"]][row["task_id"]] = (int(row["c"]), int(row["n"]))
models = sorted(counts)
resid_json = json.load(open(HERE / "data" / "residuals.json"))
caps, subm = [], []
for m in models:
    c = resid_json["models"].get(m, {}).get("cap", [None, math.inf])[1]
    if c is not None and math.isfinite(c):
        subm.append(m)
        caps.append(c)
caps = np.array(caps)

tasks_meta = {}
for fn in ["HumanEvalPlus-v0.1.10.jsonl", "MbppPlus-v0.2.0.jsonl"]:
    for line in open(Path.home() / ".cache" / "evalplus" / fn):
        r = json.loads(line)
        tasks_meta[r["task_id"]] = r

easy = [t for t in diff if diff[t] < EASY and t in tasks_meta
        and any(t in counts[m] for m in models)]

STR_METHODS = (r"\.(?:split|join|strip|lstrip|rstrip|upper|lower|"
               r"replace|startswith|endswith|find|rfind|index|title|"
               r"capitalize|isdigit|isalpha|isupper|islower|count)\(")


def prompt_stringy(t):
    p = tasks_meta[t]["prompt"].lower()
    return "string" in p or "str" in p


def sol_stringy(t):
    sol = tasks_meta[t]["canonical_solution"]
    return bool(re.search(STR_METHODS, sol)
                or re.search(r"(?<![\w.])str\(", sol)
                or re.search(r"['\"]\s*\.join", sol))


def beh_resid(side):
    ys = []
    for m in subm:
        f = sum(counts[m][t][1] - counts[m][t][0]
                for t in side if t in counts[m])
        a = sum(counts[m][t][1] for t in side if t in counts[m])
        ys.append(math.log((f + 0.5) / (a + 1)))
    y = np.array(ys)
    A = np.vstack([np.ones_like(caps), caps]).T
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


RESULTS = {}


def side_corr(A, B):
    return float(np.corrcoef(beh_resid(A), beh_resid(B))[0, 1])


def test_split(tasks, labelfn, name, stratify_bench=True):
    if stratify_bench:
        groups = defaultdict(list)
        for t in tasks:
            groups[t.split("/")[0]].append(t)
    else:
        groups = {"all": list(tasks)}
    A = [t for ts in groups.values() for t in ts if labelfn(t)]
    B = [t for ts in groups.values() for t in ts if not labelfn(t)]
    if min(len(A), len(B)) < 20:
        print(f"{name}: skipped (sides {len(A)}/{len(B)})")
        return
    sizes = {g: sum(1 for t in ts if labelfn(t))
             for g, ts in groups.items()}
    obs = side_corr(A, B)
    null = []
    for _ in range(N_NULL):
        RA, RB = [], []
        for g, ts in groups.items():
            perm = rng.permutation(len(ts))
            RA += [ts[i] for i in perm[: sizes[g]]]
            RB += [ts[i] for i in perm[sizes[g]:]]
        null.append(side_corr(RA, RB))
    null = np.array(null)
    z = (obs - null.mean()) / null.std()
    print(f"{name}: corr {obs:+.3f} vs null {null.mean():+.3f}"
          f"±{null.std():.3f}  z={z:+.2f}  sides {len(A)}/{len(B)}")
    RESULTS[name.strip()] = {"corr": obs, "null_mean": float(null.mean()), "null_sd": float(null.std()),
                             "z": float(z), "sides": [len(A), len(B)]}
    return z


print("R1 — solution-stringy (independent operationalization):")
ps = {t for t in easy if prompt_stringy(t)}
ss = {t for t in easy if sol_stringy(t)}
print(f"  prompt-stringy {len(ps)}, solution-stringy {len(ss)}, "
      f"overlap {len(ps & ss)}")
test_split(easy, sol_stringy, "  sol-stringy combined")

print("\nR2 — within one benchmark at a time (prompt-stringy):")
he = [t for t in easy if t.startswith("HumanEval")]
mb = [t for t in easy if t.startswith("Mbpp")]
test_split(he, prompt_stringy, "  HE-only", stratify_bench=False)
test_split(mb, prompt_stringy, "  MBPP-only", stratify_bench=False)
print("and solution-stringy:")
test_split(he, sol_stringy, "  HE-only (sol)", stratify_bench=False)
test_split(mb, sol_stringy, "  MBPP-only (sol)", stratify_bench=False)

print("\nR3 — capability-adjusted breadth:")
traits = json.load(open(HERE / "data" / "traits.json"))
mm = [m for m in subm if m in traits
      and traits[m].get("resid") is not None]
b = np.array([traits[m]["n_easy_fail_tasks"] for m in mm], float)
r = np.array([traits[m]["resid"] for m in mm])
c = np.array([traits[m]["cap"] for m in mm])
A = np.vstack([np.ones_like(c), c]).T
beta, *_ = np.linalg.lstsq(A, b, rcond=None)
b_adj = b - A @ beta
rr = np.corrcoef(b_adj, r)[0, 1]
rraw = np.corrcoef(b, r)[0, 1]
print(f"  raw breadth corr2 {rraw**2:.3f}; capability-adjusted "
      f"breadth corr2 {rr**2:.3f} (r={rr:+.3f}, n={len(mm)})")

json.dump(RESULTS, open(HERE / "data" / "string_axis_replication.json", "w"), indent=1)
print("written data/string_axis_replication.json")

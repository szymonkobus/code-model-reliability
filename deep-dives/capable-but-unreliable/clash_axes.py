# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Cycle 7: which task features carry the model x pool clash?

Method: split the combined easy-band kept tasks into two sides along a
task FEATURE (stratified within benchmark so benchmark identity never
confounds), compute each model's behavioral residual on each side
(log easy failure rate residualized on official combined capability),
and correlate sides across models. Compare against the null
distribution of stratified RANDOM splits with the same side sizes.
A feature whose side-correlation sits far BELOW the random band is an
axis models systematically resonate with — it names the clash.
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
rng = np.random.default_rng(20260825)

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

# task text
tasks_meta = {}
for fn, bench in [("HumanEvalPlus-v0.1.10.jsonl", "HumanEval"),
                  ("MbppPlus-v0.2.0.jsonl", "Mbpp")]:
    for line in open(Path.home() / ".cache" / "evalplus" / fn):
        r = json.loads(line)
        tasks_meta[r["task_id"]] = r

easy = [t for t in diff if diff[t] < EASY and t in tasks_meta
        and any(t in counts[m] for m in models)]
print(f"easy tasks with text: {len(easy)}")


def snake_ok(name):
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


def feature_values(t):
    r = tasks_meta[t]
    p = r["prompt"]
    sol = r.get("canonical_solution", "")
    return {
        "prompt_long": len(p),
        "sol_long": len(sol),
        "has_example": (">>>" in p or "Example" in p or "example" in p),
        "snake_entry": snake_ok(r["entry_point"]),
        "stringy": ("string" in p.lower() or "str" in p.lower()),
        "mathy": bool(re.search(r"digit|number|integer|sum|count|prime|"
                                r"factor|divis", p, re.I)),
        "listy": bool(re.search(r"list|array|element", p, re.I)),
        "edge_wordy": bool(re.search(r"empty|zero|negative|single", p, re.I)),
        "loop_sol": ("for " in sol or "while " in sol),
        "regexy": ("re." in sol or "import re" in p),
    }


feats = {t: feature_values(t) for t in easy}


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


def side_corr(sideA, sideB):
    return float(np.corrcoef(beh_resid(sideA), beh_resid(sideB))[0, 1])


by_bench = {"HumanEval": [t for t in easy if t.startswith("HumanEval")],
            "Mbpp": [t for t in easy if t.startswith("Mbpp")]}


def stratified_random(sizes):
    A, B = [], []
    for bench, ts in by_bench.items():
        perm = rng.permutation(len(ts))
        ka = sizes[bench]
        A += [ts[i] for i in perm[:ka]]
        B += [ts[i] for i in perm[ka:]]
    return A, B


results = {}
FEATS = list(next(iter(feats.values())))
for name in FEATS:
    vals = {t: feats[t][name] for t in easy}
    A, B = [], []
    sizes = {}
    for bench, ts in by_bench.items():
        vs = [vals[t] for t in ts]
        if isinstance(vs[0], bool):
            hi = [t for t in ts if vals[t]]
            lo = [t for t in ts if not vals[t]]
        else:
            med = np.median(vs)
            hi = [t for t in ts if vals[t] > med]
            lo = [t for t in ts if vals[t] <= med]
        A += hi
        B += lo
        sizes[bench] = len(hi)
    if min(len(A), len(B)) < 25:
        print(f"{name:>12s}: skipped (side sizes {len(A)}/{len(B)})")
        continue
    obs = side_corr(A, B)
    null = []
    for _ in range(N_NULL):
        RA, RB = stratified_random(sizes)
        null.append(side_corr(RA, RB))
    null = np.array(null)
    z = (obs - null.mean()) / null.std()
    dA = np.mean([diff[t] for t in A])
    dB = np.mean([diff[t] for t in B])
    results[name] = {"corr": obs, "null_mean": float(null.mean()),
                     "null_sd": float(null.std()), "z": float(z),
                     "sizes": [len(A), len(B)],
                     "diff_means": [float(dA), float(dB)]}
    print(f"{name:>12s}: corr {obs:+.3f} vs null {null.mean():+.3f}"
          f"±{null.std():.3f}  z={z:+.2f}  sides {len(A)}/{len(B)} "
          f"diff {dA:.3f}/{dB:.3f}")

# reference: the benchmark axis itself
obs = side_corr(by_bench["HumanEval"], by_bench["Mbpp"])
print(f"\nreference benchmark axis (HE vs MBPP): corr {obs:+.3f}")

json.dump(results, open(HERE / "data" / "clash_axes.json", "w"), indent=1)

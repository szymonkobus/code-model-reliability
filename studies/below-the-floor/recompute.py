#!/usr/bin/env python3
"""Recomputes the below-the-floor test: the deep attempts against the line frozen before they were read.

Reads this study's ``per_task.csv`` (per task of the frozen frame: its difficulty then, the failures of the arm's 128
published attempts, and the failures and attempts of the deep repeats) and ``frozen_line.json`` (per part of wave 1,
the two-layer line fitted on the 128-attempt data with its bootstrap draws, and the difficulty window where the line
predicts failure rates between one in ten thousand and eight in a thousand), and the published fit's ``cells.csv``.
Simulates the frozen prediction's band for the pooled failure rate of every window bin, reads the observed rate against
it and gives the verdict; counts the tasks that left the floor of zero failures when the attempts grew from 128 to about
ten thousand; and checks the 128-attempt failures against the arm's published cells. Exits 1 when a check fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import expit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

HERE = Path(__file__).resolve().parent
ARM = "Qwen--Qwen3-4B_temp_0.8"
DRAWS = 8000
JUDGE_FRAGILE = {"Mbpp/123", "Mbpp/255", "Mbpp/599", "HumanEval/130", "HumanEval/32"}   # tasks whose verdicts the judge's limits moved; the test is read with and without them


def band_and_verdict(part: dict, task: dict, rng: np.random.Generator, exclude=frozenset()):
    """Per window bin, the observed pooled failure rate against the frozen line's simultaneous 95% band.

    For each bootstrap draw of (a, b, rho): a task's rate is Beta around logistic(a + b z) with the intra-task
    correlation rho, its failures Binomial at the task's total attempts; the band is widened over the bins together
    until 95% of the draws fall inside every bin at once. The verdict is HELD when every observed rate lies inside,
    BENT when the excesses share a sign and stay within three half-widths, BROKE otherwise.
    """
    a, b, rho = part["two_layer"]["a"], part["two_layer"]["b"], part["two_layer"]["rho"]
    draws = np.array(part["bootstrap"]["draws"])
    bins, pooled_rows, obs_rows = [], [], []
    for bn in part["window_bins"]:
        tids = [t for t in bn["task_ids"] if t not in exclude]
        if not tids:
            bins.append({"z_edges": bn["z_edges"], "n_tasks": 0})
            continue
        f_tot = np.array([task[t]["f128"] + task[t]["deep_f"] for t in tids], float)
        n_tot = np.array([task[t]["n128"] + task[t]["deep_n"] for t in tids], float)
        z = np.array([task[t]["z"] for t in tids])
        pick = rng.integers(0, len(draws), DRAWS)
        aa, bb, rr = draws[pick, 0], draws[pick, 1], np.clip(draws[pick, 2], 1e-6, 1 - 1e-6)
        q = expit(aa[:, None] + bb[:, None] * z[None, :])
        alpha = q * (1 - rr[:, None]) / rr[:, None]
        beta = (1 - q) * (1 - rr[:, None]) / rr[:, None]
        p = rng.beta(alpha, beta)
        k = rng.binomial(n_tot.astype(int)[None, :].repeat(DRAWS, 0), p)
        pooled_rows.append(k.sum(1) / n_tot.sum())
        obs_rows.append(f_tot.sum() / n_tot.sum())
        bins.append({"z_edges": bn["z_edges"], "n_tasks": len(tids), "fails": int(f_tot.sum()), "attempts": int(n_tot.sum()),
                     "line_level": [float(expit(a + b * bn["z_edges"][1])), float(expit(a + b * bn["z_edges"][0]))],
                     "zero_tasks": int((f_tot == 0).sum())})
    verdict = None
    if pooled_rows:
        S = np.stack(pooled_rows)
        lo = hi = None
        for alpha_ in np.linspace(0.025, 0.0005, 50):
            lo = np.percentile(S, 100 * alpha_, axis=1)
            hi = np.percentile(S, 100 * (1 - alpha_), axis=1)
            if ((S >= lo[:, None]) & (S <= hi[:, None])).all(0).mean() >= 0.95:
                break
        inside, signs, excess = [], [], []
        j = 0
        for bn in bins:
            if bn["n_tasks"] == 0:
                continue
            o = obs_rows[j]
            bn["observed"] = float(o); bn["band"] = [float(lo[j]), float(hi[j])]
            ok = lo[j] <= o <= hi[j]
            bn["inside"] = bool(ok)
            inside.append(ok)
            if not ok:
                half = (hi[j] - lo[j]) / 2
                signs.append(1 if o > hi[j] else -1)
                excess.append((o - hi[j] if o > hi[j] else lo[j] - o) / max(half, 1e-12))
            j += 1
        verdict = "HELD" if all(inside) else ("BENT" if len(set(signs)) == 1 and max(excess) <= 3.0 else "BROKE")
    return bins, verdict


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    fit = tables.fit_dir(data, args.fit)
    cells = tables.read_cells(fit)
    frozen = json.loads((HERE / "frozen_line.json").read_text(encoding="utf-8"))
    rows = tables.read_csv(HERE / "per_task.csv")
    task = {r["task_id"]: {"z": float(r["difficulty_z_frozen"]), "f128": int(r["failures_128"]), "n128": int(r["attempts_128"]),
                           "deep_f": int(r["deep_failures"]), "deep_n": int(r["deep_attempts"])} for r in rows}
    rep = tables.Report()
    rep.say(f"published fit: {fit.name}; arm: {ARM}; tasks in the frozen frame: {len(task)}; deep attempts per task: {frozen['deep_attempts_per_task']:,}")

    # 1. the window test, with the simulation seeded as the study seeded it and run in the study's order
    rng = np.random.default_rng(frozen["seed"])
    for name, part in frozen["parts"].items():
        bins, verdict = band_and_verdict(part, task, rng)
        _, verdict_without = band_and_verdict(part, task, rng, exclude=JUDGE_FRAGILE)
        rep.say()
        rep.say(f"{name} ({part['n_tasks']} tasks; ids {part['id_prefix']}...): frozen line logit q = {part['two_layer']['a']:.3f} + {part['two_layer']['b']:.3f} z, rho {part['two_layer']['rho']:.3f}")
        for bn in bins:
            if bn["n_tasks"] == 0:
                rep.say(f"  bin z in [{bn['z_edges'][0]:.2f}, {bn['z_edges'][1]:.2f}]: no task")
                continue
            rep.say(f"  bin z in [{bn['z_edges'][0]:.2f}, {bn['z_edges'][1]:.2f}]: {bn['n_tasks']} tasks; line level {bn['line_level'][0]:.1e} to {bn['line_level'][1]:.1e}; "
                    f"observed {bn['fails']} of {bn['attempts']:,} ({bn['observed']:.1e}); band [{bn['band'][0]:.1e}, {bn['band'][1]:.1e}]; "
                    f"{'inside' if bn['inside'] else 'OUTSIDE'}; tasks still at zero {bn['zero_tasks']}")
        rep.check(verdict == "HELD" and verdict_without == "HELD", f"{name}: verdict {verdict} (without the judge-fragile tasks: {verdict_without})")

    # 2. the floor: tasks at zero failures in 128 attempts, and where they stand at about ten thousand
    zero128 = [t for t, v in task.items() if v["f128"] == 0]
    left = [t for t in zero128 if task[t]["deep_f"] > 0]
    still = [t for t in zero128 if task[t]["deep_f"] == 0]
    rates = sorted((task[t]["deep_f"] + task[t]["f128"]) / (task[t]["deep_n"] + task[t]["n128"]) for t in left)
    rep.say()
    rep.say(f"tasks at zero failures in 128 attempts: {len(zero128)}; with a failure by {frozen['deep_attempts_per_task']:,} attempts: {len(left)}"
            + (f" (rates {rates[0]:.1e} to {rates[-1]:.1e})" if rates else "") + f"; still at zero: {len(still)}")
    if still:
        t0 = still[0]
        n_all = task[t0]["deep_n"] + task[t0]["n128"]
        rep.say(f"a task still at zero after {n_all:,} attempts has a Jeffreys rate of {0.5 / (n_all + 1):.1e} and a 95% upper bound of {3 / n_all:.1e} per attempt")

    # 3. the 128-attempt failures against the arm's published cells
    same = differ = missing = pooled = 0
    examples = []
    for t, v in task.items():
        key = (ARM, t)
        if key not in cells:
            missing += 1
            continue
        if cells[key][1] != v["n128"]:
            pooled += 1   # the published cell pools a folded copy's attempts into the parent's; not comparable
            continue
        if cells[key][0] == v["f128"]:
            same += 1
        else:
            differ += 1
            if len(examples) < 6:
                examples.append(f"{t}: frozen {v['f128']} of {v['n128']}, published {cells[key][0]} of {cells[key][1]}")
    kept_now = set(tables.read_kept_wave1(data)["tasks"])
    out_now = sorted(t for t in task if t not in kept_now)
    rep.say()
    rep.say(f"the frozen 128-attempt counts against the arm's published cells: equal {same}; differ {differ}; "
            f"parents of a folded copy, pooled, not compared {pooled}; task not in the published fit {missing}")
    rep.say(f"frame tasks outside the kept list the repository ships: {len(out_now)} ({', '.join(out_now)}); "
            f"kept tasks outside the frame: {len(kept_now - set(task))}")
    for e in examples:
        rep.say(f"   differs: {e}")
    rep.check(same >= 0.95 * (same + differ), "at least 95% of the frozen counts equal the published cells (the judge's later corrections move the rest)")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())

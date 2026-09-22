#!/usr/bin/env python3
"""Draw an arm's observed failure rate against task difficulty from the published cells.

Each point is one task: failures / attempts against the task's difficulty (the fit's internal unit,
larger is harder), with a running mean over difficulty bins. The data are results/served/<fit>/cells.csv,
the same inputs the Bayesian fit consumed; the fitted curve itself is reproduced by analysis/fitting.

usage: python3 figures/failure_vs_difficulty_cells.py [--fit board_top] [--arm <arm id>] [--out path.png]
"""
import argparse
import csv
import math
import pathlib
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="board_top")
    ap.add_argument("--arm", default=None, help="arm id as in cells.csv; default: the first arm in the file")
    ap.add_argument("--bins", type=int, default=24)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    src = ROOT / "results" / "served" / args.fit / "cells.csv"
    by_arm = defaultdict(list)
    for r in csv.DictReader(open(src, encoding="utf-8")):
        by_arm[r["arm"]].append((float(r["difficulty_z"]), int(r["failures"]), int(r["attempts"])))
    arm = args.arm or sorted(by_arm)[0]
    cells = by_arm[arm]
    xs = [z for z, _, _ in cells]
    ys = [f / n if n else float("nan") for _, f, n in cells]
    lo, hi = min(xs), max(xs)
    width = (hi - lo) / args.bins or 1.0
    agg = defaultdict(lambda: [0, 0])
    for z, f, n in cells:
        b = min(int((z - lo) / width), args.bins - 1)
        agg[b][0] += f; agg[b][1] += n
    bx = [lo + (b + 0.5) * width for b in sorted(agg)]
    by = [agg[b][0] / agg[b][1] if agg[b][1] else float("nan") for b in sorted(agg)]
    fig, ax = plt.subplots(figsize=(8, 5), dpi=130)
    ax.scatter(xs, ys, s=8, alpha=0.45, color="#0b57d0", label="one task: failures / attempts")
    ax.plot(bx, by, color="#1a1a1a", linewidth=1.6, label=f"mean over {args.bins} difficulty bins")
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("task difficulty (internal unit; larger is harder)")
    ax.set_ylabel("failure rate")
    ax.set_title(f"Failure rate against difficulty: {arm} ({args.fit} fit, {len(cells)} tasks)")
    ax.grid(True, color="#e0d9c8", linewidth=0.6); ax.legend(loc="upper left", fontsize=8)
    safe = arm.replace("/", "_")
    out = pathlib.Path(args.out) if args.out else ROOT / "figures" / f"failure_vs_difficulty_{args.fit}_{safe}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out)
    print(f"{arm}: {len(cells)} tasks, {sum(n for _, _, n in cells)} attempts -> {out}")


if __name__ == "__main__":
    main()

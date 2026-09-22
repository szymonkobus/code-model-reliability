#!/usr/bin/env python3
"""Draw capability against reliability for every arm of a published fit.

Capability is the difficulty at which an arm's fitted failure curve crosses one half (column
d50_of_record_z); reliability is the difficulty at which it crosses one in a hundred
(d1_of_record_z, with its 80% credible interval). Both are read from results/served/<fit>/
crossings_of_record.csv and drawn in the fit's internal difficulty unit (standard deviations
of the task-difficulty scale; larger is harder). Rows whose reliability is a bound or is
unresolved are drawn in grey; an interval that does not enclose the value of record (which
happens for bounds) is drawn as far as it reaches.

usage: python3 figures/capability_vs_reliability.py [--fit board_top] [--out figures/capability_vs_reliability.png]
"""
import argparse
import csv
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]


def short_name(arm: str) -> str:
    return arm.split("--")[-1].replace("_temp_0.8", "").replace("_temp_0.6", "").replace("_batch", " (API)").replace("-Instruct", "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="board_top")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    src = ROOT / "results" / "served" / args.fit / "crossings_of_record.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    pts = []
    for r in rows:
        try:
            x = float(r["d50_of_record_z"]); y = float(r["d1_of_record_z"])
            lo = float(r["d1_of_record_cri80_lo"]); hi = float(r["d1_of_record_cri80_hi"])
        except (KeyError, ValueError):
            continue
        pts.append((x, y, lo, hi, r["arm"], r.get("d1_of_record_status", "")))
    fig, ax = plt.subplots(figsize=(8, 6), dpi=130)
    for x, y, lo, hi, arm, status in pts:
        plain = status.strip().lower() == "point"
        err = [[max(0.0, y - lo)], [max(0.0, hi - y)]]
        ax.errorbar(x, y, yerr=err, fmt="o", ms=4, color="#0b57d0" if plain else "#8b8477", ecolor="#cfc5ac", elinewidth=1, capsize=0)
        ax.annotate(short_name(arm), (x, y), fontsize=6, xytext=(3, 2), textcoords="offset points", color="#52514e")
    ax.set_xlabel("capability: difficulty at which the failure rate crosses one half")
    ax.set_ylabel("reliability: difficulty at which the failure rate crosses one in a hundred")
    ax.set_title(f"Capability against reliability, one point per arm ({args.fit} fit); bars are 80% intervals")
    ax.grid(True, color="#e0d9c8", linewidth=0.6)
    out = pathlib.Path(args.out) if args.out else ROOT / "figures" / f"capability_vs_reliability_{args.fit}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out)
    print(f"{len(pts)} arms -> {out}")


if __name__ == "__main__":
    main()

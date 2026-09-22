#!/usr/bin/env python3
"""Turn one arm's rows of a published cells.csv back into the fitting engine's input arrays.

The engine (bayes_full.py --run --inputs <npz>) reads an .npz with model_id, task_ids, z_hat (task difficulty),
sd (its uncertainty), f (failures) and n (attempts). results/served/<fit>/cells.csv holds exactly these per arm.

usage: python3 analysis/fitting/cells_to_npz.py --fit board_top --arm <arm id> --out arm.npz
       python3 analysis/fitting/cells_to_npz.py --fit board_top --list
"""
import argparse
import csv
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="board_top")
    ap.add_argument("--arm", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--list", action="store_true", help="list the arms in the fit and exit")
    args = ap.parse_args()
    src = ROOT / "results" / "served" / args.fit / "cells.csv"
    rows = [r for r in csv.DictReader(open(src, encoding="utf-8"))]
    arms = sorted({r["arm"] for r in rows})
    if args.list or not args.arm:
        print("\n".join(arms)); return
    sel = [r for r in rows if r["arm"] == args.arm]
    if not sel:
        raise SystemExit(f"arm {args.arm!r} not in {src}; use --list")
    out = pathlib.Path(args.out or f"{args.arm.replace('/', '_')}.npz")
    np.savez(out,
             model_id=np.array(args.arm),
             task_ids=np.array([r["task_id"] for r in sel]),
             z_hat=np.array([float(r["difficulty_z"]) for r in sel]),
             sd=np.array([float(r["difficulty_sd"]) for r in sel]),
             f=np.array([int(r["failures"]) for r in sel], dtype=np.int64),
             n=np.array([int(r["attempts"]) for r in sel], dtype=np.int64))
    print(f"{args.arm}: {len(sel)} cells -> {out}")


if __name__ == "__main__":
    main()

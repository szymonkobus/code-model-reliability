"""Verdicts become cells, and the models become a registry.

A cell is one arm on one task: failures out of attempts, where an attempt passes only when every base test and
every extended test passes. The rules that turn verdict files into cells: a re-judged task's newest verdicts
win (``judgings``); an answer cut at the output limit and re-run to completion is one attempt in two parts, and a
correction never rewrites a judged file, it lands as a companion file beside it (``corrections``); the attempts the
time limit stopped are counted apart (``cells``). ``passk`` recomputes pass@k from the verdicts; ``per_test``
summarises how alike an arm's failures on a task are.

The registry names every arm (a model under one generation protocol) once: its id, model, protocol, form,
temperature, attempts per task, the judging settings its verdicts carry and the extractor its samples carry.

Writes ``cells.csv``, ``registry/arms.jsonl`` and ``passk.csv``. Reads the verdict files, the corrections beside
them, ``arm_map.tsv`` and ``names.json``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def land_arm(arm_dir: pathlib.Path, arm: str, out_dir: pathlib.Path, set_name: str) -> dict:
    """Compose one arm's verdict files and corrections, write its cells and pass@k rows."""
    from . import cells, corrections, judgings, passk, per_test

    composed, won = judgings.compose_directory(arm_dir)
    correction_rows = corrections.read_corrections(arm_dir / "corrections.jsonl")
    composed, applied, refused = corrections.apply_corrections(composed, correction_rows)
    if refused:
        print(f"{arm}: {len(refused)} corrections refused: {refused[0]['reason']}", file=sys.stderr)
    per_test_rows = per_test_rows_of(arm_dir)
    judging_ids = sorted(set(won.values()))
    judging_id = judging_ids[0] if len(judging_ids) == 1 else "mixed:" + ",".join(judging_ids)
    rows = cells.cells_from_verdicts(arm, composed, judging_id, per_test_rows)
    for r in rows:
        r["judging"] = won.get(r["task_id"], judging_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    cells.write(rows, out_dir / "cells.csv")
    passk.write(passk.table(arm, set_name, composed), out_dir / "passk.csv")
    if per_test_rows:
        per_test.write(per_test.summarise(arm, per_test_rows), out_dir / "per_test_summary.csv")
    return {"arm": arm, "cells": len(rows), "corrections_applied": len(applied), "corrections_refused": len(refused),
            "judgings": judging_ids}


def per_test_rows_of(arm_dir: pathlib.Path) -> list[dict]:
    path = arm_dir / "per_test.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cmr land", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("cells", help="compose one arm's verdicts and corrections into cells.csv and passk.csv")
    p.add_argument("--arm-dir", required=True, help="the directory with verdicts.json, judging.json and companions")
    p.add_argument("--arm", required=True, help="the arm id")
    p.add_argument("--set", required=True, help="the set name: wave1, wave2 or wave2-parked")
    p.add_argument("--out", required=True)
    r = sub.add_parser("registry", help="build registry/arms.jsonl from the arm directories")
    r.add_argument("--arm-dirs", nargs="+", required=True)
    r.add_argument("--arm-map", required=True)
    r.add_argument("--names", default=None)
    r.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "cells":
        print(json.dumps(land_arm(pathlib.Path(args.arm_dir), args.arm, pathlib.Path(args.out), args.set)))
    elif args.command == "registry":
        from . import registry

        rows = registry.build(args.arm_dirs, registry.load_arm_map(args.arm_map), registry.load_names(args.names))
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        registry.write(rows, args.out)
        print(json.dumps({"arms": len(rows), "out": args.out}))
    return 0

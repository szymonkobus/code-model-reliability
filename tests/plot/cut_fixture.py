#!/usr/bin/env python3
"""cut_fixture.py — the plot stage's test fixture as a restriction of the published data: four arms and forty tasks of
the one fit under ``data/results/published/``, every file in the shape the export writes.

    python3 tests/plot/cut_fixture.py --data data                       # from the repository's data directory
    python3 tests/plot/cut_fixture.py --data <dir> --fit-dir <fit dir>  # a fit directory named explicitly

Reads ``results/published/<fit>/`` (meta.json, axis.csv, cells.csv, crossings.csv, crossings.json, gates.json,
panel.json, arms/<arm>.json) and ``runs/registry/`` (arms.jsonl, models.jsonl, names.json, protocols.tsv, arm_map.tsv)
and writes the same files under ``tests/fixtures/plot/data``, restricted: the four arms' rows and summaries; forty tasks
spread along the difficulty scale, every one with cells from all four arms; the registry rows of the four arms and of
the positions of any training run among them; every model row, since the colour ladder ranks a family's models of
record. Nothing is re-computed or re-worded: a value in the fixture is the published value. The
fit's engine and sampler blocks in meta.json describe the whole fit; population describes the restriction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "fixtures" / "plot" / "data"
FIT_NAME = "fixture-fit"
N_TASKS = 40
ARMS = ["Qwen--Qwen3-8B_temp_0.8", "Qwen--Qwen3-8B_think_temp_0.6", "claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch"]


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_tsv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return rows[0], rows[1:]


def write_tsv_rows(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def dump(path: Path, obj, indent: int | None = 1) -> None:
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def find_fit(data: Path) -> Path:
    base = data / "results" / "published"
    fits = sorted(p for p in base.iterdir() if p.is_dir() and (p / "crossings.csv").exists()) if base.is_dir() else []
    if len(fits) != 1:
        sys.exit(f"expected one fit under {base}, found {len(fits)}; name it with --fit-dir")
    return fits[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="cut the plot stage's test fixture as a restriction of the published data")
    ap.add_argument("--data", required=True, help="the data directory (results/published/<fit>/ and runs/registry/ under it)")
    ap.add_argument("--fit-dir", default=None, help="the fit directory, when not the one under results/published/")
    ap.add_argument("--out", default=str(OUT), help="where the fixture is written")
    args = ap.parse_args(argv)
    data = Path(args.data)
    fit = Path(args.fit_dir) if args.fit_dir else find_fit(data)
    registry = data / "runs" / "registry"
    out = Path(args.out)
    out_fit = out / "results" / "published" / FIT_NAME
    out_reg = out / "runs" / "registry"
    for d in (out_fit, out_reg):
        if d.exists():
            shutil.rmtree(d)
    (out_fit / "arms").mkdir(parents=True)
    out_reg.mkdir(parents=True)

    # the tasks: those with cells from every arm, forty of them spread evenly along the difficulty scale
    axis_header, axis_rows = read_csv(fit / "axis.csv")
    cells_header, cells_rows = read_csv(fit / "cells.csv")
    covered: dict[str, set[str]] = {}
    for r in cells_rows:
        if r["arm"] in ARMS:
            covered.setdefault(r["task_id"], set()).add(r["arm"])
    eligible = [r for r in axis_rows if len(covered.get(r["task_id"], ())) == len(ARMS)]
    if len(eligible) < N_TASKS:
        sys.exit(f"only {len(eligible)} tasks carry cells from all {len(ARMS)} arms")
    eligible.sort(key=lambda r: float(r["difficulty_z"]))
    picked_rows = [eligible[round(i * (len(eligible) - 1) / (N_TASKS - 1))] for i in range(N_TASKS)]
    picked = [r["task_id"] for r in picked_rows]
    assert len(set(picked)) == N_TASKS
    write_csv(out_fit / "axis.csv", axis_header, picked_rows)
    kept_cells = [r for r in cells_rows if r["arm"] in ARMS and r["task_id"] in set(picked)]
    write_csv(out_fit / "cells.csv", cells_header, kept_cells)

    # the crossings table and its twin, the gates and the panel, restricted to the four arms
    cr_header, cr_rows = read_csv(fit / "crossings.csv")
    kept_rows = [r for r in cr_rows if r["arm"] in ARMS]
    if len(kept_rows) != len(ARMS):
        sys.exit(f"{len(kept_rows)} of the {len(ARMS)} arms have a crossings row under {fit}")
    write_csv(out_fit / "crossings.csv", cr_header, kept_rows)
    files = ["cells.csv", "axis.csv"]
    if (fit / "panel.json").exists():
        panel = json.loads((fit / "panel.json").read_text(encoding="utf-8"))
        for key in ("voters", "positioned_only", "excluded_from_voting"):
            if isinstance(panel.get(key), list):
                panel[key] = [a for a in panel[key] if a in ARMS]
        if isinstance(panel.get("coverage"), dict):
            panel["coverage"] = {a: v for a, v in panel["coverage"].items() if a in ARMS}
        panel["n_tasks"] = N_TASKS
        dump(out_fit / "panel.json", panel)
        files.append("panel.json")
    gates = None
    if (fit / "gates.json").exists():
        gates = json.loads((fit / "gates.json").read_text(encoding="utf-8"))
        arms_block = {a: v for a, v in (gates.get("arms") or {}).items() if a in ARMS}
        gates["arms"] = arms_block
        gates["n_arms"] = len(arms_block)
        gates["n_pass"] = sum(1 for v in arms_block.values() if v.get("gate") == "pass")
        dump(out_fit / "gates.json", gates)
        files.append("gates.json")
    files.append("crossings.csv")
    if (fit / "crossings.json").exists():
        twin = json.loads((fit / "crossings.json").read_text(encoding="utf-8"))
        twin["label"] = FIT_NAME
        twin["rows"] = [r for r in twin.get("rows") or [] if r.get("arm") in ARMS]
        twin["n_arms"] = len(twin["rows"])
        twin["csv_sha256"] = hashlib.sha256((out_fit / "crossings.csv").read_bytes()).hexdigest()
        dump(out_fit / "crossings.json", twin)
        files.append("crossings.json")
    for arm in ARMS:
        shutil.copyfile(fit / "arms" / f"{arm}.json", out_fit / "arms" / f"{arm}.json")
    files.append("arms/")

    # the fit's identity, with the restriction's population
    meta = json.loads((fit / "meta.json").read_text(encoding="utf-8"))
    label = meta.get("fit") or fit.name
    voters = panel.get("voters") if (fit / "panel.json").exists() else ARMS
    meta["fit"] = FIT_NAME
    meta["population"] = {"arms_fitted": len(ARMS), "arms_voting": len(voters), "tasks": N_TASKS, "cells": len(kept_cells)}
    meta["files"] = files
    meta["note"] = (f"a test fixture: the published fit {label} restricted to {len(ARMS)} arms and {N_TASKS} of its tasks; "
                    "engine and sampler describe the whole fit, population the restriction")
    dump(out_fit / "meta.json", meta)

    # the registry: the four arms' rows, the rows of the positions of any training run among them, every model row,
    # and the names file restricted to those runs
    names = json.loads((registry / "names.json").read_text(encoding="utf-8"))
    runs = {k: r for k, r in (names.get("runs") or {}).items() if any(p.get("arm") in ARMS for p in r.get("positions") or [])}
    kept_arms = list(ARMS)
    for r in runs.values():
        kept_arms += [p["arm"] for p in r.get("positions") or [] if p.get("arm") and p["arm"] not in kept_arms]
    lines = [json.loads(l) for l in (registry / "arms.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    header = next((l for l in lines if l.get("schema")), None)
    arm_rows = [l for l in lines if l.get("arm") in kept_arms]
    with open(out_reg / "arms.jsonl", "w", encoding="utf-8") as f:
        if header is not None:
            f.write(json.dumps({**header, "n_rows": len(arm_rows)}, ensure_ascii=False) + "\n")
        for row in arm_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    shutil.copyfile(registry / "models.jsonl", out_reg / "models.jsonl")
    for name in ("protocols.tsv", "arm_map.tsv"):
        if (registry / name).exists():
            head, rows = read_tsv_rows(registry / name)
            col = head.index("arm")
            write_tsv_rows(out_reg / name, head, [r for r in rows if len(r) > col and r[col] in kept_arms])
    bases = {k: v for k, v in (names.get("bases") or {}).items() if isinstance(v, dict) and v.get("arm") in kept_arms}
    dump(out_reg / "names.json", {k: v for k, v in names.items() if k not in ("runs", "bases")} | {"runs": runs, "bases": bases})

    print(f"fixture written under {out}: {len(ARMS)} arms, {N_TASKS} tasks, {len(kept_cells)} cells, {len(arm_rows)} registry arm rows, "
          f"{len(runs)} training runs, from {fit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

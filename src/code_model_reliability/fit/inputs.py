"""From cells and the axis to the engine's inputs: one ``.npz`` per arm and the manifest of a fit.

For each arm: the tasks it has cells on that also have a position on the axis, sorted by task id; the arrays
``z_hat`` and ``sd`` (the tasks' difficulties and standard errors from ``axis``), ``f`` and ``n`` (failures and
attempts), ``task_ids`` and the scalar ``model_id`` (the arm id). An arm with fewer than ``MIN_TASKS_PER_ARM``
such tasks is not fitted and is listed in the manifest's companion ``skipped.json``.

The fit's name is the first twelve hex digits of the sha256 over the sorted arm ids and the sha256 of the cells
file, so a refreshed set of cells is a new fit directory beside the old one and every table names the fit it
came from.

Reads ``cells.csv`` and ``axis.csv``. Writes ``inputs/<arm>.npz``, ``manifest.tsv`` (one line per arm: the npz
name and the errors-in-variables switch the fit runs with) and ``skipped.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .axis import Cell, TaskDifficulty, read_axis_csv, read_cells

MIN_TASKS_PER_ARM = 50
"""An arm needs cells on at least fifty axis tasks to be fitted; with fewer the curve is not identified."""


def fit_id(cells_path, arms) -> str:
    """The fit's name from the cells file's bytes and the sorted arm ids."""
    h = hashlib.sha256()
    h.update(hashlib.sha256(Path(cells_path).read_bytes()).hexdigest().encode())
    for a in sorted(set(arms)):
        h.update(b"\n" + a.encode("utf-8"))
    return h.hexdigest()[:12]


def arm_arrays(cells: list[Cell], axis: dict[str, TaskDifficulty], arm: str) -> dict | None:
    rows = {c.task_id: c for c in cells if c.arm == arm and c.task_id in axis}
    tasks = sorted(rows)
    if not tasks:
        return None
    return {
        "model_id": arm,
        "z_hat": np.array([axis[t].z for t in tasks], float),
        "sd": np.array([axis[t].se for t in tasks], float),
        "f": np.array([rows[t].failures for t in tasks], np.int64),
        "n": np.array([rows[t].attempts for t in tasks], np.int64),
        "task_ids": np.array(tasks),
    }


def write_npz(path, arrays: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, model_id=np.array(arrays["model_id"]), z_hat=arrays["z_hat"], sd=arrays["sd"],
             f=arrays["f"], n=arrays["n"], task_ids=arrays["task_ids"])


def build_inputs(cells, axis, out_dir, arms=None, min_tasks=MIN_TASKS_PER_ARM, eiv="on") -> tuple[list, list]:
    """Write the npz files and the manifest; returns (manifest rows, skipped arms)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = sorted(arms) if arms is not None else sorted({c.arm for c in cells})
    manifest, skipped = [], []
    for arm in arms:
        arrays = arm_arrays(cells, axis, arm)
        n_tasks = 0 if arrays is None else len(arrays["task_ids"])
        if n_tasks < min_tasks:
            skipped.append({"arm": arm, "n_tasks": n_tasks})
            continue
        name = f"{arm}.npz"
        write_npz(out_dir / name, arrays)
        manifest.append((name, eiv))
    with open(out_dir.parent / "manifest.tsv", "w", encoding="utf-8") as fh:
        for name, mode in manifest:
            fh.write(f"{name}\t{mode}\n")
    (out_dir.parent / "skipped.json").write_text(json.dumps(skipped, indent=1) + "\n", encoding="utf-8")
    return manifest, skipped


def read_manifest(path) -> list[tuple[str, str]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, mode = line.split("\t")[:2]
            rows.append((name, mode))
    return rows


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cmr fit inputs", description="the engine's inputs from cells and the axis")
    ap.add_argument("--cells", required=True)
    ap.add_argument("--axis", required=True, help="axis.csv from `cmr fit axis`")
    ap.add_argument("--fit-dir", required=True, help="the fit's directory; inputs/ and manifest.tsv are written under it")
    ap.add_argument("--arm", action="append", default=None, help="fit only these arms (repeatable); default every arm with cells")
    ap.add_argument("--min-tasks", type=int, default=MIN_TASKS_PER_ARM)
    ap.add_argument("--eiv", choices=["on", "off"], default="on")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cells = read_cells(args.cells)
    axis = read_axis_csv(args.axis)
    manifest, skipped = build_inputs(cells, axis, Path(args.fit_dir) / "inputs", args.arm, args.min_tasks, args.eiv)
    print(f"inputs: {len(manifest)} arms written under {args.fit_dir}/inputs, {len(skipped)} skipped "
          f"(fewer than {args.min_tasks} axis tasks); fit id {fit_id(args.cells, [m[0][:-4] for m in manifest])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read the published tables the figures and the site pages are drawn from.

Reads, under one data directory (``data/`` in the repository):

- ``results/published/<fit>/`` — one published fit: ``meta.json``, ``axis.csv``, ``crossings.csv``, ``gates.json``,
  ``cells.csv`` and ``arms/<arm>.json`` (the draw-free summary of one arm's fitted curve: the curve on a grid with its
  quantiles, the crossing at every failure-rate level under both definitions, the dispersion parameters and the density
  of the two crossings of record);
- ``runs/registry/`` — ``arms.jsonl``, ``models.jsonl``, ``names.json`` and ``protocols.tsv``.

Writes nothing. ``docs/data-contract.md`` is the shape of every file read here; a column the contract names as optional
is read when present and left ``None`` otherwise, so a table written by an older export still loads.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

PUBLISHED = Path("results") / "published"
REGISTRY = Path("runs") / "registry"

# The two crossings' failure-rate levels. D50 is read where the fitted average failure rate crosses one half and D99
# where it crosses one in a hundred; the levels are fixed by the project's definition of capability and reliability.
LEVEL_D50 = 0.5
LEVEL_D99 = 0.01


def _num(value: str | None) -> float | None:
    """A table cell as a float, or None for an empty, missing or non-numeric cell."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    v = _num(value)
    return None if v is None or math.isnan(v) else int(round(v))


@dataclass
class Crossing:
    """One crossing of one arm: the posterior median position on the difficulty scale, its 80% credible interval and
    its status (``point``, ``bound`` or ``unresolved``). A bound carries the scale end it stands at in ``bound_z``."""

    z: float | None
    lo: float | None
    hi: float | None
    status: str = "point"
    bound_z: float | None = None
    p_left_censored: float | None = None
    p_right_censored: float | None = None

    @property
    def is_point(self) -> bool:
        return self.status == "point" and self.z is not None

    @property
    def drawn_z(self) -> float | None:
        """Where the crossing is drawn: a point at its median, a bound at the scale end it stands at."""
        if self.status == "bound" and self.bound_z is not None:
            return self.bound_z
        return self.z


@dataclass
class CrossingsRow:
    """One row of ``crossings.csv``: an arm's D50 and D99 on the average-rate curve, the median-task D99 beside them,
    the dispersion parameters and the sampler's verdicts for the two crossings."""

    arm: str
    model_name: str | None
    d50: Crossing
    d99: Crossing
    d99_median_task: Crossing
    tau: tuple[float | None, float | None, float | None]
    rho: tuple[float | None, float | None, float | None]
    n_tasks: int | None
    grid: tuple[float | None, float | None]
    gate: str | None                                        # the gates' verdict as the table carries it: pass, fail, or None without the column
    gates_failed: list[str] = field(default_factory=list)   # the gates that failed, by name (rhat, ess, divergences)


def _verdict(value: str | None) -> str | None:
    """The gates' verdict of a table cell: ``pass`` or ``fail`` (the export writes ``pass`` and ``FAIL``), None for an empty
    or missing cell."""
    s = (value or "").strip().lower()
    if not s:
        return None
    return "pass" if s == "pass" else "fail"


def _crossing(row: dict, prefix: str) -> Crossing:
    status = (row.get(f"{prefix}_status") or "point").strip().split(" ")[0].split(":")[0].lower() or "point"
    if status not in ("point", "bound", "unresolved"):
        status = "point"
    return Crossing(
        z=_num(row.get(f"{prefix}_z")),
        lo=_num(row.get(f"{prefix}_lo")),
        hi=_num(row.get(f"{prefix}_hi")),
        status=status,
        bound_z=_num(row.get(f"{prefix}_bound_z")),
        p_left_censored=_num(row.get(f"{prefix}_p_left_censored")),
        p_right_censored=_num(row.get(f"{prefix}_p_right_censored")),
    )


def read_crossings(path: Path) -> dict[str, CrossingsRow]:
    """``crossings.csv`` as rows keyed by arm, in the file's order."""
    out: dict[str, CrossingsRow] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            arm = (row.get("arm") or "").strip()
            if not arm:
                continue
            out[arm] = CrossingsRow(
                arm=arm,
                model_name=(row.get("model_name") or "").strip() or None,
                d50=_crossing(row, "d50"),
                d99=_crossing(row, "d99"),
                d99_median_task=_crossing(row, "d99_median_task"),
                tau=(_num(row.get("tau")), _num(row.get("tau_lo")), _num(row.get("tau_hi"))),
                rho=(_num(row.get("rho")), _num(row.get("rho_lo")), _num(row.get("rho_hi"))),
                n_tasks=_int(row.get("n_tasks")),
                grid=(_num(row.get("grid_lo_z")), _num(row.get("grid_hi_z"))),
                gate=_verdict(row.get("gate")),
                gates_failed=[g for g in re.split(r"[;,\s]+", (row.get("gates_failed") or "").strip()) if g],
            )
    return out


@dataclass
class AxisTask:
    task_id: str
    z: float
    sd: float | None
    n_arms: int | None
    mean_failure_rate: float | None


def read_axis(path: Path) -> list[AxisTask]:
    """``axis.csv``: every task's position on the difficulty scale, sorted from easiest to hardest."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            z = _num(row.get("difficulty_z"))
            if z is None:
                continue
            out.append(AxisTask(row["task_id"], z, _num(row.get("difficulty_sd")), _int(row.get("n_arms")),
                                _num(row.get("mean_failure_rate"))))
    out.sort(key=lambda t: (t.z, t.task_id))
    return out


def read_cells(path: Path) -> dict[str, dict[str, tuple[int, int]]]:
    """``cells.csv``: per arm, per task, (failures, attempts)."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            failures, attempts = _int(row.get("failures")), _int(row.get("attempts"))
            if failures is None or attempts is None:
                continue
            out.setdefault(row["arm"], {})[row["task_id"]] = (failures, attempts)
    return out


@dataclass
class LevelsTable:
    """The crossing of a fitted curve at every failure-rate level: per level the posterior median position, its 80%
    interval and the share of draws censored below the easiest task and above the hardest."""

    levels: list[float]
    median_z: list[float | None]
    lo_z: list[float | None]
    hi_z: list[float | None]
    p_left: list[float | None]
    p_right: list[float | None]
    rule: str | None = None

    @classmethod
    def from_json(cls, d: dict | None) -> "LevelsTable | None":
        if not isinstance(d, dict) or not d.get("levels_fail_rate"):
            return None
        n = len(d["levels_fail_rate"])

        def col(name: str) -> list:
            v = d.get(name)
            return list(v) if isinstance(v, list) and len(v) == n else [None] * n

        return cls(list(d["levels_fail_rate"]), col("median_z"), col("cri80_lo_z"), col("cri80_hi_z"),
                   col("p_left_censored"), col("p_right_censored"), d.get("rule"))

    def at(self, level: float) -> tuple[float | None, float | None, float | None]:
        """(median, lo, hi) at the level nearest the one asked for."""
        i = min(range(len(self.levels)), key=lambda k: abs(self.levels[k] - level))
        return self.median_z[i], self.lo_z[i], self.hi_z[i]


@dataclass
class Curve:
    """A fitted curve on the difficulty grid: ``quantiles[q]`` is the failure rate's logit at every grid point for the
    posterior quantile ``q`` (in percent)."""

    zgrid: list[float]
    quantiles: dict[int, list[float]]

    def median(self) -> list[float]:
        return self.quantiles[50]

    def band(self, lo: int = 10, hi: int = 90) -> tuple[list[float], list[float]]:
        return self.quantiles[lo], self.quantiles[hi]


@dataclass
class ArmSummary:
    """The draw-free summary of one arm's fit (``arms/<arm>.json``)."""

    arm: str
    average: Curve | None
    typical: Curve | None
    levels_avg: LevelsTable | None
    levels: LevelsTable | None
    estimands_avg: dict
    estimands: dict
    tau: dict
    rho: dict
    density: dict

    @classmethod
    def from_json(cls, arm: str, d: dict) -> "ArmSummary":
        """From the export's shape (``curves.average``, ``levels.average``, ``estimands.average.d99`` ...) or, for a file
        cut straight from the engine's posterior summary, from the engine's own key names."""
        curves = d.get("curves") or {}
        zgrid = list(curves.get("zgrid") or [])
        qs = [int(q) for q in (curves.get("quantiles_pct") or [])]

        def curve(*names: str) -> Curve | None:
            for name in names:
                rows = curves.get(name)
                if zgrid and qs and isinstance(rows, list) and len(rows) == len(qs):
                    return Curve(zgrid, {q: list(r) for q, r in zip(qs, rows)})
            return None

        levels = d.get("levels") if isinstance(d.get("levels"), dict) and "average" in d.get("levels") else None
        estimands = d.get("estimands") if isinstance(d.get("estimands"), dict) and "average" in d.get("estimands") else None

        def crossings(block: dict | None) -> dict:
            block = block or {}
            return {"d50": dict(block.get("d50") or {}), "d99": dict(block.get("d99") or block.get("d1") or {})}

        return cls(
            arm,
            curve("average", "average_logit"),
            curve("median_task", "typical_logit"),
            LevelsTable.from_json(levels["average"] if levels else d.get("levels_table_avg")),
            LevelsTable.from_json(levels["median_task"] if levels else d.get("levels_table")),
            crossings(estimands["average"] if estimands else d.get("estimands_avg")),
            crossings(estimands["median_task"] if estimands else d.get("estimands")),
            dict(d.get("tau") or {}),
            dict(d.get("rho") or d.get("rho_icc") or {}),
            dict(d.get("density") or {}),
        )


@dataclass
class Fit:
    """One published fit: its directory, identity and tables. The cells and the per-arm summaries are read on first use."""

    path: Path
    meta: dict
    axis: list[AxisTask]
    crossings: dict[str, CrossingsRow]
    gates: dict
    _cells: dict | None = None
    _summaries: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.meta.get("fit") or self.path.name)

    @property
    def arms(self) -> list[str]:
        return list(self.crossings)

    @property
    def cells(self) -> dict[str, dict[str, tuple[int, int]]]:
        if self._cells is None:
            p = self.path / "cells.csv"
            self._cells = read_cells(p) if p.exists() else {}
        return self._cells

    def summary(self, arm: str) -> ArmSummary | None:
        """The arm's summary, or None when the fit ships none for it."""
        if arm not in self._summaries:
            p = self.path / "arms" / f"{arm}.json"
            self._summaries[arm] = ArmSummary.from_json(arm, json.loads(p.read_text(encoding="utf-8"))) if p.exists() else None
        return self._summaries[arm]

    def summaries(self) -> Iterator[tuple[str, ArmSummary]]:
        for arm in self.arms:
            s = self.summary(arm)
            if s is not None:
                yield arm, s

    def task_z(self) -> dict[str, float]:
        return {t.task_id: t.z for t in self.axis}


def published_fits(data: Path) -> list[Path]:
    """Every fit directory under ``results/published/``, the newest cut last (by the day ``cut`` in its ``meta.json``, then
    its name)."""
    base = data / PUBLISHED
    if not base.is_dir():
        return []
    dirs = [p for p in base.iterdir() if p.is_dir() and (p / "crossings.csv").exists()]

    def key(p: Path):
        try:
            day = json.loads((p / "meta.json").read_text(encoding="utf-8")).get("cut") or ""
        except (OSError, ValueError):
            day = ""
        return (str(day), p.name)

    return sorted(dirs, key=key)


def load_fit(data: Path, fit: str | None = None) -> Fit:
    """The fit named, or the newest published fit when none is named."""
    data = Path(data)
    if fit:
        path = data / PUBLISHED / fit
    else:
        fits = published_fits(data)
        if not fits:
            raise FileNotFoundError(f"no published fit under {data / PUBLISHED}")
        path = fits[-1]
    if not (path / "crossings.csv").exists():
        raise FileNotFoundError(f"no crossings.csv under {path}")
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8")) if (path / "meta.json").exists() else {}
    gates = json.loads((path / "gates.json").read_text(encoding="utf-8")) if (path / "gates.json").exists() else {}
    axis = read_axis(path / "axis.csv") if (path / "axis.csv").exists() else []
    crossings = read_crossings(path / "crossings.csv")
    if gates and crossings and all(r.gate is None for r in crossings.values()):
        raise ValueError(f"{path / 'crossings.csv'} carries no gate column while gates.json ships: the gates' verdict is read "
                         "from the table's gate column (pass or FAIL) and never assumed")
    return Fit(path=path, meta=meta, axis=axis, crossings=crossings, gates=gates)


@dataclass
class Registry:
    """The arms and models of record and the names of the models trained in this project."""

    arms: dict[str, dict]
    models: dict[str, dict]
    names: dict
    protocols: dict[str, dict]

    def arm(self, arm: str) -> dict:
        return self.arms.get(arm) or {}

    def model(self, arm: str) -> dict:
        row = self.arm(arm)
        return self.models.get(str(row.get("model_id") or "")) or {}

    def model_name(self, arm: str) -> str:
        """The name of record of an arm's model: the arm row's name, else the model row's, else the arm id itself
        (``require_names`` keeps that last case off every figure and page)."""
        row = self.arm(arm)
        return str(row.get("model_name") or self.model(arm).get("name") or arm)

    def unnamed(self, arms: list[str]) -> list[str]:
        """The arms among ``arms`` with no name of record: no arm row carrying a ``model_name`` and no model row with
        a ``name``."""
        return [a for a in arms if not (self.arm(a).get("model_name") or self.model(a).get("name"))]

    def run_position(self, arm: str) -> tuple[str, int] | None:
        """(run key, step) when the arm is a position of a training run named in ``names.json``, else None."""
        for key, run in (self.names.get("runs") or {}).items():
            for pos in run.get("positions") or []:
                if str(pos.get("arm") or pos.get("arm_id")) == arm:
                    step = pos.get("step")
                    return key, int(step) if step is not None else 0
        return None

    def run(self, key: str) -> dict:
        return (self.names.get("runs") or {}).get(key) or {}

    def model_id_by_name(self, name: str) -> str | None:
        """The model id whose name of record is the name given, else None."""
        for mid, row in self.models.items():
            if str(row.get("name") or "") == name:
                return mid
        return None


def require_names(registry: Registry, arms: list[str]) -> None:
    """Refuse arms without a name of record: a figure or a page never prints an arm id in place of a name, so a fit
    whose registry lacks a name is not drawn until the registry carries it."""
    missing = registry.unnamed(arms)
    if missing:
        shown = ", ".join(missing[:8]) + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
        raise ValueError(f"{len(missing)} of {len(arms)} arms of the fit have no name of record in the registry "
                         f"(no arm row with a model_name and no model row with a name): {shown}")


def _read_jsonl(path: Path, key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("schema"):
                continue   # the header row names the schema and the row count
            k = row.get(key)
            if k:
                out[str(k)] = row
    return out


def load_registry(data: Path) -> Registry:
    data = Path(data)
    base = data / REGISTRY
    names = json.loads((base / "names.json").read_text(encoding="utf-8")) if (base / "names.json").exists() else {}
    protocols: dict[str, dict] = {}
    if (base / "protocols.tsv").exists():
        with open(base / "protocols.tsv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row.get("model_id"):
                    protocols[row["model_id"]] = row
    return Registry(_read_jsonl(base / "arms.jsonl", "arm"), _read_jsonl(base / "models.jsonl", "model_id"), names, protocols)

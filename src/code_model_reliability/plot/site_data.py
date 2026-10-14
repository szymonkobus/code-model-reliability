"""The data bundles the two site pages read, written from the published tables.

The pages are static: a shell (HTML, scripts and a stylesheet under ``site/`` in the repository) that fetches small JSON
files and draws them in the browser. This module writes those files from a fit and the registry:

- the capability-against-reliability page reads ``manifest.json``, ``shared.json`` (the arms with their names, colours
  and marks, the training runs' rows, the scale's reach) and ``crossings.json`` (per arm, under both definitions, D50 and
  D99 with their densities and the crossing at every failure-rate level);
- the failure-against-difficulty page reads ``manifest.json``, ``shared.json`` (the tasks on the difficulty scale and the
  arms), ``curves.json`` (per arm the fitted curve's quantiles on the grid and its two crossings of record), ``cells.json``
  (per arm the failures and attempts on every task) and ``levels.json`` (per arm the crossing at every level).

A bundle carries data and names of record only. Floats are rounded to four decimals.
"""

from __future__ import annotations

import json
from pathlib import Path

from .axes import logit
from .data import ArmSummary, Fit, LevelsTable, Registry, require_names
from .style import ArmStyle, family_order, legend_order, palette, styles_for

ROUND = 4
PARTIAL_COVERAGE = 0.9   # an arm with attempts on fewer than this share of the tasks is a partial model on the pages


def _r(x, nd: int = ROUND):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, nd)


def _rl(xs, nd: int = ROUND):
    return None if xs is None else [_r(x, nd) for x in xs]


def _write(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def coverage(fit: Fit, arm: str) -> dict:
    """How many of the fit's tasks the arm has attempts on."""
    row = fit.crossings.get(arm)
    n = (row.n_tasks if row and row.n_tasks else None) or len(fit.cells.get(arm) or {}) or None
    return {"tasks": n, "of": len(fit.axis)} if n and fit.axis else {}


def arm_row(arm: str, st: ArmStyle, fit: Fit, registry: Registry) -> dict:
    """One arm as the pages describe it: identity, name of record, family and look, run position, coverage, gate."""
    cov = coverage(fit, arm)
    table_row = fit.crossings.get(arm)
    row = {
        "id": arm,
        "label": st.label,
        "family": st.family or "",
        "color": st.color,
        "think": st.thinking,
        "marker": st.marker,
        "dot": st.dot,
        "dash": st.dash,
        "coverage": cov,
        "partial": bool(cov and cov["tasks"] < PARTIAL_COVERAGE * cov["of"]),
        "gates_failed": bool(table_row is not None and table_row.gate == "fail"),
    }
    if st.run:
        run = registry.run(st.run)
        row.update({"run": st.run, "step": st.step, "run_name": run.get("name_of_record") or st.run,
                    "base_model": run.get("base_model") or ""})
    return row


def run_rows(arm_rows: list[dict], registry: Registry) -> list[dict]:
    """The training runs' rows: per run its name of record, its base model's arm in the main list (checkpoint 0) and
    its positions in step order."""
    by_run: dict[str, list[dict]] = {}
    for c in arm_rows:
        if c.get("run"):
            by_run.setdefault(c["run"], []).append(c)
    by_label = {c["label"]: c["id"] for c in arm_rows if not c.get("run")}
    out = []
    for key, members in by_run.items():
        run = registry.run(key)
        base_name = run.get("base_model") or ""
        members.sort(key=lambda c: c.get("step") or 0)
        out.append({"key": key, "name": run.get("name_of_record") or key, "base_model": base_name,
                    "base_id": by_label.get(base_name), "color": members[0]["color"] if members else None,
                    "think": bool(members and members[0]["think"]),
                    "positions": [{"id": c["id"], "step": c.get("step"), "label": c["label"]} for c in members]})
    return out


def _levels_block(t: LevelsTable | None, grid: tuple[float, float]) -> dict | None:
    """A per-level crossing table in the pages' form: per level the median, the 80% interval, the kind (0 a point,
    -1 a crossing below the easiest task, 1 beyond the hardest) and whether each band end runs off the scale."""
    if t is None:
        return None
    kind, lo_open, hi_open = [], [], []
    for z, lo, hi, pl, pr in zip(t.median_z, t.lo_z, t.hi_z, t.p_left, t.p_right):
        k = -1 if (pl or 0) >= 0.5 else 1 if (pr or 0) >= 0.5 else 0
        kind.append(k)
        lo_open.append(bool(lo is not None and (lo <= grid[0] + 1e-6 or (pl or 0) > 0.1)))
        hi_open.append(bool(hi is not None and (hi >= grid[1] - 1e-6 or (pr or 0) > 0.1)))
    return {"mid": _rl(t.median_z), "lo": _rl(t.lo_z), "hi": _rl(t.hi_z), "kind": kind,
            "p_left": _rl(t.p_left), "p_right": _rl(t.p_right), "lo_open": lo_open, "hi_open": hi_open,
            "zg": [_r(grid[0]), _r(grid[1])], "rule": t.rule}


def _crossing_block(est: dict, density: list | None) -> dict:
    return {"median_z": _r(est.get("median_z")), "cri80_z": _rl(est.get("cri80_z") or [None, None]),
            "p_censored": _r((est.get("p_left_censored") or 0) + (est.get("p_right_censored") or 0)),
            "density": _rl(density, 4) if density else None}


def crossings_row(arm: str, s: ArmSummary, c: dict, grid: tuple[float, float]) -> dict:
    """One arm's crossings under both definitions, for the plane and its ridges."""
    dens = s.density or {}

    def block(definition: str, levels: LevelsTable | None, est: dict) -> dict:
        d = dens.get(definition) or {}
        return {"d50": _crossing_block(est.get("d50") or {}, d.get("d50")), "d99": _crossing_block(est.get("d99") or {}, d.get("d99")),
                "levels": _levels_block(levels, grid)}

    return {"id": arm, "label": c["label"], "family": c["family"], "think": c["think"], "run": c.get("run"), "step": c.get("step"),
            "tau": {"median": _r(s.tau.get("median")), "cri80": _rl(s.tau.get("cri80") or [None, None])},
            "average": block("average", s.levels_avg, s.estimands_avg), "median_task": block("median_task", s.levels, s.estimands)}


def plane_bundle(fit: Fit, registry: Registry, out: Path) -> dict:
    """Write the plane page's files under ``out`` and return the manifest."""
    arms = [a for a in fit.arms if fit.summary(a) is not None]
    styles = styles_for(arms, registry)
    order = legend_order(styles)
    arm_rows = [arm_row(a, styles[a], fit, registry) for a in order]
    zs = [t.z for t in fit.axis]
    grid = (min(zs), max(zs)) if zs else (-8.0, 4.0)
    rows, levels_fail, density_grid = [], None, None
    for c in arm_rows:
        s = fit.summary(c["id"])
        rows.append(crossings_row(c["id"], s, c, grid))
        if levels_fail is None and s.levels_avg is not None:
            levels_fail = _rl(s.levels_avg.levels, 5)
        if density_grid is None and s.density.get("grid"):
            density_grid = _rl(s.density["grid"])
    shared = {"set": {"key": "wave12", "label": "wave 1+2", "tasks": len(fit.axis), "models": len([c for c in arm_rows if not c.get("run")])},
              "axis": {"definition": fit.meta.get("axis") or "", "lo": _r(grid[0]), "hi": _r(grid[1])},
              "reachable": {"floor_z": _r(grid[0]), "top_z": _r(grid[1])},
              "families": family_order(), "arms": arm_rows, "runs": run_rows(arm_rows, registry)}
    crossings = {"levels_fail_rate": levels_fail or [], "density_grid": density_grid or [], "rows": rows}
    manifest = {"set": shared["set"], "fit": fit.name, "files": {"shared": "shared.json", "crossings": "crossings.json"}}
    _write(out / "shared.json", shared)
    _write(out / "crossings.json", crossings)
    _write(out / "manifest.json", manifest)
    return manifest


def curves_bundle(fit: Fit, registry: Registry, out: Path) -> dict:
    """Write the curves page's files under ``out`` and return the manifest."""
    arms = [a for a in fit.arms if fit.summary(a) is not None and fit.summary(a).average is not None]
    styles = styles_for(arms, registry)
    order = legend_order(styles)
    arm_rows = [arm_row(a, styles[a], fit, registry) for a in order]
    task_ids = [t.task_id for t in fit.axis]
    zs = [t.z for t in fit.axis]
    grid = (min(zs), max(zs)) if zs else (-8.0, 4.0)
    curves, cells, levels = {}, {}, {}
    for c in arm_rows:
        arm = c["id"]
        s = fit.summary(arm)
        row = fit.crossings.get(arm)

        def cross(cr) -> dict:
            return {"z": _r(cr.z), "lo": _r(cr.lo), "hi": _r(cr.hi), "status": cr.status, "bound_z": _r(cr.bound_z)}

        curves[arm] = {"zgrid": _rl(s.average.zgrid), "quantiles_pct": sorted(s.average.quantiles),
                       "average": [_rl(s.average.quantiles[q]) for q in sorted(s.average.quantiles)],
                       "median_task": [_rl(s.typical.quantiles[q]) for q in sorted(s.typical.quantiles)] if s.typical else None,
                       "crossings": {"d50": cross(row.d50), "d99": cross(row.d99), "d99_median_task": cross(row.d99_median_task)} if row else None,
                       "tau": {"median": _r(s.tau.get("median")), "cri80": _rl(s.tau.get("cri80") or [None, None])}}
        arm_cells = fit.cells.get(arm) or {}
        cells[arm] = {"fails": [arm_cells[t][0] if t in arm_cells else None for t in task_ids],
                      "n": [arm_cells[t][1] if t in arm_cells else None for t in task_ids]}
        levels[arm] = {"average": _levels_block(s.levels_avg, grid), "median_task": _levels_block(s.levels, grid)}
    shared = {"set": {"key": "wave12", "label": "wave 1+2", "tasks": len(task_ids), "models": len([c for c in arm_rows if not c.get("run")])},
              "axis": {"definition": fit.meta.get("axis") or "", "lo": _r(grid[0]), "hi": _r(grid[1])},
              "tasks": {"id": task_ids, "z": _rl(zs)}, "families": family_order(), "arms": arm_rows, "runs": run_rows(arm_rows, registry)}
    levels_fail = None
    for c in arm_rows:
        s = fit.summary(c["id"])
        if s.levels_avg is not None:
            levels_fail = _rl(s.levels_avg.levels, 5)
            break
    manifest = {"set": shared["set"], "fit": fit.name,
                "files": {"shared": "shared.json", "curves": "curves.json", "cells": "cells.json", "levels": "levels.json"}}
    _write(out / "shared.json", shared)
    _write(out / "curves.json", {"arms": curves})
    _write(out / "cells.json", {"arms": cells})
    _write(out / "levels.json", {"levels_fail_rate": levels_fail or [], "arms": levels})
    _write(out / "manifest.json", manifest)
    return manifest


def write_bundles(fit: Fit, registry: Registry, site_dir: Path) -> dict:
    """Both pages' bundles, under ``<site_dir>/<page>/data/``; returns the two manifests by page."""
    require_names(registry, fit.arms)
    site_dir = Path(site_dir)
    plane = plane_bundle(fit, registry, site_dir / "capability-vs-reliability" / "data")
    curves = curves_bundle(fit, registry, site_dir / "failure-vs-difficulty" / "data")
    return {"capability-vs-reliability": plane, "failure-vs-difficulty": curves}


def logit_levels(levels_fail_rate: list[float]) -> list[float]:
    return [logit(p) for p in levels_fail_rate]

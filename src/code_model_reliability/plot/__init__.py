"""The two figures and the two site pages, from the published tables.

``plane``: capability against reliability, one point per arm at (D50, D99) with its intervals, logit axes with
the line y = x at 45 degrees, legends by model family, one colour per model. ``curves``: failure rate against
difficulty per arm, the fitted curve with its band and the cells behind it, logit axes. ``export``: the one
function that writes a figure as SVG and PNG with the names of record as its labels and its file name.
``style``: the palette of record (``palette.json``) and the rules that give every arm its colour, line and mark.
``data``: the reader of the published tables. ``site_data``: the bundles the two page shells read. ``site``: builds
the two pages (the shells under ``site/`` in the repository plus the bundles) into ``docs/site/``.

Reads ``data/results/published/<fit>/`` and ``data/runs/registry/``; writes ``figures/`` and ``docs/site/``.

Command lines: ``cmr plot --data data --out figures [--fit <fit>] [--figure plane|curves|all]`` and
``cmr site --data data --out docs/site [--fit <fit>]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmr plot", description="draw the two figures from the published tables")
    parser.add_argument("--data", default="data", help="the data directory (results/published/<fit>/ and runs/registry/ under it)")
    parser.add_argument("--fit", default=None, help="the published fit to draw; the newest when not given")
    parser.add_argument("--out", default="figures", help="where the SVG and PNG exports are written")
    parser.add_argument("--figure", choices=("plane", "curves", "all"), default="all")
    args = parser.parse_args(argv)

    from .curves import draw_curves
    from .data import load_fit, load_registry
    from .plane import draw_plane

    fit = load_fit(Path(args.data), args.fit)
    registry = load_registry(Path(args.data))
    out = Path(args.out)
    if args.figure in ("plane", "all"):
        _fig, points, tr = draw_plane(fit, registry, out)
        print(f"plane: {len(points)} models drawn" + (f", trend slope {tr['slope']:.2f} over {tr['n']}" if tr else "") + f" -> {out}")
    if args.figure in ("curves", "all"):
        _fig, shown = draw_curves(fit, registry, out)
        print(f"curves: {len(shown)} models drawn -> {out}")
    return 0

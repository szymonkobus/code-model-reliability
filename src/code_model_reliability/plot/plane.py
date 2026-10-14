"""The capability-against-reliability plane: one point per arm at (D50, D99), drawn from ``crossings.csv``.

Both axes are the difficulty scale on the logit transform at one scale, so one logit unit is the same length across
and up and the line ``y = x`` runs at 45 degrees; a point on that line would fail outright as soon as a task exceeds
its capability. Each point carries its two 80% credible intervals as a cross. A crossing the fit could not place
inside the task set (a bound) is drawn at the edge of the scale, faded, and stays out of the trend. A thin trend line
is the least-squares fit of D99 on D50 over the arms whose two crossings are points and that are not positions of a
training run; its shaded band is the pointwise 80% envelope of a seeded bootstrap that resamples arms and jitters each
by its own interval width. The legend lists the arms by family.

Reads a fit and the registry (``data.py``); writes the export files through ``export.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .axes import logit_axis, style_axis
from .data import Fit, Registry, require_names
from .export import GATE_FADE, export_figure, legend_handles
from .style import ArmStyle, palette, styles_for

FIGURE = "capability-vs-reliability"
MARKER_SIZE = 7.3
INTERVAL_ALPHA = 0.75         # an interval side whose end lies inside the frame
INTERVAL_ALPHA_OFF = 0.18     # an interval side that runs off the frame, drawn faint to the edge
BOUND_ALPHA = 0.6             # a crossing at the scale's end
FRAME_PAD = 0.35              # logit units of room around the points on each side
PARTIAL_COVERAGE = 0.9        # an arm with attempts on fewer than this share of the tasks is partial and left out of the trend
BOOTSTRAP_SEED = 20260825     # the seed of the trend's bootstrap, fixed so the band is the same at every build
BOOTSTRAP_RESAMPLES = 2000    # resamples of the arms; two thousand leave a hundredth or less of Monte Carlo error on the band's edges
Z80 = 1.2816                  # half the width of an 80% interval in standard deviations under a normal approximation
TREND_GRID = 26               # points along the trend where the band is read


@dataclass
class PlanePoint:
    arm: str
    style: ArmStyle
    x: float
    y: float
    x_lo: float | None
    x_hi: float | None
    y_lo: float | None
    y_hi: float | None
    x_bound: bool
    y_bound: bool
    in_trend: bool
    gate_failed: bool = False   # the fit failed a sampler check (the table's gate column): drawn faded, kept in the trend


def plane_points(fit: Fit, registry: Registry, styles: dict[str, ArmStyle] | None = None) -> list[PlanePoint]:
    """The arms of the fit with both crossings drawable, as points with their intervals and their trend eligibility."""
    styles = styles or styles_for(fit.arms, registry)
    n_tasks_axis = len(fit.axis)
    out = []
    for arm in fit.arms:
        row = fit.crossings[arm]
        x, y = row.d50.drawn_z, row.d99.drawn_z
        if x is None or y is None or row.d50.status == "unresolved" or row.d99.status == "unresolved":
            continue
        st = styles[arm]
        partial = bool(n_tasks_axis and row.n_tasks and row.n_tasks < PARTIAL_COVERAGE * n_tasks_axis)
        in_trend = row.d50.is_point and row.d99.is_point and not st.run and not partial
        out.append(PlanePoint(arm, st, x, y, row.d50.lo, row.d50.hi, row.d99.lo, row.d99.hi,
                              row.d50.status == "bound", row.d99.status == "bound", in_trend, row.gate == "fail"))
    return out


def frame(points: list[PlanePoint]) -> tuple[tuple[float, float], tuple[float, float]]:
    """The window around the points, padded: one range per axis around the medians, both on the one scale."""
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return (min(xs) - FRAME_PAD, max(xs) + FRAME_PAD), (min(ys) - FRAME_PAD, max(ys) + FRAME_PAD)


def trend(points: list[PlanePoint]) -> dict | None:
    """The least-squares line of D99 on D50 over the trend arms, with the bootstrap's 80% band on the slope and on the
    line at a grid of positions; None when fewer than three arms enter."""
    rows = [(p.x, p.y, (abs(p.x - v) for v in (p.x_lo, p.x_hi)), (abs(p.y - v) for v in (p.y_lo, p.y_hi)))
            for p in points if p.in_trend]
    if len(rows) < 3:
        return None
    xs = np.array([r[0] for r in rows])
    ys = np.array([r[1] for r in rows])
    sx = np.array([max([h for h in r[2] if math.isfinite(h)] or [0.0]) / Z80 for r in rows])
    sy = np.array([max([h for h in r[3] if math.isfinite(h)] or [0.0]) / Z80 for r in rows])
    mx, my = xs.mean(), ys.mean()
    sxx = ((xs - mx) ** 2).sum()
    syy = ((ys - my) ** 2).sum()
    sxy = ((xs - mx) * (ys - my)).sum()
    if sxx <= 0 or syy <= 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    corr = sxy / math.sqrt(sxx * syy)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(xs)
    idx = rng.integers(0, n, size=(BOOTSTRAP_RESAMPLES, n))
    bx = xs[idx] + sx[idx] * rng.standard_normal(idx.shape)
    by = ys[idx] + sy[idx] * rng.standard_normal(idx.shape)
    bmx, bmy = bx.mean(axis=1), by.mean(axis=1)
    bsxx = ((bx - bmx[:, None]) ** 2).sum(axis=1)
    bsxy = ((bx - bmx[:, None]) * (by - bmy[:, None])).sum(axis=1)
    keep = bsxx > 1e-9
    bslope = bsxy[keep] / bsxx[keep]
    bint = bmy[keep] - bslope * bmx[keep]
    pad = 0.04 * (xs.max() - xs.min())
    gx = np.linspace(xs.min() - pad, xs.max() + pad, TREND_GRID)
    lines = np.sort(bslope[:, None] * gx[None, :] + bint[:, None], axis=0)

    def pct(sorted_values, p):
        k = len(sorted_values)
        return sorted_values[min(k - 1, max(0, round(p * (k - 1))))]

    return {"slope": float(slope), "intercept": float(intercept), "correlation": float(corr), "n": n,
            "slope_lo": float(pct(np.sort(bslope), 0.10)), "slope_hi": float(pct(np.sort(bslope), 0.90)),
            "grid": gx, "band_lo": pct(lines, 0.10), "band_hi": pct(lines, 0.90)}


def _interval(ax, lo, hi, at, mid, lim, color, vertical, fade=1.0):
    """One interval as a line through the point, each side faded where it runs off the frame."""
    for end in (lo, hi):
        if end is None or not math.isfinite(end):
            continue
        inside = lim[0] <= end <= lim[1]
        e = min(lim[1], max(lim[0], end))
        xs, ys = ((at, at), (mid, e)) if vertical else ((mid, e), (at, at))
        ax.plot(xs, ys, color=color, linewidth=1.0, alpha=(INTERVAL_ALPHA if inside else INTERVAL_ALPHA_OFF) * fade,
                solid_capstyle="butt", zorder=3)


def draw_plane(fit: Fit, registry: Registry, out_dir: Path | None = None, title: str = "Capability against reliability"):
    """Draw the plane and, when an output directory is given, export it. Returns (figure, points, trend)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pal = palette()
    require_names(registry, fit.arms)
    styles = styles_for(fit.arms, registry)
    points = plane_points(fit, registry, styles)
    if not points:
        raise ValueError("no arm of the fit has two drawable crossings")
    xlim, ylim = frame(points)
    tr = trend(points)

    fig, ax = plt.subplots(figsize=(11.8, 7.3), dpi=100)
    fig.patch.set_facecolor(pal["ground"])
    ax.set_facecolor(pal["ground"])
    style_axis(ax, pal)
    ax.set_aspect(1)
    ax.set_anchor("W")

    guide = (max(xlim[0], ylim[0]), min(xlim[1], ylim[1]))
    line, = ax.plot(guide, guide, color=pal["baseline"], linewidth=0.8, linestyle=(0, (3.3, 2.7)), zorder=1)
    line.set_gid("identity-line")

    if tr is not None:
        gx = tr["grid"]
        ax.fill_between(gx, np.clip(tr["band_lo"], *ylim), np.clip(tr["band_hi"], *ylim), color=pal["muted"],
                        alpha=0.14, linewidth=0, zorder=1.8).set_gid("trend-band")
        trend_line, = ax.plot(gx, tr["intercept"] + tr["slope"] * gx, color=pal["muted"], linewidth=0.9, zorder=2)
        trend_line.set_gid("trend-line")

    for p in points:
        st = p.style
        x = min(xlim[1], max(xlim[0], p.x))
        y = min(ylim[1], max(ylim[0], p.y))
        fade = GATE_FADE if p.gate_failed else 1.0
        _interval(ax, p.x_lo, p.x_hi, y, x, xlim, st.color, vertical=False, fade=fade)
        _interval(ax, p.y_lo, p.y_hi, x, y, ylim, st.color, vertical=True, fade=fade)
        mark, = ax.plot([x], [y], linestyle="none", marker=st.marker, markersize=MARKER_SIZE,
                        markerfacecolor=pal["ground"] if st.open else st.color,
                        markeredgecolor=st.color if st.open else pal["ground"],
                        markeredgewidth=1.2 if st.open else 1.0,
                        alpha=(BOUND_ALPHA if (p.x_bound or p.y_bound) else 1.0) * fade, zorder=4)
        mark.set_gid(f"arm:{p.arm}")
        if st.dot:
            ax.plot([x], [y], linestyle="none", marker="o", markersize=MARKER_SIZE * 0.3,
                    markerfacecolor=st.color if st.open else pal["ground"], markeredgewidth=0, alpha=fade, zorder=5)

    logit_axis(ax, "x", *xlim, fontsize=11.7)
    logit_axis(ax, "y", *ylim, fontsize=11.7)
    ax.set_xlabel("D50 — difficulty at which half the attempts fail\n(logit axis)", color=pal["secondary"], fontsize=12.8)
    ax.set_ylabel("D99 — difficulty at which one attempt in a hundred fails\n(logit axis)", color=pal["secondary"], fontsize=12.8)
    count = f"{len(points)} models · {len(fit.axis):,} tasks" if fit.axis else f"{len(points)} models"
    ax.set_title(count, color=pal["secondary"], fontsize=11, loc="left", pad=6)
    fig.suptitle(title, color=pal["ink"], fontsize=18.7, fontweight="bold", x=0.045, ha="left", y=0.995)

    shown = [p.arm for p in points]
    handles, labels = legend_handles(styles, shown, MARKER_SIZE, line=False, faded={p.arm for p in points if p.gate_failed})
    fig.tight_layout(rect=(0, 0.02, 1, 0.965))
    ax.apply_aspect()
    box = ax.get_position()
    fig.legend(handles=handles, labels=labels, loc="center", bbox_to_anchor=((box.x1 + 0.99) / 2, (box.y0 + box.y1) / 2),
               ncol=2 if len(labels) > 18 else 1, frameon=False, fontsize=9.3, labelcolor=pal["secondary"],
               handlelength=0.9, handletextpad=0.2, columnspacing=1.1, labelspacing=0.42, borderaxespad=0)

    if out_dir is not None:
        export_figure(fig, out_dir, FIGURE, labels, count=count, ground=pal["ground"])
    return fig, points, tr

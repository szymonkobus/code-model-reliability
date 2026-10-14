"""The failure-rate-against-difficulty curves: one fitted curve per arm over the task difficulty scale.

Each arm's curve is the posterior median of its fitted average failure rate at every point of the difficulty grid,
with the 80% credible band (the 10th to 90th percentile curves) shaded where the median lies inside the window. Behind
the curves sit the arm's own results per task: the failure rate on each task, kept on the logit axis by a small prior
(half a failure added to the failures and one attempt to the attempts). Both axes are logit; the dashed line ``y = x``
is where a model fails at the population's own rate, since a task's difficulty is the average arm's failure rate on it.
The legend lists the arms by family.

Reads a fit (its axis, cells and per-arm summaries) and the registry; writes the export files through ``export.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .axes import logit, logit_axis, style_axis
from .data import Fit, Registry, require_names
from .export import GATE_FADE, export_figure, legend_handles
from .style import palette, styles_for

FIGURE = "failure-vs-difficulty"
BAND = (10, 90)        # the credible band's quantiles, in percent: the 80% band of record
X_PAD = 0.4            # logit units beyond the easiest and the hardest task
# The window of failure rates shown: from half a failure to all but half a failure out of 128 attempts, the attempts
# per task the fits of record stand on, so a task with no failures or with none passing sits just inside the frame.
ATTEMPTS_OF_RECORD = 128
Y_WINDOW = (logit(0.5 / (ATTEMPTS_OF_RECORD + 1)), logit((ATTEMPTS_OF_RECORD + 0.5) / (ATTEMPTS_OF_RECORD + 1)))
DOT_ALPHA = 0.18
BAND_ALPHA = 0.08
LINE_WIDTH = 2.0
# The difficulty axis spans the whole task set, from tasks almost every arm solves to tasks almost none does, so its
# ticks are the shared vocabulary without 0.2%, which would sit on top of 0.1% at this width.
X_TICKS = [0.1, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5]


def jeffreys_logit(failures: np.ndarray, attempts: np.ndarray) -> np.ndarray:
    """The failure rate per task on the logit axis with the small prior that keeps 0 and 1 finite."""
    p = (failures + 0.5) / (attempts + 1.0)
    return np.log(p / (1 - p))


def draw_curves(fit: Fit, registry: Registry, out_dir: Path | None = None, arms: list[str] | None = None,
                title: str = "Failure rate against task difficulty"):
    """Draw the curves of every arm with a summary (or of the arms named) and, when an output directory is given,
    export the figure. Returns (figure, the arms drawn)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pal = palette()
    wanted = arms or fit.arms
    require_names(registry, list(wanted))
    drawn = [(a, s) for a, s in fit.summaries() if a in wanted and s.average is not None]
    if not drawn:
        raise ValueError("no arm of the fit has a fitted curve to draw")
    styles = styles_for([a for a, _ in drawn], registry)
    task_z = fit.task_z()
    zs = np.array([t.z for t in fit.axis], float)
    xlim = (float(zs.min()) - X_PAD, float(zs.max()) + X_PAD) if len(zs) else (-8.0, 4.0)
    ylim = (Y_WINDOW[0] - X_PAD, Y_WINDOW[1] + X_PAD)

    fig, ax = plt.subplots(figsize=(14.4, 12), dpi=100)
    fig.patch.set_facecolor(pal["ground"])
    ax.set_facecolor(pal["ground"])
    style_axis(ax, pal)
    guide = (min(xlim[0], ylim[0]), max(xlim[1], ylim[1]))
    line, = ax.plot(guide, guide, color=pal["baseline"], linewidth=1.2, linestyle=(0, (5, 4)), zorder=1)
    line.set_gid("identity-line")

    faded = {a for a, _ in drawn if fit.crossings.get(a) is not None and fit.crossings[a].gate == "fail"}
    for arm, summary in drawn:
        st = styles[arm]
        fade = GATE_FADE if arm in faded else 1.0
        cells = fit.cells.get(arm) or {}
        if cells:
            ids = [t for t in cells if t in task_z]
            if ids:
                z = np.array([task_z[t] for t in ids])
                f = np.array([cells[t][0] for t in ids], float)
                n = np.array([cells[t][1] for t in ids], float)
                ok = n > 0
                ax.scatter(z[ok], jeffreys_logit(f[ok], n[ok]), s=7, color=st.color, alpha=DOT_ALPHA * fade, linewidths=0, zorder=2)
        curve = summary.average
        zg = np.array(curve.zgrid, float)
        mid = np.array(curve.median(), float)
        lo, hi = (np.array(v, float) for v in curve.band(*BAND))
        inside = (mid > ylim[0]) & (mid < ylim[1])
        ax.fill_between(zg, np.clip(lo, ylim[0] - 1, ylim[1] + 1), np.clip(hi, ylim[0] - 1, ylim[1] + 1), where=inside,
                        color=st.color, alpha=BAND_ALPHA * fade, linewidth=0, zorder=2).set_gid(f"band:{arm}")
        ln, = ax.plot(zg, mid, color=st.color, linestyle=st.linestyle, linewidth=LINE_WIDTH, alpha=fade, zorder=3)
        ln.set_gid(f"curve:{arm}")

    logit_axis(ax, "x", *xlim, fontsize=16, vocabulary=X_TICKS)
    logit_axis(ax, "y", *ylim, fontsize=16)
    ax.set_xlabel("Task difficulty (logit axis)", color=pal["secondary"], fontsize=19.2)
    ax.set_ylabel("Failure rate (logit axis)", color=pal["secondary"], fontsize=19.2)
    count = f"{len(fit.axis):,} tasks · {len(drawn)} models"
    ax.set_title(count, color=pal["secondary"], fontsize=15, loc="left", pad=8)
    fig.suptitle(title, color=pal["ink"], fontsize=28, fontweight="bold", x=0.045, ha="left", y=0.99)

    shown = [a for a, _ in drawn]
    handles, labels = legend_handles(styles, shown, 6.0, line=True, faded=faded)
    fig.tight_layout(rect=(0, 0.02, 0.8, 0.93))
    box = ax.get_position()
    fig.legend(handles=handles, labels=labels, loc="center left", bbox_to_anchor=(box.x1 + 0.01, (box.y0 + box.y1) / 2),
               ncol=1 if len(labels) <= 40 else 2, frameon=False, fontsize=11, labelcolor=pal["secondary"],
               handlelength=1.6, handletextpad=0.5, labelspacing=0.4, borderaxespad=0)

    if out_dir is not None:
        export_figure(fig, out_dir, FIGURE, labels, count=count, ground=pal["ground"])
    return fig, shown

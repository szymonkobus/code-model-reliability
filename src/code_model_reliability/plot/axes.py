"""The logit difficulty axes every figure shares: the transform, the tick vocabulary and the axis style.

A difficulty or a failure rate is drawn on the logit scale: the position of a probability ``p`` is ``log(p / (1 - p))``.
Both axes of the capability-against-reliability plane and both axes of the failure-against-difficulty curves use it,
so equal distances mean equal odds ratios and the line ``y = x`` runs at 45 degrees when the two axes share a scale.
Ticks are labelled in percent from one vocabulary, the subset inside each axis's limits.
"""

from __future__ import annotations

import math

# The tick vocabulary, in percent: the same ticks on every logit axis, so figures read against each other.
LOGIT_TICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5]
# A finer vocabulary for a narrow window, where fewer than three of the ticks above would fall inside.
LOGIT_TICKS_FINE = [0.05, 0.07, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 60, 70, 80, 85, 90,
                    93, 95, 97, 98, 99, 99.3, 99.5, 99.7, 99.8, 99.9]


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def expit(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def pct(z: float) -> float:
    """A logit position as a percentage of the scale."""
    return 100 * expit(z)


def ticks_in(lo: float, hi: float, vocabulary: list[float] | None = None) -> list[float]:
    """The ticks (in percent) whose logit positions fall inside [lo, hi]; the finer vocabulary when fewer than three do."""
    vocab = vocabulary or LOGIT_TICKS
    inside = [v for v in vocab if lo <= logit(v / 100) <= hi]
    if len(inside) < 3 and vocabulary is None:
        inside = [v for v in LOGIT_TICKS_FINE if lo <= logit(v / 100) <= hi]
    return inside


def tick_label(v: float) -> str:
    return f"{v:g}%"


def style_axis(ax, palette: dict) -> None:
    """The house axis: a horizontal grid only, the bottom spine alone, muted tick labels, no tick marks."""
    ax.grid(axis="y", color=palette["grid"], linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(palette["baseline"])
    ax.tick_params(colors=palette["muted"], labelcolor=palette["muted"], length=0)


def logit_axis(ax, which: str, lo: float, hi: float, fontsize: float, vocabulary: list[float] | None = None) -> None:
    """Set one axis to the logit scale between two logit limits with the percent ticks inside."""
    vals = ticks_in(lo, hi, vocabulary)
    pos = [logit(v / 100) for v in vals]
    labels = [tick_label(v) for v in vals]
    if which == "x":
        ax.set_xticks(pos, labels, fontsize=fontsize)
        ax.set_xlim(lo, hi)
    else:
        ax.set_yticks(pos, labels, fontsize=fontsize)
        ax.set_ylim(lo, hi)
    ax.minorticks_off()

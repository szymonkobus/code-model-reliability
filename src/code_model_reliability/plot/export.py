"""The one export of a figure: an SVG and a PNG beside each other, named by the names of record of what they show.

An export is the figure as drawn, cropped to its axes and legend: no page title, no caption, no words about the method
or the fit's quality. Its legend lists every drawn arm by its name of record, grouped by family. Its file name carries
the figure's kind and the names of record of the arms shown (the first few, then how many more), so a file says what
it shows without being opened. The number of data points the figure stands on rides quietly on the x-axis label.

Writes ``<out_dir>/<figure>.<names>.svg`` and ``.png``; reads nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from .style import ArmStyle, legend_order

NAME_BUDGET = 150   # characters of a file name's names part: enough to read, short enough for every file system
PNG_DPI = 200


def safe_name(text: str) -> str:
    """A file-name segment: the characters a file system refuses become one dash; dashes never run or end a segment."""
    t = re.sub(r"[\\/:*?\"<>|\u0000-\u001f]+", "-", str(text))
    t = re.sub(r"-{2,}", "-", t)
    t = re.sub(r"\s*-\s*(?=[ _]|$)", "", t)
    t = re.sub(r"(^|[ _])-+", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def names_part(labels: list[str], budget: int = NAME_BUDGET) -> str:
    """The names of record joined with a middle dot while they fit the budget, then ``and N more``."""
    labels = [re.sub(r"\s+", " ", str(x)).strip() for x in labels if x]
    if not labels:
        return "no models"
    used, taken = 0, 0
    for i, lab in enumerate(labels):
        sep = 3 if taken else 0
        more = len(f" and {len(labels) - (taken + 1)} more") if len(labels) - (taken + 1) > 0 else 0
        if used + sep + len(lab) + more > budget:
            break
        used += sep + len(lab)
        taken += 1
    if taken == 0:
        return f"{len(labels)} models"
    out = " · ".join(labels[:taken])
    if len(labels) > taken:
        out += f" and {len(labels) - taken} more"
    return out


GATE_FADE = 0.55   # an arm whose fit failed a sampler check is drawn faded, on the figures as on the pages


def legend_handles(styles: dict[str, ArmStyle], shown: list[str], marker_size: float, line: bool = True, faded: set[str] | frozenset[str] = frozenset()):
    """One legend handle per shown arm, in legend order: the arm's colour, marker and line pattern as drawn, faded where
    the arm is drawn faded."""
    palette_ground = "#fcfaf3"
    handles, labels = [], []
    for arm in legend_order({a: styles[a] for a in shown}):
        st = styles[arm]
        handles.append(Line2D([], [], color=st.color, linestyle=st.linestyle if line else "none", linewidth=1.8 if line else 0,
                              marker=st.marker, markersize=marker_size,
                              markerfacecolor=palette_ground if st.open else st.color,
                              markeredgecolor=st.color, markeredgewidth=1.3 if st.open else 0.6,
                              alpha=GATE_FADE if arm in faded else 1.0))
        labels.append(st.label)
    return handles, labels


def export_figure(fig: Figure, out_dir: Path, figure: str, labels: list[str], count: str | None = None,
                  ground: str = "#fcfaf3") -> tuple[Path, Path]:
    """Write the figure as SVG and PNG, cropped to what is drawn: every title hidden for the export and restored after,
    the quiet count on the x-axis label."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hidden = []
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is not None and suptitle.get_visible():
        hidden.append(suptitle)
    hidden += [t for t in fig.texts if t.get_visible() and t is not suptitle]
    for ax in fig.axes:
        hidden += [t for t in (ax.title, getattr(ax, "_left_title", None), getattr(ax, "_right_title", None))
                   if t is not None and t.get_text() and t.get_visible()]
    for t in hidden:
        t.set_visible(False)
    relabel = []
    if count:
        for ax in fig.axes:
            if ax.get_xlabel():
                relabel.append((ax, ax.get_xlabel()))
                ax.set_xlabel(f"{ax.get_xlabel()} · {count}")
    base = out_dir / safe_name(f"{figure}.{names_part(labels)}")
    svg, png = Path(f"{base}.svg"), Path(f"{base}.png")   # appended, never a suffix swap: a name of record may carry a dot
    try:
        with matplotlib.rc_context({"svg.fonttype": "none"}):   # text stays text in the SVG, so a legend row can be read and edited
            fig.savefig(svg, facecolor=ground, bbox_inches="tight")
        fig.savefig(png, facecolor=ground, bbox_inches="tight", dpi=PNG_DPI)
    finally:
        for t in hidden:
            t.set_visible(True)
        for ax, lab in relabel:
            ax.set_xlabel(lab)
    return svg, png

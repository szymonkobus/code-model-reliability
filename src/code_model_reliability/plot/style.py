"""The look of every arm on every figure and page: one colour per model, families by hue, the marks of the training runs.

Reads ``palette.json`` beside this module (the hues, ladders, pins and ramps of record) and the registry (the family
and rank of each model, the names of the training runs). Writes nothing.

The rules, in the order they are applied to an arm:

1. Its family is the model row's family (``models.jsonl``), else the first family whose pattern matches the model id.
2. Its colour is the family hue (hue and saturation kept) at a lightness rung: a pinned rung where the palette pins the
   model; a position of a training run takes its run's ramp at its step (checkpoint 0 the start rung); every other
   model takes its place on the family's ladder by its rank among the family's ranked models, or on the default
   ladder from ``top`` to ``bottom`` when the family has no ladder of its own.
3. A thinking model draws dashed with an open marker; a fine-tune dotted; a reinforcement-learning run long-dash-dot-dot;
   everything else solid with a filled circle. A training run's marker shape names the failure count the run trains on
   and a small central dot every other minor fact, both read from the run's name of record (see ``run_marks``).
4. Legends list the arms by family in the palette's order, inside a family from the lightest rung to the darkest, a
   thinking variant right after its plain model.
"""

from __future__ import annotations

import colorsys
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .data import Registry

PALETTE_PATH = Path(__file__).with_name("palette.json")
_PALETTE: dict | None = None


def palette() -> dict:
    """The palette of record, read once."""
    global _PALETTE
    if _PALETTE is None:
        _PALETTE = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    return _PALETTE


def family_order() -> list[str]:
    return list(palette()["families"])


def hex_to_hls(color: str) -> tuple[float, float, float]:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def shade(hue_color: str, lightness: float) -> str:
    """The family hue at a lightness rung: the hue's hue and saturation, the rung's lightness."""
    h, _l, s = hex_to_hls(hue_color)
    r, g, b = colorsys.hls_to_rgb(h, lightness, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def family_of(model_id: str, model_row: dict | None = None) -> str | None:
    """The family of a model: its registry row's family (an alias resolved to the palette's key), else the first
    palette family whose pattern matches the id; None when nothing matches."""
    fams = palette()["families"]
    name = str((model_row or {}).get("family") or "")
    if name:
        if name in fams:
            return name
        for key, spec in fams.items():
            if name in (spec.get("aliases") or []):
                return key
    for key, spec in fams.items():
        if spec.get("match") and re.search(spec["match"], model_id, re.I):
            return key
    return None


def is_thinking(arm_row: dict, model_row: dict | None = None) -> bool:
    form = str(arm_row.get("form") or "").lower()
    if form:
        return form == "thinking"
    return str((model_row or {}).get("mode") or "").lower() == "thinking"


@dataclass
class RunMarks:
    """The marks a training run's name of record carries (the name follows one pattern: the base model, what was done
    and the task set by the failure count it trains on, the variant words, the step)."""

    band: str | None
    shape: str
    dot: bool
    variants: list[str]
    treatment: str
    thinking: bool
    steps: int | None
    teacher: str | None = None

    @property
    def marker(self) -> str:
        """The matplotlib marker letter of the shape."""
        return {"circle": "o", "square": "s", "triangle": "^", "diamond": "D"}[self.shape]


_DASH = "[–—-]"
_BANDS = [
    ("fails 1–2/8", re.compile(r"fails?\s*1\s*" + _DASH + r"\s*2\s*(?:/|of)\s*8\b", re.I), "circle"),
    ("fails 3–5/8", re.compile(r"fails?\s*3\s*" + _DASH + r"\s*5\s*(?:/|of)\s*8\b", re.I), "square"),
    ("fails 6–7/8", re.compile(r"fails?\s*6\s*" + _DASH + r"\s*7\s*(?:/|of)\s*8\b", re.I), "triangle"),
    # a failure count outside the four shapes takes the nearest shape, with the dot
    ("fails 1–3/32", re.compile(r"fails?\s*1\s*" + _DASH + r"\s*3\s*(?:/|of)\s*32\b", re.I), "circle"),
    ("fails 1–7/8", re.compile(r"solves sometimes|fails?\s*1\s*" + _DASH + r"\s*7\s*(?:/|of)\s*8\b", re.I), "diamond"),
    # "all tasks" is the training set only in its own forms; "drawn from all tasks" names the pool a set was drawn from
    ("all tasks", re.compile(r"(?:^|\bon\s+|,\s*|·\s*)all tasks\b", re.I), "diamond"),
]
_VARIANTS = [
    ("fixed", re.compile(r"\bfixed(?:\s+set)?\b", re.I)),
    ("0 redraws", re.compile(r"\b(?:0|zero|no)\s+re-?draws?\b", re.I)),
    ("1 redraw", re.compile(r"\b(?:1|one)\s+re-?draws?\b", re.I)),
    ("2 redraws", re.compile(r"\b(?:2|two)\s+re-?draws?\b", re.I)),
    ("*", re.compile(r"re-?drawn\s+every\s+(?!25\b)\d+(?:\s+steps?)?", re.I)),
    ("*", re.compile(r"\bdrawn from [^,·(]+", re.I)),
    ("*", re.compile(r"\b(?:[A-Za-z][\w-]*\s+)?penalty(?:\s+×\s?\d+)?\b", re.I)),
    ("32 answers", re.compile(r"(?:/|of)\s*32\b", re.I)),
    ("the tasks it solves sometimes", re.compile(r"solves sometimes|fails?\s*1\s*" + _DASH + r"\s*7\s*(?:/|of)\s*8\b", re.I)),
    ("a teacher's answers", re.compile(r"passing answers|teacher", re.I)),
    ("fine-tune", re.compile(r"fine-?tune|\bsft\b", re.I)),
    ("colder sampling", re.compile(r"colder\s+sampling|\btemperature\s+0\.[0-5]\b", re.I)),
]
_STEP_TAIL = re.compile(r"\s*\((?:step|checkpoint)?\s*\d+\s*steps?\)\s*$", re.I)


def run_marks(name: str) -> RunMarks | None:
    """The marks encoded in a training run's name of record, or None when the name is not a run's (a released model).

    The shape is the failure count the run trains on (circle: fails 1–2 of 8; square: 3–5 of 8; triangle: 6–7 of 8;
    diamond: all tasks; a count outside these takes the nearest shape with the dot). The dot stands for any departure
    from the plain recipe: another re-draw cadence or a fixed set, a penalty, a teacher's answers, a count outside the
    four shapes. The treatment (reinforcement learning or a fine-tune) sets the line's pattern."""
    s = re.sub(r"\s+", " ", re.sub("[⁠​﻿]", "", str(name or "")))
    band = shape = None
    for b, rx, sh in _BANDS:
        if rx.search(s):
            band, shape = b, sh
            break
    variants: list[str] = []
    for v, rx in _VARIANTS:
        m = rx.search(s)
        if m:
            variants.append(re.sub(r"\s+", " ", m.group(0)).strip() if v == "*" else v)
    cell_parts = s.split("·")
    if len(cell_parts) >= 2:
        for p in (_STEP_TAIL.sub("", x.strip()).strip() for x in re.split(r",\s*", cell_parts[1])):
            if (not p or len(p) > 40 or re.match(r"^(?:RL|fine-?tune|sft)$", p, re.I) or re.match(r"^\d+\s+steps?$", p, re.I)
                    or re.match(r"^\(?(?:step|checkpoint)\s*\d+\)?$", p, re.I) or re.match(r"^re-?drawn\s+every\s+25(?:\s+steps?)?$", p, re.I)):
                continue
            if any(rx.search(p) for _, rx, _ in _BANDS) or any(rx.search(p) for _, rx in _VARIANTS):
                continue
            if p not in variants:
                variants.append(p)
    if band is None and not variants and not re.search(r"\bRL\b", s):
        return None
    m = re.search(r"(\d+)\s+steps?\b", s)
    tm = (re.search(r"·\s*fine-?tune[^·]*?,\s*([^·,]+?)(?:(?:'|’)s)?\s+passing answers", s, re.I)
          or re.search(r"([A-Z][\w.-]*(?:\s+[\w.-]+){0,3}?)(?:(?:'|’)s)?\s+passing answers", s))
    teacher = tm.group(1).strip() if tm else None
    if not teacher and re.search(r"fine-?tune", s, re.I) and len(cell_parts) >= 2:
        for fw in [_STEP_TAIL.sub("", x.strip()).strip() for x in re.split(r",\s*", cell_parts[1])][1:]:
            if not fw or any(rx.search(fw) for _, rx, _ in _BANDS) or re.search(r"penalty|re-?draw|re-?drawn|fixed|held|all tasks", fw, re.I):
                continue
            if re.match(r"^[A-Z][\w.-]*(?:\s+[\w.-]+){0,3}$", fw) and re.search(r"\d", fw):
                teacher = fw
                break
    return RunMarks(band=band, shape=shape or "circle", dot=bool(variants), variants=variants,
                    treatment="fine-tune" if re.search(r"fine-?tune|\bsft\b|passing answers", s, re.I) else "RL",
                    thinking=bool(re.search(r"\(thinking\)|\bthinking\b", s, re.I)), steps=int(m.group(1)) if m else None,
                    teacher=teacher)


@dataclass
class ArmStyle:
    """How one arm is drawn: its colour, line pattern, marker and label, and the keys the legend sorts by."""

    arm: str
    label: str
    family: str | None
    color: str
    lightness: float
    dash: list[int] | None
    open: bool
    marker: str
    dot: bool
    thinking: bool
    run: str | None = None
    step: int | None = None
    rank: float = 0.0
    marks: RunMarks | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def linestyle(self):
        """The matplotlib line style of the dash pattern."""
        return (0, tuple(self.dash)) if self.dash else "-"


def _run_model_ids(registry: Registry) -> set[str]:
    """The model ids of the positions of the training runs named in ``names.json``: checkpoints take their run's ramp,
    never a rung of the family's ladder."""
    ids = set()
    for run in (registry.names.get("runs") or {}).values():
        for pos in run.get("positions") or []:
            arm = str(pos.get("arm") or pos.get("arm_id") or "")
            mid = registry.arm(arm).get("model_id") if arm else None
            if mid:
                ids.add(str(mid))
    return ids


def _is_variant(name: str) -> bool:
    """A name of record with a middle dot names a base model and what was done to it (``Qwen3 8B · code fine-tune``):
    a variant, drawn in its base model's colour with its treatment's line pattern. A released model's name has none."""
    return " · " in name


def _base_label(label: str) -> str:
    """The base model a label names: the part before the middle dot, without the thinking form's suffix."""
    return re.sub(r"\s*\(thinking\)\s*$", "", label.split(" · ")[0].strip())


def _family_ranks(registry: Registry, family: str) -> tuple[list[float], str]:
    """The family's ladder key and the sorted keys of its models in the registry: a model's place among them is its
    rung. The key is ``rank`` where any model of the family carries one (the two forms of one model share a rank, so
    they share a rung), else ``total_params_b``. A pinned model, a position of a training run and a variant never
    enter the count."""
    pins = palette().get("pinned") or {}
    run_ids = _run_model_ids(registry)
    rows = [(mid, row) for mid, row in registry.models.items()
            if family_of(mid, row) == family and mid not in pins and mid not in run_ids and not _is_variant(str(row.get("name") or ""))]
    key = "rank" if any(row.get("rank") is not None for _, row in rows) else "total_params_b"
    ranks = {float(row[key]) for _, row in rows if row.get(key) is not None}
    return sorted(ranks), key


def _ladder_light(family: str, ranks: list[float], rank: float | None, notes: list[str]) -> float:
    spec = palette()["families"].get(family) or {}
    ladder = spec.get("ladder")
    default = palette()["default_ladder"]
    if rank is None or rank not in ranks:
        notes.append("no rank in the registry: drawn at the ladder's end")
        place = len(ranks)
        ranks = ranks + [rank if rank is not None else float("inf")]
    else:
        place = ranks.index(rank)
    if ladder and place < len(ladder):
        return float(ladder[place])
    if ladder:
        notes.append("past the family's ladder: drawn at its darkest rung")
        return float(ladder[-1])
    if len(ranks) <= 1:
        return float(default["single"])
    return default["top"] - (default["top"] - default["bottom"]) * place / (len(ranks) - 1)


def _ramp_light(ramp_spec: dict, step: int, notes: list[str]) -> float:
    if step == 0 and ramp_spec.get("start_light") is not None:
        return float(ramp_spec["start_light"])
    lights = ramp_spec.get("lights") or {}
    if str(step) in lights:
        return float(lights[str(step)])
    r = ramp_spec.get("ramp")
    if r and r["first"] <= step <= r["last"]:
        return r["L0"] + (r["L1"] - r["L0"]) * (step - r["first"]) / (r["last"] - r["first"])
    notes.append(f"step {step} is outside the run's ramp: drawn at its darkest rung")
    if r:
        return float(r["L1"])
    return float(min(lights.values())) if lights else 0.3


def _series_spec(run: dict, base_model_id: str | None) -> dict | None:
    """The palette's ramp for a training run: by the run's base model id, else by a key the run's key starts with."""
    ramps = {k: v for k, v in (palette().get("series_ramps") or {}).items() if isinstance(v, dict) and k != "about"}
    for spec in ramps.values():
        if base_model_id and spec.get("base") == base_model_id:
            return spec
    key = str(run.get("key") or "")
    for k, spec in ramps.items():
        if key.startswith(k):
            return spec
    return None


def arm_style(arm: str, registry: Registry, family_ranks: dict[str, tuple[list[float], str]] | None = None) -> ArmStyle:
    """The style of one arm from the registry and the palette."""
    row = registry.arm(arm)
    model_id = str(row.get("model_id") or arm)
    model_row = registry.model(arm)
    label = registry.model_name(arm)
    thinking = is_thinking(row, model_row)
    notes: list[str] = []
    position = registry.run_position(arm)
    fam = family_of(model_id, model_row)
    hue = None
    dash = None
    marker, dot, marks = "o", False, None
    run_key, step = None, None
    if position:
        run_key, step = position
        run = dict(registry.run(run_key))
        run["key"] = run_key
        base_id = str(run.get("base_model_id") or registry.model_id_by_name(str(run.get("base_model") or "")) or "")
        base_row = registry.models.get(base_id) or {}
        fam = family_of(base_id, base_row) or fam
        spec = _series_spec(run, base_id or None)
        if spec:
            hue = spec.get("hue")
            light = _ramp_light(spec, step, notes)
        else:
            notes.append("no ramp for this run in the palette: drawn at the family's darkest rung")
            light = (palette()["families"].get(fam or "") or {}).get("ladder", [0.3])[-1]
        marks = run_marks(label)
        if step and marks:
            marker, dot = marks.marker, marks.dot
            dash = palette()["lines"]["fine_tune" if marks.treatment == "fine-tune" else "rl"]
    else:
        pins = palette().get("pinned") or {}
        placed_id, placed_row = model_id, model_row
        base_id = registry.model_id_by_name(_base_label(label)) if _is_variant(label) else None
        if base_id:
            placed_id, placed_row = base_id, registry.models.get(base_id) or {}
            notes.append(f"a variant of {placed_row.get('name')}: its colour, the treatment's line pattern")
            marks = run_marks(label)
            if marks:
                marker, dot = marks.marker, marks.dot
                dash = palette()["lines"]["fine_tune" if marks.treatment == "fine-tune" else "rl"]
        if placed_id in pins:
            light = float(pins[placed_id])
        else:
            ladder = (family_ranks or {}).get(fam or "") if family_ranks else None
            if ladder is None:
                ladder = _family_ranks(registry, fam) if fam else ([], "rank")
            ranks, key = ladder
            r = placed_row.get(key)
            light = _ladder_light(fam, ranks, float(r) if r is not None else None, notes) if fam else palette()["default_ladder"]["single"]
    if fam is None:
        notes.append("no family in the palette: drawn in the muted grey")
        color = palette()["muted"]
    else:
        color = shade(hue or palette()["families"][fam]["hue"], light)
    if thinking and dash is None:
        dash = palette()["lines"]["thinking"]
    rank_key = float(model_row.get("rank") or model_row.get("total_params_b") or 0)
    return ArmStyle(arm=arm, label=label, family=fam, color=color, lightness=light, dash=dash, open=thinking,
                    marker=marker, dot=dot, thinking=thinking, run=run_key, step=step, rank=rank_key, marks=marks, notes=notes)


def require_colours(styles: dict[str, ArmStyle]) -> None:
    """Refuse a set of arms the palette cannot give one colour per model: two models of one family on the same rung.
    A model, its thinking form and its variants share a colour by design (the form is the name of record's
    ``(thinking)``, a variant the part after the middle dot), and the positions of one training run share a hue and
    differ by lightness; any other collision means the registry gives the family's models no rank and no size to place
    them on the ladder, and the figures and the pages are not drawn until it does."""
    by_colour: dict[tuple[str, str], set[str]] = {}
    for st in styles.values():
        if st.family is None or st.run:
            continue
        by_colour.setdefault((st.family, st.color), set()).add(_base_label(st.label))
    clashes = [(fam, colour, sorted(bases)) for (fam, colour), bases in by_colour.items() if len(bases) > 1]
    if clashes:
        lines = [f"{fam}: {len(bases)} models share the colour {colour} ({', '.join(bases)})" for fam, colour, bases in clashes]
        raise ValueError("the palette cannot give one colour per model, because the registry gives these models no rank and no "
                         "size to place them on their family's ladder: " + "; ".join(lines))



def styles_for(arms: list[str], registry: Registry) -> dict[str, ArmStyle]:
    """The styles of many arms; the family ladders are counted once."""
    fams = {family_of(str(registry.arm(a).get("model_id") or a), registry.model(a)) for a in arms}
    ranks = {f: _family_ranks(registry, f) for f in fams if f}
    out = {a: arm_style(a, registry, ranks) for a in arms}
    require_colours(out)
    return out


def legend_order(styles: dict[str, ArmStyle]) -> list[str]:
    """Arms by family in the palette's order, then from the lightest rung to the darkest (a run's positions by step),
    a thinking variant right after its plain model; never by a measured value."""
    order = family_order()

    def key(arm: str):
        s = styles[arm]
        fam_i = order.index(s.family) if s.family in order else len(order)
        base_label = re.sub(r"\s*\(thinking\)", "", s.label)
        return (fam_i, s.run or "", -round(s.lightness, 4) if not s.run else (s.step or 0), base_label, 1 if s.thinking else 0, s.label)

    return sorted(styles, key=key)

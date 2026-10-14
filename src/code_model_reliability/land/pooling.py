"""How the judgings of one cell compose into its served figure: validity, draws, the winner per draw, the pool.

The wave 2 tasks were judged many times while the project ran: whole legs again as the judge's settings moved,
single tasks again after a setting change, the same generation on two clusters. A cell's figure is composed from
those judging rows by the rules in ``data/runs/pooling_rules.json``, which this module implements:

- a **judging row** is one judging of one shard's attempts on one task: its attempts and passes, the judge stamp
  it was judged under (the settings string and the knobs), its emission time and the identity of the attempts it
  judged (a hash over the judged programs);
- a row is **valid** only when its stamp is one of the stamps of record and no exclusion names it (a voided or
  retracted judging, a judging inside a known defect window, a held draw, a stale identity, a retired task);
- a **draw** is one generation of attempts, identified by (shard, source, identity hash); a copy of a generation
  carried to another cluster keeps its identity, a second generation under the same shard name is another draw;
- among a draw's valid rows the **winner** is the highest by the walk key: the grade (the number of grader
  corrections the stamp carries that apply to the task), the memory tier, not being more lenient than the current
  comparison rule, the task-scoped currencies (the leading-imports rule's version, the plus-input filter), the
  extractor's rank, fewer evaluator workers, the judging time, the emission time;
- the cell **pools** its distinct valid draws: attempts and passes are summed, each draw under its own winner; a
  cell whose draws carry different stamps is marked, never held;
- an attempt whose winning status is a set-cap time-out counts as a pass when another valid judging of the same
  draw passed the same program (the **time-out override**); a failure never flips;
- when a draw's winning row is held, the next valid row of the same stamp stands in; a draw with none is set
  aside and the cell serves on its remaining draws; a cell with no valid draw left has no figure.

Reads judging rows (``judgings.jsonl`` per arm, the shape in ``row_from_dict``) and the rules file; writes nothing
(``cells`` writes the composed cells).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from typing import Any, Iterable

DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "runs"
RULES_FILE = DATA_DIR / "pooling_rules.json"

# The leading-imports rule's versions, oldest to newest; a row under a newer version outranks one under an older
# version on a task whose prompt carries leading imports.
PREAMBLE_LINEAGE = (
    "none",
    "leading-imports-v1",
    "leading-imports-v2-builtins-restored",
    "leading-imports-v3-echo-neutral",
    "leading-imports-v4-module-names-bound",
    "leading-imports-v4.1-self-shadowing-refined",
)
# Comparison rules by strictness, strictest first; a row judged under a more lenient rule than the current one
# loses the draw to a row judged under the current rule, whatever its time.
COMPARE_STRICTNESS = {"exact": 0, "normalized-v1": 1, "numeric-tolerant-v2": 2}
STDOUT_STRICTNESS = {"exact": 0, "v2-symmetric": 1, "v2-symmetric-r2": 1}
CURRENT_COMPARE = "numeric-tolerant-v2"
CURRENT_STDOUT = "v2-symmetric"
EXTRACTOR_RANK = ("v1", "x2", "x3")
# Grader corrections a stamp can carry; a universal one applies on every task, a set-bound one on the tasks of its set.
UNIVERSAL_CORRECTIONS = ("extractor=x2", "task_timeout=300")
SET_BOUND_CORRECTIONS = {
    "preamble=imports": "import_bearing",
    "inputs=typed": "typed_inputs",
    "plus=bool-filtered": "plus_filtered",
    "task_timeout=sum-limits": "canonical_floor",
    "typing_fix=v1": "typing_carrier",
}
IMPLIES = {"extractor=x3": ("extractor=x2",), "task_timeout=sum-limits": ("task_timeout=300",)}
TIER_NAMES = {4: "pinned 8 GiB", 3: "pinned 4 GiB", 2: "unpinned cluster route", 1: "unpinned box route"}
_EXTRACTOR_TOKEN = re.compile(r"extractor=([A-Za-z0-9]+)")
_CAP_TOKEN = re.compile(r"task_timeout=(\d+)")


@dataclasses.dataclass
class JudgingRow:
    """One judging of one shard's attempts on one task."""

    arm: str
    task_id: str
    shard: str
    source: str              # where the attempts were generated and judged: runs (a cluster's own tree), copy (a copy carried to the other cluster), box
    identity: str            # the hash over the judged programs; the draw's identity
    stamp: str               # the judge settings string
    knobs: dict              # the judge's recorded settings (compare, stdout_compare, extractor, parallel, memory, ...)
    emitted: str             # the emission time, sortable text
    attempts: int
    base_passes: int
    plus_passes: int
    judged_at: str = ""      # the judging time when stamped apart from the emission (an alias judging), else the emission
    valid: bool = True
    invalid_reason: str | None = None
    held: bool = False
    row_id: str = ""
    time_out_shas: tuple = ()   # programs whose winning plus status is a set-cap time-out (for the override)
    pass_shas: tuple = ()       # programs this judging passed (as a witness for the override)

    @property
    def draw(self) -> tuple[str, str, str]:
        return (self.shard, self.source, self.identity)


def row_from_dict(d: dict[str, Any]) -> JudgingRow:
    return JudgingRow(
        arm=d["arm"], task_id=d["task_id"], shard=d.get("shard", ""), source=d.get("source", "runs"),
        identity=d.get("identity", ""), stamp=d.get("stamp", ""), knobs=d.get("knobs") or {}, emitted=str(d.get("emitted", "")),
        attempts=int(d["attempts"]), base_passes=int(d.get("base_passes", 0)), plus_passes=int(d.get("plus_passes", 0)),
        judged_at=str(d.get("judged_at") or d.get("emitted", "")), valid=bool(d.get("valid", True)),
        invalid_reason=d.get("invalid_reason"), held=bool(d.get("held", False)), row_id=d.get("row_id", ""),
        time_out_shas=tuple(d.get("time_out_shas") or ()), pass_shas=tuple(d.get("pass_shas") or ()),
    )


def read_rows(path: str | pathlib.Path) -> list[JudgingRow]:
    with open(path, encoding="utf-8") as fh:
        return [row_from_dict(json.loads(line)) for line in fh if line.strip()]


class PoolingRules:
    """The rules file: the stamps of record, the task sets the set-bound corrections apply to, the current values."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.stamps = set(data.get("stamps_of_record") or [])
        sets = data.get("task_sets") or {}
        self.task_sets = {k: set(v) for k, v in sets.items()}
        self.task_limits = data.get("task_effective_limits") or {}
        cap = data.get("default_set_cap_s", None)
        self.default_limit = int(cap) if cap is not None else None  # None: the summed limits alone, no cap to be lenient against

    @classmethod
    def load(cls, path: str | pathlib.Path | None = None) -> "PoolingRules":
        p = pathlib.Path(path) if path else RULES_FILE
        if not p.exists():
            return cls({})
        with open(p, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def in_set(self, name: str, task_id: str) -> bool:
        tasks = self.task_sets.get(name)
        if tasks is None:
            return True  # a set the file does not carry applies everywhere, the fail-closed reading
        parent = re.sub(r"~.*$", "", task_id)
        return task_id in tasks or parent in tasks


def stamp_is_of_record(stamp: str, rules: PoolingRules) -> bool:
    """Exact membership: an unlisted stamp is invalid, never matched by a pattern."""
    return (not rules.stamps) or stamp in rules.stamps


def tokens(stamp: str) -> set[str]:
    return {t.strip() for t in stamp.split(";") if t.strip()}


def grade(row: JudgingRow, rules: PoolingRules) -> int:
    """The number of grader corrections the stamp carries that apply to the task."""
    present = set(tokens(row.stamp))
    for tag, implied in IMPLIES.items():
        if tag in present:
            present.update(implied)
    g = sum(1 for tag in UNIVERSAL_CORRECTIONS if tag in present)
    for tag, set_name in SET_BOUND_CORRECTIONS.items():
        if tag in present and rules.in_set(set_name, row.task_id):
            g += 1
    return g


def tier(row: JudgingRow) -> int:
    """The memory tier: the record's pinned budget first, the route otherwise."""
    budget = row.knobs.get("child_mem_budget_gib")
    if row.stamp.startswith("min_time_limit=15;mem=8GiB") or budget == 8:
        return 4
    if row.knobs.get("mem_pin") and budget == 4:
        return 3
    if row.source == "box" or "box" in str(row.knobs.get("route") or ""):
        return 1
    return 2


def more_lenient_than_current(row: JudgingRow, rules: PoolingRules) -> bool:
    """Whether the row was judged under a comparison or cap more lenient than the current value, so that its
    passes might not hold under the current grading."""
    compare = row.knobs.get("compare") or "normalized-v1"
    if compare not in COMPARE_STRICTNESS or COMPARE_STRICTNESS[compare] > COMPARE_STRICTNESS[CURRENT_COMPARE]:
        return compare not in COMPARE_STRICTNESS
    stdout = row.knobs.get("stdout_compare") or "exact"
    if stdout not in STDOUT_STRICTNESS or STDOUT_STRICTNESS[stdout] > STDOUT_STRICTNESS[CURRENT_STDOUT]:
        return stdout not in STDOUT_STRICTNESS
    cap = row.knobs.get("task_timeout_s")
    if cap is None:
        m = _CAP_TOKEN.search(row.stamp)
        cap = int(m.group(1)) if m else None
    if cap is not None:
        current = rules.task_limits.get(row.task_id, rules.default_limit)
        if current is None:
            return False  # the task's limit is its summed limits; a cap below them is stricter, never lenient
        return int(cap) > int(current)
    return False


def scoped_currencies(row: JudgingRow, rules: PoolingRules) -> tuple[int, int]:
    """(the leading-imports rule's rank on an import-bearing task, the plus filter's presence on a filtered task);
    zero where the task is outside the set."""
    preamble_rank = 0
    if rules.in_set("import_bearing", row.task_id):
        value = str(row.knobs.get("preamble_rule") or "none")
        preamble_rank = PREAMBLE_LINEAGE.index(value) if value in PREAMBLE_LINEAGE else 0
    filter_rank = 0
    if rules.in_set("plus_filtered", row.task_id):
        filter_rank = 1 if (row.knobs.get("plus_filter") or "plus=bool-filtered" in row.stamp) else 0
    return preamble_rank, filter_rank


def extractor_rank(row: JudgingRow) -> int:
    value = row.knobs.get("extractor")
    if not value:
        m = _EXTRACTOR_TOKEN.search(row.stamp)
        value = m.group(1) if m else "v1"
    return EXTRACTOR_RANK.index(value) if value in EXTRACTOR_RANK else -1


def walk_key(row: JudgingRow, rules: PoolingRules) -> tuple:
    """The draw-winner key; the higher tuple wins."""
    try:
        parallel = int(row.knobs.get("parallel")) if row.knobs.get("parallel") is not None else 99
    except (TypeError, ValueError):
        parallel = 99
    return (
        grade(row, rules),
        tier(row),
        0 if more_lenient_than_current(row, rules) else 1,
        scoped_currencies(row, rules),
        extractor_rank(row),
        -parallel,
        row.judged_at or row.emitted,
        row.emitted,
    )


def valid_rows(rows: Iterable[JudgingRow], rules: PoolingRules) -> tuple[list[JudgingRow], dict[str, int]]:
    """The rows that may compete, and the count of the rest by reason."""
    kept, why = [], {}
    for r in rows:
        reason = None
        if not r.valid:
            reason = r.invalid_reason or "excluded"
        elif not stamp_is_of_record(r.stamp, rules):
            reason = "stamp not of record"
        if reason:
            why[reason] = why.get(reason, 0) + 1
        else:
            kept.append(r)
    return kept, why


@dataclasses.dataclass
class DrawResult:
    draw: tuple[str, str, str]
    winner: JudgingRow | None
    held_rows: int
    same_stamp_stand_in: bool
    overrides: int


def winner_of_draw(rows: list[JudgingRow], rules: PoolingRules) -> DrawResult:
    """The winning row of one draw, with the held-winner composition and the time-out override applied."""
    ranked = sorted(rows, key=lambda r: walk_key(r, rules))
    top = ranked[-1]
    stand_in = False
    if top.held:
        same_stamp = [r for r in ranked if not r.held and r.stamp and r.stamp == top.stamp]
        if not same_stamp:
            return DrawResult(top.draw, None, sum(1 for r in rows if r.held), False, 0)
        top = same_stamp[-1]
        stand_in = True
    overrides = 0
    if top.time_out_shas:
        witnesses = set()
        for r in rows:
            if r is not top and not r.held:
                witnesses.update(r.pass_shas)
        overrides = sum(1 for sha in top.time_out_shas if sha in witnesses)
    winner = dataclasses.replace(top, plus_passes=top.plus_passes + overrides) if overrides else top
    return DrawResult(top.draw, winner, sum(1 for r in rows if r.held), stand_in, overrides)


@dataclasses.dataclass
class Cell:
    arm: str
    task_id: str
    attempts: int
    base_passes: int
    plus_passes: int
    draws: int
    stamps: list[str]
    overrides: int
    draws_set_aside: int
    excluded_rows: dict[str, int]

    @property
    def failures(self) -> int:
        return self.attempts - self.plus_passes

    @property
    def mixed_stamps(self) -> bool:
        return len(self.stamps) > 1


def compose_cell(arm: str, task_id: str, rows: Iterable[JudgingRow], rules: PoolingRules | None = None) -> Cell | None:
    """The composed cell of one arm and task, or ``None`` when no valid draw is left."""
    rules = rules or PoolingRules.load()
    rows = [r for r in rows if r.arm == arm and r.task_id == task_id]
    kept, excluded = valid_rows(rows, rules)
    by_draw: dict[tuple[str, str, str], list[JudgingRow]] = {}
    for r in kept:
        by_draw.setdefault(r.draw, []).append(r)
    attempts = base = plus = draws = overrides = set_aside = 0
    stamps: set[str] = set()
    for draw_rows in by_draw.values():
        result = winner_of_draw(draw_rows, rules)
        if result.winner is None:
            set_aside += 1
            continue
        w = result.winner
        attempts += w.attempts
        base += w.base_passes
        plus += w.plus_passes
        draws += 1
        overrides += result.overrides
        stamps.add(w.stamp)
    if draws == 0:
        return None
    return Cell(arm, task_id, attempts, base, plus, draws, sorted(stamps), overrides, set_aside, excluded)


def compose(rows: Iterable[JudgingRow], rules: PoolingRules | None = None) -> list[Cell]:
    """Every cell of a rows file."""
    rules = rules or PoolingRules.load()
    rows = list(rows)
    keys = sorted({(r.arm, r.task_id) for r in rows})
    out = []
    for arm, task_id in keys:
        cell = compose_cell(arm, task_id, rows, rules)
        if cell is not None:
            out.append(cell)
    return out


def cells_rows(cells: Iterable[Cell], judging_label: str = "pooled") -> list[dict[str, Any]]:
    """The composed cells in ``cells.csv``'s shape; the judging column names the pooled stamps when they differ."""
    return [{
        "arm": c.arm,
        "task_id": c.task_id,
        "failures": c.failures,
        "attempts": c.attempts,
        "time_limit_fails": 0,
        "judging": c.stamps[0] if len(c.stamps) == 1 else judging_label + ":" + "|".join(c.stamps),
    } for c in cells]

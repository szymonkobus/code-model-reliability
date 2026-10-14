"""The tasks a judging runs over, in the harness's problem shape, with the input rules applied.

A problem is a dict with the harness's fields: ``task_id``, ``prompt``, ``entry_point``, ``canonical_solution``,
``base_input``, ``plus_input`` (lists of argument lists) and ``atol``; this module adds ``stdin_stdout`` (whether
the task is a program reading its input text and returning its output text) and ``kind`` (the harness's dataset
kind: ``mbpp`` for the tasks with its special oracles, ``humaneval`` for every other function task).

Reads a task file in the data contract's shape (``.jsonl`` or ``.jsonl.gz``), or one of the harness's own two
sets by name (``humaneval``, ``mbpp``, the tokens the generate command takes; the harness downloads them to its
cache on first use). Two
input rules read task facts: the plus inputs removed from a task because they carry a boolean where every base
example carries an integer (the record's ``plus_inputs_removed``; for the harness's own sets, which have no
records of ours, ``data/tasks/wave-1/plus_inputs_removed.json`` by task id), and the declared shape of each
argument of a written task (the record's ``input_shapes``; the harness's typed tasks and their copies follow the
harness's own rule). A record without the fields keeps its inputs as written. Writes nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import pathlib
import re
from typing import Any, Iterable

from evalplus.data import get_human_eval_plus, get_mbpp_plus
from evalplus.data.mbpp import mbpp_deserialize_inputs

from .settings import JudgingSettings

DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
# The wave 1 tasks' removed plus inputs, by task id (the tasks export writes it beside the task sets); the written
# copies carry theirs on the record.
PLUS_FILTER_FILE = DATA_DIR / "tasks" / "wave-1" / "plus_inputs_removed.json"

HARNESS_SETS = {"humaneval": "humaneval", "mbpp": "mbpp"}

# Task-id prefixes of the stdin-stdout tasks (converted from programming-contest problems); a record that carries
# ``io_mode`` decides by that field instead.
STDIN_STDOUT_PREFIXES = ("openr1/", "ccplus/")

# The harness's own tasks whose test inputs it reconstructs from JSON into tuples, sets or complex numbers; a
# written task derived from one of them (its id is the parent's id with a suffix) inherits the rule.
MBPP_TYPED_PARENTS = frozenset(
    (2, 63, 64, 70, 75, 94, 106, 115, 116, 120, 124, 132, 143, 222, 237, 250, 252, 259, 261, 272, 273, 278, 299,
     307, 394, 399, 400, 401, 405, 409, 413, 417, 421, 424, 429, 438, 444, 445, 446, 470, 473, 560, 579, 580,
     596, 614, 615, 616, 617, 630, 720, 722, 726, 740, 744, 750, 753, 763, 780, 791, 808, 809)
)

_PARENT = re.compile(r"~.*$")


def parent_id(task_id: str) -> str:
    """A written copy's parent: the id before its ``~`` suffix; a task without the suffix is its own parent."""
    return _PARENT.sub("", task_id)


def is_stdin_stdout(record: dict[str, Any]) -> bool:
    """Whether a task record is a stdin-stdout task: its ``io_mode`` when present, else its id prefix."""
    mode = record.get("io_mode")
    if mode in ("stdio", "function"):
        return mode == "stdio"
    return str(record.get("task_id", "")).startswith(STDIN_STDOUT_PREFIXES)


def harness_kind(record: dict[str, Any]) -> str:
    """The harness's dataset kind for a task: ``mbpp`` for the tasks the harness's special oracles name and their
    written copies, ``humaneval`` otherwise."""
    if record.get("kind") in ("humaneval", "mbpp"):
        return record["kind"]
    return "mbpp" if parent_id(record["task_id"]).startswith("Mbpp/") else "humaneval"


def _open_text(path: pathlib.Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def read_records(path) -> Iterable[dict[str, Any]]:
    """The task records of one file, one JSON object per line."""
    with _open_text(pathlib.Path(path)) as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def content_hash(record: dict[str, Any]) -> str:
    """sha256 over the eight content fields serialised with sorted keys, the task's identity in the contract."""
    fields = ("task_id", "prompt", "entry_point", "canonical_solution", "base_input", "plus_input", "expected_output", "atol")
    text = json.dumps({k: record.get(k) for k in fields}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_hash(problems: dict[str, dict[str, Any]]) -> str:
    """sha256 over the sorted task ids: the identity of the set a judging ran over."""
    return hashlib.sha256("\n".join(sorted(problems)).encode("utf-8")).hexdigest()


def load_problems(source) -> dict[str, dict[str, Any]]:
    """The problems of a task file or of a harness set by name, before the input rules; keyed by task id."""
    name = str(source)
    if name in HARNESS_SETS:
        kind = HARNESS_SETS[name]
        raw = get_human_eval_plus() if kind == "humaneval" else get_mbpp_plus()
        problems = {}
        for task_id, p in raw.items():
            problems[task_id] = {
                "task_id": task_id,
                "prompt": p["prompt"],
                "entry_point": p["entry_point"],
                "canonical_solution": p["canonical_solution"],
                "base_input": p["base_input"],
                "plus_input": p["plus_input"],
                "atol": p["atol"],
                "kind": kind,
                "stdin_stdout": False,
                "typed_by_harness": kind == "mbpp",
            }
        return problems
    problems = {}
    for r in read_records(source):
        problems[r["task_id"]] = {
            "task_id": r["task_id"],
            "prompt": r["prompt"],
            "entry_point": r["entry_point"],
            "canonical_solution": r["canonical_solution"],
            "base_input": r["base_input"],
            "plus_input": r["plus_input"],
            "atol": r.get("atol", 0),
            "kind": harness_kind(r),
            "stdin_stdout": is_stdin_stdout(r),
            "typed_by_harness": False,
            "plus_inputs_removed": r.get("plus_inputs_removed"),
            "input_shapes": r.get("input_shapes"),
        }
    return problems


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _as_key(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def apply_plus_filter(problems: dict[str, dict[str, Any]], removed_by_task: dict[str, list] | None = None) -> dict[str, int]:
    """Remove, per task, the plus inputs the record lists (``plus_inputs_removed``) or the table lists for it or
    for its parent, matched by value; returns the count removed per task. The listed inputs carry a boolean at an
    argument position where every base example carries an integer, which a correct integer function need not
    handle."""
    if removed_by_task is None:
        table = _load_json(PLUS_FILTER_FILE).get("tasks", {})
    else:
        table = removed_by_task
    removed: dict[str, int] = {}
    for task_id, p in problems.items():
        entry = p.get("plus_inputs_removed")
        if entry is None:
            entry = table.get(task_id) or table.get(parent_id(task_id))
        if not entry:
            continue
        keys = {_as_key(x) for x in (entry.get("removed_inputs") if isinstance(entry, dict) else entry)}
        kept = [inp for inp in p["plus_input"] if _as_key(inp) not in keys]
        if len(kept) != len(p["plus_input"]):
            removed[task_id] = len(p["plus_input"]) - len(kept)
            p["plus_input"] = kept
    return removed


def to_typed(value, shape: str):
    """A JSON value converted to a declared shape such as ``list[tuple[int,int]]``; ``any`` and the scalar
    shapes are no-ops, a dict keeps its JSON form."""
    if shape in ("int", "str", "bool", "float", "None", "any"):
        return value
    m = re.match(r"^(list|set|frozenset|tuple|dict)\[(.*)\]$", shape)
    if not m:
        return value
    kind, inner = m.group(1), m.group(2)
    if kind == "dict":
        return value
    if kind == "tuple":
        if inner.endswith(",...") or inner == "":
            t = inner[:-4] if inner.endswith(",...") else "any"
            return tuple(to_typed(x, t) for x in value)
        parts = _split_top(inner)
        if len(parts) == len(value):
            return tuple(to_typed(x, t) for x, t in zip(value, parts))
        return tuple(to_typed(x, parts[0] if parts else "any") for x in value)
    make = {"list": list, "set": set, "frozenset": frozenset}[kind]
    return make(to_typed(x, inner) for x in value)


def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def apply_typed_inputs(problems: dict[str, dict[str, Any]], shapes_by_task: dict[str, list[str]] | None = None) -> list[str]:
    """Reconstruct the test inputs of the tasks that declare their argument types: the harness's rule for the
    copies of its typed tasks, the declared shapes for the written tasks; returns the task ids touched."""
    table = shapes_by_task if shapes_by_task is not None else {}
    touched: list[str] = []
    for task_id, p in problems.items():
        if p.get("typed_by_harness"):
            continue
        parent = parent_id(task_id)
        number = None
        if parent.startswith("Mbpp/"):
            try:
                number = int(parent.split("/")[-1])
            except ValueError:
                number = None
        if number is not None and number in MBPP_TYPED_PARENTS:
            p["base_input"] = mbpp_deserialize_inputs(parent, p["base_input"])
            p["plus_input"] = mbpp_deserialize_inputs(parent, p["plus_input"])
            touched.append(task_id)
        elif p.get("input_shapes") or task_id in table:
            shapes = p.get("input_shapes") or table[task_id]
            convert = lambda inp: [to_typed(a, shapes[i] if i < len(shapes) else "any") for i, a in enumerate(inp)]
            p["base_input"] = [convert(inp) for inp in p["base_input"]]
            p["plus_input"] = [convert(inp) for inp in p["plus_input"]]
            touched.append(task_id)
    return touched


def prepare(problems: dict[str, dict[str, Any]], settings: JudgingSettings) -> dict[str, Any]:
    """Apply the input rules a settings record names, in the order the plus filter (on the inputs as written) then
    the typed inputs; returns what was done, for the judging record."""
    done: dict[str, Any] = {}
    if settings.plus_filter:
        removed = apply_plus_filter(problems)
        done["plus_inputs_removed"] = {"tasks": len(removed), "inputs": sum(removed.values())}
    if settings.typed_inputs:
        done["typed_input_tasks"] = len(apply_typed_inputs(problems))
    return done

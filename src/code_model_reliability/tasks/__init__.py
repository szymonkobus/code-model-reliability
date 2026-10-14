"""The task sets of record and their provenance.

Reads ``data/tasks/``: ``sets.json`` (the members and kept subsets of wave 1, wave 2 and wave 2 parked, with a
sha256 per sorted list), ``attribution.jsonl`` and ``sources.json`` (where every task comes from and under which
licence its text travels), the wave 2 and wave 2 parked records (full text where the upstream licence permits,
pointers where it does not), ``certificates.jsonl`` (identity, status, audit label, provenance and version chain per
certified task), ``labels/`` (the audit label of every task and the history of label changes) and
``wave-1/kept_tasks.json`` (the wave 1 ids kept by the audit; wave 1 texts and tests come from the judge harness at its
pinned commit).

Provides one iterator over a set's tasks in the judge's shape (``iter_tasks``), the pointers beside it
(``iter_pointers``), ``verify`` (every record's content hash and every list's hash check out) and
``rebuild_restricted`` (the pointer tasks rebuilt from their upstream datasets). Writes nothing under ``data/``.

Command line: ``cmr tasks summary | list | show | verify | rebuild-restricted | attribution-table``.
"""

from __future__ import annotations

import argparse
import json
import sys

from .attribution import attribution_table, load_attribution, load_sources
from .content import CONTENT_FIELDS, KEEP_LABELS, SET_DIRS, SET_KEYS, SET_NAMES, content_sha256, list_sha256
from .data import tasks_dir
from .records import Pointer, Task, find_task, iter_pointers, iter_tasks, read_manifest
from .sets import Sets, TaskSet, load_sets

__all__ = [
    "CONTENT_FIELDS", "KEEP_LABELS", "SET_DIRS", "SET_KEYS", "SET_NAMES", "content_sha256", "list_sha256",
    "tasks_dir", "load_sets", "Sets", "TaskSet", "iter_tasks", "iter_pointers", "find_task", "Task", "Pointer",
    "load_attribution", "load_sources", "attribution_table", "main",
]


def _summary(tdir) -> str:
    sets = load_sets(tdir)
    lines = []
    for key in SET_KEYS:
        ts = sets[key]
        line = f"{ts.name}: {len(ts.members)} members, {len(ts.kept)} kept"
        if key in SET_DIRS:
            m = read_manifest(tdir, key)
            line += f"; {m.get('full_text_tasks', '?')} with text, {m.get('pointer_tasks', '?')} pointers"
        lines.append(line)
    lines.append(f"wave 1+2: {len(sets.wave_1_plus_2_kept())} kept tasks")
    return "\n".join(lines)


def _take_data_option(argv: list[str]) -> tuple[list[str], str | None]:
    """``--data <dir>`` (or ``--data=<dir>``) anywhere on the line, so it works before or after the command name."""
    rest: list[str] = []
    data = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--data" and i + 1 < len(argv):
            data = argv[i + 1]
            i += 2
            continue
        if a.startswith("--data="):
            data = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    return rest, data


def main(argv: list[str] | None = None) -> int:
    argv, data = _take_data_option(list(sys.argv[1:] if argv is None else argv))
    if data is not None:
        argv = ["--data", data, *argv]
    ap = argparse.ArgumentParser(prog="cmr tasks", description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="the repository's data directory or its tasks folder; before or after the command")
    sub = ap.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("summary", help="the sets, their counts, texts and pointers")
    p_list = sub.add_parser("list", help="the task ids of a set, one per line")
    p_list.add_argument("--set", choices=SET_KEYS, default="wave_2")
    p_list.add_argument("--kept", action="store_true", help="only the tasks the audit keeps")
    p_show = sub.add_parser("show", help="one task: its record or pointer and its attribution row, as JSON")
    p_show.add_argument("task_id")
    sub.add_parser("verify", help="every content hash and list hash against the record (its own --help)", add_help=False)
    sub.add_parser("rebuild-restricted", help="the pointer tasks from their upstream datasets (its own --help)", add_help=False)
    sub.add_parser("convert", help="the converters of the LeetCode-derived tasks and the fetch of their upstream rows (its own --help)", add_help=False)
    sub.add_parser("attribution-table", help="the attribution table as Markdown")
    args, rest = ap.parse_known_args(argv)
    if not args.command:
        ap.print_help()
        return 2
    if args.command in ("verify", "rebuild-restricted", "convert"):
        # these have their own options; everything after the command name is theirs
        if args.command == "verify":
            from . import verify as verify_mod
            return verify_mod.main(rest + (["--data", args.data] if args.data else []))
        if args.command == "rebuild-restricted":
            from . import rebuild_restricted as rr
            return rr.main(rest + (["--data", args.data] if args.data else []))
        from . import convert as convert_mod
        return convert_mod.main(rest)
    if rest:
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    tdir = tasks_dir(args.data)
    if args.command == "summary":
        print(_summary(tdir))
    elif args.command == "list":
        ts = load_sets(tdir)[args.set]
        for tid in (ts.kept if args.kept else ts.members):
            print(tid)
    elif args.command == "show":
        sets = load_sets(tdir)
        key = sets.set_of(args.task_id)
        out: dict = {"task_id": args.task_id, "set": key}
        if key in SET_DIRS:
            found = find_task(tdir, key, args.task_id)
            out["kind"] = "text" if isinstance(found, Task) else "pointer" if isinstance(found, Pointer) else None
            out["record"] = found.record if found else None
        rows = [r for r in load_attribution(tdir) if r["task_id"] == args.task_id]
        out["attribution"] = rows[0] if rows else None
        print(json.dumps(out, indent=1, ensure_ascii=False))
    elif args.command == "attribution-table":
        print(attribution_table(load_attribution(tdir), load_sources(tdir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The converters that built the LeetCode-derived tasks, as code: ``leetcode`` (LeetCodeDataset rows) and
``livecodebench`` (LiveCodeBench rows joined to LeetCodeDataset's solutions), with the fetch of their upstream rows.

The pointer tasks of wave 2 and wave 2 parked were converted with exactly these rules, so a rebuilt record's content
hash can be checked against the certified one (``cmr tasks rebuild-restricted``). A task that was later re-issued
with some extended inputs removed is rebuilt by converting and then removing the inputs its pointer lists.

Command line: ``cmr tasks convert fetch-upstream <leetcode|livecodebench> --out <rows.jsonl> [--revision <commit>]
[--slugs <file>]``; ``cmr tasks convert <leetcode|livecodebench> --rows <rows.jsonl> --out <folder> [--references
<leetcode rows>] [--slugs <file>]``. The conversion writes ``tasks.jsonl`` (the converted records) and
``report.jsonl`` (one line per row: its status and reason).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from . import leetcode, livecodebench
from .common import read_jsonl, write_jsonl
from .upstream import fetch_leetcode, fetch_livecodebench, references_by_slug

__all__ = ["convert_rows", "main", "leetcode", "livecodebench"]


def _slugs_from(path: str | None) -> set[str] | None:
    if not path:
        return None
    return {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}


def convert_rows(source: str, rows: list[dict], out: Path, references: dict[str, dict] | None = None,
                 slugs: set[str] | None = None) -> Counter:
    """Convert rows of one source into ``out/tasks.jsonl`` with ``out/report.jsonl``; returns the status counts."""
    out.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    tasks: list[dict] = []
    report: list[dict] = []
    for n, row in enumerate(rows, 1):
        if source == "leetcode":
            key = str(row.get("task_id") or "")
            if slugs is not None and key not in slugs:
                continue
            t0 = time.time()
            status, reason, task, metrics = leetcode.convert_row(row)
        else:
            key = livecodebench.slugify(row.get("question_title"))
            if slugs is not None and key not in slugs:
                continue
            t0 = time.time()
            status, reason, task, metrics = livecodebench.convert_row(row, references or {})
        counts[status] += 1
        if task is not None:
            tasks.append(task)
        report.append({"row": key, "status": status, "reason": reason, "seconds": round(time.time() - t0, 1), "metrics": metrics})
        print("%4d %-50s %-11s %s" % (n, key[:50], status, reason[:70]), flush=True)
    write_jsonl(out / "tasks.jsonl", tasks)
    write_jsonl(out / "report.jsonl", report)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmr tasks convert", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", metavar="<command>")
    f = sub.add_parser("fetch-upstream", help="read a dataset's rows from Hugging Face into a JSON-lines file")
    f.add_argument("source", choices=("leetcode", "livecodebench"))
    f.add_argument("--out", required=True, type=Path)
    f.add_argument("--revision", help="a commit of the dataset repository, to read the rows as they stood then")
    f.add_argument("--slugs", help="a file with one problem slug per line; only those rows are written")
    for source in ("leetcode", "livecodebench"):
        c = sub.add_parser(source, help="convert %s rows into tasks" % source)
        c.add_argument("--rows", required=True, type=Path, help="the fetched rows (JSON lines)")
        c.add_argument("--out", required=True, type=Path, help="the folder for tasks.jsonl and report.jsonl")
        c.add_argument("--slugs", help="a file with one problem slug per line; only those rows are converted")
        if source == "livecodebench":
            c.add_argument("--references", required=True, type=Path, help="the fetched LeetCodeDataset rows, the join's references")
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 2
    if args.command == "fetch-upstream":
        if args.source == "leetcode":
            n = fetch_leetcode(args.out, args.revision, _slugs_from(args.slugs))
            print("%d LeetCodeDataset rows -> %s" % (n, args.out))
        else:
            kept, skipped = fetch_livecodebench(args.out, args.revision, _slugs_from(args.slugs))
            print("%d LiveCodeBench rows with a function and a LeetCode platform -> %s (%d others skipped)" % (kept, args.out, skipped))
        return 0
    rows = read_jsonl(args.rows)
    refs = references_by_slug(args.references) if args.command == "livecodebench" else None
    counts = convert_rows(args.command, rows, args.out, refs, _slugs_from(args.slugs))
    print(json.dumps(dict(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

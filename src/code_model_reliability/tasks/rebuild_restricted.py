"""``cmr tasks rebuild-restricted``: the pointer tasks rebuilt from their upstream datasets and checked by hash.

A pointer task ships as its identity (``task_id``, ``content_sha256``), its audit flag, its provenance (the upstream
dataset, the row key and the problem URL), the reason its text does not travel, and under ``rebuild`` the recipe:
the converter in this repository for its upstream (``leetcode`` or ``livecodebench``, ``cmr tasks convert``), the
hash of the task's first emission, and, where the task was later re-issued, the inputs that re-issue removed. A
rebuilt record is accepted when its content hash equals the certified one, directly or after the listed inputs are
removed (matched by value, with their expected outputs), so a rebuilt set is the set the published fits used.

``--plan`` lists, per upstream dataset, the rows to fetch and the commands to run, and with ``--write-slugs <dir>``
writes the slug lists those commands read. ``--verify <file>`` reads converted records (``.jsonl`` or ``.jsonl.gz``),
keeps the ones that reproduce a pointer's certified hash and reports the rest; ``--out`` writes the kept records as a
part a reader can drop beside the shipped ones.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .content import SET_DIRS, SET_NAMES, content_sha256
from .data import tasks_dir as resolve_tasks_dir
from .records import iter_jsonl, iter_pointers

CONVERTER_FOR = {"newfacade/LeetCodeDataset": "leetcode", "livecodebench/code_generation_lite#v6": "livecodebench"}
"""The converter in this repository per upstream dataset whose tasks ship as pointers."""


def pointers_by_dataset(tasks_dir: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for key in SET_DIRS:
        for ptr in iter_pointers(tasks_dir, key):
            prov = ptr.provenance
            out[prov.get("source_dataset", "unknown")].append(
                {"task_id": ptr.task_id, "set": key, "slug": prov.get("problem_key") or ptr.task_id.split("/", 1)[1],
                 "row": prov.get("source_row"), "url": prov.get("url"), "content_sha256": ptr.content_sha256,
                 "reason": ptr.reason, "rebuild": ptr.record.get("rebuild") or {}}
            )
    return out


def plan(tasks_dir: Path, write_slugs: Path | None = None) -> str:
    lines = []
    by_ds = pointers_by_dataset(tasks_dir)
    total = sum(len(v) for v in by_ds.values())
    lines.append(f"{total} pointer tasks to rebuild, by upstream dataset:")
    slugs: dict[str, set[str]] = {"leetcode": set(), "livecodebench": set()}
    for ds, rows in sorted(by_ds.items()):
        per_set = Counter(r["set"] for r in rows)
        reissued = sum(1 for r in rows if r["rebuild"].get("plus_inputs_removed_at_reissue") or r["rebuild"].get("base_inputs_removed_at_reissue"))
        named = {r["rebuild"].get("converter") for r in rows if r["rebuild"].get("converter")}
        conv = next(iter(named)) if len(named) == 1 else CONVERTER_FOR.get(ds, "no converter in this repository")
        lines.append(f"  {ds}: {len(rows)} tasks ({', '.join(f'{SET_NAMES[k]} {n}' for k, n in sorted(per_set.items()))}), "
                     f"{reissued} re-issued with inputs removed after conversion; converter {conv}; e.g. {[r['slug'] for r in rows[:3]]}")
        if conv in slugs:
            slugs[conv].update(r["slug"] for r in rows)
    # the LiveCodeBench join reads LeetCodeDataset's rows of the same slugs as its references
    slugs["leetcode"] |= slugs["livecodebench"]
    where = write_slugs if write_slugs is not None else Path("<slugs dir>")
    lines.append("")
    lines.append("then, from a machine that reaches Hugging Face (the fetch needs huggingface_hub; the conversion runs the references locally):")
    lines.append(f"  cmr tasks convert fetch-upstream leetcode --out rows/leetcode.jsonl --slugs {where / 'slugs-leetcode.txt'}")
    lines.append(f"  cmr tasks convert fetch-upstream livecodebench --out rows/livecodebench.jsonl --slugs {where / 'slugs-livecodebench.txt'}")
    lines.append("  cmr tasks convert leetcode --rows rows/leetcode.jsonl --out converted/leetcode")
    lines.append("  cmr tasks convert livecodebench --rows rows/livecodebench.jsonl --references rows/leetcode.jsonl --out converted/livecodebench")
    lines.append("  cmr tasks rebuild-restricted --verify converted/leetcode/tasks.jsonl --out rebuilt-leetcode.jsonl")
    lines.append("  cmr tasks rebuild-restricted --verify converted/livecodebench/tasks.jsonl --out rebuilt-livecodebench.jsonl")
    lines.append("a rebuilt record whose upstream row changed since the fetch of record fails its hash; pin the dataset revision of that time with --revision")
    if write_slugs is not None:
        write_slugs.mkdir(parents=True, exist_ok=True)
        for name, values in slugs.items():
            (write_slugs / f"slugs-{name}.txt").write_text("".join(s + "\n" for s in sorted(values)), encoding="utf-8")
        lines.append(f"slug lists written under {write_slugs} ({len(slugs['leetcode'])} LeetCodeDataset rows, {len(slugs['livecodebench'])} LiveCodeBench rows)")
    return "\n".join(lines)


def apply_reissue(rec: dict, recipe: dict) -> dict:
    """The re-issue applied to a converted record: the listed inputs leave ``plus_input`` and ``base_input`` (matched by
    value) together with their expected outputs; everything else stays."""
    out = dict(rec)
    expected = rec.get("expected_output")
    for field, part in (("plus_input", "plus"), ("base_input", "base")):
        removed = {json.dumps(x) for x in recipe.get(f"{part}_inputs_removed_at_reissue") or []}
        if not removed:
            continue
        inputs = rec.get(field) or []
        keep_idx = [i for i, x in enumerate(inputs) if json.dumps(x) not in removed]
        out[field] = [inputs[i] for i in keep_idx]
        if isinstance(expected, dict) and isinstance(expected.get(part), list) and len(expected[part]) == len(inputs):
            out.setdefault("expected_output", dict(expected))
            out["expected_output"] = dict(out["expected_output"])
            out["expected_output"][part] = [expected[part][i] for i in keep_idx]
    return out


def verify(tasks_dir: Path, src: Path, out: Path | None) -> tuple[Counter, list[dict]]:
    want: dict[str, tuple[str, dict]] = {}
    for key in SET_DIRS:
        for ptr in iter_pointers(tasks_dir, key):
            want[ptr.task_id] = (ptr.content_sha256, ptr.record.get("rebuild") or {})
    stats: Counter = Counter()
    kept: list[dict] = []
    families_seen: set[str] = set()
    for rec in iter_jsonl(src):
        tid = rec.get("task_id")
        if tid not in want:
            stats["not a pointer task"] += 1
            continue
        families_seen.add(tid.split("/")[0])
        certified, recipe = want[tid]
        if content_sha256(rec) == certified:
            stats["match"] += 1
            kept.append(rec)
            continue
        if recipe.get("plus_inputs_removed_at_reissue") or recipe.get("base_inputs_removed_at_reissue"):
            reissued = apply_reissue(rec, recipe)
            if content_sha256(reissued) == certified:
                stats["match after the re-issue's removals"] += 1
                kept.append(reissued)
                continue
        stats["hash mismatch"] += 1
    # the pointers of the families this file carries that it did not rebuild
    stats["pointers still missing"] = len([t for t in want if t.split("/")[0] in families_seen]) - len({r["task_id"] for r in kept})
    if out is not None:
        with open(out, "w", encoding="utf-8") as fh:
            for rec in kept:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return stats, kept


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmr tasks rebuild-restricted", description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="the repository's data directory or its tasks folder")
    ap.add_argument("--plan", action="store_true", help="list the upstream rows to fetch and the commands to run")
    ap.add_argument("--write-slugs", type=Path, help="with --plan: write the slug lists the fetch commands read into this directory")
    ap.add_argument("--verify", type=Path, help="converted records to check against the pointers' hashes")
    ap.add_argument("--out", type=Path, help="write the records that match, one JSON object per line")
    args = ap.parse_args(argv)
    tdir = resolve_tasks_dir(args.data)
    if args.plan:
        print(plan(tdir, args.write_slugs))
        return 0
    if args.verify:
        stats, _ = verify(tdir, args.verify, args.out)
        print(f"{args.verify.name}: {dict(stats)}" + (f" -> {args.out}" if args.out else ""))
        return 0 if stats["hash mismatch"] == 0 else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

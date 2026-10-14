"""``cmr tasks verify`` and ``cmr verify``: the shipped task data against its own hashes and contracts.

Checks, in order: the set lists (every list hash, kept within members, no overlap, the wave 1+2 identity); the parts
(bytes and sha256 against each manifest); every record's content hash recomputed from its eight fields and compared
with the record's own hash and with its certificate; every member of a text-bearing set present exactly once as a
record or a pointer; the attribution rows (one per member, each covered by a source set); the certificates; the
labels (every member labelled, kept exactly when the label keeps). Exits 1 on any mismatch and prints every problem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .attribution import check_attribution, load_attribution, load_sources
from .certificates import certificate_hashes, check_certificates
from .content import SET_DIRS
from .data import tasks_dir as resolve_tasks_dir
from .labels import check_labels, load_labels
from .records import check_parts, iter_pointers, iter_tasks
from .sets import check_sets, load_sets


def verify(tasks_dir: Path, quick: bool = False) -> tuple[list[str], dict]:
    """Run every check. Returns (problems, counts). ``quick`` skips the part hashes and the record hashes."""
    problems: list[str] = []
    counts: dict = {}
    sets = load_sets(tasks_dir)
    problems += check_sets(sets)
    members = {k: ts.member_set for k, ts in sets.by_key.items()}
    kept = {k: ts.kept_set for k, ts in sets.by_key.items()}
    counts["members"] = {k: len(v) for k, v in members.items()}
    counts["kept"] = {k: len(v) for k, v in kept.items()}

    certified = certificate_hashes(tasks_dir) if (tasks_dir / "certificates.jsonl").is_file() else {}
    if certified:
        problems += check_certificates(tasks_dir, members)
    counts["certificates"] = len(certified)

    for key in SET_DIRS:
        if not quick:
            problems += check_parts(tasks_dir, key)
        seen: dict[str, int] = {}
        n_text = n_ptr = n_bad = n_cert_bad = 0
        for task in iter_tasks(tasks_dir, key):
            seen[task.task_id] = seen.get(task.task_id, 0) + 1
            n_text += 1
            if not quick and not task.hash_matches():
                n_bad += 1
                if n_bad <= 3:
                    problems.append(f"{key}: {task.task_id}: the content hash does not match its eight fields")
            if certified and certified.get(task.task_id) not in (None, task.content_sha256):
                n_cert_bad += 1
                if n_cert_bad <= 3:
                    problems.append(f"{key}: {task.task_id}: the record's hash is not the certified hash")
            if task.kept_by_audit != (task.task_id in kept[key]):
                problems.append(f"{key}: {task.task_id}: kept_by_audit disagrees with sets.json")
        for ptr in iter_pointers(tasks_dir, key):
            seen[ptr.task_id] = seen.get(ptr.task_id, 0) + 1
            n_ptr += 1
            if certified and certified.get(ptr.task_id) not in (None, ptr.content_sha256):
                problems.append(f"{key}: pointer {ptr.task_id}: the hash is not the certified hash")
        if n_bad > 3:
            problems.append(f"{key}: {n_bad} records in all have a content hash that does not match")
        if n_cert_bad > 3:
            problems.append(f"{key}: {n_cert_bad} records in all differ from their certificate")
        twice = [t for t, n in seen.items() if n > 1]
        missing = members[key] - seen.keys()
        extra = seen.keys() - members[key]
        if twice:
            problems.append(f"{key}: {len(twice)} ids appear more than once, e.g. {twice[0]}")
        if missing:
            problems.append(f"{key}: {len(missing)} members have neither a record nor a pointer, e.g. {sorted(missing)[0]}")
        if extra:
            problems.append(f"{key}: {len(extra)} records or pointers are not members, e.g. {sorted(extra)[0]}")
        counts[key] = {"text": n_text, "pointers": n_ptr}

    if (tasks_dir / "attribution.jsonl").is_file():
        rows = load_attribution(tasks_dir)
        sources = load_sources(tasks_dir) if (tasks_dir / "sources.json").is_file() else []
        problems += check_attribution(rows, sources, members)
        counts["attribution_rows"] = len(rows)
        if certified:
            bad = [r["task_id"] for r in rows if r.get("content_sha256") and certified.get(r["task_id"]) not in (None, r["content_sha256"])]
            if bad:
                problems.append(f"attribution: {len(bad)} rows carry a hash that is not the certified hash, e.g. {bad[0]}")

    if (tasks_dir / "labels" / "labels.jsonl").is_file():
        labels = load_labels(tasks_dir)
        problems += check_labels(labels, members, kept, sets.keep_labels or ("regular", "tricky"))
        counts["labels"] = len(labels)
    return problems, counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmr tasks verify", description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="the repository's data directory or its tasks folder")
    ap.add_argument("--quick", action="store_true", help="skip the part hashes and the per-record content hashes")
    args = ap.parse_args(argv)
    tdir = resolve_tasks_dir(args.data)
    problems, counts = verify(tdir, quick=args.quick)
    for key, val in counts.items():
        print(f"{key}: {val}")
    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("verified: every hash and list checks out")
    return 0


if __name__ == "__main__":
    sys.exit(main())

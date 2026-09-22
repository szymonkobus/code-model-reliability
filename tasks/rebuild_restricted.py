#!/usr/bin/env python3
"""Rebuild, or verify, the wave-2 tasks whose statement text is not redistributed here.

tasks/wave2/restricted.jsonl and tasks/wave2-parked/restricted.jsonl list, per task, the content hash of the certified version and the upstream row it was
converted from (provenance.source_dataset = "<hugging-face id>#<config>", provenance.problem_key, source_row).
The conversion pipeline is in this repository (tasks/pipeline/acquire/stage_ab/acquisition: fetch_candidates.py fetches
the Codeforces datasets' rows into the converter's candidates_raw.jsonl shape, convert.py converts them offline; rows of
the two LeetCode-derived datasets are fetched by problem key with the datasets library into the same shape). A rebuilt
task is accepted only when its content hash (sha256 over the eight judged-content fields, json.dumps with
sort_keys) equals the certified hash, so a rebuilt pool is identical to the one the published fits used.

  python3 tasks/rebuild_restricted.py --plan
      prints the upstream datasets and problem keys to fetch, and the two pipeline commands to run
  python3 tasks/rebuild_restricted.py --verify converted/tasks.jsonl --out rebuilt-restricted.jsonl
      keeps the converted records whose hash matches a restricted pointer; reports the rest
  python3 tasks/rebuild_restricted.py --verify tasks-part-01.jsonl.gz --against certificates.jsonl
      the same check over a shipped part (every shipped task must match its certificate)
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
CONTENT_FIELDS = ["task_id", "prompt", "entry_point", "canonical_solution", "base_input", "plus_input", "atol", "expected_output"]


def content_hash(rec: dict) -> str:
    return hashlib.sha256(json.dumps({k: rec.get(k) for k in CONTENT_FIELDS}, sort_keys=True).encode()).hexdigest()


def read_jsonl(path: pathlib.Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def plan() -> None:
    by_ds = defaultdict(list)
    for ptr in list(read_jsonl(HERE / "wave2" / "restricted.jsonl")) + list(read_jsonl(HERE / "wave2-parked" / "restricted.jsonl")):
        prov = ptr.get("provenance", {})
        by_ds[prov.get("source_dataset", "?")].append(prov.get("problem_key") or prov.get("source_row"))
    print("upstream rows to fetch:")
    for ds, keys in by_ds.items():
        print(f"  {ds}: {len(keys)} rows, e.g. {keys[:3]}")
    print("\nthen, from the repository root (network needed for the fetch, none for the conversion):")
    print("  python3 tasks/pipeline/acquire/stage_ab/acquisition/fetch_candidates.py --help   # fetches the Codeforces datasets' rows into candidates_raw.jsonl;")
    print("      rows of the two LeetCode-derived datasets are fetched by their problem keys with the datasets library into the same shape")
    print("  python3 tasks/pipeline/acquire/stage_ab/acquisition/convert.py --in candidates_raw.jsonl --outdir converted")
    print("  python3 tasks/rebuild_restricted.py --verify converted/tasks.jsonl --out rebuilt-restricted.jsonl")


def verify(src: pathlib.Path, against: pathlib.Path, out: pathlib.Path | None) -> int:
    want = {}
    for rec in read_jsonl(against):
        if rec.get("content_sha256") and (against.name != "certificates.jsonl" or rec.get("fit_keep_set")):
            want[rec["task_id"]] = rec["content_sha256"]
    stats = Counter()
    kept = []
    for rec in read_jsonl(src):
        tid = rec.get("task_id")
        if tid not in want:
            stats["not a listed task"] += 1; continue
        if content_hash(rec) == want[tid]:
            stats["match"] += 1; kept.append(rec)
        else:
            stats["hash mismatch"] += 1
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            for rec in kept:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"{src.name} against {against.name}: {dict(stats)}" + (f" -> {out}" if out else ""))
    return 0 if stats["hash mismatch"] == 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--verify", type=pathlib.Path, help="converted tasks (.jsonl or .jsonl.gz) to check")
    ap.add_argument("--against", type=pathlib.Path, default=HERE / "wave2" / "restricted.jsonl", help="pointers or certificates carrying content_sha256")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()
    if args.plan:
        plan(); return
    if args.verify:
        sys.exit(verify(args.verify, args.against, args.out))
    ap.print_help()


if __name__ == "__main__":
    main()

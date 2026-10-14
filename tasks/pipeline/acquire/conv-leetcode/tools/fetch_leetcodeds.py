#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["huggingface_hub>=0.23"]
# ///
import argparse, collections, datetime, io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from restore_exponents_pinned import restore as restore_exponents
import hashlib, re
PINNED_MD5 = hashlib.md5(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "restore_exponents_pinned.py"), "rb").read()).hexdigest()
BIT_RANGE_RULE_NAME = "lcds-bit-range-rule"
BIT_RANGE_RULE_TEXT = ("on a line carrying a bracket range '[-2k, 2k - 1]' or the words 32-bit, 64-bit, "
                       "signed integer or overflow, every 2k-class shape (k in 15, 16, 31, 32, 63, 64; not "
                       "preceded by a digit, ^, . or *; not followed by a digit or ^) becomes 2^k; no other line changes")
_BIT_LINE = re.compile(r"\[\s*-\s*2(?:1[5-6]|3[0-2]|6[3-4])\s*,\s*2(?:1[5-6]|3[0-2]|6[3-4])\s*-\s*1\s*\]|32-bit|64-bit|signed integer|overflow", re.I)
_BIT_POW2 = re.compile(r"(?<![\d^.*])2(1[5-6]|3[0-2]|6[3-4])(?![\d^])")
MODULUS_RULE_NAME = "lcds-modulus-rule"
MODULUS_RULE_TEXT = ("the shape '109 + 7' (any spacing; not preceded by a digit, ^ or .; not followed by a digit) "
                     "is the flattened 10^9 + 7 wherever it stands and becomes '10^9 + 7' on any line")
_FLAT_MOD = re.compile(r"(?<![\d^.])109(\s*\+\s*)7(?!\d)")


def modulus_restore(text):
    reps = []
    def sub(m):
        new = "10^9%s7" % m.group(1)
        reps.append([m.group(0), new])
        return new
    return _FLAT_MOD.sub(sub, text), reps


def bit_range_restore(text):
    out, reps = [], []
    for line in text.split("\n"):
        if _BIT_LINE.search(line):
            def sub(m):
                new = "2^%s" % m.group(1)
                reps.append([m.group(0), new])
                return new
            line = _BIT_POW2.sub(sub, line)
        out.append(line)
    return "\n".join(out), reps

REPO = "newfacade/LeetCodeDataset"
FILES = (("train", "datasets/newfacade/LeetCodeDataset/LeetCodeDataset-train.jsonl"),
         ("test", "datasets/newfacade/LeetCodeDataset/LeetCodeDataset-test.jsonl"))
COLS = ["task_id", "question_id", "difficulty", "tags", "problem_description",
        "starter_code", "estimated_date", "prompt", "completion", "entry_point",
        "input_output"]
LICENSE = "apache-2.0 (dataset card) over LeetCode material"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chosen", required=True, help="tsv: slug, difficulty, question_id, date; in landing order")
    ap.add_argument("--twins", required=True, help="one slug per line: live leetcode ids + staged slugs")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--shard-size", type=int, default=100)
    a = ap.parse_args()
    from huggingface_hub import HfFileSystem
    fs = HfFileSystem()
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    chosen_order, chosen_meta = [], {}
    for line in open(a.chosen):
        parts = line.rstrip("\n").split("\t")
        if not parts or not parts[0]:
            continue
        slug = parts[0]
        if slug not in chosen_meta:
            chosen_order.append(slug)
            chosen_meta[slug] = {"difficulty": parts[1] if len(parts) > 1 else None,
                                 "question_id": parts[2] if len(parts) > 2 else None,
                                 "date": parts[3] if len(parts) > 3 else None}
    twins = set(l.strip() for l in open(a.twins) if l.strip())
    chosen = set(chosen_order)
    twin_hits = sorted(s for s in chosen_order if s in twins)
    wanted = chosen - twins

    sizes = {}
    for split, path in FILES:
        try:
            info = fs.info(path)
            sizes[split] = {"path": path, "bytes": info.get("size"),
                            "last_commit": str((info.get("last_commit") or {}).get("date")) if isinstance(info.get("last_commit"), dict) else str(info.get("last_commit"))}
        except Exception as e:  # sizes are a record, not a gate
            sizes[split] = {"path": path, "bytes": None, "error": repr(e)[:200]}

    per_split = {}
    kept, dup_slugs, no_completion, no_tests = {}, [], [], []
    for split, path in FILES:
        c = collections.Counter()
        with fs.open(path, "rb") as f:
            for i, line in enumerate(io.TextIOWrapper(f, encoding="utf-8")):
                line = line.strip()
                if not line:
                    continue
                c["rows"] += 1
                r = json.loads(line)
                slug = r.get("task_id")
                if r.get("completion"):
                    c["rows_with_completion"] += 1
                if r.get("input_output"):
                    c["rows_with_input_output"] += 1
                if slug in twins and slug in chosen:
                    c["chosen_twin_excluded"] += 1
                if slug not in wanted:
                    continue
                c["chosen_present"] += 1
                if slug in kept:
                    dup_slugs.append("%s@%s#%d" % (slug, split, i))
                    c["chosen_duplicate_row"] += 1
                    continue
                if not r.get("completion"):
                    no_completion.append(slug)
                    c["chosen_without_completion"] += 1
                    continue
                if not r.get("input_output"):
                    no_tests.append(slug)
                    c["chosen_without_tests"] += 1
                    continue
                rec = {k: r.get(k) for k in COLS}
                desc = rec.get("problem_description") or ""
                new_desc, reps = restore_exponents(desc)
                new_desc, breps = bit_range_restore(new_desc)
                new_desc, mreps = modulus_restore(new_desc)
                if reps or breps or mreps:
                    rec["problem_description"] = new_desc
                    c["chosen_exponents_restored"] += 1
                if breps:
                    c["chosen_bit_range_rule_fired"] += 1
                if mreps:
                    c["chosen_modulus_rule_fired"] += 1
                er = {"n": len(reps) + len(breps) + len(mreps),
                      "replacements": [[a, b] for _, a, b in reps] + list(breps) + list(mreps),
                      "pinned_tool": {"name": "restore_exponents.py (train-check-parked-3), pinned copy restore_exponents_pinned.py",
                                      "md5": PINNED_MD5, "replacements": [[a, b] for _, a, b in reps]}}
                if breps:
                    er["bit_range_rule"] = {"name": BIT_RANGE_RULE_NAME, "text": BIT_RANGE_RULE_TEXT, "replacements": breps}
                if mreps:
                    er["modulus_rule"] = {"name": MODULUS_RULE_NAME, "text": MODULUS_RULE_TEXT, "replacements": mreps}
                rec["_exponents_restored"] = er
                rec["_row"] = "%s#%d" % (os.path.basename(path), i)
                rec["_split"] = split
                rec["_fetched_at"] = fetched_at
                kept[slug] = rec
                c["chosen_kept"] += 1
        per_split[split] = dict(c)
        print("[lcds-fetch] %s: %s" % (split, dict(c)), flush=True)

    missing = [s for s in chosen_order if s in wanted and s not in kept
               and s not in no_completion and s not in no_tests]
    order = [s for s in chosen_order if s in kept]
    os.makedirs(a.outdir, exist_ok=True)
    shards = []
    for si in range(0, len(order), a.shard_size):
        chunk = order[si:si + a.shard_size]
        name = "leetcode_raw_lcds.s%02d.jsonl" % (si // a.shard_size)
        path = os.path.join(a.outdir, name)
        tmp = path + ".part"
        with open(tmp, "w") as f:
            for s in chunk:
                f.write(json.dumps(kept[s], default=str) + "\n")
        os.replace(tmp, path)
        shards.append({"file": name, "rows": len(chunk),
                       "by_difficulty": dict(collections.Counter(kept[s].get("difficulty") for s in chunk)),
                       "first": chunk[0], "last": chunk[-1]})
    with open(os.path.join(a.outdir, "candidates_order.txt"), "w") as f:
        for i, s in enumerate(order):
            f.write("%d\t%s\t%s\t%s\n" % (i // a.shard_size, s, kept[s].get("difficulty"), kept[s]["_split"]))
    report = {
        "stamp": fetched_at, "repo": REPO, "license": LICENSE, "files": sizes,
        "columns": COLS, "per_split": per_split,
        "chosen": len(chosen_order),
        "chosen_by_difficulty": dict(collections.Counter(m["difficulty"] for m in chosen_meta.values())),
        "twin_list_size": len(twins), "twin_hits": twin_hits, "twin_hits_count": len(twin_hits),
        "candidates_kept": len(order),
        "exponents_restored": {"records": sum(1 for s_ in order if kept[s_]["_exponents_restored"]["n"]),
                               "pinned_tool_md5": PINNED_MD5,
                               "bit_range_rule_records": sum(1 for s_ in order if kept[s_]["_exponents_restored"].get("bit_range_rule")),
                               "bit_range_rule_replacements": [[s_] + r for s_ in order for r in (kept[s_]["_exponents_restored"].get("bit_range_rule") or {}).get("replacements", [])],
                               "modulus_rule_records": sum(1 for s_ in order if kept[s_]["_exponents_restored"].get("modulus_rule")),
                               "modulus_rule_replacements": [[s_] + r for s_ in order for r in (kept[s_]["_exponents_restored"].get("modulus_rule") or {}).get("replacements", [])],
                               "replacements": sum(kept[s_]["_exponents_restored"]["n"] for s_ in order),
                               "by_pair": dict(collections.Counter("%s -> %s" % (a, b) for s_ in order for a, b in kept[s_]["_exponents_restored"]["replacements"]))},
        "kept_by_split": dict(collections.Counter(kept[s]["_split"] for s in order)),
        "kept_by_difficulty": dict(collections.Counter(kept[s].get("difficulty") for s in order)),
        "duplicate_rows_skipped": dup_slugs, "without_completion": no_completion,
        "without_tests": no_tests, "missing_from_dataset": missing,
        "shard_size": a.shard_size, "shards": shards,
    }
    tmp = os.path.join(a.outdir, "fetch_report.json.part")
    with open(tmp, "w") as f:
        json.dump(report, f, indent=1)
    os.replace(tmp, os.path.join(a.outdir, "fetch_report.json"))
    print("[lcds-fetch] chosen %d, twin hits excluded %d, kept %d in %d shards; missing %d, no completion %d, no tests %d"
          % (len(chosen_order), len(twin_hits), len(order), len(shards), len(missing), len(no_completion), len(no_tests)), flush=True)


if __name__ == "__main__":
    main()

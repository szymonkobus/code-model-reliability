#!/usr/bin/env python3
"""The file is downloaded whole by poolb-taco-download.sbatch and READ HERE IN
ONE STREAMING PASS (json raw_decode over 8 MB chunks, one object resident at
a time): never json.load of the whole file. Offline once the file is on disk;
pure stdlib.

Routed out at fetch (counted in fetch_report.json, ids listed per reason):
  function form  — input_output carries fn_name or the record has a
                   starter_code: the tests are calls, not stdin; written
                   whole to <outdir>/candidates_fn.taco.jsonl for the
                   function-form path, not to a stdio shard;
  interactive    — the statement says it is an interactive problem;
  image          — picture_num > 0 or an [Image] / <image> marker;
  contest twin   — a Codeforces URL whose <contest>/<index> is in
                   --live-keys (the pool's ccplus/openr1 ids); the list of
                   record is already filtered by identity, this is the
                   second check;
  nonstring io   — a stdio test whose input or output is neither a string
                   nor a list of strings (a list of strings is a list of
                   LINES in Codechef-style records and is joined with
                   "\n"; tests_meta.n_line_lists_joined counts them);
  few tests      — fewer than 5 distinct (input, output) pairs after
                   canonical form (convert.py would reject; saved converter
                   time);
  no py3 ref     — no solution parses as Python 3;
  not in file    — a listed id the file does not carry.

Statement examples: the question blob carries its own Examples / Sample
Input blocks (Codeforces "-----Examples-----", AtCoder "-----Sample
Input-----", Codechef "-----Sample Input:-----", HackerRank "Sample Input",
Hackerearth "SAMPLE INPUT", Aizu "Example / Input / Output"). Input blocks
are parsed; an official test whose input equals a parsed block in canonical
form is RE-KINDED "example" (it becomes a base input). An unmatched parse is
dropped, never added: a mis-parse must not sink a task. When nothing
matches, convert.py promotes the first two official tests to base and
records it. _examples_in_description is set so the prompt builder does not
render the examples a second time.
"""

import argparse
import ast
import datetime
import hashlib
import json
import os
import re
import sys
import time

SOURCE_DATASET = "likaixin/TACO-verified#train"
SOURCE_FILE = "taco_verified.json"
MAX_REFS_PER_CAND = 8
PER_TEST_STORE_CAP = 2_000_000
STORE_BUDGET = 8_000_000
MIN_DISTINCT_TESTS = 5

LICENSE = {
    "dataset_license": "mit (likaixin/TACO-verified card); upstream BAAI/TACO "
                       "apache-2.0 (card)",
    "upstream": "contest problem material of the named site, redistributed by "
                "the datasets; internal training use",
}


def log(msg):
    print("[fetch_taco] %s" % msg, flush=True)


# ------------------------------------------------------------ streaming read

_SEP_RE = re.compile(r"[\s,]*")


def iter_json_array(path, chunk=8 << 20):
    """Yield (index, object) for each element of a top-level JSON array,
    one object resident at a time."""
    dec = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as f:
        buf = f.read(chunk)
        i = buf.index("[") + 1
        idx = 0
        while True:
            while True:
                i = _SEP_RE.match(buf, i).end()
                if i < len(buf):
                    break
                more = f.read(chunk)
                if not more:
                    return
                buf, i = buf[i:] + more, 0
            if buf[i] == "]":
                return
            while True:
                try:
                    obj, end = dec.raw_decode(buf, i)
                    break
                except json.JSONDecodeError:
                    more = f.read(chunk)
                    if not more:
                        raise
                    buf, i = buf[i:] + more, 0
            yield idx, obj
            idx += 1
            i = end
            if i > chunk:
                buf, i = buf[i:], 0


# --------------------------------------------------------------- helpers

def canon(s):
    lines = [l.rstrip() for l in (s or "").replace("\r\n", "\n")
             .replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


_CF_URL_RE = re.compile(
    r"codeforces\.com/(?:problemset/problem/(\d+)/([A-Za-z]\d?)"
    r"|contest/(\d+)/problem/([A-Za-z]\d?)"
    r"|gym/(\d+)/problem/([A-Za-z]\d?))")


def codeforces_key(url):
    m = _CF_URL_RE.search(url or "")
    if not m:
        return None
    g = [x for x in m.groups() if x]
    return "%s/%s" % (g[0], g[1].upper()) if len(g) >= 2 else None


_TL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|sec|seconds?)?", re.I)


def parse_time_limit(s):
    if not s or not isinstance(s, str):
        return None
    m = _TL_RE.search(s)
    if not m:
        return None
    v = float(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit.startswith("m"):
        v /= 1000.0
    if v > 100:            # no contest limit exceeds 100 s: unit was ms
        v /= 1000.0
    return v


def parse_listish(s):
    """TACO stores tags / raw_tags / skill_types as a stringified list."""
    if not s:
        return []
    if isinstance(s, list):
        return s
    try:
        v = ast.literal_eval(s)
        return list(v) if isinstance(v, (list, tuple)) else [str(v)]
    except Exception:
        return [s]


_INTERACTIVE_RE = re.compile(
    r"interactive problem|this is an interactive|\binteractor\b|"
    r"flush the output|fflush\(stdout\)", re.I)
_IMAGE_RE = re.compile(r"\[Image\]|<image>", re.I)

# statement example blocks: marker lines
_IN_MARK = re.compile(
    r"^\s*-*\s*(?:Sample|Example|Examples?)?\s*Input\s*(?:#?\s*\d+)?\s*:?\s*-*\s*$",
    re.I)
_OUT_MARK = re.compile(
    r"^\s*-*\s*(?:Sample|Example|Examples?)?\s*Output\s*(?:#?\s*\d+)?\s*:?\s*-*\s*$",
    re.I)
_HDR_MARK = re.compile(r"^\s*-{2,}\s*[A-Za-z].*-{2,}\s*$|"
                       r"^\s*(?:Note|Explanation|Constraints|Examples?|"
                       r"Scoring|Subtasks?)\s*:?\s*$", re.I)


def statement_example_inputs(question):
    """Canonical forms of the input blocks of the statement's examples."""
    lines = (question or "").replace("\r\n", "\n").split("\n")
    out = []
    n = len(lines)
    k = 0
    while k < n:
        if _IN_MARK.match(lines[k]):
            j = k + 1
            block = []
            while j < n and not (_OUT_MARK.match(lines[j]) or
                                 _IN_MARK.match(lines[j]) or
                                 _HDR_MARK.match(lines[j])):
                block.append(lines[j])
                j += 1
            c = canon("\n".join(block).strip("\n"))
            if c:
                out.append(c)
            k = j
        else:
            k += 1
    return out


def python3_parses(code):
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False


# ---------------------------------------------------------------- records

def build_tests(io, example_inputs):
    """-> (tests, meta, nonstring) with the store caps of fetch_candidates."""
    inputs, outputs = io.get("inputs") or [], io.get("outputs") or []
    kept, total = [], 0
    dropped_n = dropped_b = 0
    seen = set()
    n_source = min(len(inputs), len(outputs))
    ex_set = set(example_inputs)
    n_ex = 0
    n_joined = 0
    for inp, outp in zip(inputs, outputs):
        # Codechef-style records store stdin and stdout as LISTS OF LINES
        # (inputs [["1", "5 10"]], outputs [["50"]]; the solutions read
        # input()): join the lines with "\n", trailing newline on the input
        if isinstance(inp, list) and all(isinstance(x, str) for x in inp):
            inp = "\n".join(inp) + "\n"
            n_joined += 1
        if isinstance(outp, list) and all(isinstance(x, str) for x in outp):
            outp = "\n".join(outp) + "\n"
        if not isinstance(inp, str) or not isinstance(outp, str):
            return None, None, True
        sig = (canon(inp), canon(outp))
        if sig in seen:
            continue
        seen.add(sig)
        kind = "example" if sig[0] in ex_set else "official"
        sz = len(inp) + len(outp)
        if kind != "example" and (sz > PER_TEST_STORE_CAP
                                  or total + sz > STORE_BUDGET):
            dropped_n += 1
            dropped_b += sz
            continue
        if kind == "example":
            n_ex += 1
        kept.append({"input": inp, "output": outp, "kind": kind})
        total += sz
    # examples first: convert.py's select_tests keeps source order and
    # splits by kind, but the record reads better with base first
    kept.sort(key=lambda t: 0 if t["kind"] == "example" else 1)
    meta = {"n_kept": len(kept), "n_dropped_oversize": dropped_n,
            "dropped_bytes": dropped_b, "kept_bytes": total,
            "n_source_total": n_source,
            "n_line_lists_joined": n_joined,
            "n_by_kind": {"example": n_ex, "official": len(kept) - n_ex,
                          "generated": 0}}
    return kept, meta, False


def build_record(idx, r, io, tests, meta, refs, fetched_at, chosen):
    src = (r.get("source") or "").lower() or "unknown"
    url = r.get("url")
    cf = codeforces_key(url)
    problem_key = cf if cf else "%s:%s" % (src, url or r["id"])
    date = r.get("date") if isinstance(r.get("date"), str) else None
    year = None
    if date and re.match(r"^\d{4}", date):
        year = int(date[:4])
    tags = parse_listish(r.get("tags"))
    difficulty = r.get("difficulty") or chosen.get("difficulty")
    title = r.get("name") or chosen.get("name") or (
        url.rstrip("/").split("/")[-1] if url else "taco %s" % r["id"])
    return {
        "cand_id": "taco/%s" % r["id"],
        "problem_key": problem_key,
        "source_dataset": SOURCE_DATASET,
        "source_row": {"file": SOURCE_FILE, "index": idx, "id": r["id"]},
        "title": title,
        "rating": difficulty,
        "tags": tags + ["difficulty:%s" % difficulty, "site:%s" % src],
        "url": url,
        "license": LICENSE,
        "dates": {"contest_start": date, "contest_start_year": year,
                  "fetched_at": fetched_at},
        "time_limit_s": parse_time_limit(r.get("time_limit")),
        "memory_limit": r.get("memory_limit"),
        "input_mode": "stdio",
        "interaction_format": None,
        "has_custom_checker": False,
        "checker_source": None,
        "statement": {"description": r.get("question"),
                      "input_format": None, "output_format": None,
                      "note": None},
        "tests": tests,
        "tests_meta": meta,
        "reference_candidates": refs,
        "duplicate_of": None,
        "_examples_in_description": True,
        "taco": {"difficulty": difficulty, "site": src,
                 "raw_tags": parse_listish(r.get("raw_tags")),
                 "skill_types": parse_listish(r.get("skill_types")),
                 "n_solutions_verified": len(r.get("solutions") or [])},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", required=True, help="taco_verified.json")
    ap.add_argument("--ids-json", required=True,
                    help="pool composition file (training-plan)")
    ap.add_argument("--ids-path", default="sources.taco_verified.problems")
    ap.add_argument("--ids-sha256", default=None)
    ap.add_argument("--live-keys", required=True,
                    help="live Codeforces <contest>/<index> keys, one per line")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--shard-size", type=int, default=25)
    ap.add_argument("--shard-start", type=int, default=0,
                    help="number of the first shard written (a later tranche "
                         "continues the numbering of the earlier one)")
    args = ap.parse_args()

    raw = open(args.ids_json, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    if args.ids_sha256 and sha != args.ids_sha256:
        sys.exit("ids file sha256 %s != expected %s — refusing" %
                 (sha, args.ids_sha256))
    node = json.loads(raw)
    for part in args.ids_path.split("."):
        node = node[part]
    chosen = {}
    order = []
    for row in node:
        i = str(row["id"])
        if i not in chosen:
            chosen[i] = row
            order.append(i)
    log("list of record: %d ids (sha256 %s)" % (len(order), sha[:16]))

    live = set()
    with open(args.live_keys) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                live.add(line)
    log("live Codeforces keys: %d" % len(live))

    os.makedirs(args.outdir, exist_ok=True)
    fetched_at = datetime.datetime.now(datetime.timezone.utc)\
        .isoformat(timespec="seconds")
    t0 = time.time()
    stdio = {}          # id -> record
    fn_form = {}        # id -> raw record (function form)
    excluded = {k: [] for k in ("function_form", "interactive", "image",
                                "contest_twin", "nonstring_io", "few_tests",
                                "no_py3_ref", "not_in_file")}
    seen_ids = set()
    n_scanned = 0
    for idx, r in iter_json_array(args.file):
        n_scanned += 1
        i = str(r.get("id"))
        if i not in chosen:
            continue
        seen_ids.add(i)
        q = r.get("question") or ""
        try:
            io = json.loads(r.get("input_output") or "{}")
        except json.JSONDecodeError:
            io = {}
        if not isinstance(io, dict):
            io = {}
        if "fn_name" in io or (r.get("starter_code") or "").strip():
            excluded["function_form"].append(i)
            fn_form[i] = {"index": idx, "record": r, "chosen": chosen[i]}
            continue
        if _INTERACTIVE_RE.search(q):
            excluded["interactive"].append(i)
            continue
        pn = r.get("picture_num")
        try:
            pn = int(pn) if pn not in (None, "") else 0
        except (TypeError, ValueError):
            pn = 0
        if pn > 0 or _IMAGE_RE.search(q):
            excluded["image"].append(i)
            continue
        cf = codeforces_key(r.get("url"))
        if cf and cf in live:
            excluded["contest_twin"].append(i)
            continue
        tests, meta, nonstring = build_tests(io, statement_example_inputs(q))
        if nonstring:
            excluded["nonstring_io"].append(i)
            continue
        if len(tests) < MIN_DISTINCT_TESTS:
            excluded["few_tests"].append(i)
            continue
        sols = [s for s in (r.get("solutions") or []) if isinstance(s, str)]
        py3 = [s for s in sols if python3_parses(s)]
        if not py3:
            excluded["no_py3_ref"].append(i)
            continue
        py3.sort(key=len)
        refs = [{"code": s, "language": "Python 3",
                 "origin": "likaixin/TACO-verified:solutions",
                 "submission_id": None, "time_ms": None}
                for s in py3[:MAX_REFS_PER_CAND]]
        stdio[i] = build_record(idx, r, io, tests, meta, refs, fetched_at,
                                chosen[i])
    for i in order:
        if i not in seen_ids:
            excluded["not_in_file"].append(i)
    log("scanned %d objects in %.0fs; stdio %d, function form %d, "
        "excluded %s" % (n_scanned, time.time() - t0, len(stdio),
                         len(fn_form),
                         {k: len(v) for k, v in excluded.items()
                          if k != "function_form"}))

    # shards in list order
    ordered = [stdio[i] for i in order if i in stdio]
    shards = []
    for k in range(0, len(ordered), args.shard_size):
        path = os.path.join(args.outdir, "candidates_raw.taco.s%03d.jsonl"
                            % (args.shard_start + len(shards)))
        with open(path + ".tmp", "w") as f:
            for rec in ordered[k:k + args.shard_size]:
                f.write(json.dumps(rec) + "\n")
        os.replace(path + ".tmp", path)
        shards.append({"path": path,
                       "n": len(ordered[k:k + args.shard_size]),
                       "ids": [rec["cand_id"] for rec in
                               ordered[k:k + args.shard_size]]})
    fn_path = os.path.join(args.outdir, "candidates_fn.taco.jsonl")
    with open(fn_path + ".tmp", "w") as f:
        for i in order:
            if i in fn_form:
                f.write(json.dumps(fn_form[i]) + "\n")
    os.replace(fn_path + ".tmp", fn_path)

    report = {
        "fetched_at": fetched_at, "source_dataset": SOURCE_DATASET,
        "source_file": SOURCE_FILE, "ids_json": args.ids_json,
        "ids_json_sha256": sha, "n_listed": len(order),
        "n_scanned": n_scanned, "n_stdio_records": len(ordered),
        "n_function_form": len(fn_form),
        "excluded_counts": {k: len(v) for k, v in excluded.items()},
        "excluded_ids": excluded,
        "shards": shards, "function_form_file": fn_path,
        "elapsed_s": round(time.time() - t0, 1),
    }
    rp = os.path.join(args.outdir, "fetch_report.json")
    with open(rp + ".tmp", "w") as f:
        json.dump(report, f, indent=1)
    os.replace(rp + ".tmp", rp)
    log("wrote %d shards (%d records) + %d function-form records -> %s"
        % (len(shards), len(ordered), len(fn_form), args.outdir))


if __name__ == "__main__":
    main()

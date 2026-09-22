#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyarrow>=15", "huggingface_hub>=0.23"]
# ///
"""Acquisition step 1: pull + filter hard contest problems from two vetted
HuggingFace sources into candidates_raw.jsonl (provenance included).

Sources (exact ids; both CC-BY-4.0 dataset cards; underlying problems are
Codeforces material — recorded per candidate):

  1. open-r1/codeforces, config "verifiable"  (8,338 train + 422 test)
     - official regenerated test suites inline (validated by >=3 agreeing
       human solutions), rating, tags, contest date, checker field.
     - NO reference solutions in this config; references are joined from
       open-r1/codeforces-submissions (selected_accepted first, then the
       12.5M-row default config via footer-stat targeted reads).
  2. ByteDance-Seed/Code-Contests-Plus, config dir "ccplus_1x"  (11,690)
     - materialized 1x test suites + ~100 correct submissions per problem
       (Python among them), testlib checker/validator text.
     - NO rating column; ratings joined from open-r1/codeforces by
       (contest, index). Non-Codeforces rows have no rating -> skipped.

Everything is fetched with parquet column projection / targeted row-group
reads over HfFileSystem — no full-dataset download (the 1x config alone is
46 GB). All network happens here; convert.py is offline.

Usage:
  uv run fetch_candidates.py --smoke                       # ~12 candidates
  uv run fetch_candidates.py --limit-openr1 120 --limit-ccplus 80
Output: candidates_raw.jsonl (+ fetch_report.json) in --outdir.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

OPENR1 = "open-r1/codeforces"
CCPLUS = "ByteDance-Seed/Code-Contests-Plus"
SUBS = "open-r1/codeforces-submissions"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTDIR = os.path.join(HERE, "artifacts")
CACHE_DIR = os.path.join(HERE, "cache")

MIN_RATING = 2200
REF_RICH_MAX_CONTEST = 1820
PER_TEST_STORE_CAP = 2_000_000     # bytes; single test larger than this -> dropped
STORE_BUDGET = 8_000_000           # bytes of tests stored per candidate (raw)
MAX_REFS_PER_CAND = 8              # python reference candidates kept
PY_LANG_RE = re.compile(r"py", re.I)

def _lang_pref(lang):
    l = lang.lower()
    if "python 3" in l or l in ("python3", "py3"):
        return 0
    if "pypy 3" in l:
        return 1
    if "py2" in l or "python 2" in l:
        return 3        # py2 refs rarely parse as py3; last resort
    return 2


# CC+ stores time limits in milliseconds; known sentinel: ccplus/1366_F
# (CF 1366F) = 2 s. No contest time limit exceeds 100 s, so any raw value
# above 100 is milliseconds by construction.
CC_TIME_LIMIT_SENTINEL = ("1366/F", 2.0)


def _cc_time_limit_s(raw):
    if isinstance(raw, (int, float)):
        return raw / 1000.0 if raw > 100 else float(raw)
    return raw


def _assert_time_limit_unit(records):
    """Fail loudly if the stored unit contradicts the sentinel or the
    100 s ceiling (unit is a noun: time_limit_s must be seconds)."""
    for r in records:
        tl = r.get("time_limit_s")
        if isinstance(tl, (int, float)) and tl > 100:
            raise SystemExit("UNIT ASSERT: %s time_limit_s=%s > 100 s — source "
                             "unit changed? (expected seconds)" % (r["cand_id"], tl))
        if r.get("problem_key") == CC_TIME_LIMIT_SENTINEL[0] and \
                isinstance(tl, (int, float)) and abs(tl - CC_TIME_LIMIT_SENTINEL[1]) > 1e-9:
            raise SystemExit("UNIT ASSERT: sentinel %s stored %s s, expected %s s"
                             % (r["cand_id"], tl, CC_TIME_LIMIT_SENTINEL[1]))


fs = HfFileSystem()


def log(msg):
    print("[fetch] %s" % msg, flush=True)


class Meter:
    """Rough transfer meter: sums compressed column-chunk bytes we request."""
    def __init__(self):
        self.bytes = 0
        self.requests = 0

    def add(self, n, req=1):
        self.bytes += n
        self.requests += req


METER = Meter()


def _rg_col_bytes(md, rg, columns):
    total = 0
    r = md.row_group(rg)
    want = set(columns)
    for i in range(r.num_columns):
        if r.column(i).path_in_schema.split(".")[0] in want:
            total += r.column(i).total_compressed_size
    return total


def read_row_groups(path, rgs, columns, rows_wanted=None, batch_size=8):
    """Read `columns` of the given row groups; returns list-of-dict rows."""
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f, pre_buffer=True)
        md = pf.metadata
        out = []
        for g in rgs:
            METER.add(_rg_col_bytes(md, g, columns))
            want = None if rows_wanted is None else set(rows_wanted.get(g, []))
            off = 0
            for batch in pf.iter_batches(batch_size=batch_size,
                                         row_groups=[g], columns=columns):
                n = batch.num_rows
                if want is None:
                    out.extend(batch.to_pylist())
                else:
                    sel = [i - off for i in range(off, off + n) if i in want]
                    if sel:
                        out.extend(batch.take(pa.array(sel)).to_pylist())
                del batch
                off += n
        return out


def read_rows_lean(path, g, col_groups, rows_wanted):
    """Memory-lean heavy fetch: read one row group in several column
    passes (each pass holds only its columns in Arrow), subset the wanted
    rows immediately, and merge the passes by row order."""
    merged = None
    for cols in col_groups:
        rows = read_row_groups(path, [g], cols, {g: rows_wanted})
        if merged is None:
            merged = [dict(r) for r in rows]
        else:
            for m, r in zip(merged, rows):
                m.update(r)
    return merged or []


def read_rows_lean_cached(path, g, col_groups, rows_wanted):
    import hashlib
    key_src = "%s|%d|%s|%s" % (path, g, sorted(rows_wanted),
                               [sorted(c) for c in col_groups])
    key = hashlib.md5(key_src.encode()).hexdigest()
    cdir = os.path.join(HERE, "cache", "heavy")
    os.makedirs(cdir, exist_ok=True)
    cpath = os.path.join(cdir, key + ".json")
    if os.path.exists(cpath):
        with open(cpath) as f:
            return json.load(f)
    rows = read_rows_lean(path, g, col_groups, rows_wanted)
    tmp = cpath + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, default=str)
    os.replace(tmp, cpath)
    return rows


def file_metadata(path):
    with fs.open(path, "rb") as f:
        return pq.ParquetFile(f).metadata


def scan_file_light(path, columns):
    """Read light columns of a whole file; rows annotated with location."""
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f, pre_buffer=True)
        md = pf.metadata
        rows = []
        for g in range(md.num_row_groups):
            METER.add(_rg_col_bytes(md, g, columns))
            t = pf.read_row_group(g, columns=columns)
            for k, r in enumerate(t.to_pylist()):
                r["_file"] = path
                r["_rg"] = g
                r["_row_in_rg"] = k
                rows.append(r)
        return rows


def parallel_scan(paths, columns, jobs=8):
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for part in ex.map(lambda p: scan_file_light(p, columns), paths):
            rows.extend(part)
    return rows


# --------------------------------------------------------------- open-r1

OPENR1_LIGHT = ["id", "contest_id", "index", "contest_name", "contest_start",
                "contest_start_year", "rating", "tags", "title", "time_limit",
                "memory_limit", "input_mode", "executable",
                "official_tests_complete", "testset_size", "generated_tests"]
OPENR1_HEAVY = ["id", "description", "input_format", "output_format",
                "interaction_format", "note", "examples", "official_tests",
                "generated_checker"]


def openr1_files(smoke):
    files = sorted(fs.glob("datasets/%s/verifiable/*.parquet" % OPENR1))
    if smoke:
        # the two smallest files (27 MB test split = freshest contests,
        # 26 MB train-00007) keep the smoke transfer tiny
        files = [p for p in files if "test-00000" in p or "train-00007" in p]
    return files


def scan_openr1(smoke, jobs):
    t0 = time.time()
    files = openr1_files(smoke)
    rows = parallel_scan(files, OPENR1_LIGHT, jobs)
    log("open-r1 light scan: %d rows from %d files (%.0fs)"
        % (len(rows), len(files), time.time() - t0))
    return rows


def scan_openr1_default_ratings(jobs):
    """Rating/date join map from the default config (superset of problems,
    parquet files under data/)."""
    cache = os.path.join(CACHE_DIR, "openr1_default_ratings.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    files = sorted(fs.glob("datasets/%s/data/*.parquet" % OPENR1))
    cols = ["contest_id", "index", "rating", "contest_start",
            "contest_start_year"]
    rows = parallel_scan(files, cols, jobs)
    m = {}
    for r in rows:
        if r.get("rating") is None:
            continue
        key = "%s/%s" % (r["contest_id"], r["index"])
        m[key] = {"rating": r["rating"], "contest_start": r["contest_start"],
                  "contest_start_year": r["contest_start_year"]}
    if m:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(m, f)
    log("open-r1 default rating map: %d rated problems (cached=%s)"
        % (len(m), bool(m)))
    return m


def fetch_generated_tests(problem_keys, jobs):
    """{problem_key: [{input, output}]} from generated_tests/ (per-contest
    parquet files; these are the suites validated by >=3 agreeing accepted
    human solutions — the actual verifiable-subset oracle)."""
    files = fs.glob("datasets/%s/generated_tests/*.parquet" % OPENR1)
    by_contest = {}
    for p in files:
        m = re.search(r"test_cases_0*(\d+)\.parquet$", p)
        if m:
            by_contest[m.group(1)] = p
    contests = sorted({k.split("/")[0] for k in problem_keys})
    wanted = set(problem_keys)
    out = {}

    def one(contest):
        path = by_contest.get(contest)
        if not path:
            return contest, {}
        with fs.open(path, "rb") as f:
            pf = pq.ParquetFile(f, pre_buffer=True)
            METER.add(sum(_rg_col_bytes(pf.metadata, g,
                                        ["problem_id", "input", "output"])
                          for g in range(pf.metadata.num_row_groups)))
            t = pf.read(columns=["problem_id", "input", "output"])
        part = {}
        for r in t.to_pylist():
            if r["problem_id"] in wanted:
                part.setdefault(r["problem_id"], []).append(
                    {"input": r["input"], "output": r["output"]})
        return contest, part

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for contest, part in ex.map(one, contests):
            for k, v in part.items():
                out[k] = v
    missing = [c for c in contests if c not in by_contest]
    if missing:
        log("generated_tests: no file for contests %s" % missing[:8])
    return out


# ------------------------------------------------------------------- CC+

CCPLUS_LIGHT = ["id", "source", "title", "time_limit", "memory_limit",
                "true_positive_rate", "true_negative_rate"]
CCPLUS_HEAVY = ["id", "description", "test_cases", "correct_submissions",
                "checker"]


def ccplus_files(smoke):
    files = sorted(fs.glob("datasets/%s/ccplus_1x/*.parquet" % CCPLUS))
    if smoke:
        files = files[:2]
    return files


def scan_ccplus(smoke, jobs):
    t0 = time.time()
    files = ccplus_files(smoke)
    cache = os.path.join(
        CACHE_DIR, "ccplus_light_%s.json" % ("smoke" if smoke else "full"))
    if os.path.exists(cache):
        with open(cache) as f:
            rows = json.load(f)
        log("ccplus light scan: %d rows (from cache)" % len(rows))
        return rows
    rows = parallel_scan(files, CCPLUS_LIGHT, jobs)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(rows, f)
    log("ccplus light scan: %d rows from %d files (%.0fs)"
        % (len(rows), len(files), time.time() - t0))
    return rows


def ccplus_rg_costs(files):
    """{(path, rg): compressed heavy-column bytes} from footers only."""
    cache = os.path.join(CACHE_DIR, "ccplus_rg_costs.json")
    costs = {}
    if os.path.exists(cache):
        with open(cache) as f:
            costs = {tuple(json.loads(k)): v
                     for k, v in json.load(f).items()}
    todo = [p for p in files if not any(k[0] == p for k in costs)]
    for path in todo:
        md = file_metadata(path)
        for g in range(md.num_row_groups):
            r = md.row_group(g)
            tot = 0
            for i in range(r.num_columns):
                base = r.column(i).path_in_schema.split(".")[0]
                if base in CCPLUS_HEAVY:
                    tot += r.column(i).total_compressed_size
            costs[(path, g)] = tot
    if todo:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache, "w") as f:
            json.dump({json.dumps(list(k)): v for k, v in costs.items()}, f)
    return costs


CC_ID_RE = re.compile(r"^(\d+)_(\S+)$")


def ccplus_problem_key(cc_id):
    m = CC_ID_RE.match(cc_id or "")
    return "%s/%s" % (m.group(1), m.group(2)) if m else None


# ------------------------------------- references from codeforces-submissions

SUBS_LIGHT = ["contestId", "problem_index", "programmingLanguage", "verdict",
              "timeConsumedMillis", "submission_id"]


def subs_rg_index(jobs):
    """Per (file, rg): lexical contestId min/max from parquet footers only."""
    cache = os.path.join(CACHE_DIR, "submissions_rg_index.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    files = sorted(fs.glob("datasets/%s/data/*.parquet" % SUBS))

    def one(path):
        md = file_metadata(path)
        names = {md.row_group(0).column(i).path_in_schema: i
                 for i in range(md.row_group(0).num_columns)}
        ci = names["contestId"]
        ent = []
        for g in range(md.num_row_groups):
            s = md.row_group(g).column(ci).statistics
            ent.append([g, s.min if s else None, s.max if s else None])
        return path, ent

    index = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for path, ent in ex.map(one, files):
            index[path] = ent
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(index, f)
    log("submissions footer index: %d files (cached)" % len(index))
    return index


def load_selected_accepted():
    """problem_id -> [{code, language, ...}] for the small curated config
    (74 MB single file; only ~157 problems have a Python sub, but free)."""
    cache = os.path.join(CACHE_DIR, "selected_accepted_python.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    path = "datasets/%s/selected_accepted/train-00000-of-00001.parquet" % SUBS
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f, pre_buffer=True)
        t = pf.read(columns=["problem_id", "programmingLanguage", "verdict",
                             "timeConsumedMillis", "source", "submission_id"])
        METER.add(74_000_000)
    m = {}
    for r in t.to_pylist():
        if r["verdict"] == "OK" and PY_LANG_RE.search(
                r["programmingLanguage"] or ""):
            m.setdefault(r["problem_id"], []).append({
                "code": r["source"], "language": r["programmingLanguage"],
                "origin": "%s:selected_accepted" % SUBS,
                "submission_id": r["submission_id"],
                "time_ms": r["timeConsumedMillis"]})
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(m, f)
    log("selected_accepted: python refs for %d problems (cached)" % len(m))
    return m


def subs_light_hits(problem_keys, index, jobs):
    """Light pass over the 12.5M-row submissions config: footer-targeted
    row-group reads; returns {problem_key: [(path, rg, row_in_rg, lang,
    time_ms, subid)]} for accepted Python submissions only."""
    contests = {k.split("/")[0] for k in problem_keys}
    # (file, rg) -> contests possibly inside (lexical string range)
    targets = {}
    for path, ents in index.items():
        for g, lo, hi in ents:
            if lo is None:
                continue
            for c in contests:
                if lo <= c <= hi:
                    targets.setdefault((path, g), set()).add(c)
    wanted = set(problem_keys)
    hits = {}   # problem_key -> [(path, rg, row_in_rg, lang, time_ms, subid)]

    def light_rg(args):
        path, g = args
        rows = read_row_groups(path, [g], SUBS_LIGHT)
        out = []
        for k, r in enumerate(rows):
            key = "%s/%s" % (r["contestId"], r["problem_index"])
            if key in wanted and r["verdict"] == "OK" and \
                    PY_LANG_RE.search(r["programmingLanguage"] or ""):
                out.append((key, path, g, k, r["programmingLanguage"],
                            r["timeConsumedMillis"], r["submission_id"]))
        return out

    rg_list = sorted(targets)
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for out in ex.map(light_rg, rg_list):
            for key, path, g, k, lang, tms, sid in out:
                hits.setdefault(key, []).append((path, g, k, lang, tms, sid))
    log("submissions light pass: scanned %d rgs (%d contests), python-OK "
        "hits for %d/%d problems (%.0fs)"
        % (len(rg_list), len(contests), len(hits), len(wanted),
           time.time() - t0))
    return hits


def fetch_submission_sources(hits, jobs):
    """Source pass: pick up to MAX_REFS per problem, preferring CPython
    then fastest, and read source only for the needed row groups."""
    chosen = {}
    need_rgs = {}
    for key, lst in hits.items():
        lst = sorted(lst, key=lambda x: (_lang_pref(x[3]), x[4] or 0))
        chosen[key] = lst[:MAX_REFS_PER_CAND]
        for path, g, k, *_ in chosen[key]:
            need_rgs.setdefault((path, g), set()).add(k)

    def src_rg(args):
        (path, g), rows_wanted = args
        rows = read_row_groups(path, [g], ["source", "contestId",
                                           "problem_index", "submission_id"])
        return {(path, g, k): rows[k] for k in rows_wanted}

    src = {}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for part in ex.map(src_rg, sorted(need_rgs.items())):
            src.update(part)
    log("submissions source pass: %d rgs (%.0fs)"
        % (len(need_rgs), time.time() - t0))

    refs = {}
    for key, lst in chosen.items():
        for path, g, k, lang, tms, sid in lst:
            r = src.get((path, g, k))
            if not r or not r.get("source"):
                continue
            refs.setdefault(key, []).append({
                "code": r["source"], "language": lang,
                "origin": "%s:default" % SUBS,
                "submission_id": sid, "time_ms": tms})
    return refs


# --------------------------------------------------------------- assembling

def canon_tests(groups):
    """groups = [(kind, tests)]. Apply per-test and total store caps.
    Returns (kept, dropped_n, dropped_bytes, total_bytes). Examples are
    always kept (they are small)."""
    kept, total = [], 0
    dropped_n = dropped_b = 0
    seen = set()
    for kind, tests in groups:
        for t in tests or []:
            inp, out = t.get("input") or "", t.get("output") or ""
            sig = (hash(inp), hash(out))
            if sig in seen:
                continue
            seen.add(sig)
            sz = len(inp) + len(out)
            if kind != "example" and (sz > PER_TEST_STORE_CAP
                                      or total + sz > STORE_BUDGET):
                dropped_n += 1
                dropped_b += sz
                continue
            kept.append(dict(t, _kind=kind))
            total += sz
    return kept, dropped_n, dropped_b, total


def _iso(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            int(ts), datetime.timezone.utc).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def build_record(kind, meta, heavy, refs, rating_info, fetched_at,
                 dup_of=None, gen_tests=None):
    contest, index = meta["_key"].split("/", 1)
    official = heavy.get("official_tests") or heavy.get("test_cases") or []
    examples = heavy.get("examples") or []
    groups = [("example", examples), ("official", official),
              ("generated", gen_tests or [])]
    kept, dn, db, total = canon_tests(groups)
    rec = {
        "cand_id": "%s/%s_%s" % (kind, contest, index),
        "problem_key": meta["_key"],
        "source_dataset": (OPENR1 + "#verifiable") if kind == "openr1"
                          else (CCPLUS + "#ccplus_1x"),
        "source_row": {"file": meta["_file"], "rg": meta["_rg"],
                       "row_in_rg": meta["_row_in_rg"]},
        "title": meta.get("title"),
        "rating": rating_info.get("rating"),
        "tags": meta.get("tags"),
        "url": "https://codeforces.com/contest/%s/problem/%s"
               % (contest, index),
        "license": {
            "dataset_license": "cc-by-4.0",
            "upstream": "Codeforces problem material, redistributed by the dataset under CC BY 4.0",
        },
        "dates": {
            "contest_start": _iso(rating_info.get("contest_start")),
            "contest_start_year": rating_info.get("contest_start_year"),
            "fetched_at": fetched_at,
        },
        "time_limit_s": _cc_time_limit_s(meta.get("time_limit")),
        "memory_limit": meta.get("memory_limit"),
        "input_mode": meta.get("input_mode"),
        "interaction_format": (heavy.get("interaction_format") or "").strip()
                              or None,
        "has_custom_checker": bool((heavy.get("generated_checker")
                                    or heavy.get("checker") or "").strip()),
        "checker_source": kind == "ccplus" and "ccplus_testlib" or (
            "openr1_generated" if (heavy.get("generated_checker") or "").strip()
            else None),
        "statement": {
            "description": heavy.get("description"),
            "input_format": heavy.get("input_format"),
            "output_format": heavy.get("output_format"),
            "note": heavy.get("note"),
        },
        "tests": [{"input": t.get("input"), "output": t.get("output"),
                   "kind": t["_kind"]} for t in kept],
        "tests_meta": {"n_kept": len(kept), "n_dropped_oversize": dn,
                       "dropped_bytes": db, "kept_bytes": total,
                       "n_source_total": sum(len(g or []) for _, g in groups),
                       "n_by_kind": {k: sum(1 for t in kept
                                            if t["_kind"] == k)
                                     for k in ("example", "official",
                                               "generated")}},
        "reference_candidates": refs[:MAX_REFS_PER_CAND],
        "duplicate_of": dup_of,
    }
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="small quotas, cheapest files only")
    ap.add_argument("--min-rating", type=int, default=MIN_RATING)
    ap.add_argument("--max-rating", type=int, default=None,
                    help="inclusive rating cap (band fetches, e.g. the "
                    "mid band 1500-2100)")
    ap.add_argument("--limit-openr1", type=int, default=None)
    ap.add_argument("--limit-ccplus", type=int, default=None)
    ap.add_argument("--jobs", type=int, default=2,
                    help="I/O threads for LIGHT scans only (heavy reads are "
                         "always sequential)")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--out", default=None,
                    help="output jsonl (default <outdir>/candidates_raw.jsonl)")
    ap.add_argument("--skip-ccplus", action="store_true")
    ap.add_argument("--skip-openr1", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.limit_openr1 = args.limit_openr1 or 7
        args.limit_ccplus = args.limit_ccplus or 5
    else:
        args.limit_openr1 = args.limit_openr1 or 120
        args.limit_ccplus = args.limit_ccplus or 80

    os.makedirs(args.outdir, exist_ok=True)
    out_path = args.out or os.path.join(
        args.outdir,
        "candidates_raw%s.jsonl" % (".smoke" if args.smoke else ""))
    fetched_at = datetime.datetime.now(datetime.timezone.utc)\
        .isoformat(timespec="seconds")
    t_start = time.time()
    report = {"fetched_at": fetched_at, "min_rating": args.min_rating,
              "max_rating": args.max_rating,
              "smoke": args.smoke, "sources": {}}

    rating_map = scan_openr1_default_ratings(args.jobs)

    records = []
    openr1_keys = set()

    # ---------------- source 1: open-r1/codeforces verifiable
    if not args.skip_openr1:
        rows = scan_openr1(args.smoke, args.jobs)
        for r in rows:
            r["_key"] = "%s/%s" % (r["contest_id"], r["index"])
        elig = [r for r in rows
                if (r.get("rating") or 0) >= args.min_rating
                and (args.max_rating is None
                     or (r.get("rating") or 0) <= args.max_rating)
                and r.get("input_mode") == "stdio"
                and ((r.get("testset_size") or 0) > 0
                     or (r.get("generated_tests") or 0) > 0)]
        # freshest first (contamination bookkeeping favors recent problems)
        elig.sort(key=lambda r: -(r.get("contest_start") or 0))

        subs_idx = subs_rg_index(args.jobs)
        subs_max = max((int(hi) for ents in subs_idx.values()
                        for _, lo, hi in ents
                        if hi and str(hi).isdigit()), default=0)
        log("open-r1: submissions corpus covers contests <= %d" % subs_max)
        curated = load_selected_accepted()

        def _cap2(rows_iter):
            seen = {}
            for r in rows_iter:
                c = r["contest_id"]
                if seen.get(c, 0) >= 2:          # family cap: 2 per contest
                    continue
                seen[c] = seen.get(c, 0) + 1
                yield r

        fresh_quota = max(1, args.limit_openr1 // 4)
        ref_quota = args.limit_openr1 - fresh_quota
        rich = [r for r in _cap2(elig)
                if r["contest_id"].isdigit()
                and int(r["contest_id"]) <= REF_RICH_MAX_CONTEST]
        mid = [r for r in _cap2(elig)
               if r["contest_id"].isdigit()
               and REF_RICH_MAX_CONTEST < int(r["contest_id"]) <= subs_max]
        walk = rich + mid            # freshest-first within each era
        ref_backed, all_hits, cursor = [], {}, 0
        probe_cap = 6 * args.limit_openr1
        while len(ref_backed) < ref_quota and cursor < len(walk) \
                and cursor < probe_cap:
            batch = walk[cursor:cursor + max(2 * ref_quota, 8)]
            cursor += len(batch)
            hits = subs_light_hits([r["_key"] for r in batch],
                                   subs_idx, args.jobs)
            all_hits.update(hits)
            for r in batch:
                if (r["_key"] in hits or r["_key"] in curated) \
                        and len(ref_backed) < ref_quota:
                    ref_backed.append(r)
        fresh = [r for r in _cap2(elig) if r not in ref_backed]
        sel = ref_backed + fresh[:args.limit_openr1 - len(ref_backed)]
        log("open-r1: %d/%d rows eligible (rating>=%d, stdio, has tests); "
            "probed %d, taking %d ref-backed + %d fresh/no-ref"
            % (len(elig), len(rows), args.min_rating, cursor,
               len(ref_backed), len(sel) - len(ref_backed)))

        sel_keys = [r["_key"] for r in sel]
        refs = {k: list(curated.get(k, [])) for k in sel_keys}
        src_refs = fetch_submission_sources(
            {k: v for k, v in all_hits.items() if k in set(sel_keys)},
            args.jobs)
        for k, v in src_refs.items():
            refs[k] = refs.get(k, []) + v
        n_with_refs = sum(1 for k in sel_keys if refs.get(k))
        log("open-r1: python references fetched for %d/%d selected"
            % (n_with_refs, len(sel_keys)))

        # full validated test suites (per-contest generated_tests files)
        gen_tests = fetch_generated_tests(sel_keys, args.jobs)
        log("open-r1: generated tests found for %d/%d selected (median %d "
            "tests)" % (len(gen_tests), len(sel_keys),
                        sorted(len(v) for v in gen_tests.values())
                        [len(gen_tests) // 2] if gen_tests else 0))

        by_loc = {}
        for r in sel:
            by_loc.setdefault((r["_file"], r["_rg"]), []).append(r)
        t0 = time.time()
        for (path, g), group in sorted(by_loc.items()):
            t1 = time.time()
            heavy_rows = read_rows_lean_cached(
                path, g,
                [["id", "description", "input_format", "output_format",
                  "interaction_format", "note", "examples",
                  "generated_checker"],
                 ["id", "official_tests"]],
                [r["_row_in_rg"] for r in group])
            log("  open-r1 heavy %s#%d: %d rows (%.0fs)"
                % (path.split("/")[-1], g, len(heavy_rows),
                   time.time() - t1))
            by_id = {}
            for hr in heavy_rows:
                by_id[hr["id"]] = hr
            for r in group:
                h = by_id.get(r["id"])
                if not h:
                    continue
                ri = {"rating": r.get("rating"),
                      "contest_start": r.get("contest_start"),
                      "contest_start_year": r.get("contest_start_year")}
                records.append(build_record(
                    "openr1", r, h, refs.get(r["_key"], []), ri, fetched_at,
                    gen_tests=gen_tests.get(r["_key"])))
                openr1_keys.add(r["_key"])
        report["sources"]["openr1"] = {
            "dataset": OPENR1 + "#verifiable",
            "rows_scanned": len(rows), "eligible": len(elig),
            "selected": len(sel), "with_python_refs": n_with_refs}

    # ---------------- source 2: Code-Contests-Plus 1x
    if not args.skip_ccplus:
        rows = scan_ccplus(args.smoke, args.jobs)
        elig = []
        n_cf = n_rated = 0
        for r in rows:
            if (r.get("source") or "") != "Codeforces":
                continue
            n_cf += 1
            key = ccplus_problem_key(r.get("id"))
            if not key or key not in rating_map:
                continue
            n_rated += 1
            info = rating_map[key]
            if (info.get("rating") or 0) < args.min_rating:
                continue
            if args.max_rating is not None and \
                    (info.get("rating") or 0) > args.max_rating:
                continue
            r["_key"] = key
            r["_rating_info"] = info
            elig.append(r)
        fresh_first = sorted(
            elig, key=lambda r: -(r["_rating_info"].get("contest_start") or 0))
        if args.smoke:
            # each CC+ row group costs 100-400 MB (heavy cols, compressed);
            # in smoke, walk cheapest row groups first (footer stats only)
            costs = ccplus_rg_costs({r["_file"] for r in fresh_first})
            fresh_first.sort(key=lambda r: costs.get(
                (r["_file"], r["_rg"]), 1 << 60))
        max_rgs = 2 if args.smoke else 10**9
        sel, dups, dup_taken = [], 0, 0
        per_contest, open_rgs = {}, set()
        for allow_dups in (False, True):
            for r in fresh_first:
                if len(sel) >= args.limit_ccplus:
                    break
                if r in sel:
                    continue
                if (r["_key"] in openr1_keys) != allow_dups:
                    if not allow_dups:
                        dups += 1
                    continue
                c = r["_key"].split("/")[0]
                if per_contest.get(c, 0) >= 2:
                    continue
                rg = (r["_file"], r["_rg"])
                if rg not in open_rgs and len(open_rgs) >= max_rgs:
                    continue
                open_rgs.add(rg)
                per_contest[c] = per_contest.get(c, 0) + 1
                if allow_dups:
                    r["_dup"] = True
                    dup_taken += 1
                sel.append(r)
            if sel and len(sel) >= args.limit_ccplus:
                break
        log("ccplus: %d rows scanned, %d Codeforces, %d rated, %d eligible "
            ">=%d; taking %d (skipped %d open-r1 duplicates, kept %d marked)"
            % (len(rows), n_cf, n_rated, len(elig), args.min_rating,
               len(sel), dups, dup_taken))

        by_loc = {}
        for r in sel:
            by_loc.setdefault((r["_file"], r["_rg"]), []).append(r)
        log("ccplus heavy fetch: %d row groups, sequential" % len(by_loc))
        for (path, g), group in sorted(by_loc.items()):
            t1 = time.time()
            heavy_rows = read_rows_lean_cached(
                path, g,
                [["id", "description", "checker", "correct_submissions"],
                 ["id", "test_cases"]],
                [r["_row_in_rg"] for r in group])
            log("  ccplus %s#%d: %d rows (%.0fs)"
                % (path.split("/")[-1], g, len(heavy_rows), time.time() - t1))
            by_id = {hr["id"]: hr for hr in heavy_rows}
            for r in group:
                h = by_id.get(r["id"])
                if not h:
                    continue
                subs = h.get("correct_submissions") or []
                pyrefs = [{"code": s["code"], "language": s["language"],
                           "origin": CCPLUS + ":correct_submissions",
                           "submission_id": None, "time_ms": None}
                          for s in subs
                          if PY_LANG_RE.search(s.get("language") or "")]
                pyrefs.sort(key=lambda s: (_lang_pref(s["language"]),
                                           len(s["code"])))
                records.append(build_record(
                    "ccplus", r, h, pyrefs, r["_rating_info"], fetched_at,
                    dup_of=("openr1/" + r["_key"].replace("/", "_"))
                    if r.get("_dup") else None))
        report["sources"]["ccplus"] = {
            "dataset": CCPLUS + "#ccplus_1x",
            "rows_scanned": len(rows), "codeforces_rows": n_cf,
            "rated_rows": n_rated, "eligible": len(elig),
            "selected": len(sel), "openr1_duplicates_skipped": dups}

    _assert_time_limit_unit(records)

    with open(out_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    report["n_records"] = len(records)
    report["elapsed_s"] = round(time.time() - t_start, 1)
    report["approx_transfer_mb"] = round(METER.bytes / 1e6, 1)
    report_path = os.path.join(
        args.outdir, "fetch_report%s.json" % (".smoke" if args.smoke else ""))
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    log("wrote %d candidates -> %s" % (len(records), out_path))
    log("report -> %s (elapsed %.0fs, ~%.0f MB column data)"
        % (report_path, report["elapsed_s"], METER.bytes / 1e6))


if __name__ == "__main__":
    main()

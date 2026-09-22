#!/usr/bin/env python3
"""Match rule (exact, no content heuristics): key (task_id, sample) in the family index; if several raws carry the
key, prefer the unit's own bench, then the unique candidate agreeing with the delivered stop_reason/answer_empty;
otherwise the row is 'ambiguous' and gets raw_ref/raw_sha256 null. Unmatched/ambiguous counts go to the report.
Instrument check (orthogonal to the join): delivered stop_reason / answer_empty vs the raw's — mismatches counted.
"""
import argparse, glob, hashlib, json, os, random, re, shutil, sys, time
from collections import Counter, defaultdict

CLAUDE_V1 = {"haiku", "haiku-thinking", "sonnet", "sonnet-thinking"}
OPUS = {"opus", "opus-thinking"}
API = {"gpt-5-mini", "gpt-5-nano", "gemini-3.6-flash", "gemini-3.5-flash-lite"}
CODE_RE = re.compile(r"^\s*(async\s+)?def |^\s*class |^\s*@|\w+\s*=\s*lambda\b", re.M)
THINK_RE = re.compile(r"<think>.*?</think>", re.S)  # closed <think> spans only — exactly what the extractor of record strips; <thinking>/<reasoning>/<details> are NOT stripped (they stay part of the answer for both readings)


def code_presence(text):
    """(has_code_in_answer, code_in_thinking_only): thinking is never the answer (rule of record)."""
    answer = THINK_RE.sub("", text or "")
    in_answer = bool(CODE_RE.search(answer))
    anywhere = bool(CODE_RE.search(text or ""))
    return in_answer, (anywhere and not in_answer)
SHAPES = ("attempt", "cut_at_cap_partial", "cut_at_cap_empty", "refused", "stopped_before_code", "no_code", "empty_other")


def shape_of(stop, empty, has_code):
    if stop == "refusal":
        return "refused"
    if stop in ("max_tokens", "length", "MAX_TOKENS"):
        return "cut_at_cap_empty" if empty else "cut_at_cap_partial"
    if stop == "stop_sequence" and not has_code:
        return "stopped_before_code"
    if empty:
        return "empty_other"
    if not has_code:
        return "no_code"  # ended normally (end_turn/stop) with text but no program in the answer part — prose by choice
    return "attempt"


PROVIDER = {"gpt-5-mini": "openai", "gpt-5-nano": "openai", "gemini-3.6-flash": "gemini", "gemini-3.5-flash-lite": "gemini"}


def cid(task_id, sidx):  # byte-for-byte copy of claude_gen.cid (shared by openai_gen / gemini_gen)
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)
    suffix = f"__s{sidx:03d}"
    if len(base) + len(suffix) > 64:
        digest = hashlib.sha1(task_id.encode()).hexdigest()[:8]
        base = base[: 64 - len(suffix) - 9] + "-" + digest
    return base + suffix


def family(arm, shard):
    if arm in CLAUDE_V1:
        return "bg" if re.search(r"_p\d$", shard) else "p2"
    if arm in OPUS:
        return "fo"
    if arm in API:
        return "c3" if shard.endswith("_c3") else "pa"
    return None


def row_key(r):
    t = r["task_id"]
    m = re.search(r"~r(\d+)$", t)
    if m:
        return t[: m.start()], int(m.group(1))
    return t, int(r["sample"])


def index_files(files, rel_of):
    """(task_id, sample) -> [(rel_raw_file, line, bench, sha, stop, empty)]"""
    idx = defaultdict(list)
    for p in files:
        rel = rel_of(p)
        bench = os.path.basename(p).replace(".completions.jsonl", "")
        with open(p) as f:
            for i, l in enumerate(f):
                if not l.strip():
                    continue
                r = json.loads(l)
                text = r.get("text") or ""
                idx[row_key(r)].append((rel, i, bench, hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                        r.get("stop_reason") or r.get("finish_reason"), not text.strip(), code_presence(text)))
    return idx


WRITE_SHAPE = False


class Raws:
    def __init__(self, mode, w, dur):
        self.mode, self.w, self.dur = mode, w, dur
        self.cache = {}

    def files_for(self, fam, arm, shard):
        if self.mode == "cluster":
            if fam == "p2":
                return ("p2:" + arm, sorted(glob.glob(f"{self.dur}/phase2/p2-{arm}-certshard_*.completions.jsonl")), lambda p: "phase2/" + os.path.basename(p))
            if fam == "pa":
                return ("pa:" + arm + ":" + shard, [f"{self.dur}/phase2/pa-{arm}-{shard}.completions.jsonl"], lambda p: "phase2/" + os.path.basename(p))
        else:
            if fam == "bg":
                return ("bg:" + arm, sorted(glob.glob(f"{self.w}/runs-external/bg-{arm}-p*-w*.completions.jsonl")), lambda p: "bg/" + os.path.basename(p))
            if fam == "fo":
                return ("fo:" + arm, sorted(glob.glob(f"{self.w}/runs-external/fo-{arm}-w*.completions.jsonl")), lambda p: "focused/" + os.path.basename(p))
            if fam == "c3":
                return ("c3:" + arm, [f"{self.w}/runs-{PROVIDER[arm]}/repair-c3-{arm}-0042.completions.jsonl"], lambda p: "repair/" + os.path.basename(p))
        return None

    def index(self, fam, arm, shard):
        spec = self.files_for(fam, arm, shard)
        if spec is None:
            return None, []
        key, files, rel_of = spec
        files = [p for p in files if os.path.exists(p)]
        if key not in self.cache:
            self.cache = {key: index_files(files, rel_of)} if not key.startswith("pa:") else {**{k: v for k, v in self.cache.items() if k.startswith("pa:")}, key: index_files(files, rel_of)}
            if key.startswith("pa:") and len(self.cache) > 4:
                for k in [k for k in self.cache if k != key][:-3]:
                    self.cache.pop(k, None)
        return self.cache[key], files

    def abspath(self, rel):
        if self.mode == "cluster":
            return f"{self.dur}/{rel}"
        d, b = rel.split("/", 1)
        if d in ("bg", "focused"):
            return f"{self.w}/runs-external/{b}"
        if d == "repair":
            prov = "openai" if "gpt-5" in b else "gemini"
            return f"{self.w}/runs-{prov}/{b}"
        return f"{self.dur}/{rel}"


def pick(cands, own_bench, stop, empty):
    if not cands:
        return None, "unmatched"
    if len(cands) == 1:
        return cands[0], "ok"
    own = [c for c in cands if c[2] == own_bench]
    if len(own) == 1:
        return own[0], "ok_own"
    if stop is not None or empty is not None:
        agree = [c for c in cands if (stop is None or c[4] == stop) and (empty is None or c[5] == empty)]
        if len(agree) == 1:
            return agree[0], "ok_agree"
    return None, "ambiguous"


def process_unit(units_dir, name, raws, out_dir, backup_dir, verify_pool):
    arm, shard = name.split("__", 1)
    fam = family(arm, shard)
    rep = {"unit": name, "arm": arm, "shard": shard, "family": fam, "rows": 0, "matched": 0, "unmatched": 0, "ambiguous": 0,
           "mism_stop": 0, "mism_empty": 0, "had_fields": False, "filled_from_raw": 0, "raw_files": 0, "shapes": Counter()}
    if fam is None:
        rep["skipped"] = "unmapped arm"
        return rep
    sol_p = f"{units_dir}/{name}.solutions.jsonl"
    fld_p = f"{units_dir}/{name}.fields.jsonl"
    existing = {}
    if os.path.exists(fld_p):
        rep["had_fields"] = True
        with open(fld_p) as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing[(r["task_id"], int(r["sample"]))] = r
    idx, files = raws.index(fam, arm, shard)
    rep["raw_files"] = len(files)
    own_bench = {"p2": f"p2-{arm}-{shard}", "pa": f"pa-{arm}-{shard}"}.get(fam)
    out_rows = []
    with open(sol_p) as f:
        for l in f:
            if not l.strip():
                continue
            s = json.loads(l)
            key = (s["task_id"], int(s["sample"]))
            base = existing.get(key, {})
            stop = base.get("stop_reason", s.get("stop_reason"))
            empty = base.get("answer_empty", s.get("answer_empty"))
            hit, how = pick(idx.get(key, []) if idx is not None else [], own_bench, stop, empty)
            row = {"task_id": key[0], "sample": key[1]}
            if hit is None:
                rep[how] += 1
                row["stop_reason"], row["answer_empty"] = stop, empty
                row["raw_ref"], row["raw_sha256"] = None, None
                if WRITE_SHAPE:
                    row["shape"] = None; rep["shapes"]["unknown_no_raw"] += 1
            else:
                rep["matched"] += 1
                rel, line, bench, sha, rstop, rempty, rcode = hit
                if stop is None and empty is None:
                    rep["filled_from_raw"] += 1
                if stop is not None and stop != rstop:
                    rep["mism_stop"] += 1
                if empty is not None and bool(empty) != rempty:
                    rep["mism_empty"] += 1
                row["stop_reason"] = stop if stop is not None else rstop
                row["answer_empty"] = bool(empty) if empty is not None else rempty
                row["raw_ref"] = {"raw_file": rel, "line": line, "custom_id": cid(key[0], key[1]), "bench": bench}
                row["raw_sha256"] = sha
                if WRITE_SHAPE:
                    has_code, think_only = rcode
                    row["shape"] = shape_of(rstop, rempty, has_code); rep["shapes"][row["shape"]] += 1
                    if think_only:
                        row["code_in_thinking_only"] = True; rep["shapes"]["code_in_thinking_only(flag)"] += 1
                if verify_pool is not None and random.random() < 0.0005:
                    verify_pool.append((rel, line, key, sha))
            if "content_sha256" in base:
                row["content_sha256"] = base["content_sha256"]
            out_rows.append(row)
            rep["rows"] += 1
    # write
    dest = f"{out_dir}/{name}.fields.jsonl"
    if backup_dir and os.path.exists(dest):
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(dest, f"{backup_dir}/{name}.fields.jsonl")
    tmp = dest + ".tmp"
    with open(tmp, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in out_rows))
    os.replace(tmp, dest)
    return rep


def verify(pool, raws):
    """Re-open each referenced raw_file once, pull the referenced lines, check key + sha."""
    by_file = defaultdict(list)
    for rel, line, key, sha in pool:
        by_file[rel].append((line, key, sha))
    bad = 0
    for rel, items in by_file.items():
        want = {line: (key, sha) for line, key, sha in items}
        with open(raws.abspath(rel)) as f:
            for i, l in enumerate(f):
                if i in want:
                    r = json.loads(l)
                    key, sha = want[i]
                    ok = row_key(r) == key and hashlib.sha256((r.get("text") or "").encode("utf-8")).hexdigest() == sha
                    bad += 0 if ok else 1
    return len(pool), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["local", "cluster"])
    ap.add_argument("--units", required=True)
    ap.add_argument("--out", help="cluster mode: staging dir for the new .fields.jsonl (local mode writes in place)")
    ap.add_argument("--backup", help="local mode: dir for copies of the .fields.jsonl being replaced")
    ap.add_argument("--w", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--dur", default=os.environ.get("DURABILITY_ROOT", "durability"))
    ap.add_argument("--report", required=True)
    ap.add_argument("--families", default=None, help="comma list to restrict, e.g. bg,fo,c3")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None, help="comma list of unit names to (re)process")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--shape", action="store_true", help="also write the per-row `shape` label (retro class-49 rule); default off until consumers ack")
    a = ap.parse_args()
    global WRITE_SHAPE
    WRITE_SHAPE = a.shape
    fams = set(a.families.split(",")) if a.families else ({"bg", "fo", "c3"} if a.mode == "local" else {"p2", "pa"})
    out_dir = a.units if a.mode == "local" else a.out
    os.makedirs(out_dir, exist_ok=True)
    raws = Raws(a.mode, a.w, a.dur)
    names = sorted(os.path.basename(p)[: -len(".solutions.jsonl")] for p in glob.glob(f"{a.units}/*.solutions.jsonl"))
    todo = []
    for n in names:
        if "__" not in n:
            continue
        arm, shard = n.split("__", 1)
        if family(arm, shard) in fams:
            todo.append(n)
    if a.only:
        only = set(a.only.split(","))
        todo = [n for n in todo if n in only]
    if a.limit:
        todo = todo[: a.limit]
    todo.sort(key=lambda n: (family(*n.split("__", 1)), n.split("__", 1)[0], n))  # group by family+arm so the arm index is built once
    pool = [] if a.verify else None
    reps, t0 = [], time.time()
    for k, n in enumerate(todo, 1):
        rep = process_unit(a.units, n, raws, out_dir, a.backup, pool)
        rep["shapes"] = dict(rep["shapes"]); reps.append(rep)
        if k % 25 == 0 or k == len(todo):
            print(f"[{k}/{len(todo)}] {n}: rows {rep['rows']} matched {rep['matched']} unmatched {rep['unmatched']} ambiguous {rep['ambiguous']} "
                  f"mism_stop {rep['mism_stop']} mism_empty {rep['mism_empty']}  ({time.time() - t0:.0f}s)", flush=True)
    tot = defaultdict(Counter)
    for r in reps:
        for f in ("rows", "matched", "unmatched", "ambiguous", "mism_stop", "mism_empty", "filled_from_raw"):
            tot[r["arm"]][f] += r.get(f, 0)
        tot[r["arm"]]["units"] += 1
        for k_, v_ in r.get("shapes", {}).items():
            tot[r["arm"]]["shape:" + k_] += v_
        tot[r["arm"]]["units_without_prior_fields"] += 0 if r["had_fields"] else 1
    ver = verify(pool, raws) if pool else None
    summary = {"mode": a.mode, "units_dir": a.units, "out_dir": out_dir, "families": sorted(fams), "units": len(reps),
               "by_arm": {k: dict(v) for k, v in sorted(tot.items())},
               "totals": dict(sum((v for v in tot.values()), Counter())),
               "verify": None if ver is None else {"sampled_rows": ver[0], "failures": ver[1]},
               "shape_semantics": None if not WRITE_SHAPE else {"values": list(SHAPES), "rule": "from stop/finish reason + refusal marker + code presence in the ANSWER part of the raw reply (closed <think>…</think> spans removed — exactly the spans the extractor of record strips; <thinking>/<reasoning>/<details> are not stripped), never length",
                                                                   "code_test": CODE_RE.pattern, "code_in_thinking_only": "boolean flag set when the only code sits inside a removed <think> span (shape then reads as if no code)", "scoring": "labels only; scoring rules unchanged"},
               "raw_ref_semantics": {"raw_file": "path relative to the durability root",
                                     "line": "0-based line index in raw_file", "custom_id": "API batch custom_id = claude_gen.cid(task_id, sample)",
                                     "raw_sha256": "sha256(utf-8 of the export row's text); identical for all empty replies"},
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "units_detail": reps}
    os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
    json.dump(summary, open(a.report, "w"), indent=1)
    print(json.dumps({k: summary[k] for k in ("units", "totals", "verify")}), flush=True)


if __name__ == "__main__":
    main()

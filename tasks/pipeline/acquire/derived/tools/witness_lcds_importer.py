#!/usr/bin/env python3
"""Usage: python3 witness_lcds_importer.py --old bench_import.py --new bench_import.next.py --work /tmp/<dir>
         --shards "<glob1>" ["<glob2>" ...] --slugs slugA,slugB,... [--control N] [--all-landed <file of slugs>]
Source rows are looked up by task_id (slug) in the shard globs in order (a screened row is preferred when a glob names it).
`--control N` adds every k-th slug of --all-landed not in --slugs (k chosen so about N controls come out).
Runs the two importers as subprocesses (`convert --in <rows> --outdir <dir>`), reads tasks_converted.jsonl and
conversion_report.jsonl, prints a table and writes <work>/witness.json.
"""
import argparse, glob, json, os, subprocess, sys


def load_rows(globs, want):
    found = {}
    for g in globs:
        for fn in sorted(glob.glob(g)):
            with open(fn, encoding="utf-8") as f:
                for line in f:
                    if '"task_id"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    t = r.get("task_id")
                    if t in want and t not in found:
                        found[t] = (fn, r)
            if len(found) == len(want):
                return found
    return found


def run(importer, rows_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    p = subprocess.run([sys.executable, importer, "convert", "--in", rows_path, "--outdir", outdir],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
    tasks, report = {}, {}
    tp = os.path.join(outdir, "tasks_converted.jsonl")
    rp = os.path.join(outdir, "conversion_report.jsonl")
    if os.path.exists(tp):
        for line in open(tp, encoding="utf-8"):
            d = json.loads(line)
            tasks[d["task_id"].split("/", 1)[-1]] = d
    if os.path.exists(rp):
        for line in open(rp, encoding="utf-8"):
            d = json.loads(line)
            report[(d.get("cand_id") or d.get("task_id") or "").split("/", 1)[-1]] = d
    return p.returncode, p.stdout[-2000:], tasks, report


def types(vals):
    return sorted({type(v).__name__ for v in vals})


def compare(slug, ot, nt, orp, nrp):
    moves = []
    os_, ns_ = (orp or {}).get("status"), (nrp or {}).get("status")
    if os_ != ns_:
        moves.append("status %s -> %s (%s)" % (os_, ns_, (nrp or {}).get("reason", "")[:80]))
    if ot and nt:
        for k in ("prompt", "canonical_solution", "entry_point", "base_input", "plus_input", "atol"):
            if ot.get(k) != nt.get(k):
                moves.append(k)
        oe, ne = ot.get("expected_output", {}), nt.get("expected_output", {})
        for part in ("base", "plus"):
            if oe.get(part) != ne.get(part):
                moves.append("expected.%s types %s -> %s" % (part, types(oe.get(part, [])), types(ne.get(part, []))))
    return moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--shards", nargs="+", required=True); ap.add_argument("--slugs", required=True)
    ap.add_argument("--control", type=int, default=0); ap.add_argument("--all-landed", default="")
    a = ap.parse_args()
    named = [s for s in a.slugs.split(",") if s]
    controls = []
    if a.control and a.all_landed:
        allv = [l.strip() for l in open(a.all_landed) if l.strip() and l.strip() not in named]
        k = max(1, len(allv) // a.control)
        controls = allv[::k][:a.control]
    want = set(named) | set(controls)
    rows = load_rows(a.shards, want)
    missing = sorted(want - set(rows))
    os.makedirs(a.work, exist_ok=True)
    rows_path = os.path.join(a.work, "leetcode_rows.jsonl")  # the importer picks its source converter from the input path
    with open(rows_path, "w", encoding="utf-8") as f:
        for t in sorted(rows):
            f.write(json.dumps(rows[t][1]) + "\n")
    print("rows found %d of %d wanted (%d named, %d controls); missing: %s" % (len(rows), len(want), len(named), len(controls), missing[:10]))
    rc_o, log_o, ot, orp = run(a.old, rows_path, os.path.join(a.work, "out_old"))
    rc_n, log_n, nt, nrp = run(a.new, rows_path, os.path.join(a.work, "out_new"))
    print("old importer rc %d (%d converted); new importer rc %d (%d converted)" % (rc_o, len(ot), rc_n, len(nt)))
    if rc_o or rc_n:
        print("--- old log tail:\n%s\n--- new log tail:\n%s" % (log_o[-800:], log_n[-800:]))
    res = {}
    print("%-55s %-8s %s" % ("slug", "set", "moves"))
    n_ctrl_moved = 0
    for t in sorted(rows):
        moves = compare(t, ot.get(t), nt.get(t), orp.get(t), nrp.get(t))
        which = "named" if t in named else "control"
        if moves and which == "control":
            n_ctrl_moved += 1
        res[t] = {"set": which, "old_status": (orp.get(t) or {}).get("status"), "new_status": (nrp.get(t) or {}).get("status"),
                  "moves": moves, "new_metrics": {k: (nrp.get(t) or {}).get("metrics", {}).get(k) for k in ("return_is_str", "statement_cleaned", "n_base", "n_plus", "n_example_parse_fail")}}
        print("%-55s %-8s %s" % (t[:55], which, "; ".join(moves) if moves else "-"))
    print("controls that moved: %d of %d" % (n_ctrl_moved, len(controls)))
    with open(os.path.join(a.work, "witness.json"), "w") as f:
        json.dump({"old": a.old, "new": a.new, "missing": missing, "records": res}, f, indent=1)
    print("written", os.path.join(a.work, "witness.json"))


if __name__ == "__main__":
    main()

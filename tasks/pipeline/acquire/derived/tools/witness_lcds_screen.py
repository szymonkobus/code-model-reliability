#!/usr/bin/env python3
import argparse, glob, json, os, subprocess, sys


def run(screen_dir, raw, out):
    p = subprocess.run([sys.executable, os.path.join(screen_dir, "lcds_screen_shard.py"), "--in", raw, "--out", out],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
    if p.returncode:
        sys.exit("screen failed (%s on %s):\n%s" % (screen_dir, raw, p.stdout[-1500:]))
    rows = {}
    for line in open(out, encoding="utf-8"):
        r = json.loads(line)
        rows[r["task_id"]] = r.get("_domain_screen") or {}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True)
    ap.add_argument("--work", required=True); ap.add_argument("--shards", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    tot = same = ambig = moved_bad = 0
    ev_old = ev_new = 0; unbound = 0; ambig_lines = 0
    moved = []
    for raw in sorted(glob.glob(a.shards)):
        base = os.path.basename(raw)
        o = run(a.old, raw, os.path.join(a.work, base + ".old"))
        n = run(a.new, raw, os.path.join(a.work, base + ".new"))
        for t in o:
            if t not in n:
                moved.append((t, "missing in new")); moved_bad += 1; continue
            tot += 1
            do = sorted(json.dumps(x, sort_keys=True) for x in o[t].get("dropped", []))
            dn = sorted(json.dumps(x, sort_keys=True) for x in n[t].get("dropped", []))
            ev_old += len(set(o[t].get("constraints_evaluated", [])))
            ev_new += len(set(n[t].get("constraints_evaluated", [])))
            sk = n[t].get("constraints_skipped", [])
            n_amb = sum(1 for s in sk if s.startswith("AMBIGUOUS FLATTENED BOUND"))
            unbound += sum(1 for s in sk if s.startswith("NOT EVALUATED"))
            ambig_lines += n_amb
            if do == dn:
                same += 1
            elif n_amb and set(dn) <= set(do):
                ambig += 1
                moved.append((t, "ambiguous line(s) %s: drops %d -> %d" % ([s.split(": ", 1)[1][:60] for s in sk if s.startswith("AMBIGUOUS")], len(do), len(dn))))
            else:
                moved_bad += 1
                moved.append((t, "DROPS MOVED WITHOUT AN AMBIGUOUS LINE: %d -> %d" % (len(do), len(dn))))
    print("records %d: drops identical %d; drops reduced on ambiguous-bound records %d; UNEXPECTED moves %d" % (tot, same, ambig, moved_bad))
    print("constraint lines listed as evaluated: %d before -> %d after; lines now marked NOT EVALUATED %d; AMBIGUOUS FLATTENED BOUND lines %d" % (ev_old, ev_new, unbound, ambig_lines))
    for t, why in moved[:40]:
        print("   ", t, "|", why)
    with open(os.path.join(a.work, "witness_screen.json"), "w") as f:
        json.dump({"records": tot, "identical": same, "ambiguous_reduced": ambig, "unexpected": moved_bad,
                   "evaluated_before": ev_old, "evaluated_after": ev_new, "not_evaluated": unbound, "ambiguous_lines": ambig_lines,
                   "moved": moved}, f, indent=1)
    print("written", os.path.join(a.work, "witness_screen.json"))


if __name__ == "__main__":
    main()

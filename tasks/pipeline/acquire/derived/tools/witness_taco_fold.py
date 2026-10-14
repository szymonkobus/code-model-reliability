#!/usr/bin/env python3
import argparse, glob, importlib.util, json, sys


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--new", required=True); ap.add_argument("--shards", nargs="+", required=True)
    a = ap.parse_args()
    old, new = load(a.old, "ft_old"), load(a.new, "ft_new")
    n = moved = other = 0; rows = []
    for g in a.shards:
        for fn in sorted(glob.glob(g)):
            for line in open(fn, encoding="utf-8"):
                r = json.loads(line); n += 1
                tests = r.get("tests") or []
                io = {"inputs": [t["input"] for t in tests], "outputs": [t["output"] for t in tests]}
                st = r.get("statement") or ""
                q = st.get("description") or "" if isinstance(st, dict) else st   # the fetcher stores the row's question as description
                ex = old.statement_example_inputs(q)
                ko, mo, bo = old.build_tests(io, ex)
                kn, mn, bn = new.build_tests(io, ex)
                if bo or bn or ko is None or kn is None:
                    continue
                eo, en = mo["n_by_kind"]["example"], mn["n_by_kind"]["example"]
                if len(ko) != len(kn) or mo["n_dropped_oversize"] != mn["n_dropped_oversize"]:
                    other += 1; rows.append((r.get("cand_id"), "KEPT/DROPPED MOVED", len(ko), len(kn)))
                elif eo != en:
                    moved += 1; rows.append((r.get("cand_id"), "examples %d -> %d (by fold %d)" % (eo, en, mn.get("n_example_by_fold", 0)), len(tests), fn.rsplit("/", 1)[-1]))
    print("records %d: example count moved on %d; kept/dropped moved on %d (must be 0)" % (n, moved, other))
    for row in rows[:60]:
        print("   ", row)


if __name__ == "__main__":
    main()

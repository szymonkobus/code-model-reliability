#!/usr/bin/env python3
import json
import sys


def load(path):
    header, rows = None, {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if "arm_id" not in d:
                if header is None:
                    header = d
                continue
            rows[(d.get("arm_id"), d.get("benchmark"), d.get("kind"))] = d
    return header or {}, rows


def size(v):
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 80 else s[:77] + "..."


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    old_p, new_p = sys.argv[1], sys.argv[2]
    fields = "--fields" in sys.argv[3:]
    oh, orows = load(old_p)
    nh, nrows = load(new_p)
    print(f"rows: old {len(orows)} new {len(nrows)}")
    hk = sorted(set(oh) | set(nh))
    changed_h = [k for k in hk if oh.get(k) != nh.get(k)]
    print(f"header keys changed ({len(changed_h)}):")
    for k in changed_h:
        print(f"  ~ {k}: {size(oh.get(k))} -> {size(nh.get(k))}")
    added = sorted(set(nrows) - set(orows))
    removed = sorted(set(orows) - set(nrows))
    common = sorted(set(orows) & set(nrows))
    changed = []
    for key in common:
        a, b = orows[key], nrows[key]
        diff = [f for f in sorted(set(a) | set(b)) if a.get(f) != b.get(f)]
        if diff:
            changed.append((key, diff))
    print(f"added {len(added)} removed {len(removed)} changed {len(changed)}")
    for key in added:
        print(f"  + {key}")
    for key in removed:
        print(f"  - {key}")
    for key, diff in changed:
        print(f"  ~ {key} {diff}")
        if fields:
            for f in diff:
                o = json.dumps(orows[key].get(f), ensure_ascii=False)
                n = json.dumps(nrows[key].get(f), ensure_ascii=False)
                print(f"      {f}: {o[:160]}")
                print(f"      {' ' * len(f)}  -> {n[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

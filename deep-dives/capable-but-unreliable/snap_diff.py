#!/usr/bin/env python3
import datetime, json, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
LOG = D / ".store_moves.log"


def main():
    prev = Path(sys.argv[1]) if len(sys.argv) > 2 else D / ".snap" / "store.prev.json"
    snap = Path(sys.argv[2]) if len(sys.argv) > 2 else D / ".snap" / "store.json"
    try:
        a = json.load(open(prev)); b = json.load(open(snap))
        A = a.get("arms") or {}; B = b.get("arms") or {}
        moved = sorted(k for k in set(A) | set(B) if A.get(k) != B.get(k))
        parts = []
        for k in moved:
            x = A.get(k) or {}; y = B.get(k) or {}
            new = sum(1 for t in y if t not in x); gone = sum(1 for t in x if t not in y)
            chg = sum(1 for t in y if t in x and x[t] != y[t])
            tag = " (new arm)" if k not in A else (" (arm gone)" if k not in B else "")
            parts.append(f"{k}{tag} +{new} ~{chg} -{gone}")
        line = f"{a.get('_stamp')} -> {b.get('_stamp')}: {len(moved)} arms moved"
        if parts:
            line += ": " + "; ".join(parts)
    except Exception as e:  # noqa: BLE001
        line = f"snapshot diff unreadable: {e!r}"[:200]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(LOG, "a") as fh:
            fh.write(f"{stamp} {line}\n")
    except Exception:  # noqa: BLE001
        pass
    print(line)


if __name__ == "__main__":
    main()

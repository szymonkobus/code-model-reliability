#!/usr/bin/env python3
import json
import sys

rc = 0
for p in sys.argv[1:]:
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        keys = list(d.keys())[:12] if isinstance(d, dict) else [type(d).__name__]
        print("OK", p, len(keys), "keys:", ", ".join(map(str, keys)))
    except Exception as e:  # noqa: BLE001
        print("FAIL", p, e)
        rc = 1
sys.exit(rc)

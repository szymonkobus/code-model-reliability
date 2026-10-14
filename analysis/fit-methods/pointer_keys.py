#!/usr/bin/env python3
import sys, os, glob, json, hashlib
DROP = ("frame_disclosure", "invalidated_cells_under_current_rule", "label_of_record_note", "newer", "updated_at", "flipped_at",
        "serving_word", "crossings_of_record")
F = sys.argv[1]
for p in sorted(glob.glob(os.path.join(F, "serving_*.json"))):
    b = os.path.basename(p)
    if len(b.split(".")) > 2: continue   # sha-suffixed archived copies
    try:
        d = json.load(open(p))
    except Exception:
        print(b, "unreadable"); continue
    if isinstance(d, dict):
        for k in DROP: d.pop(k, None)
    print(b, hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12])

#!/usr/bin/env python3
import hashlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_DIR = os.path.join(HERE, "board_compare")
sys.path.insert(0, PATCH_DIR)
def _sha16(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
try:
    import compare_numeric_patch as _p
    _p.apply()
except Exception as e:  # loud failure: the board must not judge on an unknown compare
    sys.stderr.write(f"board_evaluate: compare patch FAILED to apply ({e!r}); refusing to judge\n")
    sys.exit(97)
print(f"board_evaluate: compare=numeric-tolerant-v2 compare_sha={_sha16(os.path.join(PATCH_DIR, 'compare_numeric_patch.py'))} "
      f"normalize_sha={_sha16(os.path.join(PATCH_DIR, 'compare_normalize_patch.py'))} era=compare-numeric-tolerant-v2", flush=True)
from evalplus.evaluate import main as _main
sys.argv = [sys.argv[0]] + sys.argv[1:]
_main()

#!/usr/bin/env python
"""crossing_draw_atoms.py <element json> [<element json> ...] [--level d1|d50]"""
import json, sys
import numpy as np


def main(a):
    level = a[a.index('--level') + 1] if '--level' in a else 'd1'
    files = [x for x in a[1:] if not x.startswith('--') and x != level]
    for p in files:
        d = json.load(open(p))
        df = (d.get('draws_avg_full') or {}).get(level) or {}
        z = np.asarray(df.get('z') or [], dtype=float); cens = np.asarray(df.get('censor') or [], dtype=float)
        if z.size == 0: print(f"{p.split('/waves/')[-1]}: no draws_avg_full.{level}.z"); continue
        ok = np.isfinite(z)
        zz = z[ok]
        med = float(np.median(zz))
        at_med = float(np.mean(np.abs(zz - med) < 1e-9))
        vals, counts = np.unique(np.round(zz, 9), return_counts=True)
        top = sorted(zip(counts, vals), reverse=True)[:3]
        q = np.quantile(zz, [0.45, 0.5, 0.55])
        lay = d.get('config') or {}
        print(f"{p.split('/waves/')[-1]} | layout {lay.get('chains')}x({lay.get('warmup')}+{lay.get('samples')}) | {level}: n {zz.size} (non-finite {int((~ok).sum())}; censored {int((cens != 0).sum()) if cens.size else 'n/a'}) | median {med:.7f} | share of draws at the median {at_med:.4%} | distinct values {vals.size} | top values " + '; '.join(f"{v:.7f} x{c} ({c / zz.size:.3%})" for c, v in top) + f" | q45 {q[0]:.5f} q50 {q[1]:.5f} q55 {q[2]:.5f}")
    return 0


if __name__ == '__main__': sys.exit(main(sys.argv))

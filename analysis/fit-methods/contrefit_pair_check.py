#!/usr/bin/env python
"""contrefit_pair_check.py <wave dir> <arm> [--level d1|d50] [--lo Z] [--hi Z]

Read-only; prints one report; exit 0. The verdict stays the element read's (code/contrefit_elements_read.py); this prints what the pair is.
"""
import json, sys, os, glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(TREE))


def q(z):
    return {p: float(np.quantile(z, p / 100)) for p in (5, 10, 25, 50, 75, 90, 95)}


def two_cluster(z):
    s = np.sort(z)
    if len(s) < 4: return None
    gaps = np.diff(s)
    i = int(np.argmax(gaps))
    lo, hi = s[:i + 1], s[i + 1:]
    return dict(gap=float(gaps[i]), split_at=float((s[i] + s[i + 1]) / 2),
                lower=dict(share=len(lo) / len(s), median=float(np.median(lo))),
                upper=dict(share=len(hi) / len(s), median=float(np.median(hi))))


def chains(cfg):
    for k in ('chains', 'n_chains', 'num_chains', 'nchains'):
        v = cfg.get(k) if isinstance(cfg, dict) else None
        if isinstance(v, int) and v > 0: return v
    return None


def element_report(path, level, lo, hi):
    d = json.load(open(path))
    full = (d.get('draws_avg_full') or {}).get(level) or {}
    zall = np.asarray(full.get('z') or [], dtype=float)
    fin = np.isfinite(zall); z = zall[fin]
    out = dict(path=os.path.relpath(path, REPO), n_draws=int(zall.size), n_finite=int(z.size),
               share_censored_nan=(float(1.0 - fin.mean()) if zall.size else None), order=full.get('order'), thin=full.get('thin'),
               note='statistics over the finite draws; a NaN draw has no crossing of the level inside the task range (censored) and its share stands beside them')
    if z.size:
        out['median_finite_draws'] = float(np.median(z))
        out['quantiles_finite'] = q(z)
        out[f'share_below_{lo:g}'] = float(np.mean(z < lo)); out[f'share_above_{hi:g}'] = float(np.mean(z > hi))
        out['two_cluster_finite'] = two_cluster(z)
        nc = chains(d.get('config') or {})
        if nc and zall.size % nc == 0 and (full.get('order') or 'chain-major') == 'chain-major':
            per = zall.reshape(nc, -1)
            out['per_chain_median_finite'] = [(float(np.median(c[np.isfinite(c)])) if np.isfinite(c).any() else None) for c in per]
            out['per_chain_share_censored_nan'] = [float(1.0 - np.isfinite(c).mean()) for c in per]
    lt = d.get('levels_table_avg') or {}
    if isinstance(lt, dict):   # the engine's levels table is columnar: rule and method strings, the numbers per level in arrays
        out['export_rule'] = (lt.get('rule') or '')[:160]; out['export_method'] = lt.get('method')
    ea = (d.get('estimands_avg') or {}).get(level) or {}
    if ea: out['export_estimand'] = dict(median_z=ea.get('median_z'), cri80_z=ea.get('cri80_z'), note='the element\'s own export; the September engine exported the FIRST crossing, the re-fit the MIDDLE — compare cells, not exports')
    return out


def table_cells(meta, arm, level):
    import csv
    sw = meta.get('served_wave')
    if isinstance(sw, dict): sw = sw.get('wave_id') or sw.get('path')
    if not sw: return 'no served_wave leaf in the meta'
    path = os.path.join(REPO, 'definitions', 'fitting', 'waves', os.path.basename(str(sw)), 'crossings_of_record.csv')
    if not os.path.exists(path): return f'no table at {os.path.relpath(path, REPO)}'
    L = level
    with open(path, newline='') as fh:
        for row in csv.DictReader(fh):
            if row.get('arm') != arm: continue
            keys = [f'{L}_of_record_z', f'{L}_of_record_cri80_lo', f'{L}_of_record_cri80_hi', f'{L}_of_record_status', f'{L}_of_record_p_left_censored',
                    f'{L}_of_record_p_right_censored', f'{L}_conditional_median_z', f'{L}_of_record_z_source', f'{L}_of_record_bound', 'fit_crossing_rule', 'fit_crossing_locator']
            if L == 'd50': keys.append('d50_avg_z')
            return dict(table=os.path.relpath(path, REPO), **{k: ((row.get(k) or '')[:160]) for k in keys if k in row})
    return f'no row for {arm}'


def counts_record(wave_id, arm):
    for f in sorted(glob.glob(os.path.join(TREE, 'knowledge', 'contrefit_rows_verification_*.json'))):
        try: recs = json.load(open(f)).get('records') or {}
        except Exception: continue
        r = recs.get(f'{wave_id}/{arm}')
        if r: return dict(file=os.path.relpath(f, REPO), verdict=r.get('verdict'), moved_by_property=r.get('moved_by_property'), carried=r.get('carried'),
                          cells=r.get('cells_in_file'), sum_n=r.get('sum_n'), sum_f=r.get('sum_f'), disclosure_differs=r.get('disclosure_differs'))
    return None


def main(a):
    args = [x for x in a[1:] if not x.startswith('--')]
    if len(args) < 2: print(__doc__); return 2
    wave, arm = args[0].rstrip('/'), args[1]
    level = a[a.index('--level') + 1] if '--level' in a else 'd1'
    lo = float(a[a.index('--lo') + 1]) if '--lo' in a else 0.0
    hi = float(a[a.index('--hi') + 1]) if '--hi' in a else 1.0
    meta = json.load(open(os.path.join(wave, 'meta.json')))
    wid = meta.get('wave_id') or os.path.basename(wave)
    pa = (meta.get('per_arm') or {}).get(arm) or {}
    new = os.path.join(wave, 'results', f'posterior_summary_{arm}_eivon.json')
    sp = (pa.get('served_element') or {}).get('path')
    served = os.path.join(REPO, sp) if sp else None
    rep = dict(wave=wid, arm=arm, level=level, census=meta.get('census'),
               new=element_report(new, level, lo, hi) if os.path.exists(new) else 'not landed',
               served_cells_of_record=table_cells(meta, arm, level),
               served_element=element_report(served, level, lo, hi) if served and os.path.exists(served) else f'no served element ({sp})',
               gate_read=counts_record(wid, arm))
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == '__main__': sys.exit(main(sys.argv))

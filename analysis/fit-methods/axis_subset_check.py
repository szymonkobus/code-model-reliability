#!/usr/bin/env python
"""axis_subset_check.py [--wave <board_top wave dir>] [--table <crossings csv>] [--out <stem>]"""
import sys, os, csv, json, glob, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
WAVE = os.path.join(REPO, 'definitions', 'fitting', 'waves', 'board_top-20260910T2111Z')
LOGIT_SPAN = math.log(0.99 / 0.01) - math.log(0.01 / 0.99)


def logit(p): return np.log(p / (1 - p))
def sig(x): return 1 / (1 + np.exp(-x))


def load_inputs(wave):
    arms = {}
    for p in sorted(glob.glob(os.path.join(wave, 'inputs', '*.npz'))):
        d = np.load(p, allow_pickle=True)
        arms[os.path.basename(p)[:-4]] = {'tasks': [str(t) for t in d['task_ids']], 'z': d['z_hat'].astype(float), 'n': d['n'].astype(float), 'f': d['f'].astype(float)}
    return arms


def logistic_fit(z, y, w, iters=40):
    """Weighted logistic regression of the share y (weights w) on z: returns (a, b) of logit p = a + b z, by IRLS with a ridge of 1e-6."""
    X = np.column_stack([np.ones_like(z), z]); beta = np.array([logit(np.clip(np.average(y, weights=w), 1e-4, 1 - 1e-4)), 0.0])
    for _ in range(iters):
        p = sig(X @ beta); W = w * p * (1 - p) + 1e-12
        g = X.T @ (w * (y - p)); H = (X * W[:, None]).T @ X + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g); beta = beta + step
        if np.max(np.abs(step)) < 1e-9: break
    return beta[0], beta[1]


def smoothed_crossings(z, y, w, levels=(0.01, 0.5, 0.99), bw=0.6):
    """The smoothed mean of the shares along z (Gaussian kernel, attempts-weighted), the crossings by interpolation on a grid; a bound at the grid's end."""
    grid = np.linspace(z.min(), z.max(), 400)
    K = np.exp(-0.5 * ((grid[:, None] - z[None, :]) / bw) ** 2) * w[None, :]
    m = (K @ y) / np.maximum(K.sum(axis=1), 1e-12)
    out = {}
    for L in levels:
        idx = np.where(m >= L)[0]
        if len(idx) == 0: out[L] = (float(grid[-1]), 'bound: above')
        elif idx[0] == 0: out[L] = (float(grid[0]), 'bound: below')
        else:
            i = idx[0]; w_ = (L - m[i - 1]) / (m[i] - m[i - 1]) if m[i] != m[i - 1] else 0.0
            out[L] = (float(grid[i - 1] + w_ * (grid[i] - grid[i - 1])), 'point')
    return out


def rank_corr(x, y):
    rx = np.argsort(np.argsort(x)); ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1]) if len(x) > 2 else float('nan')


def main(a):
    wave = a[a.index('--wave') + 1] if '--wave' in a else WAVE
    table = a[a.index('--table') + 1] if '--table' in a else os.path.join(wave, 'crossings_of_record.csv')
    out = a[a.index('--out') + 1] if '--out' in a else os.path.join(os.path.dirname(HERE), 'figures', 'axis_subset_check')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    arms = load_inputs(wave)
    names = sorted(arms)
    # the files' task orders (and sets) differ between arms (the thinking arms' lists): align by task id over the union, a model's absent task counting no attempts
    tasks = sorted(set(t for nm in names for t in arms[nm]['tasks'])); ti = {t: i for i, t in enumerate(tasks)}
    F = np.zeros((len(names), len(tasks))); N = np.zeros((len(names), len(tasks))); Z = np.full((len(names), len(tasks)), np.nan)
    for r_, nm in enumerate(names):
        for t, z_, n_, f_ in zip(arms[nm]['tasks'], arms[nm]['z'], arms[nm]['n'], arms[nm]['f']):
            j = ti[t]; F[r_, j] = f_; N[r_, j] = n_; Z[r_, j] = z_
    z_rec = np.nanmedian(Z, axis=0)
    zdev = np.nanmax(np.nanmax(Z, axis=0) - np.nanmin(Z, axis=0))
    print(f"{len(names)} models, {len(tasks)} tasks in the union (per-file sets {min(len(a['tasks']) for a in arms.values())}–{max(len(a['tasks']) for a in arms.values())}); the axis position of a task agrees across files within {zdev:.6f}")
    d50 = {}
    for r in csv.DictReader(open(table)):
        k = r.get('arm_id') or r.get('arm')
        try: d50[k] = float(r.get('d50_of_record_z'))
        except (TypeError, ValueError): pass
    cap = np.array([d50.get(nm, np.nan) for nm in names])
    order = [i for i in np.argsort(cap) if not np.isnan(cap[i])]   # weakest to strongest by the served D50
    half = len(order) // 2
    subsets = {'all': list(range(len(names))), 'weaker half': order[:half], 'stronger half': order[half:], 'balanced (every other by rank)': order[::2]}
    axes = {'record': z_rec.copy()}   # the axis of record itself first (the Definitions recipe on the intake's cells), then the rebuilds from this wave's cells
    subsets = dict([('record', list(range(len(names))))] + list(subsets.items()))
    for key, idx in subsets.items():
        if key == 'record': continue
        Fs, Ns = F[idx].sum(axis=0), N[idx].sum(axis=0)
        axes[key] = logit((Fs + 0.5) / (Ns + 1.0))
    repro = axes['all'] - z_rec
    print(f"axis of record vs the rebuild from all {len(names)} models: max |diff| {np.max(np.abs(repro)):.4f}, median {np.median(np.abs(repro)):.4f}, corr {np.corrcoef(axes['all'], z_rec)[0, 1]:.6f}")
    rows, summary = [], {'reproduction': {'max_abs_diff': float(np.max(np.abs(repro))), 'median_abs_diff': float(np.median(np.abs(repro)))}, 'axes': {}, 'subsets': {k: [names[i] for i in v] for k, v in subsets.items()}}
    for key, z in axes.items():
        rec = {'n_models_in_axis': len(subsets[key]), 'logistic': {}, 'smoothed': {}}
        spans_l, d50s_l, spans_s, d50s_s = [], [], [], []
        for i, nm in enumerate(names):
            n, f = N[i], F[i]; msk = n > 0
            y = f[msk] / n[msk]; w = n[msk]; zz = z[msk]
            a_, b_ = logistic_fit(zz, y, w)
            span_l = LOGIT_SPAN / b_ if b_ > 0 else float('nan'); d50_l = -a_ / b_ if b_ != 0 else float('nan')
            cr = smoothed_crossings(zz, y, w)
            span_s = cr[0.99][0] - cr[0.01][0]; st_s = 'point' if cr[0.99][1] == 'point' and cr[0.01][1] == 'point' else 'bound'
            rows.append({'axis': key, 'model': nm, 'd50_served': d50.get(nm, ''), 'logistic_slope': round(b_, 5), 'logistic_d50': round(d50_l, 4), 'logistic_span': round(span_l, 4),
                         'smoothed_d50': round(cr[0.5][0], 4), 'smoothed_d99': round(cr[0.01][0], 4), 'smoothed_f99': round(cr[0.99][0], 4), 'smoothed_span': round(span_s, 4), 'smoothed_span_status': st_s})
            if np.isfinite(span_l) and np.isfinite(d50_l): spans_l.append(span_l); d50s_l.append(d50_l)
            if st_s == 'point': spans_s.append(span_s); d50s_s.append(cr[0.5][0])
        for lbl, sp, dd in (('logistic', spans_l, d50s_l), ('smoothed', spans_s, d50s_s)):
            sp, dd = np.array(sp), np.array(dd)
            slope = float(np.polyfit(dd, sp, 1)[0]) if len(sp) > 2 else float('nan')
            rec[lbl] = {'n_models': int(len(sp)), 'median_span': float(np.median(sp)), 'span_vs_d50_slope': slope, 'span_vs_d50_rank_corr': rank_corr(dd, sp),
                        'span_weakest_third': float(np.median(sp[np.argsort(dd)][:len(sp) // 3])), 'span_strongest_third': float(np.median(sp[np.argsort(dd)][-(len(sp) // 3):]))}
        # the unit: the local stretch of this axis against the record's by bins of the record's axis
        bins = np.quantile(z_rec, np.linspace(0, 1, 7)); stretch = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m_ = (z_rec >= lo) & (z_rec <= hi)
            if m_.sum() > 5:
                s = np.polyfit(z_rec[m_], z[m_], 1)[0]; stretch.append({'record_range': [round(float(lo), 2), round(float(hi), 2)], 'dz_subset_per_dz_record': round(float(s), 3), 'n_tasks': int(m_.sum())})
        rec['stretch_by_record_bins'] = stretch
        summary['axes'][key] = rec
        print(f"AXIS {key} ({len(subsets[key])} models): logistic — median span {rec['logistic']['median_span']:.3f}, span-vs-D50 slope {rec['logistic']['span_vs_d50_slope']:+.3f}, rank corr {rec['logistic']['span_vs_d50_rank_corr']:+.3f}, weakest third {rec['logistic']['span_weakest_third']:.2f} vs strongest third {rec['logistic']['span_strongest_third']:.2f}; "
              f"smoothed — median {rec['smoothed']['median_span']:.3f}, slope {rec['smoothed']['span_vs_d50_slope']:+.3f}, rank corr {rec['smoothed']['span_vs_d50_rank_corr']:+.3f} ({rec['smoothed']['n_models']} points); stretch by record sextile {[s['dz_subset_per_dz_record'] for s in stretch]}")
    with open(out + '.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(out + '_summary.json', 'w') as fh: json.dump(summary, fh, indent=1)
    try:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
        o = np.argsort(z_rec)
        for key, z in axes.items():
            if key == 'all': continue
            ax[0].plot(z_rec[o], z[o], lw=1.2, label=f'{key} ({len(subsets[key])} models)')
        ax[0].plot(z_rec[o], z_rec[o], color='0.5', lw=0.8, ls='--', label='the axis of record (y = x)')
        ax[0].set_xlabel('difficulty on the axis of record (logit)'); ax[0].set_ylabel('difficulty rebuilt from the subset (logit)'); ax[0].legend(fontsize=8, frameon=False); ax[0].set_title(f'{len(tasks)} tasks', fontsize=9, loc='right')
        for key in axes:
            if key == 'all': continue
            st = summary['axes'][key]['stretch_by_record_bins']; mids = [(s['record_range'][0] + s['record_range'][1]) / 2 for s in st]
            ax[1].plot(mids, [s['dz_subset_per_dz_record'] for s in st], marker='o', lw=1.2, label=key)
        ax[1].axhline(1.0, color='0.5', lw=0.8, ls='--'); ax[1].set_xlabel('difficulty on the axis of record (logit), sextile middles'); ax[1].set_ylabel('local stretch: subset units per record unit'); ax[1].legend(fontsize=8, frameon=False)
        fig.tight_layout(); fig.savefig(out + '_axes.png', dpi=130); plt.close(fig)
        fig, ax = plt.subplots(1, len(axes), figsize=(3.4 * len(axes), 3.8), sharey=True)
        for k_, (key, z) in enumerate(axes.items()):
            rr = [r for r in rows if r['axis'] == key and r['smoothed_span_status'] == 'point']
            ax[k_].scatter([r['smoothed_d50'] for r in rr], [r['smoothed_span'] for r in rr], s=14)
            ax[k_].set_title(f"{key}\n({len(rr)} models)", fontsize=9); ax[k_].set_xlabel('D50 on this axis (logit)')
        ax[0].set_ylabel('transition span 1% to 99% (logit units), smoothed shares')
        fig.tight_layout(); fig.savefig(out + '_trend.png', dpi=130); plt.close(fig)
        print(f"figures {out}_axes.png, {out}_trend.png")
    except Exception as e: print(f'no figures ({type(e).__name__}: {e})')
    print(f"written {out}.csv ({len(rows)} rows) and {out}_summary.json")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

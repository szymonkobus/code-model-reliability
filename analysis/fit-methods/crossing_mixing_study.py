#!/usr/bin/env python3
"""Why the GATED d50 crossing mixes slowly where the structural parameters mix. The engine (fitting's bayes_full.py) gates eta, ell,
tau, mu1 and the per-draw crossings d50 and d1 of the TYPICAL curve (the HSGP curve on the grid; censored draws to -inf/+inf),
with rank-normalised split R-hat (max of plain and folded) and bulk ESS of the rank-normalised split halves. At the 50% level the
average-rate curve's crossing equals the typical curve's exactly (E[expit(g + tau u)] = 1/2 where g = 0 for a symmetric u), so the
gated d50 is the served D50's own quantity. This tool recomputes those diagnostics from the element's exports and adds, per quantity:
the integrated autocorrelation time (draws per effective draw), the posterior sd, the Monte Carlo standard error of the all-draws
median, the per-chain medians and their spread; then the share of the d50 draws' variance a linear regression on the four exported
parameters explains — the rest is the curve's basis coefficients', which the element does not export.
"""
import json, math, sys
import numpy as np
from scipy.stats import rankdata, norm


def _split(x):
    C, S = x.shape; h = S // 2
    return np.concatenate([x[:, :h], x[:, h:2 * h]], axis=0)


def _rank_normal(x):
    flat = x.reshape(-1); r = rankdata(flat, method='average')
    return norm.ppf((r - 0.375) / (flat.size + 0.25)).reshape(x.shape)


def _rhat_plain(x):
    M, N = x.shape
    cm = x.mean(axis=1); cv = x.var(axis=1, ddof=1)
    B = N * cm.var(ddof=1); W = cv.mean()
    return math.sqrt(((N - 1) / N * W + B / N) / W)


def rhat(x):
    r1 = _rhat_plain(_rank_normal(_split(x)))
    med = np.median(x)
    folded = np.abs(x - med) if np.isfinite(med) else np.where(x == med, 0.0, np.inf)
    r2 = _rhat_plain(_rank_normal(_split(folded)))
    return max(r1, r2)


def _geyer_ess(x):
    """x [M, N] split, rank-normalised chains -> (ESS, integrated autocorrelation time) by Geyer's initial positive sequence."""
    M, N = x.shape; xm = x - x.mean(axis=1, keepdims=True)
    n2 = 1 << (2 * N - 1).bit_length()
    f = np.fft.rfft(xm, n=n2, axis=1); acov = np.fft.irfft(f * np.conj(f), n=n2, axis=1)[:, :N] / N
    W = x.var(axis=1, ddof=1).mean()
    var_hat = (N - 1) / N * W + x.mean(axis=1).var(ddof=1) if M > 1 else W
    rho = 1.0 - (W - acov.mean(axis=0)) / var_hat
    tau = -1.0; t = 0; prev = np.inf
    while t + 1 < N:
        p = rho[t] + rho[t + 1]
        if p < 0: break
        p = min(p, prev); prev = p; tau += 2 * p; t += 2
    tau = max(tau, 1e-9)
    return (M * N) / tau, tau


def bulk_ess(x):
    e, tau = _geyer_ess(_rank_normal(_split(x)))
    return min(e, x.size * math.log10(x.size)), tau


def mcse_median(flat, ess):
    f = np.sort(flat[np.isfinite(flat)])
    if f.size < 10 or not np.isfinite(ess) or ess <= 0: return float('nan')
    se_p = math.sqrt(0.25 / ess); lo = max(0.0, 0.5 - 1.96 * se_p); hi = min(1.0, 0.5 + 1.96 * se_p)
    return float((np.quantile(f, hi) - np.quantile(f, lo)) / (2 * 1.96))


def main(paths):
    for p in paths:
        d = json.load(open(p)); C = int(d['config']['chains']); S = int(d['config']['samples']); dg = d['diagnostics']
        print(f"{p.split('/waves/')[-1]}: {C}x{S} draws; tree depth {d['config'].get('max_tree_depth')}; basis {d['config'].get('m_basis')}; tasks {d['config'].get('n_tasks')}; engine gates rhat_max {dg['rhat_max_gated']:.4f} ess_min {dg['bulk_ess_min_gated']:.0f} ({'PASS' if dg.get('all_pass') else 'fails ' + ', '.join(g for g in ('rhat', 'ess') if dg.get(g + '_gate') == 'FAIL')})")
        q = {k: np.asarray(d['param_draws'][k], float).reshape(C, S) for k in ('eta', 'ell', 'tau', 'mu1')}
        for k in ('d50', 'd1'):
            z = np.array([np.nan if v is None else float(v) for v in d['draws'][k]['z']]); cen = np.asarray(d['draws'][k]['censor'], int)
            z[cen == -1] = -np.inf; z[cen == 1] = np.inf; q[k] = z.reshape(C, S)
        print(f"  {'quantity':8} {'rhat':>7} {'ess':>7} {'tau_int':>8} {'sd':>8} {'mcse_med':>9}  {'chain medians (spread)':<44} engine rhat/ess")
        for k, x in q.items():
            fin = x[np.isfinite(x)]; e, _ = bulk_ess(x); meds = [float(np.median(x[c])) for c in range(C)]
            eng_r = dg['rhat_gated'].get(k, float('nan')); eng_e = dg['bulk_ess_gated'].get(k)
            print(f"  {k:8} {rhat(x):7.4f} {e:7.0f} {x.size / e:8.1f} {fin.std():8.4f} {mcse_median(x.reshape(-1), e):9.4f}  {' '.join(f'{m:+.4f}' for m in meds)} ({max(meds) - min(meds):.4f})   {eng_r:.4f}/{(eng_e if eng_e is not None else float('nan')):.0f}")
        z = q['d50'].reshape(-1); m = np.isfinite(z)
        X = np.column_stack([np.ones(int(m.sum()))] + [q[k].reshape(-1)[m] for k in ('eta', 'ell', 'tau', 'mu1')])
        beta, *_ = np.linalg.lstsq(X, z[m], rcond=None); resid = z[m] - X @ beta
        print(f"  d50 on (eta, ell, tau, mu1), linear: R^2 {1 - resid.var() / z[m].var():.3f}; censored d50 draws {int((~m).sum())} of {z.size}; the rest of the crossing's variance is the curve's {d['config'].get('m_basis')} basis coefficients' (not exported)")
        P = np.column_stack([q[k].reshape(-1) for k in ('eta', 'ell', 'tau', 'mu1')]); c = np.corrcoef(P.T)
        print(f"  parameter correlations: eta-ell {c[0, 1]:+.2f} eta-tau {c[0, 2]:+.2f} eta-mu1 {c[0, 3]:+.2f} ell-tau {c[1, 2]:+.2f} ell-mu1 {c[1, 3]:+.2f} tau-mu1 {c[2, 3]:+.2f}")


if __name__ == '__main__':
    main(sys.argv[1:])

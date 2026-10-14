import sys, json, time, numpy as np
from scipy.optimize import minimize, brentq
from scipy.special import expit
GH_X, GH_W = np.polynomial.hermite_e.hermegauss(24); GH_W = GH_W / GH_W.sum()

def fit(z, f, n):
    """(a, b, tau) by maximum marginal likelihood of the binomial logit-normal model f ~ Bin(n, sigmoid(a + b z + tau u)), u ~ N(0,1)."""
    def nll(theta):
        a, b, lt = theta; tau = np.exp(lt)
        eta = a + b * z[:, None] + tau * GH_X[None, :]                      # tasks x nodes
        lp = f[:, None] * (-np.logaddexp(0, -eta)) + (n - f)[:, None] * (-np.logaddexp(0, eta))
        m = lp.max(axis=1, keepdims=True)
        return -np.sum(m[:, 0] + np.log(np.sum(np.exp(lp - m) * GH_W[None, :], axis=1)))
    p0 = np.clip((f + 0.5) / (n + 1), 1e-3, 1 - 1e-3); y0 = np.log(p0 / (1 - p0))
    b0 = max(np.polyfit(z, y0, 1)[0], 0.05); a0 = np.mean(y0 - b0 * z)
    r = minimize(nll, x0=[a0, b0, np.log(1.0)], method="L-BFGS-B", bounds=[(-30, 30), (0.01, 10), (-4, 3)])
    return r.x[0], r.x[1], float(np.exp(r.x[2]))

def crossings(a, b, tau, levels=(0.5, 0.01), lo=-12, hi=12):
    def p_avg(zz): return float(np.sum(expit(a + b * zz + tau * GH_X) * GH_W))
    out = []
    for lev in levels:
        g = lambda zz: p_avg(zz) - lev
        out.append(brentq(g, lo, hi) if g(lo) < 0 < g(hi) else float("nan"))
    return out

def pts(z): return 100 * expit(z)

def main():
    npz, d50_rec, d99_rec = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); reps = int(sys.argv[4]) if len(sys.argv) > 4 else 60
    d = np.load(npz, allow_pickle=True); z, f, n = d["z_hat"].astype(float), d["f"].astype(int), d["n"].astype(int)
    order = np.argsort(z); z, f, n = z[order], f[order], n[order]; N = len(z)
    rng = np.random.default_rng(20260924)
    t0 = time.time(); a, b, tau = fit(z, f, n); t_fit = time.time() - t0; d50_full, d99_full = crossings(a, b, tau)
    res = dict(model=str(d["model_id"]), n_tasks=int(N), attempts_range=[int(n.min()), int(n.max())],
               record=dict(d50_z=d50_rec, d99_z=d99_rec, d50_pts=pts(d50_rec), d99_pts=pts(d99_rec)),
               full_data_proxy=dict(a=a, b=b, tau=tau, d50_z=d50_full, d99_z=d99_full, d50_pts=pts(d50_full), d99_pts=pts(d99_full),
                                    d50_err_pts=pts(d50_full) - pts(d50_rec), d99_err_pts=pts(d99_full) - pts(d99_rec), fit_seconds=t_fit),
               cells=[])
    bias50, bias99 = pts(d50_full) - pts(d50_rec), pts(d99_full) - pts(d99_rec)
    for k in (40, 80, 160, 320, 640, N):
        idx_base = np.linspace(0, N - 1, k).round().astype(int)     # spread evenly along the axis (by rank of difficulty)
        for m in (4, 8, 16, 32):
            e50, e99, e50c, e99c, tt = [], [], [], [], []
            for r in range(reps):
                jitter = rng.integers(-max(1, N // (2 * k)), max(1, N // (2 * k)) + 1, size=k) if k < N else 0
                idx = np.clip(idx_base + jitter, 0, N - 1); idx = np.unique(idx)
                zz, nn_full, ff_full = z[idx], n[idx], f[idx]
                mm = np.minimum(m, nn_full); ff = rng.hypergeometric(ff_full, nn_full - ff_full, mm)   # m attempts drawn from the recorded ones
                t1 = time.time(); aa, bb, tt_ = fit(zz, ff, mm); tt.append(time.time() - t1); c50, c99 = crossings(aa, bb, tt_)
                e50.append(pts(c50) - pts(d50_rec)); e99.append(pts(c99) - pts(d99_rec)); e50c.append(e50[-1] - bias50); e99c.append(e99[-1] - bias99)
            e50, e99, e50c, e99c = map(np.array, (e50, e99, e50c, e99c))
            cell = dict(tasks=int(len(idx)), attempts=int(m), total_attempts=int(len(idx) * m), reps=reps, fit_seconds_median=float(np.median(tt)),
                        d50_abs_err_pts_p50=float(np.nanmedian(np.abs(e50))), d50_abs_err_pts_p80=float(np.nanpercentile(np.abs(e50), 80)),
                        d99_abs_err_pts_p50=float(np.nanmedian(np.abs(e99))), d99_abs_err_pts_p80=float(np.nanpercentile(np.abs(e99), 80)),
                        d50_bias_pts=float(np.nanmean(e50)), d99_bias_pts=float(np.nanmean(e99)),
                        calibrated_d50_abs_err_pts_p80=float(np.nanpercentile(np.abs(e50c), 80)), calibrated_d99_abs_err_pts_p80=float(np.nanpercentile(np.abs(e99c), 80)),
                        nan_frac=float(np.mean(np.isnan(e99))))
            res["cells"].append(cell)
            print(f"k={cell['tasks']:>4} m={m:>2} ({cell['total_attempts']:>6} attempts) | D50 |err| p50 {cell['d50_abs_err_pts_p50']:.2f} p80 {cell['d50_abs_err_pts_p80']:.2f} bias {cell['d50_bias_pts']:+.2f} | D99 |err| p50 {cell['d99_abs_err_pts_p50']:.2f} p80 {cell['d99_abs_err_pts_p80']:.2f} bias {cell['d99_bias_pts']:+.2f} | calibrated p80 {cell['calibrated_d50_abs_err_pts_p80']:.2f}/{cell['calibrated_d99_abs_err_pts_p80']:.2f} | fit {cell['fit_seconds_median']:.2f}s nan {cell['nan_frac']:.2f}", flush=True)
    out = sys.argv[5] if len(sys.argv) > 5 else "/tmp/probe_read_test.json"; json.dump(res, open(out, "w"), indent=1); print("wrote", out)
    fp = res["full_data_proxy"]; print(f"FULL DATA: proxy D50 {fp['d50_pts']:.2f}% vs record {res['record']['d50_pts']:.2f}% (err {fp['d50_err_pts']:+.2f} pts); D99 {fp['d99_pts']:.2f}% vs record {res['record']['d99_pts']:.2f}% (err {fp['d99_err_pts']:+.2f} pts); tau {tau:.2f}; fit {t_fit:.1f}s")

if __name__ == "__main__":
    main()

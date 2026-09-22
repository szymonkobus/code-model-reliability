import numpy as np, math
def local_logistic(zx, counts, sigma, mults=None, eval_idx=None):
    z = np.asarray(zx, float)
    fail = np.array([n - c for c, n in counts], float)
    tot = np.array([n for _, n in counts], float)
    m = None if mults is None else np.asarray(mults, float)
    out_a = np.empty(len(z))
    out_se = np.empty(len(z))
    a, b = None, 1.0
    sel = (np.arange(len(z)) if eval_idx is None
           else np.asarray(eval_idx, dtype=int))
    order = sel[np.argsort(z[sel], kind="stable")]
    for i in order:
        z0 = z[i]
        w = np.exp(-0.5 * ((z - z0) / sigma) ** 2)
        if m is not None:
            w = w * m
        u = z - z0

        def cold_start():
            p0 = (w @ fail + 0.5) / (w @ tot + 1)
            return float(np.log(p0 / (1 - p0))), 1.0

        def nll(ai, bi):
            eta = np.clip(ai + bi * u, -30, 30)
            s = -(w * (fail * eta - tot * np.logaddexp(0, eta))).sum()
            return s - (0.5 * ai - np.logaddexp(0, ai))  # pseudo obs

        if a is None or not np.isfinite(a) or abs(a) > 30:
            a, b = cold_start()  # first point, or a diverged neighbour
        cur = nll(a, b)
        for _ in range(60):
            eta = np.clip(a + b * u, -30, 30)
            p = 1 / (1 + np.exp(-eta))
            pa = 1 / (1 + np.exp(-a))
            r = w * (fail - tot * p)
            g0 = r.sum() + (0.5 - pa)
            g1 = r @ u
            wt = w * tot * p * (1 - p)
            h00 = wt.sum() + pa * (1 - pa)
            h01 = wt @ u
            h11 = (wt * u) @ u + 1e-9
            det = h00 * h11 - h01 * h01
            if det <= 0:
                break
            da = (h11 * g0 - h01 * g1) / det
            db = (-h01 * g0 + h00 * g1) / det
            step = 1.0
            while step > 1e-8 and nll(a + step * da, b + step * db) > cur:
                step /= 2
            if step <= 1e-8:
                break
            a += step * da
            b += step * db
            if not (np.isfinite(a) and np.isfinite(b)) or abs(a) > 30:
                a, b = cold_start()  # divergence guard: restart this point cold
                cur = nll(a, b)
                continue
            new = nll(a, b)
            if cur - new < 1e-10:
                cur = new
                break
            cur = new
        # se(a) from the observed information at the optimum
        eta = np.clip(a + b * u, -30, 30)
        p = 1 / (1 + np.exp(-eta))
        pa = 1 / (1 + np.exp(-a))
        wt = w * tot * p * (1 - p)
        h00 = wt.sum() + pa * (1 - pa)
        h01 = wt @ u
        h11 = (wt * u) @ u + 1e-9
        det = h00 * h11 - h01 * h01
        out_a[i] = a
        out_se[i] = float(np.sqrt(max(h11 / det, 0.0)))
    if eval_idx is None:
        return out_a, out_se
    return out_a[sel], out_se[sel]


# --- palette chrome (dataviz reference, light surface) ---
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"



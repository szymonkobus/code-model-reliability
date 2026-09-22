# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Probe 10: what does the PRIOR favor in logit-logit space? Draw curves
from the exact prior (same domain/basis as the real fits), measure rms
deviation from each draw's own OLS line, in the central band and in the
tails. Compare with the posterior median bend (0.065)."""
import numpy as np

rng = np.random.default_rng(7)
# real domain from the saved config (Qwen3-8B config values)
center, L, M = -0.6404836582376188, 7.1884018436702455, 40
zg = np.linspace(-4.97, 3.69, 200)     # observed z_hat range
j = np.arange(1, M + 1)
w = j * np.pi / (2 * L)
phi = np.sqrt(1 / L) * np.sin(w * (zg[:, None] - center + L))

N = 4000
mu0 = rng.normal(0, 3, N)
mu1 = np.abs(rng.normal(0, 3, N))
eta = np.abs(rng.normal(0, 2, N))
ell = np.exp(rng.normal(np.log(1.1), 0.5, N))
beta = rng.normal(0, 1, (N, M))
sq = eta[:, None] * (2*np.pi)**0.25 * np.sqrt(ell[:, None]) * np.exp(-0.25*(ell[:, None]*w[None, :])**2)
curves = mu0[:, None] + mu1[:, None]*zg[None, :] + (beta*sq) @ phi.T

def rms_bend(c, mask):
    z, y = zg[mask], c[mask]
    if len(z) < 10: return np.nan
    b, a = np.polyfit(z, y, 1)
    return np.sqrt(np.mean((y - (b*z + a))**2))

full = np.array([rms_bend(c, np.ones_like(zg, bool)) for c in curves])
# in-band per draw: where |curve| <= 4.6 (the observable window of that draw)
inband = np.array([rms_bend(c, np.abs(c) <= 4.6) for c in curves])
inband = inband[~np.isnan(inband)]
print(f"PRIOR curve bend (rms dev from own straight line), N={N} draws:")
print(f"  over full z-range:  median {np.median(full):.3f}  [10,90]% [{np.quantile(full,.1):.3f},{np.quantile(full,.9):.3f}]")
print(f"  within own |logit|<=4.6 band (n={len(inband)}): median {np.median(inband):.3f}  [10,90]% [{np.quantile(inband,.1):.3f},{np.quantile(inband,.9):.3f}]")
print(f"  P(bend <= 0.065, the posterior median) = full {np.mean(full<=0.065):.3f} / in-band {np.mean(inband<=0.065):.3f}")
print(f"  prior GP wiggle scale eta: median {np.median(eta):.2f}")

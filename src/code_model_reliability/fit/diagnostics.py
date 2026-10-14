"""Convergence statistics of a chain-grouped array: rank-normalised split R-hat and bulk effective sample size.

The estimators follow Vehtari et al. (2021): the draws are rank-normalised, every chain split in two, and
NumPyro's split R-hat and effective sample size taken on the result; R-hat is the larger of the bulk value and
the value on the folded draws (absolute deviations from the median). Rank-based statistics handle censored
crossing draws placed at minus or plus infinity.

Reads nothing and writes nothing; ``engine`` and ``gates`` call these on arrays of shape (chains, draws).
"""

from __future__ import annotations

import numpy as np
from numpyro.diagnostics import effective_sample_size, split_gelman_rubin
from scipy.special import ndtri
from scipy.stats import rankdata


def rank_normal(x):
    r = rankdata(x, method="average", axis=None).reshape(x.shape)
    return ndtri((r - 0.375) / (x.size + 0.25))


def split_halves(x):
    c, n = x.shape
    h = n // 2
    return x[:, :2 * h].reshape(c * 2, h)


def bulk_ess(x):
    """Bulk effective sample size of a (chains, draws) array.

    A constant finite array (a posterior pinned to one value) returns the number of draws; a constant infinite
    array is a crossing censored to one side on every draw, which has no numeric draws to count, and returns
    NaN so a gate can say so instead of passing by default."""
    x = np.asarray(x, float)
    if np.all(x == x.flat[0]):
        return float(x.size) if np.isfinite(x.flat[0]) else float("nan")
    return float(effective_sample_size(split_halves(rank_normal(x))))


def rhat(x):
    """Rank-normalised split R-hat of a (chains, draws) array: the larger of the bulk and the folded value."""
    x = np.asarray(x, float)
    if np.all(x == x.flat[0]):
        return 1.0
    r_bulk = float(split_gelman_rubin(rank_normal(x)))
    med = np.median(x)
    if np.isinf(med):
        # more than half the draws are censored to one side: fold about the infinite median directly, draws at
        # it at distance zero and everything else at infinity, which is rank-identical to |x - med| where that
        # is defined and free of NaN
        folded = np.where(x == med, 0.0, np.inf)
    else:
        folded = np.abs(x - med)
    r_tail = (1.0 if np.all(folded == folded.flat[0]) else float(split_gelman_rubin(rank_normal(folded))))
    return max(r_bulk, r_tail)


def chain_array(z, censor, chains):
    """Per-draw crossings exported chain-major (a flat list of length chains x draws) as a (chains, draws) array
    with censored draws at minus infinity (left) or plus infinity (right); None when the length does not divide."""
    n = len(z)
    if n == 0 or chains <= 0 or n % chains:
        return None
    arr = np.empty(n, float)
    for i, (v, c) in enumerate(zip(z, censor)):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            arr[i] = -np.inf if int(c) < 0 else np.inf
        else:
            arr[i] = float(v)
    return arr.reshape(chains, n // chains)

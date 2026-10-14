"""The settings of record and the pure rules of the fit, usable without the sampler's libraries.

What is here: the sampler and basis settings every published fit ran under; the HSGP domain and basis-size rules;
the two crossing rules (``first`` and ``middle``) applied per posterior draw to a curve on a grid; the summary of a
level's crossing draws (median, 80% interval, censored fractions) with the censored draws counted beyond the end
of the scale they lie past. ``engine`` imports these; ``crossings`` and the tests use them on their own.

Everything here is NumPy only. The constants are named once and their values are the ones the published tables
were produced with; a different value is a different fit and must be declared in the result's ``config`` block.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import expit

# ----------------------------------------------------------------------------------------------------- settings
SEED = 20260825
"""The random seed of every fit of record. With the library pins of ``pyproject.toml`` a rerun on the same
machine class reproduces the draws bit for bit; a different numpyro or jax moves the crossings by up to
about 0.05 on the difficulty scale, which is why the pins are part of the method."""

CHAINS = 4
WARMUP = 2000
SAMPLES = 8000
"""Four chains of 2,000 warm-up and 8,000 kept draws: the layout of every published fit. Shorter chains are
for smoke tests; longer ones were used as checks and never changed a published number beyond its band."""

TARGET_ACCEPT = 0.995
"""The sampler's target acceptance. The published fits use 0.995 because at 0.9 the chains diverged on the
arms whose tasks are nearly all failed or all passed; the higher target cured that at the price of time."""

MAX_TREE_DEPTH = 10
"""NumPyro's default tree depth for NUTS; the fits of record did not change it."""

EIV_DEFAULT = True
"""The difficulty of a task enters with its standard error (errors in variables) in every published fit."""

M_BASIS_FLOOR = 40
"""The fewest basis functions of the Hilbert-space Gaussian process; the rule below raises it with the domain."""

C_EXPAND = 1.5
"""The HSGP domain is the task range expanded by this factor about its centre, so the basis is adequate at the
ends of the data."""

WIDEN_SD_MULT = 3.0
"""Before the expansion the task range is widened by three times the largest difficulty standard error, since
the errors-in-variables positions can lie that far outside the estimates."""

GRID_N = 1201
"""The curve is evaluated on a grid of 1,201 points over the observed task range; crossings are interpolated
between grid points, so the grid step is not a resolution limit on the crossing."""

LEVELS = {"d50": 0.50, "d99": 0.01}
"""The two crossings of record and their failure-rate levels: D50 at one half and D99 at one in a hundred.
Their per-draw crossings enter the convergence checks."""

EXTRA_LEVELS = {"d97": 0.03, "d95": 0.05, "d90": 0.10}
"""Further crossings summarised beside the two of record (3%, 5% and 10% failure); never part of the gates."""

ALL_LEVELS = {**LEVELS, **EXTRA_LEVELS}

LEVEL_ALIASES = {"d1": "d99", "d3": "d97", "d5": "d95", "d10": "d90"}
"""Older result files key the levels by their failure rate (``d1`` for the 1% level); readers accept both."""

LT_LO_P, LT_HI_P, LT_STEP = 0.002, 0.995, 0.033
"""The continuous level table: failure-rate levels spaced 0.033 apart in logit from 0.2% to 99.5%, with the
five named levels inserted exactly, so a reader can place a crossing at any level between them."""

CROSSING_RULES = ("first", "middle")
CROSSING_RULE_DEFAULT = "middle"
"""Which crossing of a curve counts when it crosses a level more than once: ``middle`` is the rule of record
(see ``middle_crossings``); ``first`` is the earlier rule, kept to reproduce older fits."""

GATE_RHAT_MAX = 1.01
GATE_ESS_MIN = 400.0
GATE_DIVERGENCE_NOTE = 5
"""The engine's own convergence flags: rank-normalised split R-hat at most 1.01 and bulk effective sample size at
least 400 on the gated quantities; zero divergences passes, fewer than five passes with a note, five or more
fails. The served verdict (``gates``) reads R-hat and the sample size on the crossing draws and the divergences
as a share of the kept draws."""

DIVERGENCE_SHARE_MAX = 0.005
"""A fit fails on divergences when more than half a percent of its kept draws diverged: a handful of divergent
transitions in 32,000 draws, on a curve whose crossings mix, does not move a crossing, while a share above this
marks a geometry the sampler cannot explore; the engine's count-based flag is kept beside as a note."""

GATED_PARAMETERS = ("eta", "ell", "tau", "mu1")
"""The model parameters whose chains are gated, beside the per-draw D50 and D99 crossings."""


def m_basis_rule(L: float) -> int:
    """The number of HSGP basis functions for a domain of half-width ``L``: the squared-exponential adequacy rule
    m >= 1.75 L / ell at the prior's 2.5th percentile of the length scale (0.4), rounded up to a ten, with the
    floor of 40. L 7.35 gives 40, 9.5 gives 50, 12 gives 60. A truncation parameter, not a model change."""
    return max(M_BASIS_FLOOR, 10 * math.ceil(1.75 * float(L) / (10.0 * 0.4)))


def hsgp_domain(z_hat, sd):
    """(centre, L) of the HSGP domain: the task range widened by ``WIDEN_SD_MULT`` times the largest standard
    error, then expanded by ``C_EXPAND`` about its centre; ``L`` is the half-width of the expanded domain."""
    lo = float(np.min(z_hat) - WIDEN_SD_MULT * np.max(sd))
    hi = float(np.max(z_hat) + WIDEN_SD_MULT * np.max(sd))
    center = 0.5 * (lo + hi)
    L = C_EXPAND * 0.5 * (hi - lo)
    return center, L


# ------------------------------------------------------------------------------------------------ crossings
def _logit(q):
    return np.log(q) - np.log1p(-q)


def _interpolate(rates, zgrid, i1s, level):
    """The crossing between grid points i1s-1 and i1s, linear in the logit of the rate (exact to well under
    1e-4 on the scale for a curve smooth at the grid)."""
    rows = np.arange(rates.shape[0])
    r_lo = np.clip(rates[rows, i1s - 1], 1e-12, 1 - 1e-12)
    r_hi = np.clip(rates[rows, i1s], 1e-12, 1 - 1e-12)
    den = _logit(r_hi) - _logit(r_lo)
    safe = np.abs(den) > 0
    frac = np.clip(np.where(safe, (_logit(level) - _logit(r_lo)) / np.where(safe, den, 1.0), 1.0), 0.0, 1.0)
    return zgrid[i1s - 1] + (zgrid[i1s] - zgrid[i1s - 1]) * frac


def first_crossings(rates, zgrid, level):
    """Per draw, the first upward crossing of ``level`` after the curve has been below it.

    ``rates`` is (draws, grid). Returns (z, censor): z is NaN where censored; censor is -1 when the curve is never
    below the level in range (left-censored), +1 when it never reaches the level from below (right-censored),
    0 otherwise. A curve that starts above the level, dips below and rises again crosses at the rise."""
    below = rates < level
    has_below = below.any(axis=1)
    i0 = below.argmax(axis=1)
    idx = np.arange(rates.shape[1])[None, :]
    after = (~below) & (idx > i0[:, None])
    has_cross = after.any(axis=1) & has_below
    i1 = after.argmax(axis=1)
    i1s = np.maximum(i1, 1)
    z_exact = _interpolate(rates, zgrid, i1s, level)
    z = np.where(has_cross, z_exact, np.nan)
    censor = np.where(~has_below, -1, np.where(has_cross, 0, 1)).astype(int)
    return z, censor


def middle_crossings(rates, zgrid, level):
    """Per draw, the middle crossing of ``level``: the rule of record.

    The crossings of one draw are the sign changes of (rate - level) along the grid, plus one at the easy end when
    the curve is already above the level at the easiest grid point (it crossed below the easiest task) and one at
    the hard end when it is still below the level at the hardest grid point (it crosses beyond the hardest task).
    That list has an odd length and its middle entry is the crossing: an interior one gives its position; the
    easy-edge one is a left-censored draw (the crossing lies below the scale), the hard-edge one a right-censored
    draw. A monotone curve gives its one crossing; a curve above the level everywhere is left-censored; below
    everywhere, right-censored; a curve that starts above, dips and rises gives the downward crossing in the
    middle. Returns (z, censor) as ``first_crossings`` does."""
    above = rates >= level
    change = above[:, 1:] != above[:, :-1]
    S = rates.shape[0]
    k_int = change.sum(axis=1)
    easy = above[:, 0]
    hard = ~above[:, -1]
    k = k_int + easy.astype(int) + hard.astype(int)
    mid = k // 2
    z = np.full(S, np.nan)
    censor = np.zeros(S, dtype=int)
    on_easy = easy & (mid == 0)
    on_hard = hard & (mid == k - 1) & ~on_easy
    interior = ~on_easy & ~on_hard
    target = (mid - easy.astype(int)) + 1
    cs = np.cumsum(change, axis=1)
    hit = (cs == target[:, None]) & change
    idx = hit.argmax(axis=1) + 1
    sel = interior & (k_int > 0)
    i1s = np.maximum(idx, 1)
    z_exact = _interpolate(rates, zgrid, i1s, level)
    z[sel] = z_exact[sel]
    censor[on_easy] = -1
    censor[on_hard] = 1
    return z, censor


def crossings_by_rule(rates, zgrid, level, rule=CROSSING_RULE_DEFAULT):
    if rule not in CROSSING_RULES:
        raise ValueError(f"unknown crossing rule {rule!r}; one of {CROSSING_RULES}")
    return middle_crossings(rates, zgrid, level) if rule == "middle" else first_crossings(rates, zgrid, level)


def crossing_counts(rates, zgrid, level):
    """Per draw, the odd number of crossings under the edge rule of ``middle_crossings``."""
    above = rates >= level
    k_int = (above[:, 1:] != above[:, :-1]).sum(axis=1)
    return k_int + above[:, 0].astype(int) + (~above[:, -1]).astype(int)


# ------------------------------------------------------------------------------------------------- summaries
def censored_quantile(unc_sorted, s_lo, s_hi, alpha, lo_end, hi_end):
    """The alpha-quantile over all draws of a crossing when a share ``s_lo`` of them lies below the scale and
    ``s_hi`` above it: the scale's end when alpha falls among the censored draws, else the quantile of the
    uncensored draws (sorted) at the rescaled position (alpha - s_lo) / (1 - s_lo - s_hi)."""
    if alpha <= s_lo:
        return float(lo_end)
    if alpha >= 1 - s_hi:
        return float(hi_end)
    if unc_sorted is None or len(unc_sorted) == 0:
        return None
    return float(np.quantile(unc_sorted, (alpha - s_lo) / (1 - s_lo - s_hi)))


def estimand_block(z, censor, level, grid_lo=None, grid_hi=None, rule=CROSSING_RULE_DEFAULT):
    """Summarise one level's crossing draws.

    Under ``middle`` (the rule of record) the median and the 80% interval are taken over every draw, a censored
    draw counted beyond the end of the scale it lies past, the scale's end printed where a quantile falls among
    censored draws; the same summaries over the uncensored draws alone are kept beside as ``*_conditional``.
    Under ``first`` only the conditional summaries are written, as the older fits did."""
    unc = z[censor == 0]
    blk = {
        "level_fail_rate": level,
        "n_draws": int(z.size),
        "n_uncensored": int(unc.size),
        "p_left_censored": float(np.mean(censor == -1)),
        "p_right_censored": float(np.mean(censor == 1)),
    }
    if unc.size:
        med = float(np.median(unc))
        q10, q90 = (float(np.quantile(unc, q)) for q in (0.10, 0.90))
        blk.update(median_z=med, cri80_z=[q10, q90], median_pct=float(100 * expit(med)),
                   cri80_pct=[float(100 * expit(q10)), float(100 * expit(q90))])
    else:
        blk.update(median_z=None, cri80_z=None, median_pct=None, cri80_pct=None)
    if rule == "middle" and grid_lo is not None and grid_hi is not None:
        s_lo, s_hi = blk["p_left_censored"], blk["p_right_censored"]
        srt = np.sort(unc) if unc.size else None
        blk["median_z_conditional"] = blk["median_z"]
        blk["cri80_z_conditional"] = blk["cri80_z"]
        m = censored_quantile(srt, s_lo, s_hi, 0.50, grid_lo, grid_hi)
        lo = censored_quantile(srt, s_lo, s_hi, 0.10, grid_lo, grid_hi)
        hi = censored_quantile(srt, s_lo, s_hi, 0.90, grid_lo, grid_hi)
        blk.update(median_z=m,
                   cri80_z=([lo, hi] if lo is not None and hi is not None else None),
                   median_pct=(float(100 * expit(m)) if m is not None else None),
                   cri80_pct=([float(100 * expit(lo)), float(100 * expit(hi))] if lo is not None and hi is not None else None),
                   crossing_rule="middle: per draw the middle crossing of the odd list (interior sign changes plus the "
                                 "edge crossings); the median and the 80% interval over all draws with the censored "
                                 "ones beyond their ends; the summaries over the uncensored draws beside as *_conditional")
    return blk


def level_table_levels():
    """The failure-rate levels of the continuous crossing table, the five named levels inserted exactly."""
    def lgt(p):
        return math.log(p / (1.0 - p))
    n_lt = int((lgt(LT_HI_P) - lgt(LT_LO_P)) / LT_STEP) + 2
    return np.unique(np.concatenate([expit(np.linspace(lgt(LT_LO_P), lgt(LT_HI_P), n_lt)),
                                     [0.50, 0.01, 0.03, 0.05, 0.10]]))

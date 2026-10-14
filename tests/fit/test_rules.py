"""The pure rules: the basis-size and domain rules, the two crossing rules on known curves, the censored summaries."""

import numpy as np
import pytest

from code_model_reliability.fit import rules


def test_m_basis_rule_values_of_record():
    assert rules.m_basis_rule(7.35) == 40
    assert rules.m_basis_rule(9.489) == 50
    assert rules.m_basis_rule(12.0) == 60
    assert rules.m_basis_rule(13.268855918857549) == 60


def test_hsgp_domain_widens_then_expands():
    center, L = rules.hsgp_domain(np.array([-1.0, 1.0]), np.array([0.1, 0.1]))
    assert center == pytest.approx(0.0)
    assert L == pytest.approx(1.5 * 1.3)


def _grid():
    return np.linspace(-4, 4, 801)


def test_monotone_curve_crosses_once_under_both_rules():
    z = _grid()
    rates = (1 / (1 + np.exp(-(z - 0.7))))[None, :]
    zf, cf = rules.first_crossings(rates, z, 0.5)
    zm, cm = rules.middle_crossings(rates, z, 0.5)
    assert cf[0] == 0 and cm[0] == 0
    assert zf[0] == pytest.approx(0.7, abs=1e-6)
    assert zm[0] == pytest.approx(0.7, abs=1e-6)
    assert rules.crossing_counts(rates, z, 0.5)[0] == 1


def test_curve_above_everywhere_is_left_censored_and_below_is_right_censored():
    z = _grid()
    above = np.full((1, z.size), 0.9)
    below = np.full((1, z.size), 0.1)
    for fn in (rules.first_crossings, rules.middle_crossings):
        zz, c = fn(above, z, 0.5)
        assert c[0] == -1 and np.isnan(zz[0])
        zz, c = fn(below, z, 0.5)
        assert c[0] == 1 and np.isnan(zz[0])
    assert rules.crossing_counts(above, z, 0.5)[0] == 1
    assert rules.crossing_counts(below, z, 0.5)[0] == 1


def test_dip_curve_first_takes_the_rise_and_middle_the_dip():
    z = _grid()
    # above the level at the easy end, below it between -1 and 1, above again after: crossings at -1 (down) and 1 (up)
    rates = np.where((z > -1) & (z < 1), 0.2, 0.8)[None, :]
    zf, cf = rules.first_crossings(rates, z, 0.5)
    zm, cm = rules.middle_crossings(rates, z, 0.5)
    assert cf[0] == 0 and zf[0] == pytest.approx(1.0, abs=0.02)
    assert cm[0] == 0 and zm[0] == pytest.approx(-1.0, abs=0.02)
    assert rules.crossing_counts(rates, z, 0.5)[0] == 3


def test_crossings_by_rule_rejects_an_unknown_rule():
    with pytest.raises(ValueError):
        rules.crossings_by_rule(np.zeros((1, 5)), np.arange(5.0), 0.5, "other")


def test_censored_quantile_places_the_end_where_the_quantile_is_censored():
    unc = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    assert rules.censored_quantile(unc, 0.6, 0.0, 0.5, -9.0, 9.0) == -9.0
    assert rules.censored_quantile(unc, 0.0, 0.6, 0.5, -9.0, 9.0) == 9.0
    # 20% censored below: the median sits at the in-span quantile (0.5 - 0.2) / 0.8 = 0.375
    assert rules.censored_quantile(unc, 0.2, 0.0, 0.5, -9.0, 9.0) == pytest.approx(np.quantile(unc, 0.375))


def test_estimand_block_middle_rule_summarises_over_all_draws():
    z = np.array([np.nan] * 6 + [0.0, 1.0, 2.0, 3.0])
    cen = np.array([-1] * 6 + [0] * 4)
    blk = rules.estimand_block(z, cen, 0.01, -5.0, 5.0, "middle")
    assert blk["p_left_censored"] == pytest.approx(0.6)
    assert blk["median_z"] == -5.0                      # more than half the draws below the scale
    assert blk["cri80_z"][0] == -5.0
    assert blk["median_z_conditional"] == pytest.approx(1.5)
    assert blk["n_uncensored"] == 4
    first = rules.estimand_block(z, cen, 0.01, -5.0, 5.0, "first")
    assert first["median_z"] == pytest.approx(1.5) and "median_z_conditional" not in first


def test_level_table_holds_the_named_levels_exactly():
    L = rules.level_table_levels()
    assert np.all(np.diff(L) > 0)
    for p in (0.01, 0.03, 0.05, 0.10, 0.50):
        assert p in L
    assert L[0] == pytest.approx(0.002) and L[-1] == pytest.approx(0.995)

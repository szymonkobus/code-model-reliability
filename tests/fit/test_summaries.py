"""The per-arm summaries: the shape the figures read, the density rule, the numbers equal to the crossings table."""

import json

import numpy as np
import pytest

from code_model_reliability.fit import crossings as cr, summaries as sm


def test_kde_is_normalised_to_its_peak_and_floors_the_bandwidth():
    grid = np.linspace(-1, 1, 201)
    d = sm.kde(np.zeros(100), grid)
    assert d.max() == pytest.approx(1.0) and d[100] == pytest.approx(1.0)
    half = np.exp(-0.5 * (0.02 / 0.02) ** 2)                   # the floor bandwidth 0.02 at one step of 0.02 out
    assert d[102] == pytest.approx(half, abs=1e-3)
    assert np.all(sm.kde(np.zeros(5), grid) == 0)


def test_arm_summary_has_the_pinned_shape(synthetic_result):
    res = synthetic_result()
    s = sm.arm_summary(res, "arm-x")
    assert s["arm"] == "arm-x"
    assert len(s["curves"]["zgrid"]) == 121 and s["curves"]["quantiles_pct"] == [5, 10, 25, 50, 75, 90, 95]
    assert len(s["curves"]["average"]) == 7 and len(s["curves"]["average"][0]) == 121
    assert len(s["curves"]["median_task"]) == 7
    for curve in ("average", "median_task"):
        lv = s["levels"][curve]
        n = len(lv["levels_fail_rate"])
        assert n == len(res["levels_table_avg"]["levels_fail_rate"])
        for k in ("median_z", "cri80_lo_z", "cri80_hi_z", "p_left_censored", "p_right_censored"):
            assert len(lv[k]) == n
        assert lv["method"] and lv["rule"]
        for d in ("d50", "d99"):
            e = s["estimands"][curve][d]
            assert set(e) == {"median_z", "cri80_z", "p_left_censored", "p_right_censored", "status"}
            assert len(s["density"][curve][d]) == 220 and max(s["density"][curve][d]) == pytest.approx(1.0, abs=1e-4)
    g = s["density"]["grid"]
    assert len(g) == 220 and g[0] == pytest.approx(res["grid"]["lo"] - 0.2, abs=1e-4) and g[-1] == pytest.approx(res["grid"]["hi"] + 0.2, abs=1e-4)
    assert set(s["tau"]) == {"median", "cri80"} and set(s["rho"]) == {"median", "cri80"}


def test_summary_numbers_equal_the_crossings_table(synthetic_result):
    res = synthetic_result(left_share_d99=0.15)
    s = sm.arm_summary(res, "arm-x")
    row = cr.row_for(res, "arm-x")
    for d in ("d50", "d99"):
        assert s["estimands"]["average"][d]["median_z"] == pytest.approx(row[f"{d}_z"], abs=5e-5)
        assert s["estimands"]["average"][d]["cri80_z"][0] == pytest.approx(row[f"{d}_lo"], abs=5e-5)
        assert s["estimands"]["average"][d]["status"] == row[f"{d}_status"]
    assert s["estimands"]["median_task"]["d99"]["median_z"] == pytest.approx(row["d99_median_task_z"], abs=5e-5)


def test_censored_draws_sit_at_the_grid_end_in_the_density(synthetic_result):
    res = synthetic_result(left_share_d99=0.6)
    s = sm.arm_summary(res, "arm-x")
    dens = s["density"]["average"]["d99"]
    grid = s["density"]["grid"]
    i_lo = min(range(220), key=lambda i: abs(grid[i] - res["grid"]["lo"]))
    assert dens[i_lo] == pytest.approx(1.0, abs=0.05)


def test_write_summaries_names_files_by_arm(tmp_path, synthetic_result, write_result):
    write_result(synthetic_result(), arm="Family--Model_temp_0.8")
    written = sm.write_summaries(str(tmp_path), tmp_path / "arms")
    assert written == [str(tmp_path / "arms" / "Family--Model_temp_0.8.json")]
    s = json.loads((tmp_path / "arms" / "Family--Model_temp_0.8.json").read_text())
    assert s["arm"] == "Family--Model_temp_0.8"

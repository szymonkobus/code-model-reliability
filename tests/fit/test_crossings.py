"""The crossings reader: the all-draws median, the censored interval, the statuses, the table and its loader."""

import json

import numpy as np
import pytest

from code_model_reliability.fit import crossings as cr


def _unc(res, curve, lv):
    z, c, _ = cr.draws_of(res, curve, lv)
    return np.array([v for v, k in zip(z, c) if k == 0], float)


def test_point_crossing_is_the_median_over_the_draws(synthetic_result):
    res = synthetic_result()
    r = cr.level_read(res, "average", "d50")
    unc = _unc(res, "average", "d50")
    assert r["status"] == cr.STATUS_POINT and r["bound_z"] is None
    assert r["z"] == pytest.approx(float(np.median(unc)))
    assert r["lo"] == pytest.approx(float(np.quantile(unc, 0.10)))
    assert r["hi"] == pytest.approx(float(np.quantile(unc, 0.90)))
    assert r["p_left_censored"] == 0.0 and r["censored_edge"] == "" and r["basis"] == "full"


def test_more_than_half_censored_below_is_a_bound_at_the_easy_end(synthetic_result):
    res = synthetic_result(left_share_d99=0.6)
    r = cr.level_read(res, "average", "d99")
    assert r["status"] == cr.STATUS_BELOW
    assert r["z"] == res["grid"]["lo"] and r["bound_z"] == res["grid"]["lo"] and r["lo"] == res["grid"]["lo"]
    assert r["hi"] > res["grid"]["lo"]
    assert r["p_left_censored"] == pytest.approx(0.6)
    assert r["z_conditional"] == pytest.approx(float(np.median(_unc(res, "average", "d99"))))


def test_more_than_half_censored_above_is_a_bound_at_the_hard_end(synthetic_result):
    res = synthetic_result(right_share_d50=0.7)
    r = cr.level_read(res, "average", "d50")
    assert r["status"] == cr.STATUS_ABOVE and r["z"] == res["grid"]["hi"] and r["hi"] == res["grid"]["hi"]


def test_a_censored_tenth_marks_the_edge_but_keeps_a_point(synthetic_result):
    res = synthetic_result(left_share_d99=0.15)
    r = cr.level_read(res, "average", "d99")
    unc = np.sort(_unc(res, "average", "d99"))
    assert r["status"] == cr.STATUS_POINT and r["censored_edge"] == "lower"
    assert r["lo"] == res["grid"]["lo"]                                       # the 10th percentile is censored
    assert r["z"] == pytest.approx(cr._quantile_linear(list(unc), 100.0 * (0.5 - 0.15) / 0.85))


def test_the_engine_summary_is_the_number_when_only_thinned_draws_exist(synthetic_result):
    res = synthetic_result(with_full=False)
    r = cr.level_read(res, "average", "d50")
    blk = res["estimands_avg"]["d50"]
    assert r["basis"] == "summary" and r["z"] == blk["median_z"] and r["lo"] == blk["cri80_z"][0]
    assert r["status"] == cr.STATUS_POINT
    # the side levels of a fit of record carry every-tenth draws only: the engine's full-chain summary is the number
    res = synthetic_result()
    res["draws_avg"]["d97"] = {"thin": 10, "z": res["draws_avg"]["d50"]["z"], "censor": res["draws_avg"]["d50"]["censor"]}
    res["estimands_avg"]["d97"] = dict(res["estimands_avg"]["d50"], median_z=-1.234)
    assert cr.level_read(res, "average", "d97")["z"] == -1.234


def test_median_task_level_reads_the_typical_draws(synthetic_result):
    res = synthetic_result()
    r = cr.level_read(res, "median_task", "d99")
    assert r["z"] == pytest.approx(float(np.median(_unc(res, "median_task", "d99"))))


def test_level_from_table_exact_and_bracketed(synthetic_result):
    res = synthetic_result()
    lt = res["levels_table_avg"]
    i = lt["levels_fail_rate"].index(0.5)
    exact = cr.level_from_table(res, "average", 0.5)
    assert exact["z"] == pytest.approx(lt["median_z"][i], abs=1e-9) and exact["status"] == cr.STATUS_POINT
    he = cr.level_from_table(res, "average", 0.99)
    L = lt["levels_fail_rate"]
    lo = max(p for p in L if p < 0.99)
    hi = min(p for p in L if p > 0.99)
    assert lt["median_z"][L.index(lo)] < he["z"] < lt["median_z"][L.index(hi)]
    assert cr.level_from_table(res, "average", 0.9999)["status"] == cr.STATUS_NA


def test_old_level_keys_are_read_through_the_aliases(synthetic_result):
    res = synthetic_result()
    for key in ("draws_avg_full", "draws_avg", "draws", "estimands", "estimands_avg"):
        res[key]["d1"] = res[key].pop("d99")
    r = cr.level_read(res, "average", "d99")
    assert r["status"] == cr.STATUS_POINT and r["z"] is not None


def test_row_has_every_column_and_table_round_trips(tmp_path, synthetic_result, write_result):
    res = synthetic_result()
    p = write_result(res, arm="Family--Model-1B_temp_0.8")
    rows = cr.table_for(str(tmp_path), names={"Family--Model-1B_temp_0.8": "Model 1B"})
    assert len(rows) == 1
    row = rows[0]
    assert set(cr.COLUMNS) <= set(row)
    assert row["arm"] == "Family--Model-1B_temp_0.8" and row["model_name"] == "Model 1B"
    assert row["crossing_rule"] == "middle" and row["n_tasks"] == 60 and row["source_sha256_12"]
    cp, sha = cr.write_table(rows, tmp_path / "out", "test")
    back = cr.load_crossings(cp)
    assert back[0]["d99_z"] == repr(row["d99_z"]) and back[0]["d50_status"] == "point"
    j = json.loads((tmp_path / "out" / "crossings.json").read_text())
    assert j["csv_sha256"] == sha and j["rows"][0]["arm"] == row["arm"] and "rule" in j


def test_loader_maps_the_older_column_names(tmp_path):
    old = tmp_path / "old.csv"
    old.write_text("arm,model_id,d50_of_record_z,d1_of_record_z,d1_of_record_status,d1_median_task_z,tau_median,n_axis_tasks\n"
                   "a,a,0.1,-3.0,bound: below the easiest task used (z < -7.9; more than half the draws lie below it),-2.0,1.5,100\n")
    rows = cr.load_crossings(old)
    r = rows[0]
    assert r["d50_z"] == "0.1" and r["d99_z"] == "-3.0" and r["d99_median_task_z"] == "-2.0"
    assert r["tau"] == "1.5" and r["n_tasks"] == "100"
    assert cr.status_kind(r["d99_status"]) == cr.STATUS_BELOW
    assert cr.status_kind("unresolved: the 80% band spans 1.2") == cr.STATUS_POINT
    assert cr.status_kind("point") == cr.STATUS_POINT


def test_gates_merge_into_the_row(synthetic_result):
    res = synthetic_result()
    g = {"arm-x": {"crossing_rhat_d50": 1.002, "crossing_ess_d50": 900.0, "crossing_rhat_d99": 1.1, "crossing_ess_d99": 50.0,
                   "divergences": 0, "gate": "FAIL", "gates_failed": ["rhat", "ess"]}}
    row = cr.row_for(res, "arm-x", gates=g)
    assert row["gate"] == "FAIL" and row["gates_failed"] == "rhat;ess" and row["crossing_rhat_d99"] == 1.1

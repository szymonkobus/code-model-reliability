"""Verdicts to cells and pass@k against hand values."""

from code_model_reliability.land import cells, passk


def verdicts(rows_by_task):
    return {"date": "2000-01-01", "hash": "x", "eval": {
        t: [{"task_id": t, "solution": f"s{i}", "base_status": b, "plus_status": p, "base_fail_tests": [], "plus_fail_tests": []}
            for i, (b, p) in enumerate(rows)]
        for t, rows in rows_by_task.items()}, "pass_at_k": {}}


def test_an_attempt_passes_only_when_both_suites_pass():
    assert passk.attempt_passed({"base_status": "pass", "plus_status": "pass"})
    assert not passk.attempt_passed({"base_status": "pass", "plus_status": "fail"})
    assert not passk.attempt_passed({"base_status": "fail", "plus_status": "pass"})
    assert passk.attempt_passed({"base_status": "pass", "plus_status": "fail"}, suite="base")


def test_pass_at_k_hand_values():
    assert passk.pass_at_k(4, 0, 1) == 0.0 and passk.pass_at_k(4, 4, 1) == 1.0
    assert abs(passk.pass_at_k(4, 2, 1) - 0.5) < 1e-12
    assert abs(passk.pass_at_k(4, 1, 2) - (1 - 3 / 6)) < 1e-12
    assert passk.pass_at_k(4, 1, 4) == 1.0 and passk.pass_at_k(3, 1, 4) is None


def test_cells_count_failures_and_time_limited_attempts():
    v = verdicts({"t1": [("pass", "pass"), ("pass", "fail"), ("fail", "fail"), ("pass", "timeout")], "t2": [("pass", "pass")] * 3})
    per_test = [
        {"task_id": "t1", "attempt": 1, "suite": "plus", "status": "fail", "outcomes": "PTP", "time_outs": [1]},
        {"task_id": "t1", "attempt": 2, "suite": "base", "status": "fail", "outcomes": "PWT", "time_outs": [2]},
        {"task_id": "t1", "attempt": 2, "suite": "plus", "status": "fail", "outcomes": "TTT", "time_outs": [0, 1, 2]},
    ]
    rows = cells.cells_from_verdicts("arm-a", v, "abc123", per_test)
    assert rows[0] == {"arm": "arm-a", "task_id": "t1", "failures": 3, "attempts": 4, "time_limit_fails": 2, "judging": "abc123"}
    assert rows[1]["failures"] == 0 and rows[1]["time_limit_fails"] == 0


def test_cells_round_trip_and_passk_table(tmp_path):
    v = verdicts({"t1": [("pass", "pass"), ("fail", "fail")], "t2": [("pass", "pass"), ("pass", "pass")]})
    rows = cells.cells_from_verdicts("arm-a", v, "abc123")
    path = tmp_path / "cells.csv"
    assert cells.write(rows, path) == 2
    assert cells.read(path) == rows
    table = passk.table("arm-a", "wave2", v)
    assert table == [{"arm": "arm-a", "set": "wave2", "k": 1, "pass_at_k": 0.75}]
    passk.write(table, tmp_path / "passk.csv")
    assert (tmp_path / "passk.csv").read_text().splitlines()[1] == "arm-a,wave2,1,0.750000"

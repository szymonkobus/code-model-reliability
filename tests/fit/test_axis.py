"""The difficulty scale against a hand computation, the panel by coverage, and the files round trip."""

import math

import pytest

from code_model_reliability.fit import axis


def test_two_arm_task_matches_the_hand_computation(cells_file):
    # arm A fails 2 of 4, arm B fails 0 of 4 on task t1
    cells = axis.read_cells(cells_file([("A", "t1", 2, 4), ("B", "t1", 0, 4)]))
    out = axis.difficulty(cells, ["A", "B"])["t1"]
    M, N = 2, 8
    pbar = (2 / 4 + 0 / 4) / M
    q = (N * pbar + 0.5) / (N + 1)
    z = math.log(q / (1 - q))
    v_a = (2 + 0.5) * (2 + 0.5) / ((4 + 1) ** 2 * (4 + 2))      # an arm with 0 < failures < attempts
    v_b = q * (1 - q) / 4                                           # an arm with no failures
    se = (N / (N + 1)) * math.sqrt((v_a + v_b) / M ** 2) / (q * (1 - q))
    assert out.z == pytest.approx(z, abs=1e-12)
    assert out.se == pytest.approx(se, abs=1e-12)
    assert out.n_arms == 2 and out.n_attempts == 8
    assert out.mean_failure_rate == pytest.approx(0.25)
    assert out.se_pooled == pytest.approx(1 / math.sqrt((N + 2) * q * (1 - q)))
    assert out.resolution_logodds == pytest.approx(math.log(17))


def test_all_fail_and_all_pass_tasks_get_finite_positions(cells_file):
    cells = axis.read_cells(cells_file([("A", "hard", 8, 8), ("B", "hard", 8, 8), ("A", "easy", 0, 8), ("B", "easy", 0, 8)]))
    out = axis.difficulty(cells, ["A", "B"])
    q_hard = (16 * 1.0 + 0.5) / 17
    assert out["hard"].z == pytest.approx(math.log(q_hard / (1 - q_hard)))
    assert out["easy"].z == pytest.approx(-out["hard"].z)
    assert math.isfinite(out["hard"].se) and out["hard"].se > 0


def test_only_panel_arms_shape_the_scale(cells_file):
    cells = axis.read_cells(cells_file([("A", "t", 4, 8), ("B", "t", 4, 8), ("C", "t", 8, 8)]))
    with_c = axis.difficulty(cells, ["A", "B", "C"])["t"]
    without_c = axis.difficulty(cells, ["A", "B"])["t"]
    assert with_c.z > without_c.z
    assert without_c.n_arms == 2


def test_voters_by_coverage_threshold(cells_file):
    rows = [("A", f"t{i}", 1, 4) for i in range(10)] + [("B", f"t{i}", 1, 4) for i in range(10)] + [("C", f"t{i}", 1, 4) for i in range(8)]
    cells = axis.read_cells(cells_file(rows))
    assert axis.voters(cells) == ["A", "B"]
    assert axis.voters(cells, threshold=0.8) == ["A", "B", "C"]
    assert axis.voters(cells, exclude=["B"]) == ["A"]
    cov = axis.coverage(cells)
    assert cov["C"] == pytest.approx(0.8)


def test_cells_reader_rejects_impossible_counts(cells_file):
    with pytest.raises(ValueError):
        axis.read_cells(cells_file([("A", "t", 9, 8)]))


def test_axis_csv_and_panel_round_trip(tmp_path, cells_file):
    rows = [("A", f"t{i}", i % 4, 8) for i in range(6)] + [("B", f"t{i}", (i + 1) % 4, 8) for i in range(6)]
    p = cells_file(rows)
    rc = axis.main(["--cells", str(p), "--out", str(tmp_path / "axis.csv")])
    assert rc == 0
    back = axis.read_axis_csv(tmp_path / "axis.csv")
    cells = axis.read_cells(p)
    direct = axis.difficulty(cells, ["A", "B"])
    assert set(back) == set(direct)
    for t in direct:
        assert back[t].z == pytest.approx(direct[t].z, abs=1e-6)
        assert back[t].se == pytest.approx(direct[t].se, abs=1e-6)
        assert back[t].n_attempts == 16
    panel = axis.read_panel(tmp_path / "panel.json")
    assert panel["voters"] == ["A", "B"] and panel["threshold"] == axis.COVERAGE_THRESHOLD
    with open(tmp_path / "axis.csv") as fh:
        assert fh.readline().strip() == ",".join(axis.AXIS_COLUMNS)


def test_an_existing_panel_file_fixes_the_voters(tmp_path, cells_file):
    rows = [(a, f"t{i}", 1, 4) for a in "ABC" for i in range(5)]
    p = cells_file(rows)
    axis.write_panel(tmp_path / "panel.json", {"threshold": 0.9, "voters": ["A"], "excluded_from_voting": ["B", "C"]})
    assert axis.main(["--cells", str(p), "--out", str(tmp_path / "axis.csv"), "--panel", str(tmp_path / "panel.json"),
                      "--panel-out", str(tmp_path / "panel_out.json")]) == 0
    assert all(a.n_arms == 1 for a in axis.read_axis_csv(tmp_path / "axis.csv").values())
    assert axis.read_panel(tmp_path / "panel_out.json")["positioned_only"] == ["B", "C"]

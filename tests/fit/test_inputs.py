"""Cells and the axis to npz inputs: arrays in task order, the manifest, the skip rule, the fit id."""

import numpy as np

from code_model_reliability.fit import axis, inputs


def _setup(cells_file, n_tasks=6):
    rows = []
    for i in range(n_tasks):
        rows += [("A", f"t{i:02d}", i % 3, 8), ("B", f"t{i:02d}", (i + 1) % 3, 8)]
    rows.append(("C", "t00", 1, 8))   # a partly run arm: one cell only
    p = cells_file(rows)
    cells = axis.read_cells(p)
    ax = axis.difficulty(cells, ["A", "B"])
    return p, cells, ax


def test_arrays_follow_task_order_and_hold_failures_and_attempts(cells_file):
    _, cells, ax = _setup(cells_file)
    arr = inputs.arm_arrays(cells, ax, "A")
    assert list(arr["task_ids"]) == sorted(arr["task_ids"])
    assert arr["f"].dtype == np.int64 and arr["n"].dtype == np.int64
    assert list(arr["f"]) == [i % 3 for i in range(6)]
    assert np.all(arr["n"] == 8)
    assert arr["z_hat"][0] == ax["t00"].z and arr["sd"][0] == ax["t00"].se
    assert arr["model_id"] == "A"


def test_build_inputs_writes_npz_manifest_and_skips_small_arms(tmp_path, cells_file):
    _, cells, ax = _setup(cells_file)
    manifest, skipped = inputs.build_inputs(cells, ax, tmp_path / "inputs", min_tasks=5)
    assert [m[0] for m in manifest] == ["A.npz", "B.npz"] and all(m[1] == "on" for m in manifest)
    assert skipped == [{"arm": "C", "n_tasks": 1}]
    rows = inputs.read_manifest(tmp_path / "manifest.tsv")
    assert rows == manifest
    d = np.load(tmp_path / "inputs" / "A.npz", allow_pickle=False)
    assert set(d.files) == {"model_id", "z_hat", "sd", "f", "n", "task_ids"}
    assert str(d["model_id"]) == "A" and len(d["task_ids"]) == 6


def test_fit_id_is_twelve_hex_and_changes_with_cells_or_arms(tmp_path, cells_file):
    p, _, _ = _setup(cells_file)
    a = inputs.fit_id(p, ["A", "B"])
    assert len(a) == 12 and int(a, 16) >= 0
    assert inputs.fit_id(p, ["B", "A"]) == a
    assert inputs.fit_id(p, ["A"]) != a
    q = cells_file([("A", "t00", 1, 8)], name="other.csv")
    assert inputs.fit_id(q, ["A", "B"]) != a


def test_main_runs_end_to_end(tmp_path, cells_file):
    p, _, _ = _setup(cells_file)
    assert axis.main(["--cells", str(p), "--out", str(tmp_path / "f" / "axis.csv")]) == 0
    assert inputs.main(["--cells", str(p), "--axis", str(tmp_path / "f" / "axis.csv"), "--fit-dir", str(tmp_path / "f"),
                        "--min-tasks", "5"]) == 0
    assert (tmp_path / "f" / "inputs" / "A.npz").exists() and (tmp_path / "f" / "manifest.tsv").exists()

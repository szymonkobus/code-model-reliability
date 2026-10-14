"""The reader of the published tables: the fixture loads whole and every shape the contract names is there."""

import pytest

from code_model_reliability.plot.data import published_fits


def test_the_fixture_fit_is_found_and_named(data_dir, fit):
    assert [p.name for p in published_fits(data_dir)] == ["fixture-fit"]
    assert fit.name == "fixture-fit"
    assert fit.meta["set"] == "wave 1+2"
    assert fit.meta["cut"] == "2026-09-10"


def test_the_newest_fit_by_its_cut_day_is_read_when_none_is_named(data_dir, tmp_path):
    import json
    import shutil
    from code_model_reliability.plot.data import load_fit
    src = data_dir / "results" / "published" / "fixture-fit"
    for name, day in (("zz-older", "2026-08-01"), ("aa-newer", "2026-09-30")):
        dst = tmp_path / "results" / "published" / name
        shutil.copytree(src, dst)
        meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
        meta["fit"], meta["cut"] = name, day
        (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    shutil.copytree(data_dir / "runs", tmp_path / "runs")
    assert [p.name for p in published_fits(tmp_path)] == ["zz-older", "aa-newer"]   # by the day, not the name
    assert load_fit(tmp_path).name == "aa-newer"
    assert load_fit(tmp_path, "zz-older").name == "zz-older"


def test_crossings_rows_carry_both_crossings(fit):
    assert len(fit.arms) == 4
    for arm in fit.arms:
        row = fit.crossings[arm]
        assert row.model_name
        assert row.d50.status in ("point", "bound", "unresolved")
        assert row.d99.status in ("point", "bound", "unresolved")
        assert row.d50.z is not None and row.d99.z is not None
        assert row.d50.lo <= row.d50.z <= row.d50.hi
        assert row.d99.lo <= row.d99.z <= row.d99.hi
        assert row.tau[0] is not None and row.rho[0] is not None


def test_axis_is_sorted_from_easiest_to_hardest(fit):
    zs = [t.z for t in fit.axis]
    assert len(zs) == 40
    assert zs == sorted(zs)


def test_cells_cover_every_arm_and_task(fit):
    tasks = {t.task_id for t in fit.axis}
    for arm in fit.arms:
        cells = fit.cells[arm]
        assert set(cells) == tasks
        assert all(0 <= f <= n for f, n in cells.values())


def test_summaries_carry_the_curves_levels_and_densities(fit):
    for arm, s in fit.summaries():
        assert len(s.average.zgrid) == 121
        assert sorted(s.average.quantiles) == [5, 10, 25, 50, 75, 90, 95]
        assert len(s.average.median()) == 121
        assert s.typical is not None
        assert len(s.levels_avg.levels) == len(s.levels.levels) >= 100   # the per-level crossing table under both definitions
        assert all(0 < v < 1 for v in s.levels_avg.levels)
        z, lo, hi = s.levels_avg.at(0.5)
        assert lo <= z <= hi
        assert abs(z - fit.crossings[arm].d50.z) < 0.05   # the table's D50 is the levels table's crossing at one half
        assert set(s.estimands_avg) == {"d50", "d99"}
        assert len(s.density["grid"]) == 220
        assert max(s.density["average"]["d99"]) == 1.0
    assert len(list(fit.summaries())) == 4


def test_the_gates_verdict_is_read_from_the_table(fit, data_dir, tmp_path):
    """The published table's gate column (pass or FAIL) is the one source of an arm's flag; a table without the column
    beside a gates.json is refused rather than read as all passing."""
    import csv
    import shutil
    from code_model_reliability.plot.data import load_fit
    assert fit.crossings["Qwen--Qwen3-8B_temp_0.8"].gate == "fail"
    assert fit.crossings["Qwen--Qwen3-8B_temp_0.8"].gates_failed == ["rhat"]
    for arm in ("Qwen--Qwen3-8B_think_temp_0.6", "claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch"):
        assert fit.crossings[arm].gate == "pass" and fit.crossings[arm].gates_failed == []
    src = data_dir / "results" / "published" / "fixture-fit"
    dst = tmp_path / "results" / "published" / "fixture-fit"
    shutil.copytree(src, dst)
    with open(src / "crossings.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(dst / "crossings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[c for c in rows[0] if c != "gate"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(ValueError, match="no gate column"):
        load_fit(tmp_path)


def test_registry_joins_on_the_arm_id(registry, fit):
    for arm in fit.arms:
        assert registry.arm(arm)["model_id"] and registry.arm(arm)["family"]
    assert registry.model("Qwen--Qwen3-8B_temp_0.8")["family"] == "Qwen3"   # the model row joins on the arm row's model_id
    assert registry.model_name("Qwen--Qwen3-8B_think_temp_0.6") == "Qwen3 8B (thinking)"
    assert registry.run_position("Qwen--Qwen3-8B_temp_0.8") is None
    import dataclasses
    key = "r1-distill-qwen-7b-thinking-rl-fails-1-7-8-fixed-kl"
    run = {"positions": [{"step": 50, "arm": "r1d7b-rl-f17-kl-step0050_think_temp_0.6"}]}   # a run entry in names.json's shape, keyed by its slug
    reg = dataclasses.replace(registry, names={**registry.names, "runs": {key: run}})
    assert reg.run_position("r1d7b-rl-f17-kl-step0050_think_temp_0.6") == (key, 50)

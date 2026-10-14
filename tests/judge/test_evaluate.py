"""The judge end to end on the fixture set: the expected verdicts, the rules that decide the variants, and the
agreement with the harness's own evaluator under its stock settings."""

import dataclasses
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("evalplus")

from code_model_reliability.judge import evaluate, reference, settings, tasks  # noqa: E402
from code_model_reliability.land import cells  # noqa: E402

TEST_SETTINGS = settings.JudgingSettings(
    name="fixture-test", time_limit_floor_s=1.0, time_limit_factor=4.0, set_cap_s=4.0, memory_gib=2.0,
    leading_imports="leading-imports-v4.1-self-shadowing-refined", leading_imports_applied="at-load",
    typing_prelude="typing-prelude-v5", comparison="normalised-values, float tolerance 1e-9, canonical stdout",
    plus_filter=True, typed_inputs=True, reference="isolated", workers=2,
)
RULES_OFF = dataclasses.replace(TEST_SETTINGS, name="rules-off", leading_imports=None, typing_prelude=None)


def statuses(verdicts):
    return {t: [(r["base_status"], r["plus_status"]) for r in rows] for t, rows in verdicts["eval"].items()}


def test_fixture_set_judges_to_the_expected_verdicts_and_cells(fixture_dir, tmp_path):
    record = evaluate.judge(fixture_dir / "tasks" / "fixture_tasks.jsonl", fixture_dir / "samples" / "samples.jsonl",
                            tmp_path, TEST_SETTINGS, workers=2, per_test_rows=True)
    got = json.load(open(tmp_path / "verdicts.json"))
    expected = json.load(open(fixture_dir / "expected" / "verdicts.json"))
    assert statuses(got) == statuses(expected)
    assert record["settings_id"] == TEST_SETTINGS.id
    assert record["n_attempts"] == sum(len(r) for r in expected["eval"].values())
    assert got["pass_at_k"] == expected["pass_at_k"]
    rows = [json.loads(l) for l in open(tmp_path / "per_test.jsonl") if l.strip()]
    got_cells = cells.cells_from_verdicts("fixture-standin", got, record["settings_id"], rows)
    assert got_cells == cells.read(fixture_dir / "expected" / "cells.csv")


def test_each_answer_kind_judges_as_meant(fixture_dir, standin, tmp_path):
    """Every task's four answers under the rules: correct and variant pass, wrong fails on an output, slow fails on
    the time limit; with the import rule off the import-reliant variant fails at definition."""
    task_records = list(tasks.read_records(fixture_dir / "tasks" / "fixture_tasks.jsonl"))
    samples = tmp_path / "samples.jsonl"
    with open(samples, "w") as fh:
        for t in task_records:
            for kind in ("correct", "variant", "wrong", "slow"):
                fh.write(json.dumps({"task_id": t["task_id"], "solution": t["fixture_answers"][kind]}) + "\n")
    evaluate.judge(fixture_dir / "tasks" / "fixture_tasks.jsonl", samples, tmp_path / "on", TEST_SETTINGS, workers=2, per_test_rows=True)
    got = json.load(open(tmp_path / "on" / "verdicts.json"))
    per_test = [json.loads(l) for l in open(tmp_path / "on" / "per_test.jsonl") if l.strip()]
    for t in task_records:
        rows = got["eval"][t["task_id"]]
        assert (rows[0]["base_status"], rows[0]["plus_status"]) == ("pass", "pass"), t["task_id"]
        assert (rows[1]["base_status"], rows[1]["plus_status"]) == ("pass", "pass"), (t["task_id"], "variant")
        assert "fail" in (rows[2]["base_status"], rows[2]["plus_status"]), (t["task_id"], "wrong")
        assert (rows[3]["base_status"], rows[3]["plus_status"]) != ("pass", "pass"), (t["task_id"], "slow")
        slow_rows = [p for p in per_test if p["task_id"] == t["task_id"] and p["attempt"] == 3]
        assert slow_rows and all(p["time_outs"] for p in slow_rows), (t["task_id"], "slow")
        wrong_rows = [p for p in per_test if p["task_id"] == t["task_id"] and p["attempt"] == 2]
        assert any("W" in p["outcomes"] for p in wrong_rows), (t["task_id"], "wrong")
    evaluate.judge(fixture_dir / "tasks" / "fixture_tasks.jsonl", samples, tmp_path / "off", RULES_OFF, workers=2)
    off = json.load(open(tmp_path / "off" / "verdicts.json"))
    variant = off["eval"]["fixture/has_close_pair"][1]
    assert (variant["base_status"], variant["plus_status"]) == ("fail", "fail"), "without the import rule the prompt's import is missing"


def test_agrees_with_the_harness_stock_evaluator_on_the_fixture(fixture_dir, tmp_path):
    """The harness's own evaluator, run on the same tasks and programs in a subprocess with the fixture tasks as its
    dataset, gives the same statuses as this judge under a record with the harness's own limits and no import
    rule, on the answers whose verdict does not depend on the comparison rule."""
    task_records = list(tasks.read_records(fixture_dir / "tasks" / "fixture_tasks.jsonl"))
    samples = tmp_path / "samples.jsonl"
    with open(samples, "w") as fh:
        for t in task_records:
            for kind in ("correct", "wrong"):
                fh.write(json.dumps({"task_id": t["task_id"], "solution": t["fixture_answers"][kind]}) + "\n")
    stock_like = dataclasses.replace(settings.STOCK_EVALUATOR, name="stock-like", leading_imports=None, plus_filter=False,
                                     typed_inputs=False, memory_gib=2.0)
    evaluate.judge(fixture_dir / "tasks" / "fixture_tasks.jsonl", samples, tmp_path / "ours", stock_like, workers=2)
    ours = json.load(open(tmp_path / "ours" / "verdicts.json"))
    env = dict(os.environ, HUMANEVAL_OVERRIDE_PATH=str(fixture_dir / "tasks" / "harness_override.jsonl"),
               XDG_CACHE_HOME=str(tmp_path / "cache"), OMP_NUM_THREADS="1")
    run = subprocess.run([sys.executable, "-m", "evalplus.evaluate", "--dataset", "humaneval", "--samples", str(samples),
                          "--parallel", "2"], capture_output=True, text=True, env=env, timeout=600)
    assert run.returncode == 0, run.stderr[-2000:]
    theirs = json.load(open(tmp_path / "samples.eval_results.json"))
    assert statuses(ours) == statuses(theirs)
    assert ours["pass_at_k"] == theirs["pass_at_k"]


def test_reference_outputs_are_isolated_and_cached(fixture_dir, tmp_path):
    probs = tasks.load_problems(fixture_dir / "tasks" / "fixture_tasks.jsonl")
    p = probs["fixture/half_box_volume"]
    exp = reference.expected_outputs(p, tmp_path)
    assert exp["base"][0] == 12.0 and len(exp["plus_time"]) == len(p["plus_input"])
    again = reference.expected_outputs(p, tmp_path)
    assert again == exp
    bad = dict(p, canonical_solution="    raise RuntimeError('a defective reference')\n")
    with pytest.raises(RuntimeError):
        reference.expected_outputs(bad)

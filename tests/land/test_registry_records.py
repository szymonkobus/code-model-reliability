"""The registry's schema and builder, the raw-reply reader, the per-test summary."""

import json

import pytest

from code_model_reliability.land import per_test, records, registry


def arm_dir(tmp_path, name, stem, form="plain", judging_id="j1"):
    d = tmp_path / name
    d.mkdir()
    (d / "generation.json").write_text(json.dumps({
        "arm": name, "model_stem": stem, "model_id": stem.replace("--", "/"), "task_set": "wave2", "attempts_per_task": 32,
        "form": form, "protocol": "two-phase-thinking" if form == "thinking" else "plain-chat", "protocol_version": None,
        "sampling": {"temperature": 0.6 if form == "thinking" else 0.8, "top_p": 1.0},
        "extractor": {"name": "fenced-block", "stamp": "v2@9ac5071166f8adaa", "sha256": "e" * 64},
    }))
    (d / "judging.json").write_text(json.dumps({"settings_id": judging_id}))
    return d


def test_registry_rows_join_the_map_and_round_trip(tmp_path):
    arm_map = {"Org--Model-7B": {"stem": "Org--Model-7B", "arm": "model-7b", "model_id": "Org/Model-7B", "model_name": "Model 7B", "family": "Model"}}
    dirs = [arm_dir(tmp_path, "model-7b_temp_0.8", "Org--Model-7B"), arm_dir(tmp_path, "model-7b_think_temp_0.6", "Org--Model-7B", "thinking")]
    rows = registry.build(dirs, arm_map)
    assert [r["arm"] for r in rows] == ["model-7b_temp_0.8", "model-7b_think_temp_0.6"]
    assert rows[0]["model_name"] == "Model 7B" and rows[0]["family"] == "Model" and rows[0]["judging"] == "j1"
    assert rows[1]["form"] == "thinking" and rows[1]["temperature"] == 0.6 and rows[1]["sets"] == ["wave2"]
    path = tmp_path / "arms.jsonl"
    registry.write(rows, path)
    header, back = registry.read(path)
    assert header["n_rows"] == 2 and back[0]["extractor_sha256"] == "e" * 64
    assert back[0]["extractor"] == "v2@9ac5071166f8adaa"


def test_registry_refuses_a_duplicate_arm_and_an_unknown_form(tmp_path):
    arm_map = {}
    dirs = [arm_dir(tmp_path, "a", "S"), arm_dir(tmp_path, "b", "S")]
    (dirs[1] / "generation.json").write_text(json.dumps({"arm": "a", "form": "plain", "protocol": "plain-chat"}))
    with pytest.raises(ValueError):
        registry.build(dirs, arm_map)
    bad = arm_dir(tmp_path, "c", "S", form="mystery")
    with pytest.raises(ValueError):
        registry.build([bad], arm_map)


def test_registry_read_checks_the_header_count(tmp_path):
    path = tmp_path / "arms.jsonl"
    path.write_text(json.dumps({"schema": registry.SCHEMA, "n_rows": 2}) + "\n" + json.dumps({"arm": "a"}) + "\n")
    with pytest.raises(ValueError):
        registry.read(path)


def test_raw_reader_normalises_the_three_shapes(tmp_path):
    p = tmp_path / "raw.jsonl"
    p.write_text(json.dumps({"task_id": "t", "solution": "a"}) + "\n" + json.dumps({"task_id": "t", "solution": "b"}) + "\n")
    rows = list(records.iter_raw(p, "raw-v1"))
    assert [r["attempt"] for r in rows] == [0, 1] and rows[1]["text"] == "b"
    p.write_text(json.dumps({"task_id": "t", "sample": 3, "answer_raw": "x", "think_text": "y", "think_finish_reason": "length", "closure": "forced"}) + "\n")
    r = next(iter(records.iter_raw(p, "records-v2")))
    assert r == {"task_id": "t", "attempt": 3, "text": "x", "think_text": "y", "finish": "length", "closure": "forced"}
    p.write_text(json.dumps({"task_id": "t", "sample": 1, "text": "z", "stop_reason": "end_turn"}) + "\n")
    assert next(iter(records.iter_raw(p, "records-api-v1")))["finish"] == "end_turn"
    with pytest.raises(ValueError):
        list(records.iter_raw(p, "other"))


def test_per_test_summary_statistics():
    rows = [
        {"task_id": "t", "attempt": 0, "suite": "base", "outcomes": "PW"},
        {"task_id": "t", "attempt": 1, "suite": "base", "outcomes": "PW"},
        {"task_id": "t", "attempt": 2, "suite": "base", "outcomes": "WW"},
    ]
    s = per_test.summarise("arm", rows)[0]
    assert s["n_fails"] == 3 and s["distinct"] == 2 and abs(s["modal_share"] - 2 / 3) < 1e-9
    assert abs(s["collision"] - 2 / 6) < 1e-9
    assert abs(s["entropy_bits"] - 0.9182958340544896) < 1e-9

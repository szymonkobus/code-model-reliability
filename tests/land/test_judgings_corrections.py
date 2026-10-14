"""The newest judging of a task wins; corrections live beside the judged file and never rewrite it."""

import json

import pytest

from code_model_reliability.land import corrections, judgings


def verdicts(rows_by_task, solutions=None):
    out = {"date": "2000-01-01", "hash": "x", "eval": {}, "pass_at_k": {}}
    for t, rows in rows_by_task.items():
        out["eval"][t] = [
            {"task_id": t, "solution": (solutions or {}).get((t, i), f"{t}-{i}"), "base_status": b, "plus_status": p,
             "base_fail_tests": [], "plus_fail_tests": []}
            for i, (b, p) in enumerate(rows)]
    return out


def test_newest_judging_wins_per_task_and_names_itself():
    first = verdicts({"t1": [("fail", "fail"), ("pass", "pass")], "t2": [("pass", "pass")]})
    rejudge = verdicts({"t1": [("pass", "pass"), ("pass", "pass")]})
    composed, won = judgings.compose([(first, "j0"), (rejudge, "j1")])
    assert [r["base_status"] for r in composed["eval"]["t1"]] == ["pass", "pass"]
    assert won == {"t1": "j1", "t2": "j0"}
    assert composed["pass_at_k"]["plus"]["pass@1"] == 1.0


def test_a_rejudging_of_other_attempts_is_refused():
    first = verdicts({"t1": [("fail", "fail")]})
    other = verdicts({"t1": [("pass", "pass")]}, solutions={("t1", 0): "another program"})
    with pytest.raises(ValueError):
        judgings.compose([(first, "j0"), (other, "j1")])


def test_compose_directory_orders_numbered_files(tmp_path):
    (tmp_path / "verdicts.json").write_text(json.dumps(verdicts({"t1": [("fail", "fail")]})))
    (tmp_path / "judging.json").write_text(json.dumps({"settings_id": "aaa"}))
    (tmp_path / "verdicts.2.json").write_text(json.dumps(verdicts({"t1": [("pass", "pass")]})))
    (tmp_path / "judging.2.json").write_text(json.dumps({"settings_id": "ccc"}))
    (tmp_path / "verdicts.1.json").write_text(json.dumps(verdicts({"t1": [("pass", "fail")]})))
    (tmp_path / "judging.1.json").write_text(json.dumps({"settings_id": "bbb"}))
    composed, won = judgings.compose_directory(tmp_path)
    assert composed["eval"]["t1"][0]["plus_status"] == "pass" and won == {"t1": "ccc"}


def test_corrections_apply_by_entry_hash_and_leave_the_judged_file_alone(tmp_path):
    v = verdicts({"t1": [("fail", "fail"), ("pass", "pass")]})
    judged = tmp_path / "verdicts.json"
    judged.write_text(json.dumps(v))
    before = judged.read_bytes()
    rows = [
        {"task_id": "t1", "attempt": 0, "kind": "continuation", "solution_sha256": corrections.solution_sha256("t1-0"),
         "new_solution": "t1-0 completed", "base_status": "pass", "plus_status": "pass", "judging": "j2", "note": "cut at the output limit"},
        {"task_id": "t1", "attempt": 1, "kind": "verdict", "solution_sha256": "0" * 64,
         "base_status": "fail", "plus_status": "fail", "judging": "j2"},
    ]
    companion = tmp_path / "corrections.jsonl"
    assert corrections.append_corrections(rows, companion) == 2
    composed, applied, refused = corrections.apply_corrections(v, corrections.read_corrections(companion))
    assert len(applied) == 1 and len(refused) == 1 and refused[0]["reason"] == "the attempt holds a different solution text"
    entry = composed["eval"]["t1"][0]
    assert entry["solution"] == "t1-0 completed" and entry["base_status"] == "pass"
    assert entry["corrected"]["previous"] == {"base_status": "fail", "plus_status": "fail"}
    assert len(composed["eval"]["t1"]) == 2, "a continuation is one attempt in two parts"
    assert judged.read_bytes() == before, "the judged file is never rewritten"
    assert v["eval"]["t1"][0]["solution"] == "t1-0", "the input verdicts are not modified either"


def test_a_malformed_correction_is_refused_before_it_is_written(tmp_path):
    with pytest.raises(ValueError):
        corrections.append_corrections([{"task_id": "t1", "attempt": 0, "kind": "guess"}], tmp_path / "c.jsonl")
    assert not (tmp_path / "c.jsonl").exists() or (tmp_path / "c.jsonl").read_text() == ""

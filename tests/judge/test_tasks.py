"""The task loader and the input rules: the plus-input filter by value, the typed inputs, the kinds."""

import pytest

pytest.importorskip("evalplus")

from code_model_reliability.judge import tasks  # noqa: E402


def test_parent_and_kinds():
    assert tasks.parent_id("Mbpp/273~twin1") == "Mbpp/273"
    assert tasks.parent_id("fixture/x") == "fixture/x"
    assert tasks.harness_kind({"task_id": "Mbpp/2~twin1"}) == "mbpp"
    assert tasks.harness_kind({"task_id": "HumanEval/0"}) == "humaneval"
    assert tasks.harness_kind({"task_id": "ccplus/1497_D"}) == "humaneval"
    assert tasks.is_stdin_stdout({"task_id": "ccplus/1497_D"})
    assert not tasks.is_stdin_stdout({"task_id": "ccplus/1497_D", "io_mode": "function"})
    assert tasks.is_stdin_stdout({"task_id": "written/x", "io_mode": "stdio"})


def test_plus_filter_matches_by_value_and_reaches_a_written_copy():
    probs = {
        "HumanEval/114~twin1": {"task_id": "HumanEval/114~twin1", "plus_input": [[[1, 2]], [[True, True]], [[3]]]},
        "HumanEval/0": {"task_id": "HumanEval/0", "plus_input": [[[1.0], 0.5]]},
    }
    table = {"HumanEval/114": {"removed_inputs": [[[True, True]]]}}
    removed = tasks.apply_plus_filter(probs, table)
    assert removed == {"HumanEval/114~twin1": 1}
    assert probs["HumanEval/114~twin1"]["plus_input"] == [[[1, 2]], [[3]]]
    assert probs["HumanEval/0"]["plus_input"] == [[[1.0], 0.5]]


def test_record_fields_take_precedence_over_the_tables():
    probs = {
        "w/one": {"task_id": "w/one", "plus_input": [[1], [True], [2]], "plus_inputs_removed": [[True]], "base_input": [[0]], "input_shapes": None, "typed_by_harness": False},
        "w/two": {"task_id": "w/two", "plus_input": [[[1, 2]]], "plus_inputs_removed": None, "base_input": [[[3, 4]]], "input_shapes": ["tuple[int,int]"], "typed_by_harness": False},
    }
    assert tasks.apply_plus_filter(probs, {}) == {"w/one": 1}
    assert probs["w/one"]["plus_input"] == [[1], [2]]
    assert tasks.apply_typed_inputs(probs, {}) == ["w/two"]
    assert probs["w/two"]["base_input"] == [[(3, 4)]] and probs["w/two"]["plus_input"] == [[(1, 2)]]


def test_plus_filter_data_file_lists_the_tasks_of_record():
    """The wave 1 removed-inputs file is written by the tasks export into the data directory: the 155 wave 1 tasks
    with a removed input (1,594 inputs), and the two harness tasks with one that are outside wave 1, by id."""
    if not tasks.PLUS_FILTER_FILE.exists():
        pytest.skip("no exported data directory beside this checkout")
    data = tasks._load_json(tasks.PLUS_FILTER_FILE)
    table = data["tasks"]
    assert len(table) == 155 and "HumanEval/114" in table
    assert sum(len(v) for v in table.values()) == 1594
    assert sorted(data["tasks_outside_wave_1"]) == ["Mbpp/233", "Mbpp/555"]


def test_typed_inputs_use_the_declared_shapes_and_the_harness_rule():
    probs = {
        "written/edges": {"task_id": "written/edges", "base_input": [[3, [[1, 2], [2, 3]]]], "plus_input": [], "typed_by_harness": False},
        "Mbpp/2~twin1": {"task_id": "Mbpp/2~twin1", "base_input": [[[3, 4, 5], [5, 4, 3]]], "plus_input": [], "typed_by_harness": False},
        "fixture/plain": {"task_id": "fixture/plain", "base_input": [[1]], "plus_input": [], "typed_by_harness": False},
    }
    touched = tasks.apply_typed_inputs(probs, {"written/edges": ["int", "list[tuple[int,int]]"]})
    assert sorted(touched) == ["Mbpp/2~twin1", "written/edges"]
    assert probs["written/edges"]["base_input"] == [[3, [(1, 2), (2, 3)]]]
    assert probs["Mbpp/2~twin1"]["base_input"] == [[(3, 4, 5), (5, 4, 3)]]
    assert probs["fixture/plain"]["base_input"] == [[1]]
    assert tasks.to_typed([[1, 2], [3]], "set[tuple[int,...]]") == {(1, 2), (3,)}


def test_fixture_tasks_load_with_their_hashes(fixture_dir):
    probs = tasks.load_problems(fixture_dir / "tasks" / "fixture_tasks.jsonl")
    assert len(probs) == 3
    assert probs["fixture/sorted_lines"]["stdin_stdout"] is True
    assert probs["fixture/has_close_pair"]["kind"] == "humaneval"
    for record in tasks.read_records(fixture_dir / "tasks" / "fixture_tasks.jsonl"):
        assert tasks.content_hash(record) == record["content_sha256"]

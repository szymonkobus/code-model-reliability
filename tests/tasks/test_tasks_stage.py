"""The tasks stage on the fixture data package: the hash recipes reproduce the shipped hashes, the loaders give the
judge's shape, verify passes on the fixture and fails on a tampered copy, a pointer task rebuilds from its cached
upstream row, and the attribution table counts every row."""

from __future__ import annotations

import gzip
import json
import pathlib
import shutil

import pytest

from code_model_reliability import tasks
from code_model_reliability.tasks import attribution, rebuild_restricted, verify
from code_model_reliability.tasks.content import CONTENT_FIELDS, content_sha256, list_sha256
from code_model_reliability.tasks.records import Pointer, Task, iter_pointers, iter_tasks, read_manifest
from code_model_reliability.tasks.sets import check_sets, load_sets

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "tasks"


def test_content_hash_recipe_reproduces_every_shipped_hash():
    n = 0
    for key in ("wave_2", "wave_2_parked"):
        for task in iter_tasks(FIXTURE, key):
            assert content_sha256(task.record) == task.content_sha256, task.task_id
            n += 1
    assert n == 3


def test_list_hash_recipe_reproduces_the_set_identities():
    sets = load_sets(FIXTURE)
    for key, ts in sets.by_key.items():
        assert list_sha256(ts.members) == ts.sha256_sorted_members, key
        assert list_sha256(ts.kept) == ts.sha256_sorted_kept, key
    assert check_sets(sets) == []
    assert len(sets.wave_1_plus_2_kept()) == sets.wave_1_plus_2["kept_count"] == 5


def test_tasks_come_in_the_judges_shape_and_pointers_apart():
    texts = list(iter_tasks(FIXTURE, "wave_2"))
    pointers = list(iter_pointers(FIXTURE, "wave_2"))
    assert [t.task_id for t in texts] == ["fx/add_two", "fx/count_vowels"]
    assert [p.task_id for p in pointers] == ["fxp/is_even"]
    judged = texts[0].judged()
    assert tuple(judged) == CONTENT_FIELDS
    assert judged["entry_point"] == "add_two" and judged["base_input"][0] == [1, 2]
    assert all(t.kept_by_audit for t in texts) and pointers[0].reason == "upstream-terms"
    assert [t.io_mode for t in texts] == ["function", "function"] and pointers[0].record["io_mode"] == "function"
    assert texts[0].input_shapes is None and texts[1].input_shapes == ["str"]
    assert texts[0].plus_inputs_removed == []
    parked = next(iter(iter_tasks(FIXTURE, "wave_2_parked")))
    assert parked.plus_inputs_removed == [[5, 10, 0]]
    assert Task({"prompt": "def solve(input_data: str) -> str:\n", "task_id": "x/1", "content_sha256": ""}).io_mode == "stdio"
    assert [t.task_id for t in iter_tasks(FIXTURE, "wave_2_parked", kept_only=True)] == []
    assert isinstance(tasks.find_task(FIXTURE, "wave_2", "fxp/is_even"), Pointer)
    assert isinstance(tasks.find_task(FIXTURE, "wave_2", "fx/clip"), type(None))
    assert isinstance(tasks.find_task(FIXTURE, "wave_2_parked", "fx/clip"), Task)


def test_verify_passes_on_the_fixture():
    problems, counts = verify.verify(FIXTURE)
    assert problems == []
    assert counts["wave_2"] == {"text": 2, "pointers": 1}
    assert counts["members"] == {"wave_1": 2, "wave_2": 3, "wave_2_parked": 1}
    assert verify.main(["--data", str(FIXTURE)]) == 0


def _rewrite_part(folder: pathlib.Path, change) -> None:
    part = folder / "tasks-part-01.jsonl"
    rows = [json.loads(l) for l in part.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [change(r) for r in rows]
    part.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def test_a_compressed_part_reads_the_same(tmp_path):
    copy = tmp_path / "tasks"
    shutil.copytree(FIXTURE, copy)
    folder = copy / "wave-2"
    plain = folder / "tasks-part-01.jsonl"
    with gzip.open(folder / "tasks-part-01.jsonl.gz", "wb") as gz:
        gz.write(plain.read_bytes())
    plain.unlink()
    m = read_manifest(copy, "wave_2")
    m["parts"][0]["file"] = "tasks-part-01.jsonl.gz"
    m["parts"][0]["bytes"] = (folder / "tasks-part-01.jsonl.gz").stat().st_size
    m["parts"][0]["sha256"] = __import__("hashlib").sha256((folder / "tasks-part-01.jsonl.gz").read_bytes()).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert [t.task_id for t in iter_tasks(copy, "wave_2")] == ["fx/add_two", "fx/count_vowels"]
    problems, _ = verify.verify(copy)
    assert problems == []


def test_verify_fails_on_a_tampered_copy(tmp_path):
    copy = tmp_path / "tasks"
    shutil.copytree(FIXTURE, copy)

    def change(r):
        if r["task_id"] == "fx/add_two":
            r["prompt"] = r["prompt"].replace("sum", "difference")
        return r

    _rewrite_part(copy / "wave-2", change)
    problems, _ = verify.verify(copy)
    assert any("content hash does not match" in p for p in problems)
    assert any("does not match its manifest sha256" in p for p in problems)
    assert verify.main(["--data", str(copy)]) == 1


def test_verify_sees_a_member_without_a_row_or_a_record(tmp_path):
    copy = tmp_path / "tasks"
    shutil.copytree(FIXTURE, copy)
    rows = [json.loads(l) for l in (copy / "attribution.jsonl").read_text().splitlines() if l.strip()]
    (copy / "attribution.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows if r["task_id"] != "fx/clip"))
    (copy / "wave-2" / "restricted.jsonl").write_text("")
    problems, _ = verify.verify(copy, quick=True)
    assert any("members of wave_2_parked have no row" in p for p in problems)
    assert any("wave_2: 1 members have neither a record nor a pointer" in p for p in problems)


def test_pointer_task_rebuilds_from_its_cached_upstream_row(tmp_path):
    # the cached upstream conversion is the first emission; the pointer's recipe removes the input the re-issue dropped
    stats, kept = rebuild_restricted.verify(FIXTURE, FIXTURE / "upstream" / "converted.jsonl", tmp_path / "rebuilt.jsonl")
    assert stats["match after the re-issue's removals"] == 1 and stats["hash mismatch"] == 0 and stats["pointers still missing"] == 0
    assert kept[0]["task_id"] == "fxp/is_even" and [42] not in kept[0]["plus_input"]
    assert content_sha256(kept[0]) == next(iter_pointers(FIXTURE, "wave_2")).content_sha256
    assert (tmp_path / "rebuilt.jsonl").read_text().count("\n") == 1
    # a record already in its certified form matches directly
    direct = tmp_path / "direct.jsonl"
    direct.write_text(json.dumps(kept[0]) + "\n")
    stats, _ = rebuild_restricted.verify(FIXTURE, direct, None)
    assert stats["match"] == 1
    plan_text = rebuild_restricted.plan(FIXTURE, tmp_path / "slugs")
    assert "1 pointer tasks to rebuild" in plan_text and (tmp_path / "slugs" / "slugs-leetcode.txt").read_text().strip() == "is_even"
    wrong = tmp_path / "wrong.jsonl"
    row = json.loads((FIXTURE / "upstream" / "converted.jsonl").read_text())
    row["canonical_solution"] = "    return n % 2 == 1\n"
    wrong.write_text(json.dumps(row) + "\n")
    stats, kept = rebuild_restricted.verify(FIXTURE, wrong, None)
    assert stats["hash mismatch"] == 1 and kept == []
    assert rebuild_restricted.main(["--data", str(FIXTURE), "--verify", str(wrong)]) == 1
    assert rebuild_restricted.main(["--data", str(FIXTURE), "--plan"]) == 0


def test_attribution_table_counts_every_row_by_source():
    rows = attribution.load_attribution(FIXTURE)
    sources = attribution.load_sources(FIXTURE)
    table = attribution.attribution_table(rows, sources)
    lines = [l for l in table.splitlines() if l.startswith("| fixture")]
    assert len(lines) == 2
    fx = next(l for l in lines if l.startswith("| fixture tasks"))
    assert fx.rstrip("|").rstrip().endswith("| 2 | 2 | 1")   # wave 1, wave 2, wave 2 parked
    fxp = next(l for l in lines if l.startswith("| fixture upstream"))
    assert fxp.rstrip("|").rstrip().endswith("| 0 | 1 | 0")
    assert "| **all** | | | | **2** | **3** | **1** |" in table
    counts = attribution.counts_by_source(rows, sources)
    assert sum(counts[None].values()) == 0


def test_command_line_summary_show_and_table(capsys):
    assert tasks.main(["--data", str(FIXTURE), "summary"]) == 0
    out = capsys.readouterr().out
    assert "wave 2: 3 members, 3 kept; 2 with text, 1 pointers" in out
    assert "wave 1+2: 5 kept tasks" in out
    assert tasks.main(["--data", str(FIXTURE), "show", "fxp/is_even"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["kind"] == "pointer" and shown["attribution"]["source_set"] == "fixture/upstream"
    assert tasks.main(["--data", str(FIXTURE), "show", "fx/count_vowels"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["kind"] == "text" and shown["record"]["entry_point"] == "count_vowels"
    assert tasks.main(["--data", str(FIXTURE), "list", "--set", "wave_2_parked"]) == 0
    assert capsys.readouterr().out.split() == ["fx/clip"]
    assert tasks.main(["--data", str(FIXTURE), "attribution-table"]) == 0
    assert "| fixture tasks |" in capsys.readouterr().out
    assert tasks.main(["--data", str(FIXTURE), "verify", "--quick"]) == 0


def test_manifest_names_the_parts_and_the_recipe():
    m = read_manifest(FIXTURE, "wave_2")
    assert m["full_text_tasks"] == 2 and m["pointer_tasks"] == 1
    assert m["hash_recipe"].startswith("sha256(json.dumps({task_id, prompt, entry_point")
    assert m["parts"][0]["file"] == "tasks-part-01.jsonl"


def test_data_dir_resolution_prefers_the_explicit_path(monkeypatch, tmp_path):
    assert tasks.tasks_dir(FIXTURE) == FIXTURE
    assert tasks.tasks_dir(FIXTURE.parent / "tasks") == FIXTURE
    monkeypatch.setenv("CMR_DATA_DIR", str(FIXTURE))
    assert tasks.tasks_dir(None) == FIXTURE
    assert tasks.tasks_dir(tmp_path / "nowhere") == FIXTURE   # an explicit path without data falls through to the variable
    monkeypatch.delenv("CMR_DATA_DIR")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tasks.data, "_tasks_folder", lambda c: None)
    with pytest.raises(FileNotFoundError):
        tasks.tasks_dir(tmp_path / "nowhere")

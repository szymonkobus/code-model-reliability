"""The stage end to end on the fixture set with the stand-in model: every form, every file, the counts and the order."""

import json
import os
import pathlib

from code_model_reliability.generate import command, records as R
from code_model_reliability.generate.taskset import load_tasks

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "generate"
TASKS = str(FIXTURES / "tasks.jsonl")


def _run(tmp_path, protocol, attempts=6, extra=()):
    out = str(tmp_path / protocol)
    rc = command.main(["run", "--model", "fixture-model", "--tasks", TASKS, "--protocol", protocol, "--attempts", str(attempts),
                       "--backend", "standin", "--out", out, "--seed", "7", *extra])
    assert rc == 0
    return out


def _check_files(out, attempts):
    tasks = load_tasks(TASKS)
    samples = list(R.read_rows(os.path.join(out, R.SAMPLES)))
    raw = list(R.read_rows(os.path.join(out, R.RAW)))
    assert len(samples) == len(raw) == len(tasks) * attempts
    order = [(r["task_id"], r["attempt"]) for r in raw]
    assert order == [(t, i) for t in tasks for i in range(attempts)]
    assert [s["task_id"] for s in samples] == [t for t, _ in order]
    rec = R.GenerationRecord.read(out)
    assert rec.n_tasks == len(tasks) and rec.attempts_per_task == attempts and rec.finished
    assert rec.extractor["stamp"] == "v2@9ac5071166f8adaa" and rec.seed == 7
    return tasks, samples, raw, rec


def test_plain_chat_form(tmp_path):
    out = _run(tmp_path, "plain-chat")
    tasks, samples, raw, rec = _check_files(out, 6)
    assert rec.form == "plain" and rec.prompt_style == "chat" and rec.sampling["geometry"] == "flat"
    assert "\n```\n" in rec.stops
    # some attempts are wrong by the stand-in's seeded rule, so cells carry failures
    wrong = [s for s in samples if "return None" in s["solution"]]
    right = [s for s in samples if "return None" not in s["solution"]]
    assert wrong and right
    for s in right:
        assert s["solution"].startswith("def ")


def test_resume_continues_from_the_attempts_on_disk(tmp_path):
    out = _run(tmp_path, "plain-chat", attempts=3)
    first = list(R.read_rows(os.path.join(out, R.RAW)))
    out2 = _run(tmp_path, "plain-chat", attempts=5)
    assert out2 == out
    second = list(R.read_rows(os.path.join(out, R.RAW)))
    assert len(second) == 15 and second[:3] == first[:3]


def test_two_phase_thinking_form(tmp_path):
    out = _run(tmp_path, "two-phase-thinking", attempts=4)
    _, samples, raw, rec = _check_files(out, 4)
    assert rec.form == "thinking" and rec.thinking_budget == 32768 and rec.answer_budget == 4096
    assert all(r["closure"] == "natural" and r["think_text"].endswith("</think>") for r in raw)
    assert rec.notes["template_class"] == "thinking-only"


def test_completion_form(tmp_path):
    out = _run(tmp_path, "completion", attempts=4)
    tasks, samples, raw, rec = _check_files(out, 4)
    assert rec.form == "completion" and rec.stops == ["\nif __name__", "\nprint(", "\nassert ", "\n\n\n\n"]
    for s in samples:
        prompt = tasks[s["task_id"]]["prompt"].rstrip("\n") + "\n"
        assert s["solution"].startswith(prompt)  # the program is prompt plus completion, whole


def test_greedy_check_draws_one_attempt(tmp_path):
    out = _run(tmp_path, "plain-chat", attempts=9, extra=["--greedy"])
    _check_files(out, 1)
    rec = R.GenerationRecord.read(out)
    assert rec.sampling["temperature"] == 0.0 and rec.sampling["top_p"] == 1.0


def test_generation_json_names_every_setting(tmp_path):
    out = _run(tmp_path, "plain-chat", attempts=2)
    with open(os.path.join(out, R.GENERATION), encoding="utf-8") as fh:
        rec = json.load(fh)
    for key in ("arm", "task_set", "task_set_sha256", "model_id", "form", "protocol", "protocol_version", "backend", "prompt_style", "sampling",
                "output_limit", "stops", "harness_commit", "instruction", "extractor", "pins", "seed", "started", "finished"):
        assert key in rec, key
    assert rec["arm"] == "fixture-model_temp_0.8"
    assert rec["protocol"] == "plain-chat" and rec["protocol_version"] == ""
    assert rec["harness_commit"] == "26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"

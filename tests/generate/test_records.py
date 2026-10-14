"""The output files: paired, resumable, counted."""

import json
import os

import pytest

from code_model_reliability.generate import records as R


def test_writer_pairs_and_resumes(tmp_path):
    out = str(tmp_path)
    with R.AttemptWriter(out) as w:
        w.write("T/1", 0, "def f(): pass", "```python\ndef f(): pass\n```", "stop", tokens=5)
        w.write("T/1", 1, "def f(): pass", "...", "max_tokens")
    rows = list(R.read_rows(os.path.join(out, R.RAW)))
    assert [r["attempt"] for r in rows] == [0, 1]
    assert rows[1]["finish_reason"] == "length"
    assert rows[0]["tokens"] == 5 and "tokens" not in rows[1]
    samples = list(R.read_rows(os.path.join(out, R.SAMPLES)))
    assert samples == [{"task_id": "T/1", "solution": "def f(): pass"}] * 2
    # a kill after the samples line and before the raw line leaves one extra samples line
    with open(os.path.join(out, R.SAMPLES), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"task_id": "T/1", "solution": "orphan"}) + "\n")
    # and a torn raw line
    with open(os.path.join(out, R.RAW), "a", encoding="utf-8") as fh:
        fh.write('{"task_id": "T/1", "attempt": 2, "te')
    w = R.AttemptWriter(out)
    assert w.repaired["torn_raw"] is True and w.repaired["cut_to"] == 2
    assert w.done["T/1"] == 2
    w.close()
    assert len(list(R.read_rows(os.path.join(out, R.SAMPLES)))) == 2


def test_check_counts(tmp_path):
    out = str(tmp_path)
    tasks = {"T/1": {}, "T/2": {}}
    with R.AttemptWriter(out) as w:
        for t in tasks:
            for i in range(3):
                w.write(t, i, "x", "x", "stop")
    R.check_counts(out, tasks, 3)
    with pytest.raises(ValueError):
        R.check_counts(out, tasks, 4)
    with pytest.raises(ValueError):
        R.check_counts(out, {"T/1": {}}, 3)


def test_generation_record_round_trip(tmp_path):
    rec = R.GenerationRecord(
        arm="m_temp_0.8", task_set="fixture", task_set_sha256="0" * 64, n_tasks=3, attempts_per_task=4,
        model_id="m", model_revision=None, form="plain", protocol="plain-chat", protocol_version="", backend="standin",
        prompt_style="chat", sampling={"temperature": 0.8}, output_limit=4096, thinking_budget=None, answer_budget=None,
        max_model_len=4096, stops=["\n```\n"], harness_commit="abc", instruction="Please", extractor={"name": "v2"},
        pins={}, seed=1, started="2000-01-01",
    )
    rec.write(str(tmp_path))
    back = R.GenerationRecord.read(str(tmp_path))
    assert back == rec
    assert R.normalise_finish_reason("MAX_TOKENS") == "length" and R.normalise_finish_reason(None) == "stop"

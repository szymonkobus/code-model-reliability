"""The API back ends build the published request shape for every provider, with no network."""

import json
import os
import pathlib

import pytest

from code_model_reliability.generate import settings as S
from code_model_reliability.generate.api import anthropic, batch, gemini, openai, openrouter
from code_model_reliability.generate.taskset import load_tasks

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "generate"
TASKS = str(FIXTURES / "tasks.jsonl")


def test_request_ids():
    assert batch.request_id("HumanEval/0", 0) == "HumanEval_0__s000"
    long_id = "leetcode/" + "x" * 80
    rid = batch.request_id(long_id, 127)
    assert len(rid) <= 64 and rid.endswith("__s127") and rid == batch.request_id(long_id, 127)
    assert batch.request_id(long_id, 127) != batch.request_id(long_id + "y", 127)


@pytest.mark.parametrize("provider_cls, card_name", [
    (anthropic.Anthropic, "claude-sonnet-5"),
    (anthropic.Anthropic, "claude-haiku-4-5-thinking"),
    (openai.OpenAI, "gpt-5-mini"),
    (openai.OpenAI, "gpt-6-astra"),
    (gemini.Gemini, "gemini-3.6-flash"),
    (gemini.Gemini, "gemini-4-argon"),
    (anthropic.Anthropic, "claude-fable-5-1-thinking"),
    (openrouter.OpenRouter, "muse-wonder"),
])
def test_build_writes_one_request_per_attempt(tmp_path, provider_cls, card_name):
    provider = provider_cls()
    card = provider.card(card_name)
    run = batch.BatchRun(provider, card, str(tmp_path))
    tasks = load_tasks(TASKS)
    n = run.build(tasks, 3, "fixture")
    assert n == 9
    rows = [json.loads(l) for l in open(tmp_path / "requests.jsonl", encoding="utf-8")]
    assert [batch._rid(r) for r in rows][:3] == ["Fixture_add__s000", "Fixture_add__s001", "Fixture_add__s002"]
    meta = json.load(open(tmp_path / "meta.json"))
    assert meta["arm"] == card.arm and meta["attempts_per_task"] == 3 and meta["task_ids"] == list(tasks)


def test_anthropic_request_shape():
    p = anthropic.Anthropic()
    card = p.card("claude-haiku-4-5")
    r = p.build_request("x__s000", card, "MESSAGE")
    assert r["params"]["model"] == "claude-haiku-4-5-20251001"
    assert r["params"]["messages"] == [{"role": "user", "content": "MESSAGE"}]
    assert r["params"]["max_tokens"] == 4096 and r["params"]["temperature"] == 0.8
    assert r["params"]["stop_sequences"] == S.EOS_STOPS and "system" not in r["params"]
    thinking = p.card("claude-sonnet-5-thinking").params
    assert thinking["max_tokens"] == 36864 and thinking["thinking"]["type"] == "adaptive" and "stop_sequences" not in thinking
    assert p.card("claude-sonnet-5-5").params["thinking"] == {"type": "between_tools"}
    assert anthropic._finish("max_tokens") == "length" and anthropic._finish("refusal") == "refusal"


def test_openai_request_shape():
    p = openai.OpenAI()
    r = p.build_request("x__s000", p.card("gpt-5-nano"), "MESSAGE")
    assert r["method"] == "POST" and r["url"] == "/v1/chat/completions"
    assert r["body"] == {"model": "gpt-5-nano-2025-08-07", "messages": [{"role": "user", "content": "MESSAGE"}], "max_completion_tokens": 36864}
    assert openai._finish("length", None) == "length" and openai._finish("stop", "no") == "refusal"
    astra = p.build_request("x__s000", p.card("gpt-6-astra"), "MESSAGE")
    assert astra["body"] == {"model": "gpt-6-astra", "messages": [{"role": "user", "content": "MESSAGE"}],
                             "max_completion_tokens": 36864, "reasoning_effort": "high"}
    assert p.card("gpt-6-astra").arm == "gpt-6-astra_batch" and p.card("gpt-6-astra").output_limit() == 36864


def test_openrouter_request_shape():
    p = openrouter.OpenRouter()
    card = p.card("muse-wonder")
    r = p.build_request("x__s000", card, "MESSAGE")
    assert r["method"] == "POST" and r["url"] == "/v1/chat/completions"
    assert r["body"] == {"model": "meta/muse-wonder", "messages": [{"role": "user", "content": "MESSAGE"}],
                         "max_tokens": 36864, "reasoning": {"effort": "high"}}
    wire = openrouter.wire_body(r)
    assert wire["provider"] == {"order": ["meta"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny"}
    assert wire["usage"] == {"include": True} and wire["stream"] is True and "temperature" not in wire
    assert card.arm == "muse-wonder-1.0_meta" and card.form == "thinking" and card.output_limit() == 36864
    assert openrouter._finish("length", None) == "length" and openrouter._finish("stop", "no") == "refusal"
    assert p.status("answers:/nonexistent/answers.jsonl") == "failed"


def test_gemini_request_shape():
    p = gemini.Gemini()
    r = p.build_request("x__s000", p.card("gemini-3.5-flash-lite"), "MESSAGE")
    assert r["key"] == "x__s000"
    assert r["request"]["contents"] == [{"role": "user", "parts": [{"text": "MESSAGE"}]}]
    assert r["request"]["generation_config"] == {"max_output_tokens": 16384, "temperature": 0.8}
    assert gemini._finish("MAX_TOKENS") == "length" and gemini._finish("SAFETY") == "refusal"
    argon = p.card("gemini-4-argon")
    assert argon.arm == "gemini-4-argon_batch" and argon.form == "thinking" and argon.output_limit() == 32768
    assert p.build_request("y__s000", argon, "M")["request"]["generation_config"] == {"max_output_tokens": 32768, "thinking_config": {"thinking_level": "high"}}


def test_fable_live_card():
    card = anthropic.Anthropic().card("claude-fable-5-1-thinking")
    assert card.arm == "claude-fable-5-1-thinking_live" and card.model == "claude-fable-5-1" and card.form == "thinking"
    assert card.output_limit() == 36864 and card.params["thinking"] == {"type": "adaptive", "display": "summarized"} and card.params["output_config"] == {"effort": "high"}
    assert "stop_sequences" not in card.params


def test_finalize_refuses_an_incomplete_ledger(tmp_path):
    provider = anthropic.Anthropic()
    run = batch.BatchRun(provider, provider.card("claude-opus-5"), str(tmp_path / "state"))
    tasks = load_tasks(TASKS)
    run.build(tasks, 2, "fixture")
    with pytest.raises(RuntimeError):
        run.finalize(tasks, str(tmp_path / "out"))
    # a complete ledger finalizes into the stage's files through the extractor
    with open(tmp_path / "state" / "results.jsonl", "w", encoding="utf-8") as fh:
        for t in tasks.values():
            for i in range(2):
                fh.write(json.dumps({"request_id": batch.request_id(t["task_id"], i), "text": f"```python\n{t['prompt']}{t['canonical_solution']}```",
                                     "finish_reason": "stop", "model": "claude-opus-5", "usage": {"output_tokens": 10}}) + "\n")
    summary = run.finalize(tasks, str(tmp_path / "out"))
    assert summary["missing"] == 0 and summary["written"] == 6
    samples = [json.loads(l) for l in open(tmp_path / "out" / "samples.jsonl", encoding="utf-8")]
    assert len(samples) == 6 and all(s["solution"].startswith("def ") for s in samples)
    assert os.path.exists(tmp_path / "out" / "generation.json")

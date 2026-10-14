"""The named protocols and the shipped table."""

import os

import pytest

from code_model_reliability.generate import protocols as PR
from code_model_reliability.generate import settings as S


def test_arm_ids_follow_the_contract():
    assert PR.arm_id("Qwen/Qwen2.5-7B-Instruct", "plain", 0.8) == "Qwen--Qwen2.5-7B-Instruct_temp_0.8"
    assert PR.arm_id("Qwen/Qwen3-8B", "thinking", 0.6) == "Qwen--Qwen3-8B_think_temp_0.6"
    assert PR.arm_id("org/base-model", "completion", 0.8) == "org--base-model_completion_temp_0.8"


def test_protocols_carry_the_published_settings():
    assert sorted(PR.PROTOCOLS) == ["completion", "deepseek-v32-chat", "deepseek-v32-thinking", "plain-chat",
                                    "plain-generation-prompt", "plain-runner", "single-phase-thinking", "two-phase-thinking"]
    for name, make in PR.PROTOCOLS.items():
        assert make("org/model").protocol == name, name  # the record's protocol is the name given to --protocol
    p = PR.plain_chat("Qwen/Qwen2.5-7B-Instruct")
    assert (p.temperature, p.top_p, p.output_limit, p.geometry) == (S.TEMPERATURE, S.TOP_P, S.ANSWER_LIMIT, "flat")
    assert p.stops == S.EOS_STOPS + [S.CHAT_FENCE_STOP]
    assert (p.protocol, p.protocol_version) == ("plain-chat", "")
    t = PR.two_phase_thinking("Qwen/Qwen3-8B")
    assert (t.temperature, t.top_k, t.min_p, t.thinking_budget, t.answer_budget) == (0.6, 20, 0.0, 32768, 4096)
    s = PR.single_phase_thinking("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", distilled=True)
    assert (s.thinking_budget, s.max_model_len, s.stops) == (30000, 32768, [])
    c = PR.completion("allenai/some-base")
    assert c.form == "completion" and c.stops == S.COMPLETION_STOPS
    assert (c.protocol, c.protocol_version) == ("completion", "completion-v1")
    v = PR.deepseek_v32("deepseek-ai/DeepSeek-V3.2", thinking=False)
    assert v.form == "plain" and v.prompt_style == "deepseek-v32-chat"
    assert (v.protocol, v.protocol_version) == ("deepseek-v32-chat", "")


def test_stop_encoding_round_trips():
    stops = S.EOS_STOPS + [S.CHAT_FENCE_STOP]
    cell = PR.encode_stops(stops)
    assert "\n" not in cell and "\t" not in cell
    assert PR.decode_stops(cell) == stops
    assert PR.decode_stops("") == []


FIXTURE_TABLE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "generate", "protocols.tsv")
"""Ten rows of the table the build writes (one published arm per prompt style and back end; the completion form has
no published arm); the shipped table itself
is regenerated from the registry at every build and is not in the source tree."""


def test_table_loads():
    table = PR.load_table(FIXTURE_TABLE)
    assert len(table) == 10
    for arm, p in table.items():
        assert p.arm == arm
        assert p.form in PR.FORMS and p.backend in PR.BACKENDS and p.prompt_style in PR.PROMPT_STYLES, arm
        assert p.temperature >= 0 and (p.output_limit or p.thinking_budget), arm
        assert p.protocol in PR.PROTOCOLS or p.protocol == "api-message", arm  # a name a run can be given under
        assert p.protocol_version == ("completion-v1" if p.form == "completion" else ""), arm
    plain = [p for p in table.values() if p.form == "plain" and p.prompt_style in ("chat", "generation-prompt", "completion")]
    assert plain and all(p.temperature == S.TEMPERATURE for p in plain)
    thinking = [p for p in table.values() if p.form == "thinking" and p.backend == "vllm"]
    assert thinking and all(p.temperature == 0.6 and p.thinking_budget for p in thinking)
    chat = table["Qwen--Qwen2.5-Coder-7B-Instruct_temp_0.8"]
    assert chat.stops == S.EOS_STOPS + [S.CHAT_FENCE_STOP] and chat.output_limit == S.ANSWER_LIMIT and chat.first_pass_limit == S.FIRST_PASS_LIMIT
    assert (chat.protocol, chat.protocol_version) == ("plain-chat", "")
    two_phase = table["Qwen--Qwen3-8B_think_temp_0.6"]
    assert (two_phase.thinking_budget, two_phase.answer_budget, two_phase.top_k) == (S.THINKING_BUDGET, S.TWO_PHASE_ANSWER_BUDGET_AS_RUN, 20)
    api = table["claude-sonnet-5_batch"]
    assert api.backend == "anthropic" and api.prompt_style == "api-message" and api.output_limit == S.API_ANSWER_LIMIT
    assert (api.protocol, api.protocol_version) == ("api-message", "")
    marker = table["google--gemma-4-12B-it_temp_0.8@768-marker"]
    assert marker.prompt_style == "generation-prompt" and marker.output_limit == S.ANSWER_LIMIT
    assert marker.protocol == "plain-generation-prompt"
    assert {p.backend for p in table.values()} == {"vllm", "anthropic", "openai", "gemini"}
    assert PR.default_table_path().endswith(os.path.join("data", "runs", "registry", "protocols.tsv"))

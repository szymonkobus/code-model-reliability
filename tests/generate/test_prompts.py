"""The prompt forms: the chat prompt is the harness's, byte for byte; the other forms are as documented."""

import pytest

from code_model_reliability.generate import prompts as P
from code_model_reliability.generate import settings as S
from code_model_reliability.generate.standin import StandInTokenizer

TASK = 'def add(a: int, b: int) -> int:\n    """Return the sum of a and b.\n    >>> add(1, 2)\n    3\n    """\n'


class TemplateTokenizer:
    """A tokenizer whose chat template renders turns as tagged blocks, enough to exercise the rendering."""

    chat_template = "tagged"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False, **kwargs):
        text = "<s>" + "".join(f"[{m['role']}]{m['content']}[/{m['role']}]" for m in messages)
        if add_generation_prompt:
            text += "[assistant]"
        return text


class NoTemplateTokenizer:
    chat_template = None


def test_chat_prompt_matches_the_harness():
    """Needs the judge harness at its pinned commit (the package's ``judge`` extra); the tests are run with it."""
    import evalplus.provider.utility as harness

    tok = TemplateTokenizer()
    prompt = P.harness_task_prompt(TASK)
    assert P.chat_prompt(prompt, tok) == harness.make_raw_chat_prompt(prompt, S.INSTRUCTION_PREFIX, S.RESPONSE_PREFIX, tok)
    assert P.chat_prompt(prompt, NoTemplateTokenizer()) == harness.make_raw_chat_prompt(prompt, S.INSTRUCTION_PREFIX, S.RESPONSE_PREFIX, NoTemplateTokenizer())
    assert S.EOS_STOPS == harness.EOS
    assert S.MAGIC_SPLITTER == harness._MAGIC_SPLITTER_


def test_chat_prompt_shape():
    text = P.chat_prompt(P.harness_task_prompt(TASK), TemplateTokenizer())
    expected_user = f"[user]{S.INSTRUCTION_PREFIX}\n```\n{TASK.strip()}\n```\n[/user]"
    assert text == f"<s>{expected_user}[assistant]{S.RESPONSE_PREFIX}\n```python\n"
    assert P.MAGIC_SPLITTER not in text


def test_without_a_chat_template_the_bare_prompt_is_sent():
    assert P.chat_prompt(P.harness_task_prompt(TASK), NoTemplateTokenizer()) == TASK.strip() + "\n"


def test_generation_prompt_equals_chat_prompt_for_a_template_without_turn_tokens():
    tok = TemplateTokenizer()
    assert P.generation_prompt(TASK, tok) == P.chat_prompt(P.harness_task_prompt(TASK), tok)


def test_api_message_shape():
    msg = P.api_user_message(TASK)
    assert msg == S.INSTRUCTION_PREFIX + "\n```python\n" + TASK.strip() + "\n```\n"


def test_completion_prompt_has_exactly_one_trailing_newline():
    assert P.completion_prompt(TASK + "\n\n") == TASK.rstrip("\n") + "\n"
    assert P.completion_prompt(TASK.rstrip("\n")) == TASK.rstrip("\n") + "\n"


def test_two_phase_closures():
    tok = StandInTokenizer()
    base = P.two_phase_base_prompt(TASK, tok)
    assert base.endswith("<think>\n")
    trace = "some thinking\n</think>"
    natural, c1 = P.answer_phase_prompt(base, trace)
    assert c1 == "natural" and natural.endswith(f"\n\n{S.RESPONSE_PREFIX}\n```python\n")
    assert natural[len(base) + len(trace):].startswith("\n\n")  # nothing appended between the trace and the opening
    forced, c2 = P.answer_phase_prompt(base, "thinking that ran out")
    assert c2 == "forced" and forced[len(base):].startswith("thinking that ran out" + S.FORCED_CLOSE)
    no_trace, c3 = P.answer_phase_prompt("[assistant]", "an answer without a trace")
    assert c3 == "no_think"
    assert P.template_class(tok) == "thinking-only"


def test_single_phase_split():
    assert P.split_single_phase("thoughts</think>\ncode", "stop") == ("thoughts", "\ncode", "natural")
    assert P.split_single_phase("thoughts and more", "length") == ("thoughts and more", "", "overlong")
    assert P.split_single_phase("thoughts and more", "stop") == ("thoughts and more", "", "no_marker")


def test_deepseek_v32_prompt():
    assert P.deepseek_v32_prompt(TASK, thinking=True).endswith("<｜Assistant｜><think>")
    assert P.deepseek_v32_prompt(TASK, thinking=False).endswith("<｜Assistant｜></think>")

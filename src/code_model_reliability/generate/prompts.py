"""The prompt a model sees, in each of the forms that were run.

Every form puts the task's prompt (the function signature and its docstring) after one instruction sentence; the
forms differ in how the model's own turn is opened. The chat form is the harness's own instruct prompt at the
pinned commit, reproduced here function for function so a test can hold it byte-equal to the harness. The
thinking forms and the completion form were written for this project because the harness cannot express them: it
always pre-fills the assistant turn, which switches a thinking model's reasoning off, and it always wraps the task
in a chat turn, which a base model has no template for.

Reads: a task's prompt; a tokenizer carrying the model's chat template, where a form renders one. Writes nothing.
"""

from __future__ import annotations

from .settings import (
    INSTRUCTION_PREFIX,
    MAGIC_SPLITTER,
    RESPONSE_PREFIX,
    THINK_CLOSE,
    FORCED_CLOSE,
)

THINK_OPEN = "<think>"
"""The tag that opens a thinking trace in the templates that write one."""

DEEPSEEK_V32_USER = "<｜User｜>"
DEEPSEEK_V32_ASSISTANT = "<｜Assistant｜>"
"""The turn markers of the DeepSeek V3.2 encoding, which has no chat template; the inference engine adds the start token."""


def harness_task_prompt(task_prompt: str) -> str:
    """The task text as the harness hands it to a model: stripped, with one trailing newline."""
    return task_prompt.strip() + "\n"


def user_turn(task_prompt: str) -> str:
    """The user turn of every chat and thinking form: the instruction, then the task in a bare code fence."""
    return f"{INSTRUCTION_PREFIX}\n```\n{task_prompt.strip()}\n```\n"


def assistant_opening() -> str:
    """How the chat forms open the model's turn: the response sentence and an open Python fence."""
    return f"{RESPONSE_PREFIX}\n```python\n"


def chat_prompt(task_prompt: str, tokenizer) -> str:
    """The harness's chat prompt: a user turn and a complete assistant message that holds the response sentence, an
    open Python fence and a marker, rendered through the model's chat template and cut at the marker. The cut keeps
    the template's own turn tokens and leaves the fence open, so the model continues with code. A tokenizer without a
    chat template gets the bare task prompt (the harness's direct-completion case)."""
    if tokenizer.chat_template is None:
        return task_prompt
    task_turn = f"""\
{INSTRUCTION_PREFIX}
```
{task_prompt.strip()}
```
"""
    response = f"""\
{RESPONSE_PREFIX}
```python
{MAGIC_SPLITTER}
```
"""
    rendered = tokenizer.apply_chat_template(
        [
            {"role": "user", "content": task_turn},
            {"role": "assistant", "content": response},
        ],
        tokenize=False,
    )
    return rendered.split(MAGIC_SPLITTER)[0]


def generation_prompt(task_prompt: str, tokenizer) -> str:
    """The chat prompt opened with the template's generation prompt instead of a cut assistant message: the same
    user turn, the template's own marker for the start of the model's turn with thinking off, then the response
    sentence and the open fence. Byte-equal to ``chat_prompt`` for templates with no generation-time tokens; needed
    for templates that mark the model's turn (a thinking-off marker the cut message would lose)."""
    try:
        head = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_turn(task_prompt)}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        head = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_turn(task_prompt)}], tokenize=False, add_generation_prompt=True
        )
    return head + assistant_opening()


def two_phase_base_prompt(task_prompt: str, tokenizer) -> str:
    """Phase one of the two-phase thinking form: the user turn, the template's generation prompt with thinking on,
    and no assistant text, so the model opens its own trace."""
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": user_turn(task_prompt)}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )


def answer_phase_prompt(base_prompt: str, trace: str) -> tuple[str, str]:
    """Phase two of the two-phase form: the base prompt, the trace as generated, a forced close where the trace
    reached its budget without closing, then the response sentence and the open fence. Returns the prompt and how
    the thinking closed: ``natural`` (the trace ends with the closing tag), ``forced`` (a tag is still open in the
    prompt and trace together, so the close is appended) or ``no_think`` (the template opened no trace)."""
    if trace.endswith(THINK_CLOSE):
        closure, mid = "natural", ""
    elif (base_prompt + trace).rfind(THINK_OPEN) > (base_prompt + trace).rfind(THINK_CLOSE):
        closure, mid = "forced", FORCED_CLOSE
    else:
        closure, mid = "no_think", ""
    return base_prompt + trace + mid + f"\n\n{RESPONSE_PREFIX}\n```python\n", closure


def template_class(tokenizer) -> str:
    """Whether a template opens the thinking tag inside the generation prompt (``thinking-only``) or leaves it to
    the model (``hybrid``). Both run under the two-phase form; a thinking-only template never yields ``no_think``."""
    probe = two_phase_base_prompt("def f():\n    pass\n", tokenizer)
    return "thinking-only" if probe.rfind(THINK_OPEN) > probe.rfind(THINK_CLOSE) else "hybrid"


def single_phase_prompt(task_prompt: str, tokenizer) -> str:
    """The single-phase thinking form: the user turn and the template's generation prompt, nothing pre-filled; the
    model writes its trace, closes it and answers in one generation."""
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": user_turn(task_prompt)}], tokenize=False, add_generation_prompt=True
    )


def deepseek_v32_prompt(task_prompt: str, thinking: bool) -> str:
    """The DeepSeek V3.2 encoding, which ships no chat template: the user turn between its turn markers, then the
    open thinking tag (thinking form) or the closed one (chat form)."""
    mode = THINK_OPEN if thinking else THINK_CLOSE
    return f"{DEEPSEEK_V32_USER}{user_turn(task_prompt)}{DEEPSEEK_V32_ASSISTANT}{mode}"


def completion_prompt(task_prompt: str) -> str:
    """The completion form for base models: the task prompt bare, with exactly one trailing newline, no instruction
    and no fence; the model continues the function body."""
    return task_prompt.rstrip("\n") + "\n"


def api_user_message(task_prompt: str) -> str:
    """The API forms' one user message (the harness's own API provider shape): the instruction, then the task in a
    ```python fence. No system prompt and no pre-filled assistant turn: the providers' current models refuse a
    pre-fill, so every API arm shares this one shape."""
    return INSTRUCTION_PREFIX + f"\n```python\n{harness_task_prompt(task_prompt).strip()}\n```\n"


def split_single_phase(text: str, finish_reason: str) -> tuple[str, str, str]:
    """A single-phase output split into trace, answer and closure: ``natural`` when the closing tag is present
    (the answer follows it), ``overlong`` when the budget ran out before it, ``no_marker`` when the model stopped
    without ever closing."""
    if THINK_CLOSE in text:
        trace, answer = text.split(THINK_CLOSE, 1)
        return trace, answer, "natural"
    return text, "", ("overlong" if finish_reason == "length" else "no_marker")


def forced_close_prompt(base_prompt: str, trace: str) -> str:
    """The answer phase for a stored single-phase trace that reached its budget: the trace is kept whole and closed
    in the form the model writes after a natural close, and the model answers from there."""
    return base_prompt + trace + FORCED_CLOSE + "\n"

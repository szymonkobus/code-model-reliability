"""Every setting the generation stage ran under, as named constants with the values the published attempts were
produced under.

A setting here is one that can move a verdict: the prompt a model sees, how its output is cut, how it is sampled,
and how many answers it gives. The values are the ones the published attempts were produced with. Each constant
carries one sentence saying why it has that value. The judge's own settings live in ``judge/settings.py``.
"""

from __future__ import annotations

# --- the harness -----------------------------------------------------------------------------------------------

HARNESS_COMMIT = "26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"
"""The judge harness (EvalPlus) commit every prompt, extractor baseline and verdict refers to; a later commit
changes the prompt text or the sanitizer and would make the attempts incomparable."""

HARNESS_DATASETS = {"humaneval": "HumanEvalPlus-v0.1.10", "mbpp": "MbppPlus-v0.2.0"}
"""The two task files the harness fetches for wave 1 (the harness's own names); wave 2 is read from this
repository's task files in the same shape through the harness's override path."""

# --- the prompt -------------------------------------------------------------------------------------------------

INSTRUCTION_PREFIX = (
    "Please provide a self-contained Python script that solves the following problem in a markdown code block:"
)
"""The harness's instruct prompt at the pinned commit, word for word; every model sees the same instruction so that
a difference between arms is the model's and not the prompt's."""

RESPONSE_PREFIX = (
    "Below is a Python script with a self-contained function that solves the problem and passes corresponding tests:"
)
"""The harness's assistant-turn prefix, word for word: the chat forms start the model's turn with this sentence and
an open ```python fence, so the model answers with code first."""

MAGIC_SPLITTER = "-[[]]-this-is-really-our-highest-priority-[[]]-"
"""The harness's marker: the assistant turn is rendered as a complete message containing this token and cut at it,
which leaves the template's own turn markers in place and the fence open."""

# --- how an answer is cut -----------------------------------------------------------------------------------------

EOS_STOPS = ["<|endoftext|>", "<|endofmask|>", "</s>", "\nif __name__", "\ndef main(", "\nprint("]
"""The harness's stop strings for every chat-form answer: end-of-text markers and the first line of a demonstration,
so an answer ends where its program ends."""

CHAT_FENCE_STOP = "\n```\n"
"""The harness's extra stop for chat-form answers: the closing code fence on its own line."""

DIRECT_COMPLETION_STOPS = {
    "humaneval": ["\ndef ", "\nclass ", "\nimport ", "\nfrom ", "\nassert "],
    "mbpp": ['\n"""', "\nassert"],
}
"""The harness's extra stops when a model has no chat template and completes the bare prompt: the start of the
next top-level definition or test, per task file."""

COMPLETION_STOPS = ["\nif __name__", "\nprint(", "\nassert ", "\n\n\n\n"]
"""The completion form's stops (a base model continuing the bare prompt): a demonstration's first line or four
blank lines; no definition stops, because a module-level completion may itself begin with a definition or an import."""

ANSWER_LIMIT = 4096
"""The output limit for a plain or completion answer, in new tokens: an answer still unfinished here is counted as
cut by the limit."""

FIRST_PASS_LIMIT = 768
"""The harness's default output limit, under which the wave 1 attempts were first drawn; an attempt the first pass
cut was continued to ANSWER_LIMIT, the two parts one attempt (see ``vllm.continue_cut_attempts``)."""

CONTINUATION_LIMIT = ANSWER_LIMIT - FIRST_PASS_LIMIT
"""The new tokens a continuation may add: the difference between the limit and the first pass."""

# --- sampling -----------------------------------------------------------------------------------------------------

TEMPERATURE = 0.8
"""The sampling temperature of the plain and completion forms: the repeated-sampling convention for these tasks."""

TOP_P = 0.95
"""Nucleus sampling for every sampled answer; 1.0 when decoding greedily (the harness's rule)."""

ATTEMPTS_PER_TASK = 128
"""Attempts per task on wave 1; the open-weight arms drew 32 per task on wave 2 and the fit uses every attempt."""

GREEDY_TEMPERATURE = 0.0
"""A single greedy attempt per task is drawn beside the sampled attempts as a check on the generation path, never
as a row of the fit."""

# --- the inference back end ---------------------------------------------------------------------------------------------

DTYPE = "bfloat16"
"""The weights' precision in the inference engine (the harness's default); a model shipped in another precision keeps its own."""

MAX_MODEL_LEN_STOCK = 2048
"""The context window the harness's own generation path sets; wave 1 prompts fit under it with the first pass."""

MAX_MODEL_LEN_WAVE2 = 4096
"""The context window used for wave 2 plain-form generation: the new tasks' prompts run longer than wave 1's; it
grows by the output limit when the limit exceeds the harness's default."""

CHUNKED_PREFILL = True
"""Chunked prefill is enabled; the harness's default of off is an unsupported mode in the pinned inference engine."""

VLLM_PIN = "vllm==0.26.0"
"""The inference engine pin: the kernels, batching and numerics every open-weight attempt was produced with."""

TRANSFORMERS_PIN = "transformers==5.15.0"
"""The tokenizer and chat-template library pin: a template renders byte-identically only under one version."""

TRUST_REMOTE_CODE_FAMILIES = ("deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "moonshotai/")
"""Model id prefixes whose loading needs the repository's own code (custom tokenizers or configs)."""

# --- the thinking forms -------------------------------------------------------------------------------------------

THINKING_CARD = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0}
"""The two-phase thinking form's sampling, the makers' recommended settings for reasoning; greedy decoding is not
used for thinking models."""

THINKING_BUDGET = 32768
"""The two-phase form's thinking budget in tokens; the thinking is closed when it reaches it."""

TWO_PHASE_ANSWER_BUDGET_AS_RUN = 2048
"""The answer budget under which the two-phase arms in the published fit were generated."""

TWO_PHASE_ANSWER_BUDGET = ANSWER_LIMIT
"""The answer budget for every thinking form: the same limit as a plain answer; an answer cut at the budget as run
is continued to it."""

MAX_MODEL_LEN_TWO_PHASE = 40960
"""The context window for the two-phase form: the position limit of the models it was written for."""

THINK_CLOSE = "</think>"
"""The tag that ends a thinking trace; phase one stops at it (kept in the text) and phase two resumes after it."""

FORCED_CLOSE = "\n" + THINK_CLOSE
"""Appended to a trace that reached the thinking budget without closing itself, so the answer phase can begin."""

SINGLE_PHASE_CARD = {"temperature": 0.6, "top_p": 0.95}
"""The single-phase thinking form's sampling (models that emit the trace and the answer in one generation)."""

SINGLE_PHASE_BUDGET = 65536
"""The single-phase budget for thinking and answer together, for the largest reasoning models."""

SINGLE_PHASE_BUDGET_DISTILLED = 30000
"""The single-phase budget for the distilled reasoning models, whose context is 32,768 tokens."""

MAX_MODEL_LEN_SINGLE_PHASE = 70000
"""The context window for the single-phase form at SINGLE_PHASE_BUDGET."""

MAX_MODEL_LEN_SINGLE_PHASE_DISTILLED = 32768
"""The context window for the single-phase form at SINGLE_PHASE_BUDGET_DISTILLED."""

ANSWER_PHASE_WINDOW = 40960
"""The context window for an answer phase generated after a stored single-phase trace was forced closed."""

# --- the API forms --------------------------------------------------------------------------------------------------

API_INSTRUCTION_FENCE = "python"
"""The API forms put the task in a ```python fence (the harness's own API provider shape); the open-weight forms put it
in a bare fence and open ```python in the assistant turn, which the API forms cannot do."""

API_ANSWER_LIMIT = 4096
"""The plain API arms' output limit, the same as the open-weight arms' limit."""

API_THINKING_LIMIT = 36864
"""The thinking API arms' output limit: a 32,768-token thinking budget plus a 4,096-token answer."""

API_THINKING_BUDGET = 32768
"""The thinking budget where a provider takes one explicitly."""

API_BATCH_LIMIT = 100_000
"""The most requests one batch may carry (the providers' own limit)."""

API_WIDENED_LIMIT = 36864
"""The limit under which plain API answers cut at API_ANSWER_LIMIT were continued or redrawn on wave 2."""

API_REDRAW_LIMIT = 16384
"""The limit under which API answers cut on wave 1 were redrawn."""

OPENAI_WAVE1_LIMIT = 10240
"""The output limit of the OpenAI arms' first draw on wave 1 (reasoning tokens count against it)."""

OPENAI_WAVE2_LIMIT = 36864
"""The output limit of the OpenAI arms on wave 2."""

GEMINI_WAVE1_LIMIT = 10240
"""The output limit of the Gemini thinking arm's first draw on wave 1."""

GEMINI_LITE_WAVE1_LIMIT = 2048
"""The output limit of the Gemini plain arm's first draw on wave 1."""

GEMINI_WAVE2_LIMIT = 16384
"""The output limit of the Gemini arms on wave 2."""

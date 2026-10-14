"""Generation for the thinking forms: the model reasons at length, then answers.

Two forms were run, both outside the harness because its prompt pre-fills the assistant turn and so switches a
model's reasoning off:

- **two-phase**: phase one asks the model to think, with the closing tag as the one stop string and the thinking
  budget as the limit; a trace that reaches the budget is closed by appending the tag. Phase two appends the
  response sentence and an open Python fence and asks for the answer under the chat stops. The trace and the
  answer are recorded apart, with how the thinking closed (natural, forced, or no trace at all).
- **single-phase**: models that write the trace and the answer in one generation (``<think> ... </think>`` then
  code) are asked once, with a budget for both and no stop strings; the output is split at the closing tag. A
  trace that reaches the budget leaves no answer (``overlong``); such attempts get an answer phase afterwards:
  the stored trace is kept whole, closed in the form the model writes after a natural close, and the model answers
  from there under the answer budget (``answer_cut_traces``).

Reads the task set and the protocol. Writes ``samples.jsonl``, ``raw.jsonl`` and ``generation.json`` into the
output directory (see ``records``); the raw rows carry ``think_text``, ``think_tokens``, ``answer_tokens`` and
``closure``.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from . import extract as X
from . import prompts as P
from . import settings as S
from .inference import Backend, Sampling
from .protocols import Protocol
from .records import AttemptWriter, GenerationRecord, RAW, read_rows, today
from .taskset import set_sha256
from .vllm import FOUR_SPACES, TAB, choose_extractor


def _card(protocol: Protocol, n: int, max_tokens: int, stops: list, include_stop: bool = False) -> Sampling:
    return Sampling(
        n=n, max_tokens=max_tokens, temperature=protocol.temperature, top_p=protocol.top_p,
        top_k=protocol.top_k, min_p=protocol.min_p, stop=stops, include_stop_in_output=include_stop,
    )


def _record(protocol: Protocol, tasks, attempts, task_set_name, seed, extractor_name, model_revision, notes) -> GenerationRecord:
    return GenerationRecord(
        arm=protocol.arm, task_set=task_set_name, task_set_sha256=set_sha256(tasks), n_tasks=len(tasks),
        attempts_per_task=attempts, model_id=protocol.model_id, model_revision=model_revision,
        form=protocol.form, protocol=protocol.protocol, protocol_version=protocol.protocol_version, backend=protocol.backend, prompt_style=protocol.prompt_style,
        sampling=protocol.sampling() | {"n": attempts, "geometry": protocol.geometry},
        output_limit=protocol.output_limit, thinking_budget=protocol.thinking_budget, answer_budget=protocol.answer_budget,
        max_model_len=protocol.max_model_len, stops=list(protocol.stops), harness_commit=S.HARNESS_COMMIT,
        instruction=S.INSTRUCTION_PREFIX,
        extractor={"name": extractor_name, "stamp": X.CURRENT_STAMP if extractor_name == "v2" else "harness",
                   "logic_sha256": X.logic_sha256() if extractor_name == "v2" else None},
        pins={"vllm": S.VLLM_PIN, "transformers": S.TRANSFORMERS_PIN, "harness": S.HARNESS_COMMIT},
        seed=seed, started=today(), notes=notes,
    )


def generate_two_phase(
    tasks: Dict[str, Dict], protocol: Protocol, backend: Backend, out_dir: str, attempts: int, task_set_name: str,
    seed: Optional[int], extractor_name: str = "v2", model_revision: Optional[str] = None,
) -> GenerationRecord:
    """The two-phase thinking form over the set; resumes from the attempts on disk."""
    extractor = choose_extractor(extractor_name)
    tok = backend.tokenizer
    budget = protocol.thinking_budget or S.THINKING_BUDGET
    answer_budget = protocol.answer_budget or S.TWO_PHASE_ANSWER_BUDGET
    answer_stops = list(protocol.stops) or (S.EOS_STOPS + [S.CHAT_FENCE_STOP])
    record = _record(protocol, tasks, attempts, task_set_name, seed, extractor_name, model_revision,
                     {"template_class": P.template_class(tok), "closures": "natural, forced or no_think per attempt"})
    os.makedirs(out_dir, exist_ok=True)
    record.write(out_dir)
    with AttemptWriter(out_dir) as writer:
        for task_id, task in tasks.items():
            have = writer.done.get(task_id, 0)
            need = attempts - have
            if need <= 0:
                continue
            base = P.two_phase_base_prompt(task["prompt"], tok)
            traces = backend.generate([base], _card(protocol, need, budget, [S.THINK_CLOSE], include_stop=True))[0]
            answer_prompts, closures = [], []
            for t in traces:
                p2, closure = P.answer_phase_prompt(base, t.text)
                answer_prompts.append(p2)
                closures.append(closure)
            answers = backend.generate(answer_prompts, _card(protocol, 1, answer_budget, answer_stops))
            for i, (trace, closure, outs) in enumerate(zip(traces, closures, answers)):
                ans = outs[0]
                text = ans.text.replace(TAB, FOUR_SPACES)
                writer.write(
                    task_id, have + i, extractor(text, task["entry_point"]), text, ans.finish_reason,
                    think_text=trace.text, think_tokens=trace.tokens, think_finish_reason=trace.finish_reason,
                    answer_tokens=ans.tokens, closure=closure, tokens=(trace.tokens or 0) + (ans.tokens or 0),
                )
    record.finished = today()
    record.write(out_dir)
    return record


def single_phase_prompt(task: Dict, protocol: Protocol, tokenizer) -> str:
    if protocol.prompt_style == "single-phase":
        return P.single_phase_prompt(task["prompt"], tokenizer)
    if protocol.prompt_style == "deepseek-v32-thinking":
        return P.deepseek_v32_prompt(task["prompt"], thinking=True)
    if protocol.prompt_style == "deepseek-v32-chat":
        return P.deepseek_v32_prompt(task["prompt"], thinking=False)
    raise ValueError(f"{protocol.prompt_style!r} is not a single-phase prompt style")


def generate_single_phase(
    tasks: Dict[str, Dict], protocol: Protocol, backend: Backend, out_dir: str, attempts: int, task_set_name: str,
    seed: Optional[int], extractor_name: str = "v2", model_revision: Optional[str] = None,
) -> GenerationRecord:
    """The single-phase thinking form (and the DeepSeek V3.2 chat form, recorded the same way) over the set."""
    extractor = choose_extractor(extractor_name)
    tok = backend.tokenizer
    budget = protocol.thinking_budget or protocol.output_limit or S.SINGLE_PHASE_BUDGET
    chat_only = protocol.prompt_style == "deepseek-v32-chat"
    record = _record(protocol, tasks, attempts, task_set_name, seed, extractor_name, model_revision,
                     {"tokens": "the whole generation, trace and answer together",
                      "closures": "chat" if chat_only else "natural, overlong or no_marker per attempt"})
    os.makedirs(out_dir, exist_ok=True)
    record.write(out_dir)
    with AttemptWriter(out_dir) as writer:
        for task_id, task in tasks.items():
            have = writer.done.get(task_id, 0)
            need = attempts - have
            if need <= 0:
                continue
            prompt = single_phase_prompt(task, protocol, tok)
            outs = backend.generate([prompt], _card(protocol, need, budget, list(protocol.stops)))[0]
            for i, o in enumerate(outs):
                if chat_only:
                    trace, answer, closure = "", o.text, "chat"
                else:
                    trace, answer, closure = P.split_single_phase(o.text, o.finish_reason)
                text = answer.replace(TAB, FOUR_SPACES)
                writer.write(
                    task_id, have + i, extractor(text, task["entry_point"]), text, o.finish_reason,
                    think_text=trace, think_tokens=_count_tokens(tok, trace), think_finish_reason=o.finish_reason,
                    answer_tokens=o.tokens, closure=closure, tokens=o.tokens,
                )
    record.finished = today()
    record.write(out_dir)
    return record


def _count_tokens(tokenizer, text: str) -> Optional[int]:
    try:
        return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception:  # a tokenizer without that interface (the stand-in)
        return None


def answer_cut_traces(
    tasks: Dict[str, Dict], protocol: Protocol, backend: Backend, source_dir: str, out_dir: str,
    answer_budget: int = S.ANSWER_LIMIT, extractor_name: str = "v2",
) -> int:
    """The answer phase for single-phase attempts whose trace reached the budget (``closure`` is ``overlong``):
    the stored trace is kept whole and closed, and the model answers from there under ``answer_budget`` inside a
    window of ``ANSWER_PHASE_WINDOW`` tokens, with the protocol's sampling and no stop strings. The answered
    attempt is written to ``out_dir`` under its original index and the land stage puts it in the cut attempt's
    place. Returns how many were answered."""
    import hashlib

    extractor = choose_extractor(extractor_name)
    tok = backend.tokenizer
    rows = [r for r in read_rows(os.path.join(source_dir, RAW)) if r.get("closure") == "overlong"]
    n = 0
    with AttemptWriter(out_dir) as writer:
        done = {(r["task_id"], r["attempt"]) for r in read_rows(os.path.join(out_dir, RAW))} if os.path.exists(os.path.join(out_dir, RAW)) else set()
        for r in rows:
            if (r["task_id"], r["attempt"]) in done or r["task_id"] not in tasks:
                continue
            task = tasks[r["task_id"]]
            base = single_phase_prompt(task, protocol, tok)
            prompt = P.forced_close_prompt(base, r["think_text"])
            ans = backend.generate([prompt], _card(protocol, 1, answer_budget, []))[0][0]
            text = ans.text.replace(TAB, FOUR_SPACES)
            writer.write(
                r["task_id"], r["attempt"], extractor(text, task["entry_point"]), text, ans.finish_reason,
                think_text=r["think_text"], think_tokens=r.get("think_tokens"), think_finish_reason="length",
                answer_tokens=ans.tokens, closure="forced", tokens=(r.get("think_tokens") or 0) + (ans.tokens or 0),
                continued_from={"source_sha256": hashlib.sha256(r["think_text"].encode("utf-8")).hexdigest(),
                                "thinking_budget": protocol.thinking_budget, "answer_budget": answer_budget,
                                "window": S.ANSWER_PHASE_WINDOW},
            )
            n += 1
    return n

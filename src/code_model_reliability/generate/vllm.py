"""Generation with the inference engine for the plain and completion forms, and the continuation of cut answers.

One model, one task set, one protocol: every task gets the same number of attempts, each attempt is written as
the model returned it and as the program the judge reads, and an interrupted run resumes from the attempts on
disk. The prompt is the harness's chat prompt (or its generation-prompt variant, or the bare prompt for a model
with no chat template); the completion form hands a base model the bare task and keeps prompt plus completion as
the program. The thinking forms are in ``thinking``.

Request geometry follows the path the attempts were produced through: the harness's path sends one single-output request per attempt
(``flat``), the runner path one request for all attempts of a task (``grouped``); the two realise different
samples from the same settings, so the geometry is part of the protocol and recorded.

Reads the task set and the protocol. Writes ``samples.jsonl``, ``raw.jsonl`` and ``generation.json`` into the
output directory (see ``records``).
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from . import extract as X
from . import prompts as P
from . import settings as S
from .inference import Backend, Output, Sampling
from .protocols import Protocol
from .records import AttemptWriter, GenerationRecord, today
from .taskset import set_sha256

TAB = "\t"
FOUR_SPACES = "    "
"""The harness replaces tabs in a chat answer with four spaces before extraction; the completion form keeps the text."""


def render_prompt(task: Dict, protocol: Protocol, tokenizer) -> str:
    """The prompt for one task under a plain or completion protocol."""
    style = protocol.prompt_style
    if style == "completion":
        return P.completion_prompt(task["prompt"])
    if style == "direct" or (style == "chat" and getattr(tokenizer, "chat_template", None) is None):
        return P.harness_task_prompt(task["prompt"])
    if style == "chat":
        return P.chat_prompt(P.harness_task_prompt(task["prompt"]), tokenizer)
    if style == "generation-prompt":
        return P.generation_prompt(task["prompt"], tokenizer)
    raise ValueError(f"{style!r} is not a plain or completion prompt style; see thinking for the thinking forms")


def is_direct(protocol: Protocol, tokenizer) -> bool:
    """The harness's direct-completion case: a plain-form model with no chat template completes the bare prompt."""
    return protocol.prompt_style == "direct" or (
        protocol.prompt_style == "chat" and getattr(tokenizer, "chat_template", None) is None
    )


def stops_for(protocol: Protocol, task_set_name: str, tokenizer) -> list:
    """The stop strings of the protocol, plus the harness's extra stops for a direct completion on a wave 1 set."""
    stops = list(protocol.stops)
    if is_direct(protocol, tokenizer) and task_set_name in S.DIRECT_COMPLETION_STOPS:
        stops = list(S.EOS_STOPS) + S.DIRECT_COMPLETION_STOPS[task_set_name]
    return stops


def judged_program(task: Dict, protocol: Protocol, prompt: str, text: str, tokenizer, extractor: Callable) -> str:
    """The program the judge reads for one attempt: the completion form keeps prompt plus completion whole; a
    direct completion is extracted from prompt plus completion (the harness's rule); a chat answer is extracted
    from the answer alone."""
    if protocol.prompt_style == "completion":
        return prompt + text
    if is_direct(protocol, tokenizer):
        return extractor(prompt + text, task["entry_point"])
    return extractor(text, task["entry_point"])


def sampling_for(protocol: Protocol, n: int, max_tokens: Optional[int], stops: list, greedy: bool = False) -> Sampling:
    temperature = S.GREEDY_TEMPERATURE if greedy else protocol.temperature
    return Sampling(
        n=n,
        max_tokens=max_tokens or protocol.output_limit or S.ANSWER_LIMIT,
        temperature=temperature,
        top_p=1.0 if greedy or temperature == 0 else protocol.top_p,
        top_k=protocol.top_k,
        min_p=protocol.min_p,
        stop=stops,
        include_stop_in_output=False,
    )


def choose_extractor(name: str) -> Callable[[str, str], str]:
    """``v2`` is the current extractor; ``harness`` the harness's own sanitizer at the pinned commit."""
    if name == "v2":
        return X.extract
    if name == "harness":
        return X.harness_sanitize
    raise ValueError(f"unknown extractor {name!r}")


def generate_arm(
    tasks: Dict[str, Dict],
    protocol: Protocol,
    backend: Backend,
    out_dir: str,
    attempts: int,
    task_set_name: str,
    seed: Optional[int],
    extractor_name: str = "v2",
    greedy: bool = False,
    model_revision: Optional[str] = None,
    task_source: Optional[str] = None,
) -> GenerationRecord:
    """Every task of the set answered ``attempts`` times under the protocol; resumes from the attempts already in
    the output directory. Returns the generation record it wrote."""
    extractor = choose_extractor(extractor_name)
    tokenizer = backend.tokenizer
    os.makedirs(out_dir, exist_ok=True)
    stops = stops_for(protocol, task_set_name, tokenizer)
    record = GenerationRecord(
        arm=protocol.arm, task_set=task_set_name, task_set_sha256=set_sha256(tasks), n_tasks=len(tasks),
        attempts_per_task=attempts, model_id=protocol.model_id, model_revision=model_revision,
        form=protocol.form, protocol=protocol.protocol, protocol_version=protocol.protocol_version, backend=protocol.backend, prompt_style=protocol.prompt_style,
        sampling=sampling_for(protocol, 1, None, stops, greedy).__dict__ | {"n": attempts, "geometry": protocol.geometry},
        output_limit=protocol.output_limit, thinking_budget=None, answer_budget=None,
        max_model_len=protocol.max_model_len, stops=stops, harness_commit=S.HARNESS_COMMIT,
        instruction=S.INSTRUCTION_PREFIX if protocol.prompt_style != "completion" else "",
        extractor={"name": extractor_name, "stamp": X.CURRENT_STAMP if extractor_name == "v2" else "harness",
                   "logic_sha256": X.logic_sha256() if extractor_name == "v2" else None},
        pins={"vllm": S.VLLM_PIN, "transformers": S.TRANSFORMERS_PIN, "harness": S.HARNESS_COMMIT},
        seed=seed, started=today(),
        notes={"task_source": os.path.basename(task_source) if task_source else None,
               "tab_rule": "tabs in a chat answer become four spaces before extraction" if protocol.prompt_style != "completion" else "the completion is kept as returned"},
    )
    record.write(out_dir)
    with AttemptWriter(out_dir) as writer:
        for task_id, task in tasks.items():
            have = writer.done.get(task_id, 0)
            need = attempts - have
            if need <= 0:
                continue
            prompt = render_prompt(task, protocol, tokenizer)
            outputs = _draw(backend, prompt, need, protocol, stops, greedy)
            for i, out in enumerate(outputs):
                text = out.text if protocol.prompt_style == "completion" else out.text.replace(TAB, FOUR_SPACES)
                solution = judged_program(task, protocol, prompt, text, tokenizer, extractor)
                writer.write(task_id, have + i, solution, text, out.finish_reason, tokens=out.tokens)
    record.finished = today()
    record.write(out_dir)
    return record


def _draw(backend: Backend, prompt: str, n: int, protocol: Protocol, stops: list, greedy: bool) -> list:
    """``n`` outputs for one prompt in the protocol's request geometry."""
    if protocol.geometry == "grouped":
        return backend.generate([prompt], sampling_for(protocol, n, None, stops, greedy))[0]
    batch = backend.generate([prompt] * n, sampling_for(protocol, 1, None, stops, greedy))
    return [outs[0] for outs in batch]


def continue_cut_attempts(
    tasks: Dict[str, Dict],
    protocol: Protocol,
    backend: Backend,
    source_dir: str,
    out_dir: str,
    task_set_name: str,
    first_pass_limit: int = S.FIRST_PASS_LIMIT,
    limit: int = S.ANSWER_LIMIT,
    extractor_name: str = "v2",
) -> int:
    """Every attempt in ``source_dir`` that the first pass cut (``finish_reason`` is ``length``) is continued: the
    model is given its prompt followed by the cut text verbatim and may add up to ``limit`` minus
    ``first_pass_limit`` tokens under the same sampling and stops. The continued text is the cut text plus the
    addition, so the two parts are one attempt; it is written to ``out_dir`` with the attempt's index and the
    source text's sha256, and the land stage replaces the cut attempt by it. Returns how many were continued."""
    import hashlib

    from .records import RAW, read_rows

    extractor = choose_extractor(extractor_name)
    tokenizer = backend.tokenizer
    stops = stops_for(protocol, task_set_name, tokenizer)
    rows = [r for r in read_rows(os.path.join(source_dir, RAW)) if r.get("finish_reason") == "length"]
    n = 0
    with AttemptWriter(out_dir) as writer:
        already = {(r["task_id"], r["attempt"]) for r in read_rows(os.path.join(out_dir, RAW))} if os.path.exists(os.path.join(out_dir, RAW)) else set()
        for r in rows:
            key = (r["task_id"], r["attempt"])
            if key in already or r["task_id"] not in tasks:
                continue
            task = tasks[r["task_id"]]
            prompt = render_prompt(task, protocol, tokenizer)
            addition = backend.generate([prompt + r["text"]], Sampling(
                n=1, max_tokens=limit - first_pass_limit, temperature=protocol.temperature, top_p=protocol.top_p,
                top_k=protocol.top_k, min_p=protocol.min_p, stop=stops))[0][0]
            text = r["text"] + (addition.text if protocol.prompt_style == "completion" else addition.text.replace(TAB, FOUR_SPACES))
            solution = judged_program(task, protocol, prompt, text, tokenizer, extractor)
            writer.write(
                r["task_id"], r["attempt"], solution, text, addition.finish_reason, tokens=addition.tokens,
                continued_from={"source_sha256": hashlib.sha256(r["text"].encode("utf-8")).hexdigest(),
                                "first_pass_limit": first_pass_limit, "limit": limit},
            )
            n += 1
    return n

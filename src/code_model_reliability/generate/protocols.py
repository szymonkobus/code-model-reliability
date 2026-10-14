"""The generation protocols: which prompt form, sampling and limits each arm ran under.

A protocol is the complete description of how a model was asked and how its output was cut; an arm is a model
under one protocol. The shipped table is ``data/runs/registry/protocols.tsv``, one row per published arm, regenerated
at every build from the registry; this module reads it and also carries the protocols as named defaults,
so a new model can be run under a protocol by name.

Reads ``data/runs/registry/protocols.tsv`` (or a table given by path). Writes nothing.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import os
from typing import Dict, List, Optional

from . import settings as S

FORMS = ("plain", "thinking", "completion")
"""The three forms (see the glossary): a chat model answering directly, a model reasoning before it answers, a
base model continuing the bare prompt."""

BACKENDS = ("vllm", "anthropic", "openai", "gemini", "standin")
"""Where the attempts are produced: the inference engine on a GPU machine, one of three provider batch APIs, or the
deterministic stand-in used by the tests."""

PROMPT_STYLES = (
    "chat",  # the harness's chat prompt: cut assistant message with the response sentence and an open fence
    "generation-prompt",  # the same, opened with the template's own generation prompt (thinking off)
    "direct",  # the bare prompt for a model without a chat template (the harness's rule)
    "two-phase",  # thinking first, forced closed at its budget, then the answer phase under the chat opening
    "single-phase",  # trace and answer in one generation, split at the closing tag
    "deepseek-v32-thinking",  # the DeepSeek V3.2 encoding with the thinking tag open
    "deepseek-v32-chat",  # the DeepSeek V3.2 encoding with the thinking tag closed
    "completion",  # the bare prompt with one trailing newline; the program is prompt plus completion
    "api-message",  # one user message with the task in a ```python fence (the API forms)
)


@dataclasses.dataclass
class Protocol:
    """One arm's protocol. ``protocol`` is the protocol's name as given to ``--protocol`` and ``protocol_version`` its
    version token where it has one (``completion-v1``), else empty; ``output_limit`` is the answer limit; ``first_pass_limit`` the shorter limit the first
    draw used where there was one (the cut attempts were continued to the limit);
    ``thinking_budget`` and ``answer_budget`` apply to the thinking forms; ``stops`` is the stop-string list; the
    ``geometry`` of a request is ``flat`` (one single-output request per attempt, the harness's way) or ``grouped``
    (one request asking for all attempts of a task)."""

    arm: str
    model_id: str
    form: str
    protocol: str
    protocol_version: str
    backend: str
    prompt_style: str
    temperature: float
    top_p: float
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    output_limit: Optional[int] = None
    first_pass_limit: Optional[int] = None
    thinking_budget: Optional[int] = None
    answer_budget: Optional[int] = None
    max_model_len: Optional[int] = None
    stops: List[str] = dataclasses.field(default_factory=list)
    geometry: str = "flat"
    attempts_wave1: Optional[int] = None
    attempts_wave2: Optional[int] = None
    card: dict = dataclasses.field(default_factory=dict)
    note: str = ""

    @property
    def token(self) -> str:
        """The protocol token in the arm id: none for the plain form, ``think`` or ``completion`` otherwise."""
        return {"plain": "", "thinking": "think", "completion": "completion"}[self.form]

    def sampling(self) -> dict:
        d = {"temperature": self.temperature, "top_p": self.top_p}
        if self.top_k is not None:
            d["top_k"] = self.top_k
        if self.min_p is not None:
            d["min_p"] = self.min_p
        return d


def arm_id(model_id: str, form: str, temperature: float) -> str:
    """The arm id: the model stem (``/`` written ``--``), the protocol token where the form has one, and the
    temperature; for example ``Qwen--Qwen2.5-7B-Instruct_temp_0.8`` or ``Qwen--Qwen3-8B_think_temp_0.6``."""
    stem = model_id.strip("./").replace("/", "--")
    token = {"plain": "", "thinking": "_think", "completion": "_completion"}[form]
    return f"{stem}{token}_temp_{temperature}"


# --- the named protocols as run ------------------------------------------------------------------------------------

def plain_chat(model_id: str, output_limit: int = S.ANSWER_LIMIT, first_pass: Optional[int] = None) -> Protocol:
    """The plain form through the harness's chat prompt and the inference engine: temperature 0.8, top-p 0.95, the harness's
    stop strings, one single-output request per attempt."""
    return Protocol(
        arm=arm_id(model_id, "plain", S.TEMPERATURE), model_id=model_id, form="plain",
        protocol="plain-chat", protocol_version="", backend="vllm", prompt_style="chat",
        temperature=S.TEMPERATURE, top_p=S.TOP_P, output_limit=output_limit, first_pass_limit=first_pass,
        max_model_len=S.MAX_MODEL_LEN_WAVE2 + (output_limit if output_limit > S.FIRST_PASS_LIMIT else 0),
        stops=S.EOS_STOPS + [S.CHAT_FENCE_STOP], geometry="flat",
    )


def plain_generation_prompt(model_id: str, output_limit: int = S.ANSWER_LIMIT) -> Protocol:
    """The plain form opened with the template's generation prompt (for templates that mark the model's turn), the
    rest as ``plain_chat``; all attempts of a task in one request."""
    p = plain_chat(model_id, output_limit)
    p.protocol, p.prompt_style, p.geometry = "plain-generation-prompt", "generation-prompt", "grouped"
    return p


def plain_runner(model_id: str, output_limit: int = S.ANSWER_LIMIT, max_model_len: Optional[int] = None) -> Protocol:
    """The plain form through the project's runner with the harness's prompt imported, for models whose tokenizer
    the harness's own path cannot load; all attempts of a task in one request."""
    p = plain_chat(model_id, output_limit)
    p.protocol, p.geometry = "plain-runner", "grouped"
    if max_model_len:
        p.max_model_len = max_model_len
    return p


def two_phase_thinking(model_id: str, answer_budget: int = S.TWO_PHASE_ANSWER_BUDGET) -> Protocol:
    """The two-phase thinking form: thinking under the makers' sampling to a 32,768-token budget, forced closed
    there, then the answer under the chat opening."""
    return Protocol(
        arm=arm_id(model_id, "thinking", S.THINKING_CARD["temperature"]), model_id=model_id, form="thinking",
        protocol="two-phase-thinking", protocol_version="", backend="vllm", prompt_style="two-phase",
        temperature=S.THINKING_CARD["temperature"], top_p=S.THINKING_CARD["top_p"],
        top_k=S.THINKING_CARD["top_k"], min_p=S.THINKING_CARD["min_p"],
        thinking_budget=S.THINKING_BUDGET, answer_budget=answer_budget, output_limit=answer_budget,
        max_model_len=S.MAX_MODEL_LEN_TWO_PHASE, stops=S.EOS_STOPS + [S.CHAT_FENCE_STOP], geometry="grouped",
    )


def single_phase_thinking(model_id: str, distilled: bool = False) -> Protocol:
    """The single-phase thinking form: trace and answer in one generation under a budget for both, no stop strings,
    split at the closing tag; the distilled models take the smaller budget their context allows."""
    budget = S.SINGLE_PHASE_BUDGET_DISTILLED if distilled else S.SINGLE_PHASE_BUDGET
    window = S.MAX_MODEL_LEN_SINGLE_PHASE_DISTILLED if distilled else S.MAX_MODEL_LEN_SINGLE_PHASE
    return Protocol(
        arm=arm_id(model_id, "thinking", S.SINGLE_PHASE_CARD["temperature"]), model_id=model_id, form="thinking",
        protocol="single-phase-thinking", protocol_version="", backend="vllm", prompt_style="single-phase",
        temperature=S.SINGLE_PHASE_CARD["temperature"], top_p=S.SINGLE_PHASE_CARD["top_p"],
        thinking_budget=budget, answer_budget=S.ANSWER_LIMIT, output_limit=budget, max_model_len=window,
        stops=[], geometry="grouped",
    )


def deepseek_v32(model_id: str, thinking: bool) -> Protocol:
    """The DeepSeek V3.2 encoding (no chat template) in its thinking or chat form, under the single-phase settings."""
    p = single_phase_thinking(model_id)
    p.protocol = p.prompt_style = "deepseek-v32-thinking" if thinking else "deepseek-v32-chat"
    if not thinking:
        p.form = "plain"
        p.arm = arm_id(model_id, "plain", p.temperature)
        p.thinking_budget, p.answer_budget = None, None
    return p


def completion(model_id: str, output_limit: int = S.ANSWER_LIMIT) -> Protocol:
    """The completion form for base models: the bare prompt, temperature 0.8, top-p 0.95, the completion stops;
    the program is the prompt plus the completion, no extraction."""
    return Protocol(
        arm=arm_id(model_id, "completion", S.TEMPERATURE), model_id=model_id, form="completion",
        protocol="completion", protocol_version="completion-v1", backend="vllm", prompt_style="completion",
        temperature=S.TEMPERATURE, top_p=S.TOP_P, output_limit=output_limit,
        max_model_len=S.MAX_MODEL_LEN_WAVE2 + output_limit, stops=list(S.COMPLETION_STOPS), geometry="grouped",
    )


PROTOCOLS = {
    "plain-chat": plain_chat,
    "plain-generation-prompt": plain_generation_prompt,
    "plain-runner": plain_runner,
    "two-phase-thinking": two_phase_thinking,
    "single-phase-thinking": single_phase_thinking,
    "deepseek-v32-thinking": lambda model_id: deepseek_v32(model_id, thinking=True),
    "deepseek-v32-chat": lambda model_id: deepseek_v32(model_id, thinking=False),
    "completion": completion,
}
"""The named protocols of the open-weight arms, each under the name a run's record carries and ``--protocol`` takes;
the API arms' cards are in ``api``."""


# --- the shipped table ----------------------------------------------------------------------------------------------

def default_table_path() -> str:
    """``data/runs/registry/protocols.tsv`` relative to the repository root this package is installed from."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, "data", "runs", "registry", "protocols.tsv")


def _opt_int(v: str) -> Optional[int]:
    return int(v) if v not in ("", None) else None


def _opt_float(v: str) -> Optional[float]:
    return float(v) if v not in ("", None) else None


def load_table(path: Optional[str] = None) -> Dict[str, Protocol]:
    """Every arm's protocol from the shipped table, keyed by arm id."""
    path = path or default_table_path()
    out: Dict[str, Protocol] = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            p = Protocol(
                arm=row["arm"], model_id=row["model_id"], form=row["form"], protocol=row["protocol"],
                protocol_version=row.get("protocol_version", ""),
                backend=row["backend"], prompt_style=row["prompt_style"],
                temperature=float(row["temperature"]), top_p=float(row["top_p"]) if row["top_p"] else 1.0,
                top_k=_opt_int(row.get("top_k", "")), min_p=_opt_float(row.get("min_p", "")),
                output_limit=_opt_int(row.get("output_limit", "")), first_pass_limit=_opt_int(row.get("first_pass_limit", "")),
                thinking_budget=_opt_int(row.get("thinking_budget", "")), answer_budget=_opt_int(row.get("answer_budget", "")),
                max_model_len=_opt_int(row.get("max_model_len", "")),
                stops=decode_stops(row.get("stops", "")),
                geometry=row.get("geometry", "flat") or "flat",
                attempts_wave1=_opt_int(row.get("attempts_wave1", "")), attempts_wave2=_opt_int(row.get("attempts_wave2", "")),
                note=row.get("note", ""),
            )
            out[p.arm] = p
    return out


def encode_stops(stops: List[str]) -> str:
    """Stop strings as one table cell: a JSON list, so a newline or a space inside a stop survives the table."""
    return json.dumps(list(stops), ensure_ascii=True)


def decode_stops(cell: str) -> List[str]:
    return json.loads(cell) if cell.strip() else []

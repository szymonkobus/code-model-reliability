"""The Anthropic arms: the cards the published attempts were drawn with, and the Message Batches wire format.

Sampling differs by model generation, as the API allows it: the Haiku 4.5 plain arm samples at temperature 0.8
with top-p unset (the API refuses temperature and top-p together); its thinking arm runs at the temperature the
API forces for thinking (1.0) with an explicit 32,768-token budget; the Claude 5 family refuses temperature,
top-p and top-k and samples under the provider's defaults, its thinking arms under adaptive thinking at high
effort with the summarized trace returned. Plain arms stop at the end-of-text stop strings; thinking arms
take no stop strings. Every arm's output limit is 4,096 (plain) or 36,864 (thinking).

Reads ``ANTHROPIC_API_KEY`` from the environment. Writes nothing itself; see ``batch``.
"""

from __future__ import annotations

from typing import Iterable, List

from .. import settings as S
from .batch import Card, Provider, Result

PLAIN = {"max_tokens": S.API_ANSWER_LIMIT}
THINKING = {"max_tokens": S.API_THINKING_LIMIT}
ADAPTIVE = {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "high"}}

CARDS = {
    "claude-haiku-4-5": Card(
        "claude-haiku-4-5_batch", "claude-haiku-4-5-20251001",
        {**PLAIN, "temperature": S.TEMPERATURE, "stop_sequences": list(S.EOS_STOPS)}, "plain", "0.8",
        "the one Claude arm that samples at the open-weight arms' temperature; top-p unset",
    ),
    "claude-haiku-4-5-thinking": Card(
        "claude-haiku-4-5-thinking_batch", "claude-haiku-4-5-20251001",
        {**THINKING, "thinking": {"type": "enabled", "budget_tokens": S.API_THINKING_BUDGET}}, "thinking", "1.0",
        "thinking forces temperature 1.0; a fixed budget; no stop strings",
    ),
    "claude-sonnet-5": Card(
        "claude-sonnet-5_batch", "claude-sonnet-5",
        {**PLAIN, "thinking": {"type": "disabled"}, "stop_sequences": list(S.EOS_STOPS)}, "plain", "1.0",
        "provider-default sampling",
    ),
    "claude-sonnet-5-thinking": Card(
        "claude-sonnet-5-thinking_batch", "claude-sonnet-5", {**THINKING, **ADAPTIVE}, "thinking", "1.0",
        "adaptive thinking at high effort; no stop strings",
    ),
    "claude-opus-5": Card(
        "claude-opus-5_batch", "claude-opus-5",
        {**PLAIN, "thinking": {"type": "disabled"}, "output_config": {"effort": "high"}, "stop_sequences": list(S.EOS_STOPS)},
        "plain", "1.0", "thinking disabled is accepted only with an effort setting on this model",
    ),
    "claude-opus-5-thinking": Card(
        "claude-opus-5-thinking_batch", "claude-opus-5", {**THINKING, **ADAPTIVE}, "thinking", "1.0",
    ),
    "claude-haiku-5-5": Card(
        "claude-haiku-5-5_batch", "claude-haiku-5-5",
        {**PLAIN, "thinking": {"type": "disabled"}, "stop_sequences": list(S.EOS_STOPS)}, "plain", "1.0",
    ),
    "claude-haiku-5-5-thinking": Card(
        "claude-haiku-5-5-thinking_batch", "claude-haiku-5-5", {**THINKING, **ADAPTIVE}, "thinking", "1.0",
    ),
    "claude-sonnet-5-5": Card(
        "claude-sonnet-5-5_batch", "claude-sonnet-5-5",
        {**PLAIN, "thinking": {"type": "between_tools"}, "stop_sequences": list(S.EOS_STOPS)}, "plain", "1.0",
        "this model's form for a reply without thinking",
    ),
    "claude-sonnet-5-5-thinking": Card(
        "claude-sonnet-5-5-thinking_batch", "claude-sonnet-5-5", {**THINKING, **ADAPTIVE}, "thinking", "1.0",
    ),
    "claude-opus-5-5-thinking": Card(
        "claude-opus-5-5-thinking_batch", "claude-opus-5-5", {**THINKING, **ADAPTIVE}, "thinking", "1.0",
        "the service offers this model no form without thinking, so it is the one Opus 5.5 arm",
    ),
}
"""The published arms' cards by arm name. An arm's id is the key the fit's files were produced under: the model
name with its thinking form and the batch token. The plain cards first carried the closing-fence stop as well;
attempts it ended before any code were redrawn without it, and the cards stand as listed."""


class Anthropic(Provider):
    name = "anthropic"

    def __init__(self):
        self._client = None

    def client(self):
        if self._client is None:
            import os

            import anthropic

            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def card(self, name: str) -> Card:
        return CARDS[name]

    def build_request(self, rid: str, card: Card, message: str) -> dict:
        return {
            "custom_id": rid,
            "params": {"model": card.model, "messages": [{"role": "user", "content": message}], **card.params},
        }

    def submit(self, requests: List[dict], card: Card, label: str) -> str:
        batch = self.client().messages.batches.create(requests=requests)
        return batch.id

    def status(self, batch_id: str) -> str:
        b = self.client().messages.batches.retrieve(batch_id)
        return "ended" if b.processing_status == "ended" else "in_progress"

    def results(self, batch_id: str) -> Iterable[Result]:
        for res in self.client().messages.batches.results(batch_id):
            if res.result.type != "succeeded":
                yield Result(res.custom_id, ok=False, error={"type": res.result.type})
                continue
            m = res.result.message
            text = "".join(b.text for b in m.content if b.type == "text")
            thinking = [getattr(b, "thinking", "") or "" for b in m.content if b.type == "thinking"]
            redacted = sum(1 for b in m.content if b.type == "redacted_thinking")
            yield Result(
                res.custom_id, ok=True, text=text, finish_reason=_finish(m.stop_reason), model=m.model,
                usage={"input_tokens": m.usage.input_tokens, "output_tokens": m.usage.output_tokens},
                thinking_text="\n".join(thinking) if thinking else None,
                provider={"stop_reason": m.stop_reason, "message_id": getattr(m, "id", None), "redacted_thinking_blocks": redacted},
            )


def _finish(stop_reason: str) -> str:
    return {"max_tokens": "length", "refusal": "refusal"}.get(stop_reason or "", "stop")

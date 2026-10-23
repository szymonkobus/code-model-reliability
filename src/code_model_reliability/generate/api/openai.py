"""The OpenAI arms: the cards the published attempts were drawn with, and the Batch API wire format.

The three arms are reasoning models that take no temperature or top-p; they sample under the provider's defaults
and their reasoning tokens count against the output limit (``max_completion_tokens``). For the two GPT-5 arms, on
wave 1 the first draw ran under a limit of 10,240 and the attempts it cut were redrawn under 16,384; on wave 2 the
limit was 36,864. GPT-6 Astra answered once per task on both waves under 36,864 with reasoning effort high; no
attempt reached that limit, so none was redrawn (a cut attempt would have been redrawn once at 128,000). No stop
strings.

Reads ``OPENAI_API_KEY`` from the environment. Writes nothing itself; see ``batch``.
"""

from __future__ import annotations

import io
import json
from typing import Iterable, List

from .. import settings as S
from .batch import Card, Provider, Result

CARDS = {
    "gpt-5-mini": Card("gpt-5-mini_batch", "gpt-5-mini-2025-08-07",
                       {"max_completion_tokens": S.OPENAI_WAVE2_LIMIT}, "thinking", "1.0",
                       f"wave 1 first draw at {S.OPENAI_WAVE1_LIMIT}, cut attempts redrawn at {S.API_REDRAW_LIMIT}"),
    "gpt-5-nano": Card("gpt-5-nano_batch", "gpt-5-nano-2025-08-07",
                       {"max_completion_tokens": S.OPENAI_WAVE2_LIMIT}, "thinking", "1.0",
                       f"wave 1 first draw at {S.OPENAI_WAVE1_LIMIT}, cut attempts redrawn at {S.API_REDRAW_LIMIT}"),
    "gpt-6-astra": Card("gpt-6-astra_batch", "gpt-6-astra",
                        {"max_completion_tokens": S.ONE_ANSWER_LIMIT, "reasoning_effort": "high"}, "thinking", "1.0",
                        f"one answer per task on both waves at reasoning effort high; a cut attempt would have been redrawn once at {S.ONE_ANSWER_REDRAW_LIMIT}, none was cut"),
}

ENDPOINT = "/v1/chat/completions"
COMPLETION_WINDOW = "24h"


class OpenAI(Provider):
    name = "openai"

    def __init__(self):
        self._client = None

    def client(self):
        if self._client is None:
            import os

            import openai

            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            self._client = openai.OpenAI(api_key=key)
        return self._client

    def card(self, name: str) -> Card:
        return CARDS[name]

    def build_request(self, rid: str, card: Card, message: str) -> dict:
        return {
            "custom_id": rid,
            "method": "POST",
            "url": ENDPOINT,
            "body": {"model": card.model, "messages": [{"role": "user", "content": message}], **card.params},
        }

    def submit(self, requests: List[dict], card: Card, label: str) -> str:
        payload = "".join(json.dumps(r) + "\n" for r in requests).encode("utf-8")
        upload = self.client().files.create(file=(f"{label}.jsonl", io.BytesIO(payload)), purpose="batch")
        batch = self.client().batches.create(
            input_file_id=upload.id, endpoint=ENDPOINT, completion_window=COMPLETION_WINDOW,
            metadata={"description": label},
        )
        return batch.id

    def status(self, batch_id: str) -> str:
        b = self.client().batches.retrieve(batch_id)
        if b.status in ("completed",):
            return "ended"
        if b.status in ("failed", "expired", "cancelled"):
            return "failed"
        return "in_progress"

    def results(self, batch_id: str) -> Iterable[Result]:
        b = self.client().batches.retrieve(batch_id)
        for fid in (b.output_file_id, b.error_file_id):
            if not fid:
                continue
            content = self.client().files.content(fid).text
            for line in content.splitlines():
                if not line.strip():
                    continue
                res = json.loads(line)
                resp = res.get("response") or {}
                if res.get("error") or resp.get("status_code") != 200:
                    yield Result(res["custom_id"], ok=False, error=res.get("error") or (resp.get("body") or {}).get("error"))
                    continue
                body = resp["body"]
                choice = body["choices"][0]
                msg = choice["message"]
                yield Result(
                    res["custom_id"], ok=True, text=msg.get("content") or "",
                    finish_reason=_finish(choice.get("finish_reason"), msg.get("refusal")), model=body.get("model", ""),
                    usage=_usage(body.get("usage") or {}),
                    provider={"finish_reason": choice.get("finish_reason"), "refusal": msg.get("refusal")},
                )


def _finish(finish_reason: str, refusal) -> str:
    if refusal:
        return "refusal"
    return {"length": "length", "content_filter": "refusal"}.get(finish_reason or "", "stop")


def _usage(u: dict) -> dict:
    return {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
            "reasoning_tokens": ((u.get("completion_tokens_details") or {}).get("reasoning_tokens"))}

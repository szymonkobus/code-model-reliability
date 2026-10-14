"""The Gemini arms: the cards the published attempts were drawn with, and the batch wire format of the Google GenAI SDK.

Both arms sample at temperature 0.8 (the open-weight arms' temperature) with the provider's default thinking setting
(the plain arm has no thinking; the thinking arm thinks at the provider's default). On wave 1 the first draw ran
under an output limit of 2,048 (plain arm) or 10,240 (thinking arm) and the attempts it cut were redrawn under
16,384; on wave 2 the limit was 16,384. A batch job carries one model, so a run submits one card at a time.

Reads ``GEMINI_API_KEY`` from the environment. Writes nothing itself; see ``batch``.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Iterable, List

from .. import settings as S
from .batch import Card, Provider, Result

CARDS = {
    "gemini-3.5-flash-lite": Card("gemini-3.5-flash-lite_batch", "gemini-3.5-flash-lite",
                                  {"max_output_tokens": S.GEMINI_WAVE2_LIMIT, "temperature": S.TEMPERATURE}, "plain", "0.8",
                                  f"wave 1 first draw at {S.GEMINI_LITE_WAVE1_LIMIT}, cut attempts redrawn at {S.API_REDRAW_LIMIT}"),
    "gemini-3.6-flash": Card("gemini-3.6-flash_batch", "gemini-3.6-flash",
                             {"max_output_tokens": S.GEMINI_WAVE2_LIMIT, "temperature": S.TEMPERATURE}, "thinking", "0.8",
                             f"wave 1 first draw at {S.GEMINI_WAVE1_LIMIT}, cut attempts redrawn at {S.API_REDRAW_LIMIT}; thinking at the provider's default"),
}

TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


class Gemini(Provider):
    name = "gemini"
    one_model_per_batch = True

    def __init__(self):
        self._client = None

    def client(self):
        if self._client is None:
            from google import genai

            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=key)
        return self._client

    def card(self, name: str) -> Card:
        return CARDS[name]

    def build_request(self, rid: str, card: Card, message: str) -> dict:
        return {
            "key": rid,
            "request": {"contents": [{"role": "user", "parts": [{"text": message}]}], "generation_config": dict(card.params)},
        }

    def submit(self, requests: List[dict], card: Card, label: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for r in requests:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            path = fh.name
        try:
            upload = self.client().files.upload(file=path, config={"mime_type": "application/jsonl", "display_name": label})
            job = self.client().batches.create(model=card.model, src=upload.name, config={"display_name": label})
        finally:
            os.unlink(path)
        return job.name

    def status(self, batch_id: str) -> str:
        job = self.client().batches.get(name=batch_id)
        state = job.state.name if hasattr(job.state, "name") else str(job.state)
        if state == "JOB_STATE_SUCCEEDED":
            return "ended"
        if state in TERMINAL:
            return "failed"
        return "in_progress"

    def results(self, batch_id: str) -> Iterable[Result]:
        job = self.client().batches.get(name=batch_id)
        dest = getattr(job, "dest", None)
        file_name = getattr(dest, "file_name", None) if dest else None
        if not file_name:
            return
        blob = self.client().files.download(file=file_name)
        text = blob.decode("utf-8") if isinstance(blob, bytes) else str(blob)
        for line in text.splitlines():
            if not line.strip():
                continue
            res = json.loads(line)
            rid = res.get("key")
            if res.get("error"):
                yield Result(rid, ok=False, error=res["error"])
                continue
            resp = res.get("response") or {}
            candidates = resp.get("candidates") or []
            parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
            answer = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            thought = "".join(p.get("text", "") for p in parts if p.get("thought")) or None
            raw_finish = (candidates[0].get("finishReason") or candidates[0].get("finish_reason")) if candidates else None
            usage = resp.get("usageMetadata") or resp.get("usage_metadata") or {}
            yield Result(
                rid, ok=True, text=answer, finish_reason=_finish(raw_finish),
                model=resp.get("modelVersion") or resp.get("model_version") or "",
                usage={"input_tokens": usage.get("promptTokenCount") or usage.get("prompt_token_count"),
                       "output_tokens": usage.get("candidatesTokenCount") or usage.get("candidates_token_count"),
                       "reasoning_tokens": usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count")},
                thinking_text=thought, provider={"finish_reason": raw_finish},
            )


def _finish(raw: str) -> str:
    return {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "refusal", "RECITATION": "refusal"}.get(raw or "", "stop")

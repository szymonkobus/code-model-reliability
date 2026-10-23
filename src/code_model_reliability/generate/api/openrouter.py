"""The arm served through OpenRouter: the card the published attempts were drawn with, and OpenRouter's
chat-completions wire format (an OpenAI-compatible request answered live, not a batch).

Muse Wonder is a reasoning model served by its maker behind OpenRouter. Every request pins the maker's own
endpoint (``provider``: order ``meta``, no fallbacks, parameters required, data collection denied), asks for
reasoning at high effort and caps reasoning plus answer under one limit (``max_tokens`` 36,864). No temperature or
top-p is sent, so the model samples under the provider's defaults; no stop strings. Each request was answered over
a streamed connection and assembled into the plain response shape, with usage accounting asked for on every call.
An attempt cut at the limit with no answer text was redrawn once at 128,000 tokens (seven of the 858 pool attempts;
an eighth reached the limit with an answer text and stands as drawn); where the provider never served the redraw,
the cut first attempt stands.

The cycle is live rather than batched: ``submit`` sends the requests at a bounded concurrency, retrying
OpenRouter's rate-limit and server errors, and writes the answers to an answers file; ``status`` reads that file;
``results`` yields it. Reads ``OPENROUTER_API_KEY`` from the environment and the answers directory from
``OPENROUTER_ANSWERS_DIR`` (default ``openrouter-answers`` under the working directory). Writes the answers file; see
``batch`` for the rest of the cycle.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Optional

from .. import settings as S
from .batch import Card, Provider, Result

CARDS = {
    "muse-wonder": Card("muse-wonder-1.0_meta", "meta/muse-wonder",
                        {"max_tokens": S.ONE_ANSWER_LIMIT, "reasoning": {"effort": "high"}}, "thinking", "1.0",
                        f"one answer per task on both waves at reasoning effort high, served by the maker through OpenRouter; "
                        f"eight attempts reached the limit: the seven with no answer text were redrawn once at {S.ONE_ANSWER_REDRAW_LIMIT} "
                        f"(five redraws stand, two the provider never served stand as their cut first attempts), the eighth, cut with "
                        f"an answer text, stands as drawn"),
}

BASE_URL = "https://openrouter.ai/api/v1"
"""OpenRouter's base; the request path below it is the chat-completions one."""

ENDPOINT = "/v1/chat/completions"
"""The path recorded on every request row (OpenRouter serves it under BASE_URL as ``/chat/completions``)."""

PROVIDER_PIN = {"order": ["meta"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny"}
"""The pin sent with every request: the maker's own endpoint, no fallback to another host, every parameter honoured
or the request refused, and no retention of the prompts by the host."""

CONCURRENCY = 8
"""Requests in flight at once, as the published attempts were drawn."""

TIMEOUT_S = 3000.0
"""The read timeout of one streamed answer, in seconds (a long trace at high effort)."""

MAX_ATTEMPTS = 7
"""Tries per request on a rate limit, a server error or a dropped connection, with a growing wait between them."""

STREAM = True
"""Answers were streamed and assembled; the plain response shape is what the answers file keeps."""


def wire_body(request: dict) -> dict:
    """The body as sent: the request row's body with the pin, the usage accounting and the streaming flag."""
    b = dict(request["body"])
    b["provider"] = dict(PROVIDER_PIN)
    b["usage"] = {"include": True}
    if STREAM:
        b["stream"] = True
    return b


class OpenRouter(Provider):
    name = "openrouter"

    def card(self, name: str) -> Card:
        return CARDS[name]

    def build_request(self, rid: str, card: Card, message: str) -> dict:
        return {
            "custom_id": rid,
            "method": "POST",
            "url": ENDPOINT,
            "body": {"model": card.model, "messages": [{"role": "user", "content": message}], **card.params},
        }

    # --- the live cycle -------------------------------------------------------------------------------------------

    def _answers_dir(self) -> pathlib.Path:
        d = pathlib.Path(os.environ.get("OPENROUTER_ANSWERS_DIR") or pathlib.Path.cwd() / "openrouter-answers")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _headers(self) -> dict:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def submit(self, requests: List[dict], card: Card, label: str) -> str:
        """Send the requests now and keep their answers; the returned id names the answers file."""
        import httpx

        answers = self._answers_dir() / f"{label}.jsonl"
        if answers.exists():
            raise RuntimeError(f"{answers} already holds answers; an answers file is never rewritten")
        rows = []
        with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=30.0), headers=self._headers()) as client, \
                ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            for row in pool.map(lambda r: _answer(client, r), requests):
                rows.append(row)
        with open(answers, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return f"answers:{answers}"

    def status(self, batch_id: str) -> str:
        return "ended" if pathlib.Path(batch_id.split(":", 1)[1]).exists() else "failed"

    def results(self, batch_id: str) -> Iterable[Result]:
        for line in open(batch_id.split(":", 1)[1], encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("error"):
                yield Result(row["custom_id"], ok=False, error=row["error"])
                continue
            choice = row["response"]["choices"][0]
            msg = choice["message"]
            yield Result(
                row["custom_id"], ok=True, text=msg.get("content") or "",
                finish_reason=_finish(choice.get("finish_reason"), msg.get("refusal")), model=row["response"].get("model", ""),
                usage=_usage(row["response"].get("usage") or {}), thinking_text=msg.get("reasoning") or None,
                provider={"finish_reason": choice.get("finish_reason"), "native_finish_reason": choice.get("native_finish_reason"),
                          "refusal": msg.get("refusal"), "host": row["response"].get("provider")},
            )


def _answer(client, request: dict) -> dict:
    """One request answered, with the retries the published attempts had; a terminal error is kept as a row."""
    body = wire_body(request)
    last: Optional[dict] = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return {"custom_id": request["custom_id"], "response": _stream(client, body) if STREAM else _plain(client, body)}
        except _Retry as e:
            last = {"status": e.status, "message": e.text}
            time.sleep(min(120.0, 5.0 * 2 ** attempt))
        except _Terminal as e:
            return {"custom_id": request["custom_id"], "error": {"status": e.status, "message": e.text}}
    return {"custom_id": request["custom_id"], "error": {"status": (last or {}).get("status"), "message": "gave up: " + str((last or {}).get("message"))}}


class _Retry(Exception):
    def __init__(self, status, text):
        super().__init__(f"HTTP {status}")
        self.status, self.text = status, text


class _Terminal(_Retry):
    pass


def _raise_for(status: int, text: str):
    if status == 429 or status >= 500:
        raise _Retry(status, text[:300])
    raise _Terminal(status, text[:300])


def _plain(client, body: dict) -> dict:
    try:
        r = client.post(BASE_URL + "/chat/completions", json=body)
    except Exception as e:  # a dropped connection is retried like a server error
        raise _Retry(0, str(e)[:300])
    if r.status_code >= 400:
        _raise_for(r.status_code, r.text)
    return r.json()


def _stream(client, body: dict) -> dict:
    """One streamed answer assembled into the plain response shape; an error object mid-stream is an error."""
    text, reasoning, refusal = [], [], None
    finish = native = model = host = rid = None
    usage = None
    try:
        with client.stream("POST", BASE_URL + "/chat/completions", json=body) as r:
            if r.status_code >= 400:
                _raise_for(r.status_code, r.read().decode("utf-8", "replace"))
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    e = chunk["error"]
                    code = int(e["code"]) if str(e.get("code") or "").isdigit() else 500
                    _raise_for(code, json.dumps(e))
                model = chunk.get("model") or model
                host = chunk.get("provider") or host
                rid = chunk.get("id") or rid
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for c in chunk.get("choices") or []:
                    d = c.get("delta") or {}
                    if d.get("content"):
                        text.append(_content_text(d["content"]))
                    if d.get("reasoning"):
                        reasoning.append(d["reasoning"])
                    elif d.get("reasoning_content"):
                        reasoning.append(d["reasoning_content"])
                    if d.get("refusal"):
                        refusal = (refusal or "") + d["refusal"]
                    if c.get("finish_reason"):
                        finish = c["finish_reason"]
                    if c.get("native_finish_reason"):
                        native = c["native_finish_reason"]
    except _Retry:
        raise
    except Exception as e:  # a connection dropped mid-stream is retried
        raise _Retry(0, str(e)[:300])
    return {"id": rid, "model": model, "provider": host, "usage": usage,
            "choices": [{"message": {"content": "".join(text), "reasoning": "".join(reasoning), "refusal": refusal},
                         "finish_reason": finish, "native_finish_reason": native}]}


def _content_text(c) -> str:
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def _finish(finish_reason, refusal) -> str:
    if refusal:
        return "refusal"
    return {"length": "length", "content_filter": "refusal"}.get(finish_reason or "", "stop")


def _usage(u: dict) -> dict:
    return {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
            "reasoning_tokens": ((u.get("completion_tokens_details") or {}).get("reasoning_tokens"))}

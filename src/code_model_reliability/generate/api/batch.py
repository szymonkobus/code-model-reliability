"""The batch cycle every provider runs through: build, submit, status, fetch, resubmit, finalize.

State lives in one directory per arm and set (``--state``): ``requests.jsonl`` (every request, one per attempt),
``state.json`` (the batches submitted and whether each was fetched), ``submitted.txt`` (request ids in flight),
``results.jsonl`` (one row per answered request, appended at fetch, deduplicated by request id) and
``errored.jsonl`` (requests the provider could not serve, rewritten at each fetch). Finalize reads the ledger and
writes the stage's output files (``records``) in task order and attempt order, through the current extractor;
it refuses to write while a request is unanswered unless told to allow a partial set.

A request id names its task and attempt: the task id with every character outside ``[A-Za-z0-9_-]`` replaced by
``_``, then ``__s`` and the attempt index with three digits; an id longer than the providers' 64-character limit
is cut and given an eight-hex-digit digest of the task id so it stays unique and stable across resubmissions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, Iterable, List, Optional

from .. import extract as X
from .. import prompts as P
from .. import settings as S
from ..records import AttemptWriter, GenerationRecord, today
from ..taskset import set_sha256

REQUEST_ID_LIMIT = 64
"""The longest request id the providers accept."""


def request_id(task_id: str, attempt: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)
    suffix = f"__s{attempt:03d}"
    if len(base) + len(suffix) > REQUEST_ID_LIMIT:
        digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:8]
        base = base[: REQUEST_ID_LIMIT - len(suffix) - 9] + "-" + digest
    return base + suffix


class Result:
    """One answered request, provider-neutral."""

    def __init__(self, request_id: str, ok: bool, text: str = "", finish_reason: str = "stop", model: str = "",
                 usage: Optional[dict] = None, thinking_text: Optional[str] = None, error: Optional[dict] = None,
                 provider: Optional[dict] = None):
        self.request_id = request_id
        self.ok = ok
        self.text = text
        self.finish_reason = finish_reason
        self.model = model
        self.usage = usage or {}
        self.thinking_text = thinking_text
        self.error = error
        self.provider = provider or {}

    def row(self) -> dict:
        return {
            "request_id": self.request_id, "text": self.text, "finish_reason": self.finish_reason,
            "model": self.model, "usage": self.usage, "thinking_text": self.thinking_text, "provider": self.provider,
        }


class Provider:
    """What a provider module supplies to the cycle."""

    name = ""
    one_model_per_batch = False

    def card(self, name: str) -> "Card":
        raise NotImplementedError

    def build_request(self, rid: str, card: "Card", message: str) -> dict:
        raise NotImplementedError

    def submit(self, requests: List[dict], card: "Card", label: str) -> str:
        raise NotImplementedError

    def status(self, batch_id: str) -> str:
        """``in_progress``, ``ended`` or ``failed``."""
        raise NotImplementedError

    def results(self, batch_id: str) -> Iterable[Result]:
        raise NotImplementedError


class Card:
    """A provider card: the arm, the model string sent, the request parameters, and the form."""

    def __init__(self, arm: str, model: str, params: dict, form: str, temperature_label: str, note: str = ""):
        self.arm = arm
        self.model = model
        self.params = params
        self.form = form
        self.temperature_label = temperature_label
        self.note = note

    def output_limit(self) -> Optional[int]:
        for key in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
            if key in self.params:
                return self.params[key]
        return None


def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class BatchRun:
    def __init__(self, provider: Provider, card: Card, state_dir: str):
        self.provider = provider
        self.card = card
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)

    # --- files -------------------------------------------------------------------------------------------------

    def _path(self, name: str) -> str:
        return os.path.join(self.state_dir, name)

    def load_state(self) -> dict:
        p = self._path("state.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return {"batches": []}

    def save_state(self, state: dict) -> None:
        tmp = self._path("state.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, self._path("state.json"))

    def answered_ids(self) -> set:
        return {r["request_id"] for r in _read_jsonl(self._path("results.jsonl"))}

    def submitted_ids(self) -> set:
        p = self._path("submitted.txt")
        if not os.path.exists(p):
            return set()
        with open(p, encoding="utf-8") as fh:
            return set(fh.read().split())

    # --- the cycle -----------------------------------------------------------------------------------------------

    def build(self, tasks: Dict[str, dict], attempts: int, task_set_name: str, task_set_sha: Optional[str] = None) -> int:
        """One request per task and attempt, in task order; ``meta.json`` records the set and the card."""
        requests = []
        for task_id, task in tasks.items():
            message = P.api_user_message(task["prompt"])
            for attempt in range(attempts):
                requests.append(self.provider.build_request(request_id(task_id, attempt), self.card, message))
        with open(self._path("requests.jsonl"), "w", encoding="utf-8") as fh:
            for r in requests:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        meta = {
            "arm": self.card.arm, "provider": self.provider.name, "model": self.card.model, "params": self.card.params,
            "form": self.card.form, "task_set": task_set_name, "task_set_sha256": task_set_sha or set_sha256(tasks),
            "n_tasks": len(tasks), "attempts_per_task": attempts, "requests": len(requests),
            "task_ids": list(tasks), "built": today(),
        }
        with open(self._path("meta.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
        return len(requests)

    def meta(self) -> dict:
        with open(self._path("meta.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def submit(self, batch_limit: int = S.API_BATCH_LIMIT, note: str = "initial", max_batches: Optional[int] = None) -> List[str]:
        """Every request not yet answered and not in flight, in batches of at most ``batch_limit``."""
        requests = _read_jsonl(self._path("requests.jsonl"))
        done = self.answered_ids() | self.submitted_ids()
        todo = [r for r in requests if _rid(r) not in done]
        state = self.load_state()
        ids = []
        for i in range(0, len(todo), batch_limit):
            if max_batches is not None and len(ids) >= max_batches:
                break
            chunk = todo[i : i + batch_limit]
            batch_id = self.provider.submit(chunk, self.card, f"{self.card.arm}-{note}-{len(state['batches'])}")
            state["batches"].append({"id": batch_id, "n": len(chunk), "note": note, "fetched": False})
            self.save_state(state)
            with open(self._path("submitted.txt"), "a", encoding="utf-8") as fh:
                fh.write("".join(_rid(r) + "\n" for r in chunk))
            ids.append(batch_id)
        return ids

    def status(self) -> List[dict]:
        return [{"id": b["id"], "note": b["note"], "n": b["n"], "status": self.provider.status(b["id"])}
                for b in self.load_state()["batches"]]

    def fetch(self) -> dict:
        """Results of every ended batch appended to the ledger; errored requests listed for resubmission."""
        state = self.load_state()
        seen = self.answered_ids()
        n_new = n_err = 0
        errored = []
        with open(self._path("results.jsonl"), "a", encoding="utf-8") as out:
            for b in state["batches"]:
                if b.get("fetched"):
                    continue
                status = self.provider.status(b["id"])
                if status == "in_progress":
                    continue
                for res in self.provider.results(b["id"]):
                    if not res.ok:
                        n_err += 1
                        errored.append({"request_id": res.request_id, "error": res.error, "batch": b["id"]})
                        continue
                    if res.request_id in seen:
                        continue
                    row = res.row()
                    row["batch"] = b["id"]
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    seen.add(res.request_id)
                    n_new += 1
                b["fetched"] = True
                b["status"] = status
                self.save_state(state)
        if errored:
            with open(self._path("errored.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps(e) + "\n" for e in errored))
        return {"new": n_new, "errored": n_err, "answered": len(seen)}

    def resubmit(self, batch_limit: int = S.API_BATCH_LIMIT) -> List[str]:
        """Every request without an answer, in flight or not, submitted again."""
        requests = _read_jsonl(self._path("requests.jsonl"))
        done = self.answered_ids()
        todo = [r for r in requests if _rid(r) not in done]
        if not todo:
            return []
        state = self.load_state()
        ids = []
        for i in range(0, len(todo), batch_limit):
            chunk = todo[i : i + batch_limit]
            batch_id = self.provider.submit(chunk, self.card, f"{self.card.arm}-resubmit-{len(state['batches'])}")
            state["batches"].append({"id": batch_id, "n": len(chunk), "note": "resubmit", "fetched": False})
            self.save_state(state)
            ids.append(batch_id)
        return ids

    def finalize(self, tasks: Dict[str, dict], out_dir: str, extractor_name: str = "v2", allow_partial: bool = False) -> dict:
        """The ledger written as the stage's output: ``samples.jsonl`` through the extractor, ``raw.jsonl`` with
        the provider's answer, ``generation.json`` with the card. Every task in the set gets its attempts in order;
        a missing attempt stops the write unless ``allow_partial``."""
        meta = self.meta()
        results = {r["request_id"]: r for r in _read_jsonl(self._path("results.jsonl"))}
        extractor = X.extract if extractor_name == "v2" else X.harness_sanitize
        missing = []
        models = set()
        counts = {"refusal": 0, "length": 0, "empty": 0}
        for task_id in meta["task_ids"]:
            for attempt in range(meta["attempts_per_task"]):
                if request_id(task_id, attempt) not in results:
                    missing.append((task_id, attempt))
        if missing and not allow_partial:
            raise RuntimeError(f"{len(missing)} attempts have no answer yet (first {missing[:3]}); fetch or resubmit first")
        os.makedirs(out_dir, exist_ok=True)
        if os.path.exists(os.path.join(out_dir, "raw.jsonl")):
            raise RuntimeError(f"{out_dir} already holds attempts; a finalized run is never rewritten")
        card = self.card
        record = GenerationRecord(
            arm=card.arm, task_set=meta["task_set"], task_set_sha256=meta["task_set_sha256"], n_tasks=meta["n_tasks"],
            attempts_per_task=meta["attempts_per_task"], model_id=card.model, model_revision=None,
            form=card.form, protocol="api-message", protocol_version="", backend=self.provider.name, prompt_style="api-message",
            sampling={k: v for k, v in card.params.items() if k in ("temperature", "top_p", "top_k")} | {"n": meta["attempts_per_task"], "provider_default": "temperature" not in card.params},
            output_limit=card.output_limit(),
            thinking_budget=(card.params.get("thinking") or {}).get("budget_tokens") if isinstance(card.params.get("thinking"), dict) else None,
            answer_budget=None, max_model_len=None,
            stops=list(card.params.get("stop_sequences", [])), harness_commit=S.HARNESS_COMMIT, instruction=S.INSTRUCTION_PREFIX,
            extractor={"name": extractor_name, "stamp": X.CURRENT_STAMP if extractor_name == "v2" else "harness",
                       "logic_sha256": X.logic_sha256() if extractor_name == "v2" else None},
            pins={"harness": S.HARNESS_COMMIT}, seed=None, started=meta["built"],
            notes={"card": card.params, "card_note": card.note, "batches": [b["id"] for b in self.load_state()["batches"]]},
        )
        record.write(out_dir)
        with AttemptWriter(out_dir) as writer:
            for task_id in meta["task_ids"]:
                task = tasks[task_id]
                for attempt in range(meta["attempts_per_task"]):
                    r = results.get(request_id(task_id, attempt))
                    if r is None:
                        continue
                    text = r["text"] or ""
                    models.add(r.get("model") or "")
                    fr = r.get("finish_reason") or "stop"
                    if fr in counts:
                        counts[fr] += 1
                    if not text.strip():
                        counts["empty"] += 1
                    writer.write(
                        task_id, attempt, extractor(text, task["entry_point"]), text, fr,
                        tokens=(r.get("usage") or {}).get("output_tokens"),
                        think_text=r.get("thinking_text"),
                        provider={"model": r.get("model"), "usage": r.get("usage"), "batch": r.get("batch"), **(r.get("provider") or {})},
                    )
        record.finished = today()
        record.notes["models_served"] = sorted(m for m in models if m)
        record.notes["counts"] = counts
        record.notes["missing"] = len(missing)
        record.write(out_dir)
        return {"written": len(results), "missing": len(missing), "models_served": sorted(models), **counts}


def _rid(request: dict) -> str:
    return request.get("custom_id") or request.get("key")

"""A deterministic stand-in for a model, for the tests and the end-to-end smoke run.

Given a task and an attempt index it returns a reply in the shape a chat model writes: the task's reference
solution in a Python code block, or a wrong program under the same function name. Whether an attempt is wrong is
decided by a seeded hash of the task id and the attempt index against a per-task failure probability that is itself
seeded from the task id, so a fixture set yields cells with different failure counts and the same run twice yields
the same attempts. No model, no network, no randomness beyond the seed.

Reads a task's prompt, entry point and canonical solution. Writes nothing.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List


def _unit(*parts: object) -> float:
    """A number in [0, 1) derived from the parts, stable across runs and machines."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _wrong_program(entry_point: str) -> str:
    return f"def {entry_point}(*args, **kwargs):\n    return None\n"


class StandInModel:
    """``generate(task, attempts)`` returns one reply per attempt, each a code block with the reference solution or
    a wrong program; ``finish_reason`` is always ``stop``."""

    def __init__(self, seed: int = 0, failure_scale: float = 1.0):
        self.seed = seed
        self.failure_scale = failure_scale

    def failure_probability(self, task_id: str) -> float:
        """The task's own failure probability, between 0 and ``failure_scale``: easy tasks near 0, hard ones near 1."""
        return self.failure_scale * _unit("task", self.seed, task_id)

    def is_wrong(self, task_id: str, attempt: int) -> bool:
        return _unit("attempt", self.seed, task_id, attempt) < self.failure_probability(task_id)

    def reply(self, task: Dict, attempt: int) -> str:
        """The model's text for one attempt: a fenced code block holding the whole program."""
        if self.is_wrong(task["task_id"], attempt):
            body = _wrong_program(task["entry_point"])
        else:
            body = task["prompt"].rstrip("\n") + "\n" + task["canonical_solution"].rstrip("\n") + "\n"
        return f"```python\n{body}```\n"

    def generate(self, task: Dict, attempts: int, first_attempt: int = 0) -> List[dict]:
        return [
            {"text": self.reply(task, i), "finish_reason": "stop", "tokens": None}
            for i in range(first_attempt, first_attempt + attempts)
        ]


class StandInTokenizer:
    """A chat template in miniature, so the prompt code runs end to end without a model: turns are wrapped in
    ``<|user|>`` and ``<|assistant|>`` markers; the generation prompt opens the assistant turn, with an empty
    thinking block when thinking is off and an open one when it is on."""

    chat_template = "standin"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False, enable_thinking=None):
        out = "".join(f"<|{m['role']}|>\n{m['content']}<|end|>\n" for m in messages)
        if add_generation_prompt:
            out += "<|assistant|>\n"
            if enable_thinking is False:
                out += "<think>\n\n</think>\n\n"
            elif enable_thinking:
                out += "<think>\n"
        return out

    def encode(self, text, add_special_tokens=False):
        return text.split()


class StandInBackend:
    """The ``Backend`` interface over ``StandInModel``: the prompt is parsed back to its task by the task's entry
    point, which every prompt form carries in the signature; a thinking phase returns a short closed trace."""

    def __init__(self, tasks: Dict[str, Dict], seed: int = 0, failure_scale: float = 1.0):
        self.model = StandInModel(seed, failure_scale)
        self.tasks = tasks
        self.tokenizer = StandInTokenizer()
        self.calls = 0

    def _task_for(self, prompt: str) -> Dict:
        for task in self.tasks.values():
            if f"def {task['entry_point']}(" in prompt:
                return task
        raise KeyError("no task's entry point appears in the prompt")

    def generate(self, prompts, sampling):
        from .inference import Output

        self.calls += 1
        results = []
        for prompt in prompts:
            task = self._task_for(prompt)
            outs = []
            for i in range(sampling.n):
                attempt = _unit("order", self.model.seed, prompt, self.calls, i)
                index = int(attempt * 10**6)
                if list(sampling.stop) == ["</think>"]:
                    text = f"thinking about {task['entry_point']}\n</think>"
                    outs.append(Output(text=text, finish_reason="stop", tokens=len(text.split())))
                    continue
                reply = self.model.reply(task, index)
                if prompt.rstrip().endswith("```python") or prompt.endswith("```python\n"):
                    reply = reply.split("```python\n", 1)[1].split("```", 1)[0]  # the fence is already open
                elif prompt.endswith(task["prompt"].rstrip("\n") + "\n") and "<|" not in prompt:
                    body = task["canonical_solution"] if not self.model.is_wrong(task["task_id"], index) else "    return None\n"
                    reply = body  # the completion form: the body continues the bare prompt
                outs.append(Output(text=reply, finish_reason="stop", tokens=len(reply.split())))
            results.append(outs)
        return results

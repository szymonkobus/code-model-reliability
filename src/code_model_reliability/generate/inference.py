"""The inference back end: the one interface the generation code talks to, and its two implementations, the
inference engine on a GPU machine and the deterministic stand-in the tests use.

A back end takes prompts and sampling settings and returns, per prompt, a list of outputs with the text, why it
ended and how many tokens it holds. Loading the real back end imports the inference library and the model's
tokenizer, so it happens only when a back end is asked for.

Reads a model id (a repository id or a local directory). Writes nothing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from typing import List, Optional, Sequence

from . import settings as S


@dataclasses.dataclass
class Output:
    text: str
    finish_reason: str  # "stop" or "length" as the back end reports it
    tokens: Optional[int] = None  # output tokens, when the back end counts them


@dataclasses.dataclass
class Sampling:
    """What one generation request asks for."""

    n: int
    max_tokens: int
    temperature: float
    top_p: float = 1.0
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    stop: Sequence[str] = ()
    include_stop_in_output: bool = False
    presence_penalty: Optional[float] = None


class Backend:
    """``generate(prompts, sampling)`` returns one list of ``Output`` per prompt, ``sampling.n`` outputs each."""

    tokenizer = None

    def generate(self, prompts: List[str], sampling: Sampling) -> List[List[Output]]:
        raise NotImplementedError


def leg_seed(out_dir: str, task_source: Optional[str], model_id: str, job_id: Optional[str] = None) -> tuple[int, str]:
    """The sampling seed for one run when none is given: a 32-bit integer from the sha256 of what differs between
    runs by construction, joined with ``|``: the real path of the output directory, the sha256 (first sixteen
    hex digits) of the task file's bytes when the tasks come from a file, the model id, and the scheduler's job id
    when present. Two runs over the same shard then draw different streams, and a run restarted under a new job
    draws afresh; a seed given explicitly overrides this."""
    try:
        with open(task_source, "rb") as fh:  # type: ignore[arg-type]
            source_hash = hashlib.sha256(fh.read()).hexdigest()[:16]
    except (OSError, TypeError):
        source_hash = "no-task-file" if not task_source or not os.path.exists(str(task_source)) else "task-file-unreadable"
    job = job_id or os.environ.get("SLURM_JOB_ID") or "no-job"
    real = os.path.realpath(out_dir)
    text = f"{real}|{source_hash}|{model_id}|{job}"
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16), (
        f"derived from out={real!r} tasks_sha16={source_hash} model={model_id!r} job={job}"
    )


def needs_remote_code(model_id: str) -> bool:
    """Whether the model's repository ships its own loading code (custom tokenizer or config)."""
    return model_id.startswith(S.TRUST_REMOTE_CODE_FAMILIES)


class VllmBackend(Backend):
    """The inference engine as the attempts were produced: bfloat16 weights, chunked prefill on, prefix caching on
    for the runner paths, the context window and tensor-parallel degree from the protocol and the machine."""

    def __init__(
        self,
        model_id: str,
        max_model_len: int,
        seed: int,
        tensor_parallel: int = 1,
        prefix_caching: bool = True,
        trust_remote_code: Optional[bool] = None,
        gpu_memory_utilization: Optional[float] = None,
        enforce_eager: bool = False,
    ):
        from transformers import AutoTokenizer
        from vllm import LLM

        trust = needs_remote_code(model_id) if trust_remote_code is None else trust_remote_code
        self.model_id = model_id
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=trust)
        kwargs = dict(
            model=model_id,
            max_model_len=max_model_len,
            dtype=S.DTYPE,
            tensor_parallel_size=tensor_parallel,
            trust_remote_code=trust,
            enable_chunked_prefill=S.CHUNKED_PREFILL,
            enable_prefix_caching=prefix_caching,
            seed=seed,
        )
        if gpu_memory_utilization is not None:
            kwargs["gpu_memory_utilization"] = gpu_memory_utilization
        if enforce_eager:
            kwargs["enforce_eager"] = True
        self.llm = LLM(**kwargs)

    def generate(self, prompts: List[str], sampling: Sampling) -> List[List[Output]]:
        from vllm import SamplingParams

        params = dict(
            n=sampling.n,
            max_tokens=sampling.max_tokens,
            temperature=sampling.temperature,
            top_p=sampling.top_p,
            stop=list(sampling.stop) or None,
            include_stop_str_in_output=sampling.include_stop_in_output,
        )
        if sampling.top_k is not None:
            params["top_k"] = sampling.top_k
        if sampling.min_p is not None:
            params["min_p"] = sampling.min_p
        if sampling.presence_penalty is not None:
            params["presence_penalty"] = sampling.presence_penalty
        results = self.llm.generate(prompts, SamplingParams(**params), use_tqdm=False)
        return [
            [Output(text=o.text, finish_reason=o.finish_reason or "stop", tokens=len(o.token_ids)) for o in r.outputs]
            for r in results
        ]

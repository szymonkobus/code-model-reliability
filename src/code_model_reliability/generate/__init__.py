"""A model answers every task of a set many times.

One command for every model: the task set, the number of attempts per task and the protocol (the form, plain,
thinking or completion; the sampling; the output limit and, for thinking, the budgets) are arguments; the prompt is
the harness's own instruct prompt at the pinned commit, so every model sees the same words. Back ends: the
inference engine on a GPU machine (``vllm``, for the plain and completion forms, and ``thinking`` for the two-phase
and single-phase thinking forms the harness's path cannot express), the three provider batch interfaces (``api``:
one build, submit, fetch, finalize cycle; keys from the environment only) and a deterministic stand-in for tests.
``extract`` is the one extractor, its version named by hash on every arm it produced.

Writes, per set and arm: ``samples.jsonl`` (the extracted program per attempt, in the harness's shape),
``raw.jsonl`` (the model's text as returned, one shape for every back end) and ``generation.json`` (every setting
the attempts were produced under). Reads the task set and ``data/runs/registry/protocols.tsv``.
"""

from .command import main

__all__ = ["main"]

"""Every setting that can move a verdict, kept as one record the judge writes beside its verdicts.

A judging-settings record names: the harness and the commit it is pinned to; the rule for the time limit of each
test; the cap on the whole test set of one attempt; the memory limit of the judged process; the leading-imports
rule and its version; the typing prelude for the completion form; the comparison rule; the plus-input filter; the
typed-inputs rule; how the reference outputs are computed; and the number of evaluator workers. Two records
stand behind the published verdicts: ``CURRENT`` is what every verdict this package produces carries, ``CAPPED`` is the same with the whole-suite
cap the earlier wave 2 files were judged under, and ``STOCK_EVALUATOR`` is what the verdict files judged by the
harness's own evaluator carry. A record's id is a
hash of its values, so judgings under equal settings share an id and the land stage can tell them apart from
the rest. Reads nothing; ``describe`` writes a record as the ``judging.json`` the contract names.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

HARNESS_NAME = "evalplus"
HARNESS_COMMIT = "26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"
HARNESS_VERSION = "0.4.0.dev44"


@dataclasses.dataclass(frozen=True)
class JudgingSettings:
    """The settings of one judging; every field can move a verdict and every field is written beside the verdicts."""

    name: str
    # The time limit of one test is max(time_limit_floor_s, time_limit_factor x the reference's own time on that
    # test). The floor is what decides on nearly every test: a reference takes milliseconds.
    time_limit_floor_s: float
    time_limit_factor: float
    # The whole test set of one attempt is killed after the sum of the tests' limits plus one second (plus another
    # second when every test is run rather than stopping at the first failure); ``set_cap_s`` caps that sum where a
    # record carries one (``None`` means the summed limits stand alone). An attempt killed this way has the status
    # ``timeout`` on that suite.
    set_cap_s: float | None
    # The address-space limit of the judged process, in GiB, over and above what the interpreter already holds when
    # the process is forked (see ``memory_limit_bytes``). A process over the limit fails on a MemoryError.
    memory_gib: float
    # The leading-imports rule: a task prompt's leading import lines are placed before the judged program (with the
    # version of the rule named), so a program that relies on the prompt's imports is not failed for them. None
    # means the program is judged as written.
    leading_imports: str | None
    # Whether the leading-imports rule is applied by the judge when it loads an attempt (``at-load``) or was applied
    # to the samples before they reached the judge (``before-judging``); the judged program is the same either way.
    leading_imports_applied: str
    # The typing prelude for the completion form (a base model continuing the prompt): a line importing the common
    # typing names is placed first, so a trailing block with typed signatures does not fail the module at import.
    typing_prelude: str | None
    # The comparison rule between an attempt's output and the expected output; see ``compare``.
    comparison: str
    # Whether the plus inputs that carry a boolean where every base example carries an integer are removed from the
    # extended tests of the tasks listed in ``data/judge/plus_filter.json``.
    plus_filter: bool
    # Whether test inputs are reconstructed with their declared types (tuples, sets, complex numbers) where a task
    # declares them (the harness's own rule for its tasks; ``data/judge/typed_inputs.json`` for the written tasks).
    typed_inputs: bool
    # How the expected outputs are computed: ``isolated`` runs each reference in a forked child, so a reference's
    # process-global side effects (a raised recursion limit, a changed decimal context) cannot reach the judge.
    reference: str
    # Evaluator workers; a load setting, kept on the record because a loaded node slows the judged code against
    # time limits measured on a quiet one.
    workers: int

    def values(self) -> dict[str, Any]:
        """The fields that define the settings: everything but the name and the load fields."""
        return {k: v for k, v in dataclasses.asdict(self).items() if k != "name" and k not in LOAD_FIELDS}

    @property
    def id(self) -> str:
        """Twelve hex digits of the sha256 over the values; equal settings give equal ids. The load fields
        (``workers``) are recorded beside the verdicts but do not enter the id: they change how long a judging
        takes and how a loaded node meets the limits, not what the settings are."""
        text = json.dumps(self.values(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


LOAD_FIELDS = ("workers",)


CURRENT = JudgingSettings(
    name="current",
    time_limit_floor_s=15.0,
    time_limit_factor=4.0,
    set_cap_s=None,
    memory_gib=8.0,
    leading_imports="leading-imports-v4.1-self-shadowing-refined",
    leading_imports_applied="at-load",
    typing_prelude="typing-prelude-v5",
    comparison="normalised-values, float tolerance 1e-9, canonical stdout",
    plus_filter=True,
    typed_inputs=True,
    reference="isolated",
    workers=4,
)
"""What every verdict this package produces carries. The floor of 15 s dominates every reference time measured
(the slowest reference known takes 3.49 s, 4 x 3.49 s < 15 s); the whole suite's limit is the sum of its tests'
limits and nothing shorter, so a program slow on many tests is judged to the end of them (the judge that produced
the published verdicts runs a 300 s default with the summed limit on every task whose summed limits exceed it,
which comes to the same verdicts); 8 GiB is what one judge worker can hold on the nodes used, beside three
others; the comparison and import rules are the ones in ``compare`` and ``leading_imports``. ``workers`` is the block's
value, four on most judgings, two to sixteen on others."""

CAPPED = JudgingSettings(
    name="capped-300",
    time_limit_floor_s=15.0,
    time_limit_factor=4.0,
    set_cap_s=300.0,
    memory_gib=8.0,
    leading_imports="leading-imports-v4.1-self-shadowing-refined",
    leading_imports_applied="at-load",
    typing_prelude="typing-prelude-v5",
    comparison="normalised-values, float tolerance 1e-9, canonical stdout",
    plus_filter=True,
    typed_inputs=True,
    reference="isolated",
    workers=4,
)
"""The same settings with a 300 s cap on an attempt's whole suite on every task: what a wave 2 verdict file carries
where a task whose summed limits exceed 300 s was judged at the cap rather than to its summed limits. A verdict
file under this record is read as it stands; the task's judging under the summed limits is a newer judging that
wins under ``land.judgings``."""

STOCK_EVALUATOR = JudgingSettings(
    name="stock-evaluator",
    time_limit_floor_s=4.0,
    time_limit_factor=4.0,
    set_cap_s=60.0,
    memory_gib=12.0,
    leading_imports="leading-imports-v2-builtins-restored",
    leading_imports_applied="before-judging",
    typing_prelude=None,
    comparison="stock exact comparison",
    plus_filter=True,
    typed_inputs=True,
    reference="in-process",
    workers=8,
)
"""What the verdict files judged by the harness's own evaluator carry: its default time limits (a 4 s floor, a
60 s set cap), 12 GiB for the judged process, the imports rule's second version applied to the samples before
judging, the plus-input filter applied by serving filtered task files, and the harness's own comparison. The
corrections later applied to those files (the float tolerance, the typing cleaning) are companion files beside
them, composed by the land stage (``land.corrections``), never rewrites."""

RECORDS = {s.name: s for s in (CURRENT, CAPPED, STOCK_EVALUATOR)}


def memory_limit_bytes(settings: JudgingSettings) -> int:
    """The address-space limit for a judged process: the record's GiB plus what this interpreter already holds.

    The limit is set in the judged child after it is forked from a judge worker, and an address-space limit counts
    the interpreter's own mappings, so the budget the judged program gets is the record's figure only when the
    parent's current size is added. The total is capped at the machine's memory, as the harness does.
    """
    residual = 0
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmSize:"):
                    residual = int(line.split()[1]) * 1024
                    break
    except OSError:
        residual = 0
    limit = int(settings.memory_gib * 2**30) + residual
    try:
        import os

        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        limit = min(limit, total)
    except (ValueError, OSError, AttributeError):
        pass
    return limit


def describe(settings: JudgingSettings, **facts: Any) -> dict[str, Any]:
    """The ``judging.json`` record: the settings, their id, the harness, and the facts of one judging the caller adds
    (the task set and its hash, the number of tasks and attempts, the attempts the time limit stopped per task)."""
    record = {
        "settings_id": settings.id,
        "settings": {"name": settings.name, **settings.values(), **{k: getattr(settings, k) for k in LOAD_FIELDS}},
        "harness": {"name": HARNESS_NAME, "commit": HARNESS_COMMIT, "version": HARNESS_VERSION},
    }
    record.update(facts)
    return record


def load(path) -> dict[str, Any]:
    """Read a ``judging.json`` written by ``describe``."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

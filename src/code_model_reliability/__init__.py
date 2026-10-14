"""Capability and reliability of code models.

The project measures two numbers per model on one scale of task difficulty: capability, the difficulty at
which the model's fitted failure rate crosses one half (D50), and reliability, the difficulty at which it
crosses one in a hundred (D99). Both are read from a Bayesian failure-against-difficulty curve fitted to many
judged attempts per task on two task sets, wave 1 and wave 2, together wave 1+2.

The package is the pipeline in the order the data flows, one sub-package per stage:

- ``tasks``: the task sets of record and their provenance.
- ``generate``: a model answers every task many times; the answers are extracted into the judge's shape.
- ``judge``: every attempt is run against the task's tests; a verdict per attempt.
- ``land``: verdicts become cells (failures out of attempts per model and task) and the model registry.
- ``fit``: the difficulty scale, the failure curve per model, its gates and its two crossings.
- ``plot``: the two figures and the two site pages, from the published tables.

``docs/data-contract.md`` names every file that passes between the stages and its shape.
"""

__version__ = "2.0.0.dev0"

STAGES = ("tasks", "generate", "judge", "land", "fit", "plot")

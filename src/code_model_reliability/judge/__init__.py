"""Every attempt is run against its task's tests; a verdict per attempt.

The judge is the harness's evaluator at its pinned commit, written out as one evaluation loop over the harness's
sandbox primitives, with every setting that can move a verdict named in one record and written beside the
verdicts: the time limit of each test and the cap on the whole set, the memory limit, the leading-imports rule (a
task prompt's leading import lines are placed before the judged program), the typing prelude for the completion
form, the comparison rule (values normalised to plain builtins, a float tolerance, the canonical form of a
program's output text), the plus-input filter and the typed inputs, and how the reference outputs are computed.

``per_test`` records the outcome of every test for a failing attempt, where a verdict says only pass or fail.

Writes, per set and arm: ``verdicts.json`` (the harness's own shape: per task, per attempt, pass or fail on the
base tests and on the extended tests), ``judging.json`` (the settings and the facts of the judging) and, when
asked, ``per_test.jsonl``. Reads the samples the generate stage wrote and the task set.
"""


def main(argv=None) -> int:
    from .evaluate import main as judge_main

    return judge_main(argv)

# Rare failures: what goes wrong when a model fails a task it otherwise solves

## The question

Reliability is read where failures are rare: D99 is the difficulty at which one attempt in a hundred fails. A case
is one arm on one wave 1 task that it solves most of the time but fails 1 to 10 times in 128 attempts. Are those
failures the model's own, or the tests' and the judge's? And do they repeat the same way, or vary from attempt to
attempt?

## The answer

Every such case of 51 arms was bundled with its failing attempts and read, one case at a time, and given one
category. Over the 2,930 cases on record:

| category | cases | share of cases | share of failing attempts |
|---|---|---|---|
| edge-case logic (a small slip: an empty or negative input, an off-by-one, a tie) | 1,939 | 66% | 67% |
| wrong approach (a wrong algorithm or a misread task) | 489 | 17% | 18% |
| format or extraction (the code was right; the step that takes it out of the reply lost it) | 231 | 8% | 9% |
| malformed code | 131 | 4.5% | 2.6% |
| truncated or incomplete | 55 | 1.9% | 1.3% |
| test or judge at fault (confirmed case by case) | 42 | 1.4% | 1.4% |
| time limit | 32 | 1.1% | 1.1% |
| other | 11 | 0.4% | 0.2% |

By failing attempts, 89.6% are the model's own doing, 9.0% were lost by the extraction step and 1.4% trace to the
tests or the judge. The failing attempts are not flaky: an arm that fails a task repeatedly almost always makes the
same wrong choice every time (one misreading or one self-imposed convention), which the per-test outcome vectors
confirm (below). Of the 501 tasks the cases touch, 80 (16%) carry a defect label from the audit; those tasks sit in the
reliability tail, among the almost-solved tasks just above an arm's D99.

## What depends on it

The cases that traced to the test setup were confirmed one by one and each became a rule of the pipeline:

- a float result one rounding step from the expected float was failed by a type-strict comparison before any
  tolerance applied: the comparison rule normalises returned values to plain builtins and compares a float meeting a
  number within a relative tolerance (`judge/compare.py`);
- a judging child inherited the parent process's consumed recursion budget and memory, failing correct deep recursion:
  every reference runs in a forked child of its own, the memory limit is the program's own and is named in the record
  of settings (`judge/settings.py`);
- an answer whose first statement is `from __future__ import annotations` failed at import once the task's leading
  import lines were placed before it: the leading-imports rule hoists such lines first (`judge/leading_imports.py`);
- the extractor dropped a decorator above the kept definition, and a bare code fence the model opened for a formula
  stopped generation before the code: the extractor's later version and a redraw of the cut attempts under a stop set
  without the bare fence (`generate/extract.py`, `generate/protocols.py`);
- a tolerant comparison over million-element outputs ran past the whole-suite limit and scored completed attempts as
  timeouts: equality is tried exactly first and the tolerant path only where it fails (`judge/compare.py`);
- an expected output computed in floating point above 2^53 was wrong on integer-domain inputs: an audit label on the
  task and a screen that recomputes expected outputs with exact arithmetic where the domain permits (`docs/tasks.md`).

The question whether failures repeat is what the per-test outcome vector answers: every failing attempt re-run against
the task's whole test set gives one letter per test, two attempts with the same string failed the same tests the same
way, and the entropy of the strings per arm and task measures how consistently an arm fails (`judge/per_test.py`,
`land/per_test.py`).

## What is here

- `cases.csv`: one row per case (2,930): the arm id of record, the task, the failures of 128, the category, and the
  task's audit label when the case was read. The notes behind the categories quote model replies and do not ship.
  The table is the study's whole record; the script reports any arm of it that the published fit of a build does not
  carry.
- `recompute.py` recounts the table above from `cases.csv`, rebuilds the frame (1 to 10 failures of 128 on a wave 1
  task) from the published fit's `cells.csv` for the arms in it and reports how the two agree (a case leaves the range
  when a later correction moves its cell), and reads the cases' tasks against the published labels.

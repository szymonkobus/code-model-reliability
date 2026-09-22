# The new tasks: how wave 2 and wave 2 parked were built

Wave 1, the kept tasks of two public Python benchmarks, is small and mostly easy for current models, so it shows little
of where a model's ability runs out and, at one failure in a hundred, little of how reliable it is on easy work. The new
tasks were built to cover the whole difficulty range at the same one-function, executable-test shape, so that every arm
can be measured with the same judge. They form two sets of record: **wave 2** (869 tasks), the new tasks
in the published fits, and **wave 2 parked** (893 tasks), run with the same protocol but kept out of the
fits for now. The split is fixed by a frozen membership list (`tasks/sets.json`): the two easier quarters of the new
tasks in the difficulty order at the time of the split are wave 2, the rest is wave 2 parked; wave 2 never includes the
parked tasks.

## Sources

Tasks entered through three channels; `tasks/certificates/certificates.jsonl` names the channel and upstream of every
task.

- **Imported** from public datasets and converted to the one-function, executable-test shape: competitive-programming
  problems (Codeforces through two datasets), interview-style problems (through two LeetCode-derived datasets, whose
  text this repository does not redistribute; see `DATA-LICENSE.md`), and two Apache-licensed benchmark sets.
- **Derived**: paraphrase twins of wave-1 tasks, re-worded copies whose statement changes and whose tests do not, to
  measure whether a model's success depends on the wording it has seen.
- **Written for this project**: targeted tasks aimed at specific difficulty bands, and an easy tail of very simple tasks
  to place the reliability crossing.

## Acquisition and conversion

`tasks/pipeline/acquire/stage_ab/` holds what is included of the pipeline. `acquisition/fetch_candidates.py` fetches
upstream rows (with column projection, so no full dataset download); `acquisition/bench_import.py` imports rows of the
benchmark datasets; `acquisition/convert.py` rewrites a stdin/stdout problem with an accepted human solution into a
single-turn function-level task: the prompt is the signature `solve(input_data: str) -> str` with the statement as its
docstring, the reference is the human solution inlined with its input and output redirected, and the tests are the
official test cases with their expected outputs. A candidate converts only if some reference reproduces the official
expected output exactly on every kept test, in a sandboxed subprocess with resource limits. Every candidate ends with a
status: converted, needs human review with a reason, or rejected with a reason.

## Screening and certification

Converted candidates pass through screens (`screens.py`, `acquisition/screens_check.py`): input and output purity, a duplicate
check against wave 1 and against the other new tasks, a reference re-execution, and a timing floor for the judge. The
screens are tagged by stage in their docstrings: stage 0 screens check a task on its own (its reference, determinism, size,
timing, recursion depth, float tolerance, well-formedness, duplicates, degenerate tests and side effects), stage 1 screens
check the power of its tests (coverage, oracle), the stage 2/4 screen is behavioural (a task every strong model fails),
and stage A is the back-test driver (`backtest.py`) that runs the screens blind over the pool. The screens and the twin
checks (`tasks/pipeline/acquire/derived/tools/`) read the harness's task files from its cache under
`$EVALPLUS_HOME/.cache/evalplus/` (the home directory when the variable is unset) and run from the repository root.
Survivors are certified: a certificate records the task's content hash over its eight judged fields, its status, its
provenance and the audit label; a changed task is a new version with a new hash, and the certificate keeps the previous
hash, so every judged cell is tied to the exact content it was judged on. The certificates are in `tasks/certificates/`
(the README there defines the fields and the status values); the certification tools are not part of this import.

## Audit and labels

Every task was reviewed for defects independently of the models: a statement that contradicts its tests, an answer the
statement leaves unspecified, a test that depends on an unstated convention. Labels are recorded per task
(`tasks/labels/` for wave 1, the `audit_label` field of the certificates for the new tasks), and a task whose label
marks it unsound leaves the fits; `tasks/labels/README.md` lists the labels. Of wave 2, 861 tasks are kept
by the audit; of wave 2 parked, 885. Wave 1 went through the same audit, which is how its kept set of
431 tasks was chosen.

## What ships

Wave 2 (`tasks/wave2/`): 774 tasks as full text and 95 as identity and provenance only,
because their upstream does not permit republishing statements. Wave 2 parked (`tasks/wave2-parked/`):
654 as text and 239 as pointers. `tasks/rebuild_restricted.py` rebuilds and verifies
the pointer tasks from the upstream datasets against the certified content hashes. At the snapshot, 866 of
the 869 wave-2 tasks had judged cells in the published fit; a task is fitted from its cells, failures out
of attempts for every arm that ran it, at 32 to 256 attempts per task depending on the arm.

## Difficulty coverage

Task difficulty is estimated from the arm population (`docs/method.md`). The new tasks extend the range on both sides of
wave 1: the easy tail places the one-in-a-hundred crossing for most arms inside the observed range, and the contest
imports extend the hard end past the point where the strongest arms fail half the time; the parked set holds the hardest
half of the new tasks.

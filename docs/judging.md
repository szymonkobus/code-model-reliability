# Judging and landing

How an attempt becomes a verdict, and how verdicts become the cells the fits read. The code is
`src/code_model_reliability/judge/` and `land/`; the files between the stages are in `data-contract.md` § judge and
§ land; the terms are in `glossary.md`.

## What the judge does

Every attempt (one program a model wrote for one task) is run against the task's tests twice: on the **base
tests**, the examples the task came with, and on the **extended tests**, the larger set added to catch programs
the examples miss. On each suite the attempt gets a status: `pass` when every test's output counts as the
expected output, `timeout` when the whole suite was killed at its time cap, `fail` otherwise. An attempt
**passes** only when both statuses are `pass`.

The evaluator is the open-source harness's at the commit the package pins (`settings.HARNESS_COMMIT`), written
out as one evaluation loop over the harness's sandbox primitives, so that every setting that can move a verdict
is a named constant in `judge/settings.py` and is written beside the verdicts in `judging.json`. The expected
outputs come from the task's reference solution, run on every test in a process of its own; the reference's time
per test sets the test's limit.

Run it as:

```
cmr judge --tasks data/tasks/wave2/tasks-part-01.jsonl.gz --samples out/wave2/<arm>/samples.jsonl --out out/wave2/<arm> --per-test
cmr judge --tasks humaneval --samples out/wave1/<arm>/samples.jsonl --out out/wave1/<arm>
```

The first form reads a task file in the contract's shape; the second names one of the harness's own two task
sets, which the harness downloads to its cache on first use. `cluster/judge.sbatch` runs the same command as a
job array over arms.

## The settings, and why

`judge/settings.py` holds three records. `CURRENT` is what every verdict this package produces carries:

| setting | value | why |
|---|---|---|
| time limit per test | max(15 s, 4 × the reference's time on the test) | the floor decides on nearly every test: the slowest reference known takes 3.49 s; a slow correct program is not failed for the node's load |
| limit on one attempt's whole suite | the sum of the tests' limits + 1 s, no shorter cap | a program is judged to the end of its tests; a suite that still runs past the summed limits is killed and its status is `timeout`. The judge that produced the published verdicts runs a 300 s default and the summed limit on every task whose summed limits exceed it, the same verdicts; a file where such a task was judged at the cap carries the `CAPPED` record, and the task's judging under its summed limits wins under the land rules |
| memory limit of the judged process | 8 GiB, over the interpreter's own size | a program over the limit fails with a MemoryError rather than taking the node down; the budget is what the program itself may use |
| leading-imports rule | `leading-imports-v4.1-self-shadowing-refined` | a task prompt that opens with import lines is the program's environment; a correct program is not failed for not repeating them (details in `judge/leading_imports.py`) |
| typing prelude (completion form only) | `typing-prelude-v5` | a base model's continuation may leave a trailing block with typed signatures; the common typing names are imported first so the module does not fail at import |
| comparison rule | normalised values; float tolerance 1e-9; canonical stdout | equality is decided by builtin values, never by a method the program defined; a float meeting an integer compares within rounding; a program's output text is compared in the same canonical form the expected outputs were produced in (details in `judge/compare.py`) |
| plus-input filter | on | the extended tests that carry a boolean where every example carries an integer are removed on the tasks that list them (the record's `plus_inputs_removed`; for the wave 1 tasks `data/tasks/wave-1/plus_inputs_removed.json`) |
| typed inputs | on | test inputs are rebuilt as the tuples, sets and complex numbers the task declares (the harness's rule for its tasks and their copies; the record's `input_shapes` for the written ones) |
| reference isolation | each reference in a forked child | a reference's side effects on the process (a raised recursion limit, a changed decimal context) cannot reach the judge or the next reference |
| workers | 4 (the block's value; two to sixteen on some judgings) | a load setting, recorded beside the verdicts and outside the record's id; time limits measured on a quiet node are met differently on a loaded one |

`CAPPED` is `CURRENT` with the 300 s cap on an attempt's whole suite on every task, the record of a wave 2 file
where a task above the cap was judged at it. `STOCK_EVALUATOR` is what the verdict files judged by the harness's own evaluator carry: its default
limits (a 4 s floor, a 60 s cap), 12 GiB, the second version of the imports rule applied to the samples before
judging, the plus-input filter applied by serving filtered task files, and the harness's own comparison. The
corrections applied to those files afterwards (the float tolerance, the typing cleaning) are companion files
beside them.

One detail of the sandbox matters for anyone who executes model code from Python: `exec` compiles a program with
the calling module's `from __future__` flags, so a module that imports deferred annotations lets a program whose
signature names an undefined type pass where the harness fails it at definition. The judge's modules carry no such
import and compile every program with `dont_inherit`.

A record's id is twelve hex digits of the hash of its values, so two judgings under the same settings share an id;
every cell names the id of the judging its verdicts carry.

## Per-test outcomes

A verdict says pass or fail per suite. With `--per-test` the judge also writes `per_test.jsonl`: for every failing
attempt and suite, one letter per test in the suite's order:

| letter | meaning |
|---|---|
| `P` | the output counted as the expected output |
| `W` | the program returned, and its output did not count as the expected output |
| `T` | the test's time limit stopped the program |
| `E` | the program raised an exception on the test |
| `A` | the test was not run: the attempt stopped at an earlier failure, failed at definition, or was killed at the suite's limit |

Two attempts with the same outcome string failed the same tests in the same way; `land/per_test.py` counts the
distinct strings per arm and task, the share of the commonest, the collision probability and the entropy.

## What the land stage does

```
cmr land cells --arm-dir out/wave2/<arm> --arm <arm> --set wave2 --out results/wave2/<arm>
cmr land registry --arm-dirs out/wave2/* --arm-map data/runs/arm_map.tsv --names data/runs/registry/names.json --out data/runs/registry/arms.jsonl
```

A **cell** is one arm on one task: failures out of attempts, with the attempts the time limit stopped counted
apart and the judging settings id the verdicts carry. Three rules compose an arm's verdict files before they are
counted:

- **the newest judging of a task wins** (`land/judgings.py`): a re-judging is its own file beside the first,
  `verdicts.1.json`, `verdicts.2.json` and so on, each with its `judging.N.json`; task by task the newest judging
  that judged the task stands, and a re-judging is accepted only when it judged the same programs in the same
  order;
- **a correction never rewrites a judged file** (`land/corrections.py`): corrections are rows of `corrections.jsonl`
  beside the verdicts, each naming the attempt by the hash of the program text it holds, so a correction
  written against other verdicts is refused rather than applied;
- **a continuation is one attempt in two parts** (`land/corrections.py`): an answer the output limit cut, run on to
  completion and judged again, replaces the cut answer as the same attempt with the completed answer's verdict; the
  attempt count does not move.

`land/passk.py` recomputes pass@k from the verdicts with the unbiased estimator (`1 - C(n-c, k) / C(n, k)` per
task, the mean over tasks); `land/registry.py` builds the one list of arms from what the generate and judge stages
wrote beside each arm's samples, joined to the curated model map and the names of the trained models; `land/records.py`
reads the raw replies of every generation back end as one record shape.

The judged attempts of wave 1 ship: `results/per-attempt/wave1_<benchmark>.csv.gz` has one row per attempt of every
published arm on the wave 1 tasks the published fit has cells for (`arm`, `task_id`, `attempt`, `base_status`,
`plus_status`), read from the arm's verdict file of record; `attempt` is the attempt's position in that file, the
index a correction names. The attempts on tasks outside the published cells stay out, like the tasks themselves.
Every pass@k figure of wave 1 can be recomputed from these rows with the estimator above.

## Tests

`tests/judge/` and `tests/land/` run on the fixture set in `tests/fixtures/`: three tasks in the contract's shape (a
prompt with a leading import, a float reference against an exact integer answer, a stdin-stdout task whose output
carries a trailing newline) and a deterministic stand-in model with four answers per task (correct, a correct
variant only the rules accept, wrong, slow). The tests check the expected verdicts and cells, that each answer
kind judges as meant, that the harness's own evaluator agrees with this judge under its stock settings on the
answers whose verdict does not depend on the comparison rule, and the land rules on hand values. The judge's
tests need the harness in the environment (`pip install -e .[judge]`); the land tests need nothing beyond the
package.

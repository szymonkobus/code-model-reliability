# The task sets: how they were built, screened, certified and audited

Every task is a Python function to write, judged by executable tests: a prompt (the signature and a docstring with
worked examples), an entry point, a reference solution, base tests (the examples) and extended tests, with an exact
or tolerance comparison. The shape is the judge harness's own, so every model is measured on every task with one
judge. Three sets exist: wave 1, wave 2 and wave 2 parked. Wave 1+2, the kept tasks of wave 1 and wave 2 together, is
the population the published fit stands on. The files that carry the sets are described in `data-contract.md`
(section tasks); the counts of the shipped build are in `data/tasks/README.md` and `data/tasks/manifest.json`; the
licences and the attribution table are in `DATA-LICENSE.md`.

## Wave 1

Wave 1 is the kept subset of two public Python benchmarks of short function-writing problems, used through the judge
harness at its pinned commit with the harness's extended test inputs. All 542 tasks of the two benchmarks were
reviewed by the audit described below; the 430 whose label keeps them form wave 1. The repository ships wave 1 as
task ids and labels (`data/tasks/wave-1/kept_tasks.json`, `data/tasks/labels/`); the texts and tests come from the
harness.

## Wave 2 and wave 2 parked

Wave 1 is small and mostly easy for current models, so it shows little of where a model's ability runs out and, at one
failure in a hundred, little of how reliable it is on easy work. The new tasks were built to cover the whole
difficulty range in the same shape. They were drawn from a pool of certified new tasks and split into two sets by a
membership list fixed before the fits were run and pinned by a hash per sorted id list in `data/tasks/sets.json`:
wave 2 (869 tasks) holds the new tasks in the published fits, wave 2 parked (893 tasks) the new tasks run with the
same protocol but kept out of the fits; the two never overlap. Fourteen reworded copies turned out identical to their
parent's prompt apart from whitespace and folded into their parents: their attempts count toward the parent's and
none is a member. Twelve of them had been members and left the sets (eight from wave 2, four from wave 2 parked;
`sets.json` lists them under `folded_twins`); the other two were members of neither set.

### Where the new tasks come from

Every member of wave 2 and wave 2 parked has one row in `data/tasks/attribution.jsonl` naming its source set and row,
its kind, its method, where its reference solution comes from, the licence its text travels under, its audit label
and its content hash. There are four kinds.

- **Converted** from a public dataset into the one-function, executable-test shape. The text is the source statement
  (cleaned, with the shape's conventions restated), the tests are the source's official or dataset tests, the reference
  is a solution from the dataset. Sources: two Codeforces-derived datasets (Code-Contests-Plus and open-r1/codeforces),
  two LeetCode-derived datasets (LeetCodeDataset and LiveCodeBench), LBPP and the five EvoEval subsets.
- **Reworded copies** of wave 1 tasks: the prompt rewritten in a named style (formal, narrative, imperative and
  others, the `dial` column), the entry point, reference, tests and inputs inherited byte for byte from the wave 1
  task (`source_task`). They measure whether a model's success depends on the wording it has seen. The channel was
  closed after these were made: a new task must change the problem, never only its wording.
- **Generated** by seeded template code (the EasyTail family): a programmatic core with correctness by construction,
  and a rendered or templated surface. They thicken the easy end of the scale, where the reliability crossing lies.
- **Targeted**: a model-generated specification, reference and seeded input generator, accepted only when two further
  solutions written from independent framings agree byte for byte with the reference on about two hundred generated
  inputs, then screened and placed by a ladder of models so that the hard end of the scale is populated. This is the
  lowest-trust channel: its tasks are marked model-conditioned in their provenance, and the attempts used to screen
  them never entered any measurement.

### Conversion methods

The `conversion_method` column names one of five.

- `stdin-stdout-inline-wrap` (Code-Contests-Plus, open-r1/codeforces): a standard-input, standard-output contest
  problem wrapped into a function `solve(input_data: str) -> str` whose docstring is the statement; the official tests
  inline as inputs and expected outputs; the output layout pinned as observed on every official test (for example, a
  single line); the time limit noted. The reference is a correct submission from the dataset, converted to the
  function form with its input and output redirected. A candidate converts only when a reference reproduces the
  official expected output exactly on every kept test, in a sandboxed subprocess with resource limits; every
  candidate ends as converted, needing review with a reason, or rejected with a reason.
- `leetcode-solution-wrap` (LeetCodeDataset): the dataset's starter code and completion wrapped; the dataset's tests;
  the statement's examples as the base inputs.
- `lcb-functional-join` (LiveCodeBench): the problem joined by its LeetCode slug to LeetCodeDataset's completion as
  the reference; the benchmark's tests.
- `evoeval-native` (EvoEval): the dataset's own function form and canonical solution; the dataset's tests.
- `lbpp-body-extract` (LBPP): the function body extracted from the dataset's completion; the dataset's tests, the
  first two as the base inputs (LBPP marks no statement examples).

Constraints stated in a problem were parsed (row fields, chained inequalities, per-index and array relations, minimum
and maximum, uniqueness) and official test inputs that fall outside the stated domain were dropped before conversion,
so that the tests ask only what the statement promises. Where that screen later proved to have read a bound wrongly,
the task was re-issued as a new content version (see Certification).

### Generation methods

**EasyTail** (generator configuration `easytail_gen_config_v1`). Every task has a programmatic core generated by
seeded template code: the entry point, the canonical solution, an input generator producing the prompt's worked
examples and one to two hundred seeded inputs including edge cases, exact comparison. Correctness is by construction
and re-verified by running the solution on every input twice. The surface is rendered per task: archetype E4 uses
direct template text; E1, E2, E3 and E5 use a language-model rendering pass over pinned specification facts under a
verifier contract (the signature and the example lines byte-pinned, the conventions restated identically). The five
archetypes, each with its dials:

- E1, long but trivial narrative: a 300 to 600 word domain story (payroll, inventory, sports, logs, shipping) reducing
  to one elementary computation; dials: domain, length, mild distractors.
- E2, explicit multi-step pipeline: three to six elementary ordered steps (filter, map, sort, format); dials: step
  count, element type.
- E3, format following: trivial logic with an exact output-format requirement; dial: format shape.
- E4, parameterised micro-variants: one-sentence elementary operations over lists, strings and integers on a parameter
  grid; dials: operation, parameters.
- E5, specification-to-code transcription: an unambiguous formula or pseudocode in words; dial: formula family.

Before emission every candidate passed anti-degenerate rules: identity, constant and first-element solutions must
fail the suite; the canonical solution runs twice with byte-equal outputs; no input, printing or file access in the
solution; payload under 1 MB; under 0.1 s per test.

**Targeted** (generator configuration `targeted_gen_config_v1`). A language model generates the task specification, a
reference solution and seeded input-generator code; two additional solutions are generated from independent framings
(solution-only prompts, no shared reference); all three must agree byte for byte on every generated input, about two
hundred including edge cases, and any disagreement rejects the candidate with no repair loop. The same local screens
as above run before emission, the full screen suite afterwards. Candidates are run against a ladder of models and
those solved easily (pass rate above one half on any ladder model) are moved to the middle gap or dropped. Gaps: G1,
the hard end (contest-grade algorithmic styles: dynamic programming, combinatorics, number theory, greedy with proof,
implementation-heavy simulation, tricky invariants); G2, the upper middle; G3, reserved for model-specific gaps.
Themes: dp-bitmask, dp-digit, dp-on-trees, number-theory, combinatorics-counting, greedy-exchange-argument,
string-suffix-structures, graph-shortest-path-variants, flows-and-matching, game-theory, integer-geometry,
offline-queries-data-structures, inclusion-exclusion, parity-invariants, constructive-algorithms,
interval-scheduling. A docstring states input bounds and never an unenforced efficiency claim; a scale the graded
inputs themselves enforce may be stated.

**Reworded copies** (generator configuration `twin_gen_config_v1`). A paraphrase of a wave 1 task's prompt in a named
style; everything else inherited byte for byte; sources chosen among the kept wave 1 tasks and stratified by
difficulty. Rewording is not presentation-neutral for a latent defect, so a copy of a defective source stays
defective, and the audit labels copies and sources independently.

### Screening

Every candidate passed one serialised duplicate gate and then the screen suite before certification.

The duplicate criterion: an exact match of the normalised prompt or of the normalised canonical solution (whitespace
stripped, lower-cased, hashed) against the 542 wave 1 tasks, every candidate previously admitted through the gate
from any channel, and the earlier records of the same batch. A reworded copy is exempt by family: a collision is
allowed only when every collision target is the copy's own source task or a member of the same family. Task ids are
globally unique; a reused id with different content is rejected.

The screen suite, run on every task on its own: the reference passes its own tests; determinism (identical outputs
over two runs on every input); payload size; runtime margin (the slowest input against the judge's time floor);
recursion depth on the largest inputs; float tolerance (whether floats appear and the tolerance is set); entry-point
name well-formedness; duplicates in the pool; trivial solutions (a set of trivial stubs must all be rejected by the
tests); output diversity (the number of distinct expected outputs); input and output purity (no network, file
system, randomness or clock); mutation adequacy (the suite kills a small set of mutants of the reference); a source
blocklist; the reference passes the production judge; and floor adequacy (the reference runs well inside the judge's
per-input time floor). A behavioural screen flags a task every strong model fails unanimously, for review rather than
exclusion. Each certificate records the suite's version hash and a verdict with a reason per screen.

### Certification

A certificate was written for a task once its eight judged fields were fixed and its reference reproduced every
expected output. The content hash over those fields (`content_sha256`, the recipe in `data/tasks/manifest.json`) is
the identity every judged cell carries: a task whose content changed after judging got a new hash and a new
certificate naming the previous hash (`superseded_prev_sha256`), and the old cells stay tied to the old content. The
certificate records the set the task was certified into (`frame`, the pool the two measured sets were drawn from, or
`pilot`, a pilot of very easy tasks that entered neither set), the status, whether the task is eligible for the fits
by status and audit label (`fit_keep_set`), the audit label with the review round that set it, the difficulty band it
was aimed at, the conversion method with the reference's origin, and the provenance block. The statuses:
`complete-for-admission` (certified with a complete test set), `retracted-to-reserve` (certified, then set aside from
the measured pool), `withdrawn` (removed after certification), `excluded-provisional-tier1` (held out pending a
check), `awaiting-components` (certification incomplete) and `held-empty-tests` (no usable tests). Set membership is
not in the certificates: it is the list in `sets.json`.

## The audit

Every task of every set was reviewed for defects by readers blind to earlier labels, tags and verdicts and to each
other; the readers did read the models' answers, as the stages below say. The review asks whether the statement,
its examples, the reference solution and the tests agree, and gives each task one of four labels:

| label | meaning | kept |
|---|---|---|
| `regular` | statement, examples, reference and tests agree | yes |
| `tricky` | consistent and solvable, with a subtle gotcha a careless reading misses; also the label for a task that is technically underspecified but whose intent is obvious from the examples | yes |
| `underspecification` | the tests require behaviour that cannot reasonably be derived from the prompt: undefined edge cases actually exercised, or types, ordering or format pinned down arbitrarily | no |
| `contradiction` | the prompt, its examples, the reference or the tests contradict each other, including tasks no correct solution can pass | no |

The stance is not adversarial: when in doubt between tricky and a defect label and the examples make the intent
obvious, the task is tricky or regular. The criterion is that the intended behaviour, as enforced by the tests and
the reference, must be understandable from the task description and its included examples. A trap must be
concentrated and nameable and lie outside what the base examples exercise; a wrong core algorithm is a matter of
capability and leaves the task regular, as do input size inside the declared domain and core-algorithm errors.

The stages, per intake wave: scripted hard gates first (the reference passes its own tests under a sound judge
configuration, a contract is present, runtime and memory have a fourfold margin or the limits are declared in the
prompt, the oracle type is explicit); a blind first tag, one reader per task, from the task's data digest and the rubric, with a
forced structured output of label and justification; a full blind audit, one reader per task at full effort, that
takes a census of failure modes where attempts exist, implements every plausible reading of the prompt and runs each
against all graded inputs, checks the grader's settings for the task from source, and argues all four labels before
deciding. A disagreement between the first tag and the full audit, or between two independent readers, went to a
decision queue with both records; crossings of the defect boundary (a defect label on one side, tricky or regular on
the other) were decided one by one and blocked the task's admission until decided; within-group disagreements were
batched. A label changed automatically on a blind verdict with a record in the history (`labels/label_history.jsonl`:
the label before and after, the review round, the days recorded and applied, the reason), the same rule for every
set. A small number of labels were settled by hand after the review rounds disagreed; their rows say so
(`settled_by_hand`). Readers were several language models, with disputed cases settled as above.

Labels are per task instance: a reworded copy and its source are labelled independently. Grader-side matters are
never label-bearing: float tolerance, output comparison, a sanitiser's effect, emission slips, refusals, the numeric
type of a huge input, the recursion limit of the environment; those are the judge's settings (`data-contract.md`,
section judge).

A task is kept when its current label is `regular` or `tricky` (`label_rule` in `sets.json`). Of wave 1, 430 of 542
are kept (79 labelled `underspecification`, 33 `contradiction`); of wave 2, 858 of 869; of wave 2 parked, 879 of
893. The members not kept are listed with their reason in `sets.json`.

## What ships and what does not

- Wave 1: ids and labels only; the texts come from the judge harness.
- Wave 2 and wave 2 parked: the full record for every task whose upstream permits redistribution or which was written
  for this project; a pointer (identity, audit flag, provenance, the reason, the rebuild recipe and a sentence saying
  how to rebuild) for the tasks converted from the two LeetCode-derived datasets, whose upstream terms permit pointers
  only, and for a task whose text fails the publication check (a filtered string); the reasons are counted per set in
  each folder's `manifest.json`.
- On every record and pointer, `io_mode`: `function` when the tests call the entry point with arguments, `stdio` for
  the converted contest problems, whose program reads standard input and writes standard output and whose output is
  compared as text. Where they apply, two facts the judge uses: `plus_inputs_removed`, the extended inputs removed
  before judging (an input that carries a boolean at an argument position where no example carries one; a reworded
  copy inherits its parent's list), and `input_shapes`, the declared shape per argument of the tasks whose inputs
  are typed before the call. Wave 1's removed inputs are in `data/tasks/wave-1/plus_inputs_removed.json`, since wave 1
  ships as ids.
- The certificates with a curated field list and no run outcomes; the labels of every reviewed task; the attribution
  rows; the source sets with their licences.
- A reviewer's justification that quotes internal notes is withheld rather than rewritten (`justification_withheld`);
  the count per file is in `data/tasks/manifest.json` under `withheld`, with every other treatment of the files of
  record.
- No generated program text and no judged outcomes: those are the results' (`data-contract.md`, sections judge and
  land).

## Rebuilding the pointer tasks

The converters that produced the two LeetCode-derived families ship in this repository as
`code_model_reliability.tasks.convert` (`cmr tasks convert`): `leetcode` turns a LeetCodeDataset row into a task
(`leetcode-solution-wrap`), `livecodebench` joins a LiveCodeBench row to LeetCodeDataset's solution of the same
problem (`lcb-functional-join`), and `fetch-upstream` reads the rows from Hugging Face, all of them or only the slugs
of a list. The rules are those the tasks were first built with: the statement as the docstring of the method's
signature written as a module-level function, the dataset's completion wrapped as the reference, the statement's
examples as the base tests and the dataset's pairs as the extended tests, exact comparison, and acceptance only
when the reference reproduces every expected value in an isolated subprocess.

Every pointer carries its recipe under `rebuild`: the converter, the hash of the task's first emission and, where
the task was later re-issued, the extended or base inputs that re-issue removed (185 of the 333 pointer tasks: 179
LeetCodeDataset, 6 LiveCodeBench; the re-issues removed inputs that fell outside the statement's stated domain or
whose expected value the statement did not define, and changed nothing else). `cmr tasks rebuild-restricted --plan
--write-slugs <dir>` prints the commands and writes the slug lists; `--verify <converted records>` accepts a rebuilt
record when its content hash equals the certified one, directly or after the listed inputs are removed with their
expected values, and `--out` writes the accepted records as a part. Checked on the day this document was written,
the converters reproduce the first emission of all 333 pointer tasks from the datasets' rows as they then stood;
a row the upstream changes afterwards fails its hash, and `fetch-upstream --revision` pins the dataset repository at
a commit of that time.

## Checking a copy

`cmr tasks verify` recomputes every list hash in `sets.json`, every part's sha256 against its manifest, every record's
content hash from its eight fields against the record's own hash and its certificate, and checks that every member of
a set appears exactly once as a record or a pointer, that every member has an attribution row covered by a source set,
and that every member is kept exactly when its label is a keep label. It exits 1 on any mismatch and prints every
problem.

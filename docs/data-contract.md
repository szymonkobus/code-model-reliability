# Data contract: the files between the stages

Every file one stage writes and the next reads, with its shape. The stages run in this order: tasks, generate,
judge, land, fit, plot. A reader who has only the published tables can start at `fit` or `plot`; a reader with a
model can start at `generate`.

Conventions that hold everywhere:

- Paths are repository-relative. The three task sets have one name each in three forms: in prose wave 1, wave 2
  and wave 2 parked (wave 1+2 for the two measured sets together); in paths `wave-1`, `wave-2`, `wave-2-parked`;
  as JSON keys and labels `wave_1`, `wave_2`, `wave_2_parked`. No other spelling appears.
- The repository's `data/` is written whole by the build from the files of record, so a published file is never
  carried from an earlier build; the package's source tree holds nothing under `data/`, and the tests read
  fixtures, never the exported data.
- The published fit lives under `data/results/published/<fit>/`; a fit a reader makes lives under `fits/<fit>/`
  in the same shape. The word is published, never served.
- An **arm** is a model under one generation protocol. Its id is the key the published fit's cells and crossings
  were produced under, and every other table carries that same id: for the engine arms the model stem (the
  model's id with `/` written `--`), a token where the generation path is not the harness's own, and the
  temperature (`Qwen--Qwen2.5-7B-Instruct_temp_0.8`, `Qwen--Qwen3-8B_think_temp_0.6`); for the API arms the model
  name with its thinking form and the `_batch` token (`claude-haiku-4-5_batch`, `claude-haiku-4-5-thinking_batch`,
  `gpt-5-mini_batch`, `gemini-3.6-flash_batch`); a protocol variant run beside an arm carries a `@<variant>` suffix
  (`google--gemma-4-12B-it_temp_0.8@768-marker`). No table composes an id of its own. The registry (section land)
  is the one list of arms, keyed by these ids, and every table joins on the arm id.
- Every file a stage writes names what it was produced from: the set and its hash, the arm, and the settings that
  can move a result, in a sidecar beside the data or a header inside it.
- A date in a published file is a day, written year-month-day. No file carries a clock stamp, a host, a path
  outside the repository, a key or a credential.
- Difficulty is on one scale in logit units (`_z` columns; larger is harder): the logit of the panel-average
  failure rate on the task with one Jeffreys pseudo-observation, not standardised; where a difficulty is printed as
  a percentage it is 100 times the logistic of the z value, written 0 to 100%.
- A crossing is named by the success rate it stands at: D50 (capability, half the attempts fail) and D99
  (reliability, one attempt in a hundred fails) are the two the project reads; D97, D95 and D90 (3%, 5% and 10%
  failure) and D1 (99% failure, the hard end) are carried beside them. Their columns are `d50_*`, `d99_*` and so
  on, and `d1_*` is always the 99%-failure crossing.
- A crossing's status is `point` (inside the fitted range), `bound below` (the curve is still above the level at
  the easiest task; the value is the easiest task's difficulty), `bound above` (the curve never reaches the level
  by the hardest task; the value is the hardest task's difficulty) or `unavailable` (no draws exported). Every arm
  has a value at every level; a censored draw counts past the end it lies beyond.

## tasks

`data/tasks/sets.json` — the membership of record. Per set, under the keys `wave_1`, `wave_2` and `wave_2_parked`:
the task ids, the subset kept by the audit, the count of each, and a sha256 over each sorted list, so a copy can be
checked against the record. Wave 2 and wave 2 parked never overlap; a reworded copy of a task that folded into its
parent is listed under the parent. The export copies every row whole from the files of record, drops the keys
that hold the producers' bookkeeping (stamps, authorship, input listings), checks each copied file against its
source's manifest and pins the sources by sha256 in the shipped `manifest.json`.

`data/tasks/attribution.jsonl` — one row per task: the set, the task id, the kept label, the source set and the
source row key, the derivation kind (imported, converted, reworded, written for this project), the licence the
row's text travels under. `data/tasks/sources.json` — one row per source set: what it is, the licence as recorded,
how its tasks ship here (full text, or pointers) and the families it covers. The attribution table in
`DATA-LICENSE.md` is generated from these two files (`cmr tasks attribution-table` prints it).

`data/tasks/wave-1/kept_tasks.json` — the wave 1 task ids kept after the audit, the labels that keep a task, the
count. The texts and tests of wave 1 come from the judge harness at its pinned commit, not from this repository.
`data/tasks/wave-1/plus_inputs_removed.json` — for the wave 1 tasks whose extended inputs the judge removes (the
rule in `docs/judging.md`), the removed argument lists per task, since wave 1 ships as ids.

`data/tasks/wave-2/tasks-part-NN.jsonl.gz`, `data/tasks/wave-2-parked/tasks-part-NN.jsonl.gz` — one JSON object
per line, the judged content of a task:

| field | meaning |
|---|---|
| `task_id` | `<source prefix>/<key>`; the prefix names the upstream dataset (see `DATA-LICENSE.md`) |
| `prompt` | the function signature and docstring the model completes |
| `entry_point` | the function name the tests call |
| `canonical_solution` | a reference body that passes every test |
| `base_input`, `plus_input` | lists of argument lists: the base tests and the extended tests |
| `expected_output` | the expected result per input, produced by the reference |
| `atol` | numerical tolerance for the comparison (0 for exact) |
| `io_mode` | `function` (the tests call the entry point with arguments) or `stdio` (the program reads stdin and writes stdout; its output text is compared in canonical form); set from the certificate's conversion method, with the `solve(input_data: str) -> str` signature as the fallback; on every record and pointer |
| `plus_inputs_removed` | only where the judge removes extended inputs: the removed argument lists (a reworded copy carries its parent's list) |
| `input_shapes` | only on the typed tasks: the declared shape per positional argument, which the judge uses to type the inputs |
| `content_sha256` | sha256 of the eight fields above serialised as JSON with sorted keys; equals the certificate's hash |
| `kept_by_audit` | whether the task's audit label keeps it in the fits |
| `provenance` | upstream dataset, row key, title, URL, licence, and the contest rating and tags where the upstream has them |

`restricted.jsonl` in each set folder — the same identity, audit flag and provenance for tasks whose text does not
travel because the upstream's terms do not permit republishing statements, plus a one-sentence pointer to the
source and the recipe that rebuilds the text, `rebuild`: `converter` (the converter the task was imported with,
one of `cmr tasks convert leetcode | livecodebench`, after `cmr tasks convert fetch-upstream`), `first_emission_sha256`
(the content hash of the task as first emitted), and `plus_inputs_removed_at_reissue` and
`base_inputs_removed_at_reissue` (the test inputs removed when the task was re-issued, so a rebuilt text matches the
certified content directly or after those removals). `cmr tasks rebuild-restricted` applies the recipes to the
upstream datasets (`--revision` pins a dataset at a commit; a row the upstream changed since fails its hash) and
checks every content hash.

`data/tasks/certificates.jsonl` — one row per certified task: identity (`task_id`, `content_sha256`, the previous
hash where a task was re-issued), the set and whether it is in the measured set, the status, the audit label,
the day it was generated, and the provenance block above. No run outcomes: those are the judge's and live in the
results.

`data/tasks/labels/labels.jsonl`, `label_history.jsonl` — the audit label of every task (regular, tricky,
underspecification, contradiction, the file's own values) and the history of review-round outcomes on the tasks of the three sets, label
changes and confirmations alike (a confirmation's label before equals its label after), with their reasons, from
every review round the audit kept. A label's justification that carries a name or quoted words is withheld, never
rewritten, and the withheld count per field is in the manifest.

`cmr tasks verify` recomputes every content hash and every list hash and fails on a mismatch.

## generate

Per set and arm, under an output directory of the caller's choosing (`<out>/<set>/<arm>/`):

`samples.jsonl` — one JSON object per attempt, `{"task_id", "solution"}`, in task order and attempt order within
a task, the same number of attempts per task; `solution` is the program after extraction, the shape the judge
reads. This is the harness's own samples shape.

`raw.jsonl` — one object per attempt as the model returned it: `task_id`, `attempt`, `text`, `finish_reason`
(stop, length, refusal), `tokens` (the output tokens where the back end counts them), for the thinking protocols
`think_text`, `think_tokens`, `answer_tokens` and how the thinking closed, for the API arms a `provider` object
(the model string the provider answered with, its stop reason, its usage, the batch id), and on a continued or
answer-phase row `continued_from` (the sha256 of the text continued and the limits). One shape for every back end.

`generation.json` — every setting the attempts were produced under: the arm; the set and its hash; the model id
and revision; the protocol by its name, as given to `--protocol` (`protocol`), its version token
(`protocol_version`), the form (plain, thinking or completion), the sampling (temperature, top_p, top_k, min_p),
the output limit and the thinking budget; the prompt rule (the harness commit whose instruct prompt is used, the
instruction text); the extractor's stamp (`v2@<sha16>`, the sixteen hex digits of the sha256 of the extractor file as it
ran; every version the published verdicts rest on ships, `docs/generate.md` tables them); the library pins; the seed; attempts
per task; the number of tasks; the days the run started and finished.

## judge

Per set and arm, beside the samples:

`verdicts.json` — the harness's evaluation output at the pinned commit: per task, a list in attempt order with
`base_status` and `plus_status` (pass or fail on the base tests and on the extended tests) and the first failing
input of each; the file's `pass_at_k` block recomputed from the verdicts. An attempt **passes** only when both
statuses are pass.

`judging.json` — the record of every setting that can move a verdict, and its id (twelve hex digits of the hash of
its values), written beside the verdicts it produced: the harness commit; the time limit of each test and the cap
on an attempt's whole suite (the record names both; the attempts this package judges carry the current rule, and
a verdict file judged under an older rule carries that rule); the memory limit (8 GiB for every verdict this
package produces; 12 GiB for the wave 1 files judged by the harness's own evaluator); the leading-imports rule (a
task prompt's leading import lines are placed before the judged program) and the typing prelude for the completion
form; the comparison rule (returned values normalised to plain builtins; a float meeting a number compares within a
relative tolerance of 1e-9; a stdin-stdout task's output text compared in its canonical form: line ends, trailing
whitespace per line, trailing blank lines); the plus-input filter and the typed inputs; how the reference outputs
are computed; the judge's version string; and per task the number of attempts the limits stopped, their status
`timeout`.

`per_test.jsonl` — written by `cmr judge --per-test` for failing attempts: `task_id`, `attempt`, the suite (base or
extended) and the outcome letter per test input (P, W, T, E, A, defined in `docs/judging.md`), where the default
judge stops at the first failing test.

A re-judge of a task writes `verdicts.N.json` with `judging.N.json` beside it; the land stage takes a task's newest
judging, the same programs required. A correction lands as `corrections.jsonl` beside `verdicts.json`, each row
naming its attempt by the sha256 of the solution text; no judged file is rewritten.

## land

`cells.csv` — one row per arm and task:

| column | meaning |
|---|---|
| `arm` | the arm id |
| `task_id` | the task |
| `failures` | attempts that failed (an attempt passes only when the base tests and the extended tests all pass) |
| `attempts` | attempts judged |
| `time_limit_fails` | the attempts the time limit stopped, a subset of the failures |
| `judging` | the id of the `judging.json` the verdicts carry |

The rules: a re-judged attempt's newest verdict wins; an answer cut at the output limit and re-run to completion is
one attempt in two parts; a correction never rewrites a judged file and lands as a companion file beside it. For
the wave 2 cells, which pool several judgings of one task, `land/pooling.py` carries the composition rules and
`data/runs/pooling_rules.json` their values. Of the successive readings of the judged results, the one published
is the newest that passes two checks: every arm keeps its published count of attempts and every task's judgings
are complete, and against the previously published reading no cell's failures fell at equal attempts except
through a named re-judging; a reading that fails either check is not published.

Every table under `data/runs/` and `data/results/` covers the arms of the published fit and no other: an arm the
published fit does not carry has no registry row, no protocol row, no name and no per-attempt rows here, whatever
else ran on this project's machines, so every row of every table leads to a published result. The population is read
once, from the fit of record, by every exporter.

`registry/arms.jsonl` — the one list of arms, one row each after a header row with the schema name and the row count:

| field | meaning |
|---|---|
| `arm` | the arm id |
| `model_id`, `model_name` | the model's id in `models.jsonl` (every arm row joins one model row by it) and its name of record |
| `family` | the model family (a maker's line of models) |
| `form` | plain, thinking or completion |
| `protocol`, `protocol_version`, `temperature` | the protocol's name as `cmr generate --protocol` takes it; its version token where one exists, else null (a complete row); the sampling temperature |
| `attempts_per_task` | per set, from the arm's published cells: the one count where every task got it, else the modal count with the range beside it (cells topped up after the first pass carry more) |
| `sets` | the sets the arm has cells on in the published fit |
| `judging` | per set, the id of the judging settings its verdicts carry; for wave 2, where several judgings pool into one cell, the ids the arm's pooled draws carry, read over the arm's published cells from the census of judgings as it stands at the build; every id names a record of `judge/settings.py` (`docs/judging.md`) |
| `extractor` | per set, the stamps its verdict files carry; for wave 2, where the extractor is a fact per cell, both stamps with a by-cell mark |

`registry/models.jsonl` — one row per model: `model_id` (the id the arm rows join on), `name`, `family`, `rank`
(the model's place among its family's models, as the models file of record carries it; the figures' colour ladder
puts a family's shades in this order and falls back to size where a model has no rank), parameter counts (total and
active, in billions) and the mode where a model has several (plain, thinking).

`registry/names.json` — the names of record of the models trained in this project whose arms the published fit
carries (a run with no published position has no entry); the figures print a run's name from this file and compose
none. Per run (`runs`): `name_of_record`, `base_model`, `what_was_done` (the name's
second half, the training in plain words), `chip` (the short form printed beside the base model's name),
`position_form` (the pattern that puts a step count into the chip), `slug`, and `positions`, one entry per
position with its `step` and the arm id it stands in the registry under. Per base model (`bases`):
`name_of_record`, `chip`, `slug`, `position_form` and its arm id. Two runs that share one name (a run and its
branch from a checkpoint) are one entry with every position and one sentence saying so.

The judge's task-side facts (which extended inputs are removed, which tasks take typed inputs, a task's
input-output mode) are fields of the task records and, for wave 1, the file `data/tasks/wave-1/plus_inputs_removed.json`;
the judge reads them from there and keeps no copy.

`registry/protocols.tsv` — one row per arm, the protocol it was run under: the model id, form, protocol token,
back end, prompt style, temperature, top_p, top_k, min_p, the output limit and the first pass's shorter limit
where there was one, the thinking and answer budgets, the model's context length, the stop strings (a JSON list in
one cell), the request geometry and the attempts per task on each set. Built at every build from the registry and
the back ends' cards; `cmr generate --arm <arm>` runs an arm from its row.

`registry/arm_map.tsv` — model stem to arm id, the one curated map the registry builder uses.

`passk.csv` — `arm`, `set`, `k`, `pass_at_k`, recomputed from the verdicts with the unbiased estimator.

`results/per-attempt/wave1_humaneval.csv.gz`, `wave1_mbpp.csv.gz` — every attempt in the verdict file of record of
every published arm on the wave 1 tasks the published fit has cells for (the kept tasks and the task set aside after
the cut; an attempt on a task outside the published cells stays out as the task does), one row each. Where a cell
was topped up on another route after the file of record was judged, its count in `cells.csv` exceeds its rows here,
and the manifest carries per arm the rows written beside the attempts the published cells count, so the difference
is in the open; the cells are the counts the fit stands on, these rows the attempts a verdict file of record holds.
The columns: `arm`, `task_id`, `attempt` (the attempt's position in its arm's verdict file for the task, the index a
correction names), `base_status`, `plus_status` (pass, fail or timeout, the verdict file's own words; the two suites
were judged independently, so a base failure beside an extended pass occurs). The pass@k figures of wave 1 recompute
from these rows. Wave 2's attempts ship as cells only, since several judgings pool into one cell there.
`manifest.json` beside the tables: per table its file name, sha256, size in bytes, fields, arms and rows (the header
line not counted), and per arm the tasks and rows written and the attempts the published cells count; the gzip
header is written without a clock, so a table's hash stands from build to build while its inputs stand.

## fit

One shape for a fit a reader makes (`fits/<fit>/`) and for the published fit (`data/results/published/<fit>/`),
where `<fit>` is the first twelve hex digits of the sha256 over the sorted arm ids and the cells file the fit
stands on, so a refreshed fit is a new directory beside the old one and no internal id names a directory. The
published fit's tasks are the tasks that had judged attempts when it was cut: every kept task of wave 1 and wave 2
(the build fails when a kept task has no cells) and the tasks the audit set aside after the cut, whose ids and labels
`docs/numbers.json` lists under `tasks_fit_not_kept`.

`axis.csv` — one row per task:

| column | meaning |
|---|---|
| `task_id` | the task |
| `difficulty_z` | its difficulty, in logit units |
| `difficulty_sd` | the standard error of that estimate |
| `n_arms` | the voting arms with attempts on the task |
| `n_attempts` | their attempts on it |
| `mean_failure_rate` | the panel-average failure rate the difficulty is the logit of |

`panel.json` beside it is the axis's recipe: the threshold an arm must meet to vote, the voting arms, the arms
positioned on the axis without voting, the coverage; the axis cannot be re-made without it.

`inputs/<arm>.npz` — the engine's arrays for one arm: `z_hat`, `sd`, `f`, `n`, `task_ids`, `model_id`.

`posterior_summary_<arm>.json` — the engine's output: the configuration it ran under, the estimands (D50 and D99
on the average-rate curve, D99 on the median-task curve; medians, 80% credible intervals, censored fractions), the
curve on a grid with its band, the dispersion parameters, the sampler diagnostics and the time it took. It carries
the posterior draws (about 11 MB per arm) and does not ship; it is regenerated by `cmr fit`.

`arms/<arm>.json` — the draw-free summary of that file, about 60 KB per arm, written by the fit stage's summaries
step and shipped under `data/results/published/<fit>/arms/`; the figures and the two pages read nothing else of the
posterior:
`curves` (a grid of 121 difficulty values; seven quantile levels in percent; the logit failure rate of the
average-rate curve and of the median-task curve at every quantile and grid point); `levels` (for each of 352
failure-rate levels, the crossing's median, its 80% interval and its left- and right-censored fractions, under the
average-rate and the median-task definition, with the method and the crossing rule named); `estimands` (D50 and
D99 under both definitions: median, 80% interval, censored fractions and the status); `tau` and `rho` (median and
80% interval); `density` (for D50 and D99 under both definitions, a 220-point grid with the density of the crossing
draws, a Gaussian kernel at Silverman's bandwidth with a floor of 0.02, normalised to its maximum; censored draws
sit at the grid's ends).

The engine's equivalence to the engine the published fits ran under: every numeric expression, constant, seed and
library pin is the same, and the test is bit-identical draws on one arm's inputs at short chains against the
engine of record, run on the cluster; `docs/method.md` names the engine hash every published row carries. The
shipped file is not byte-identical, since the original's header carries text that does not travel.

`gates.json` — the gates over every arm of the fit: `rule` (the verdict rule in words, the concentration note and
its regimes), `n_arms`, `n_pass`, and `arms.<arm>`, one record per arm: `divergences` and `divergence_share`,
`divergence_gate`, `engine_divergence_flag`, `rhat_gate`, `ess_gate`, `gates_failed` (the failed gates as a list,
empty on a pass) and `gate` (pass or FAIL); the crossing-level diagnostics (`crossing_rhat_d50`, `crossing_ess_d50`,
`crossing_rhat_d99`, `crossing_ess_d99`, whether each level's chains mix and their spread), the hyperparameters'
gated R-hat and sample size, and the concentration reading (whether failures sit on the easiest third of tasks)
with its regime, carried beside the gates and never holding a row. The gates: divergent transitions above half a
percent of the kept draws; split R-hat above 1.01 or bulk effective sample size below 400 on the D50 or D99
crossing draws, a bound level exempt. A failed gate keeps the arm's row in the crossings table and marks it there
(`gate`, `gates_failed`); the figures and pages draw such an arm faded and flag it.

`crossings.csv` — one row per arm:

| column | meaning |
|---|---|
| `arm`, `model_name` | the arm id and the model's name of record, read from the registry's `arms.jsonl`; a fit a reader makes without a registry writes the arm id in both |
| `d50_z`, `d50_lo`, `d50_hi`; `d99_z`, `d99_lo`, `d99_hi` | for D50 and D99 on the average-rate curve: the crossing's median and its 80% interval, in logit units |
| `d50_status`, `d50_bound_z`; `d99_status`, `d99_bound_z` | point, bound below, bound above or unavailable; the bound's value where the status is a bound |
| `d50_p_left_censored`, `d50_p_right_censored`, `d50_z_conditional`, `d50_censored_edge`; the same for `d99` | the shares of draws censored at each end, the median over the uncensored draws alone, and the end the censored draws sit at |
| `d99_median_task_z`, `_lo`, `_hi`, `_status`, `_p_left_censored`, `_p_right_censored` | the median-task D99 beside the average-rate one |
| `d97_z`, `d95_z`, `d90_z`, `d1_z`, each with `_lo`, `_hi`, `_status`, `_p_left_censored`, `_p_right_censored` | the levels beside the two of record, on the average-rate curve |
| `tau`, `rho`, each with `_lo`, `_hi`; `ell_median` | the per-task dispersion and the intraclass correlation it implies, with their 80% intervals; the median length scale of the curve |
| `crossing_rhat_d50`, `crossing_ess_d50`, `crossing_rhat_d99`, `crossing_ess_d99` | the crossings' own split R-hat and bulk effective sample size |
| `divergences`, `gate`, `gates_failed` | the divergent transitions; the gates' verdict (pass or FAIL) and the failed gates, semicolon-joined, empty on a pass |
| `n_tasks`, `grid_lo_z`, `grid_hi_z` | the fitted tasks and the fitted range |
| `m_basis`, `hsgp_L`, `crossing_rule` | the size and the half-width of the curve's basis expansion, and the rule a crossing is read by |
| `draws_basis` | how many draws the reading rests on |
| `engine_sha256_12`, `source_sha256_12` | the first twelve hex digits of the engine's hash and of the posterior file the row was read from |

`crossings.json` beside it carries the same rows with the crossing rule in words.

`meta.json` — the fit's identity: its name, the set, the population (arms, tasks, cells), the axis
definition in one sentence, the engine (version, md5, library pins), the sampler settings (chains, warm-up, draws,
target acceptance, tree depth, seed), the estimator (the average-rate curve for both crossings; the median-task
D99 carried beside), the day it was cut.

## plot

`figures/<figure>.<name>.svg` and `.png` — written by the one export function; the legend rows and the file name
carry the names of record whole.

`src/code_model_reliability/plot/palette.json` — the colours of record: one hue per model family, the lightness
ladder within a family, the training runs' ramps and marks; the ladder rule in code gives a new arm its colour
and every published arm keeps its colour of record.

`site/` in the repository holds the two page shells as authored source and, once under `site/kit/`, the shared
kit files (the chart kit, its visual helpers, the export function and the stylesheet); `cmr site` copies what each
page's index.html names beside the page and nothing else, writes the bundles below, and checks every asset,
fetch, path, JSON and script. It is the build's step after the data export; `docs/site/` is its output and is not
kept in the source tree.

`docs/site/<page>/data/manifest.json` and the bundle files it names — the two page shells read nothing else. The
plane's bundle carries per arm the name of record, the family and colour, D50 and D99 with their intervals and
statuses; the curves' bundle carries per arm the curve grid with its band and the cells behind it, and a shared
file carries the axis, the tasks and the arm list. A bundle carries data and names of record only; no stamp,
pointer, disclosure or decision text.

# Data contract

The files a reader consumes, their shape, and where they come from. Paths are repository-relative.

## Arm names

Two naming systems are in use and both are documented here. The result tables (`cells.csv`, `crossings_of_record.csv`,
`meta.json`) name an arm by its model stem and protocol suffix, for example `Qwen--Qwen2.5-7B-Instruct_temp_0.8` or
`claude-opus-5_batch`. The registry (`runs/registry/arms.jsonl`) names the same arm by a short id, for example `q3-8b`,
and carries the model stem in `model_stem`; the per-attempt verdicts use the short id. `tasks/golden_set.json` lists the
golden arms in both forms.

## Task sets

**`tasks/sets.json`** — the membership of record: the task ids of wave 1, wave 2 and wave 2 parked, the subset of each
kept by the audit, their counts, and a sha256 of every sorted list (`members_sha256`) so that a copy can be checked
against the record. Wave 2 is the set of new tasks in the published fits; wave 2 parked is the new tasks run but kept
out of the fits; the two never overlap.

**`tasks/wave1/kept_tasks.json`** — the ids of the wave-1 tasks kept after the task audit (`tasks`), the labels that keep a
task (`keep_labels`), and the count. Texts and tests come from the pinned judge harness (`runs/generate/cluster/setup_env.sh`
names the commit).

**`tasks/wave2/tasks-part-NN.jsonl.gz`** and **`tasks/wave2-parked/tasks-part-NN.jsonl.gz`** — one JSON object per line,
the judged content of a new task:

| field | meaning |
|---|---|
| `task_id` | `<source prefix>/<key>`; the prefix names the upstream (see `DATA-LICENSE.md`) |
| `prompt` | the function signature and docstring the model completes |
| `entry_point` | the function name the tests call |
| `canonical_solution` | a reference body that passes every test |
| `base_input`, `plus_input` | lists of argument lists: the base tests and the extended tests |
| `expected_output` | expected results per input, produced by the reference |
| `atol` | numerical tolerance (0 for exact) |
| `content_sha256` | sha256 of the eight fields above, `json.dumps(..., sort_keys=True)`; equals the certificate's hash |
| `kept_by_audit` | whether the task's audit label keeps it in the fits |
| `provenance` | upstream dataset, row key, title, URL, licence, contest rating and tags where the upstream has them |

**`restricted.jsonl`** in each set folder — the same identity, audit flag and provenance for tasks whose text is not
shipped, without the content fields, each with a note saying why. **`manifest.json`** in each set folder — the set's
member count, the kept count, the counts of text and pointer tasks, the hash of the member list, the part list with
sizes and hashes, and the hash recipe. **`tasks/rebuild_restricted.py`** rebuilds the pointer tasks from the upstream
datasets and verifies any task file against the certified hashes.

**`tasks/certificates/certificates.jsonl`** — one line per new task ever certified (2377 lines, the
two sets of record and the pilot tasks together; the pilot tasks are the first written easy tasks, kept out of both sets
and marked `set: pilot`): `task_id`, `set`, `status`, `fit_keep_set` (eligible for the fits by
status and audit), `content_sha256`, `superseded_prev_sha256`, `certified_on` (the day), `audit_label`, `band_aim`,
`provenance`; `tasks/certificates/README.md` defines the status values. `task_versions.json` records every version
boundary as its pair of content hashes and `version_pins.json` the re-imported tasks with their changed fields;
`suite_v1_manifest.jsonl` is the first fixed task list, kept for the version chain.

**`tasks/labels/`** — the audit labels for wave 1 (`labels_humaneval.jsonl`, `labels_mbpp.jsonl`), the label history, and
a README describing the labels.

## Registry

**`runs/registry/arms.jsonl`** — a header line, then one row per arm and benchmark: `arm_id` (the short id), `benchmark`,
`kind` (`full` for the published attempt count, `greedy-gate` for a single greedy anchor), `status` (`published` or
`quarantined`), `model_stem`, `protocol`, `temperature`, `reasoning_mode`, `records_schema`, `n_samples_per_task`,
`golden_set`, `judging_era` and `judging_era_source` (the judge configuration the arm was scored under and the kind of
record it was read from). The header carries the published arm set (`board_arm_set`: count and ids) and the row count.
**`models.jsonl`** maps model stems to families and parameter counts.

## Results

Per published fit, under `results/served/<fit>/` (`board_top` is wave 1+2, `old` wave 1 alone, `top` wave 2 alone,
`golden` the golden set):

| file | content |
|---|---|
| `cells.csv` | `arm, task_id, difficulty_z, difficulty_sd, failures, attempts` — the fit's input; `arm` as in the crossings table |
| `crossings_of_record.csv` / `.json` | one row per arm: the two crossings, intervals, censoring status as a token (`point`, `bound`, `unresolved`), dispersion, diagnostics |
| `gates_summary.json` | sampler and concentration gates per arm, with two notes stating the gate convention and the all-fail-share diagnostic |
| `meta.json` | the fit's frame: dataset, population, counts of arms, tasks and cells, the axis definition and smoothing recipe with the per-task moves it caused, the estimator label, the engine hash, the arms fitted |
| `manifest.tsv` | the arms fitted and whether each is served |
| `arm_ids.json`, `axis_export.csv` | the arm list (from the cells table) and the exported difficulty axis: per task its position `z_hat`, its `se`, the arms holding it, the total attempts, the resolution limit, the per-task and per-arm smoothed positions and the move between them, the smoothing recipe and the pooled-count sd |

Arm names in these tables are the model stem with a protocol suffix (`_temp_<t>` for a sampling temperature, `_batch` for
an API batch run); a suffix after `@` (for example `@768-marker`) names the output-cap variant of the same protocol under
which those attempts were generated. `gates_summary.json` carries per arm the sampler gates (`half_pct_gate`, `rhat_gate`,
`ess_gate`, `strict_gate`, the failed gates), the share of all-fail cells and two sentences describing a failed gate
(`mixing_disclosure_long`, `mixing_disclosure_short`).

`results/served/serving_*.json` are pointers: which fit directory each view of the site copies reads, with its counts.
`results/served/fit_exclusions.json` lists the arms excluded from the difficulty axis with the kind of defect (none at
the snapshot) and the arms whose earlier exclusion was cleared. `results/per-task/` holds the task-difficulty tables on
wave 1 under both scorers and the per-arm per-task failure matrix on wave 1 (`fail_counts_matrix.csv`: `benchmark, task,
model, fails, n`). `results/per-attempt/wave1_<benchmark>.csv.gz` holds `arm_id, task_id, attempt, base_status,
plus_status` for every attempt of every published arm on that benchmark; a status is `pass`, `fail` or `timeout` (the
judge's per-test time limit was hit). `results/board/board_numbers.jsonl` holds, per published arm and source benchmark,
the task and attempt counts and pass@k for k = 1, 10 and 100 on the base tests and on both test sets, recomputed from the
per-attempt verdicts with the unbiased estimator (its header states the formula).

## Invariants

- The per-attempt verdicts and the cells are exported from judged files that are byte-format-identical to the pinned
  harness's own output, so anyone with the harness at the pinned commit and the model outputs reproduces every judged
  number; the judged files themselves are not in this repository.
- A new task is identified by `(task_id, content_sha256)`; a changed task gets a new hash and its certificate records
  the previous one. A judged cell belongs to the version whose hash it carries.
- Set membership is the frozen list in `tasks/sets.json`; a task is in wave 2 or in wave 2 parked, never both.
- Every number in the Markdown files is computed from these files by the build (`docs/numbers.json`).

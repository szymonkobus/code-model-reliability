# code-model-reliability

How capable and how reliable are code models? This repository measures both on one scale of task difficulty:

- **Capability (D50)** is the task difficulty at which a model's failure rate crosses one half.
- **Reliability (D99)** is the task difficulty at which its failure rate crosses one in a hundred.

Both are read from a Bayesian failure-against-difficulty curve fitted to many judged attempts per task on two
task sets, wave 1 (the kept tasks of two public Python benchmarks) and wave 2 (new tasks built for the whole
difficulty range), together wave 1+2. A model runs every task many times, every attempt is judged by executable
tests, the judged counts per task are the cells the curve is fitted to, and the two crossings are read from the
curve. The published fit covers 64 arms (a model under one generation protocol) on 1,297 tasks,
76,591 cells and 8.3 million attempts.

Every number in this file is written by the build from the data it ships beside; `docs/numbers.json` lists them.

## What is here

```
src/code_model_reliability/        the pipeline, one sub-package per stage (below); cmr is its command, short for code-model-reliability
data/tasks/                        the task sets: membership, texts or pointers, certificates, attribution, labels
data/runs/registry/                the arms, the models, the protocols, the names of the models trained here
data/runs/pooling_rules.json       how several judgings of one task pool into a cell
data/results/published/<fit>/      the published fit: cells, difficulty scale, crossings, gates, per-arm summaries
data/results/per-attempt/          the verdict files of record of every published arm on the wave 1 tasks of the published fit, one row per attempt
docs/                              method, data contract, the task sets, judging, generation, figures and pages, glossary
docs/site/                         the two pages, built from the published fit
site/                              the two page shells as source
cluster/                           Slurm templates for generation, judging, fitting and the tests
studies/                           the studies a published number or rule rests on, each with its recomputing script
tests/                             the tests, on a three-task fixture set with a stand-in for a model
```

## The pipeline

`cmr <stage>` runs each stage; `pip install -e .` installs the package and the command (Python 3.11 or later).

| stage | what it does | reads | writes | runs where |
|---|---|---|---|---|
| `tasks` | the task sets, their provenance and verification (`cmr tasks summary`, `verify`, `attribution-table`), and the pointer tasks' recovery from their upstream datasets (`cmr tasks convert`, `rebuild-restricted`) | `data/tasks/` | nothing | anywhere |
| `generate` | a model answers every task many times under one protocol (`cmr generate run --model … --tasks … --protocol …`) | the task set, a model | samples per arm | a GPU machine (`cluster/generate.sbatch`), or a provider's batch interface (`cmr generate api …`) |
| `judge` | every attempt runs against its task's tests under the pinned harness (`cmr judge --tasks … --samples … --out …`) | the samples | verdicts per arm with their settings | a CPU machine (`cluster/judge.sbatch`) |
| `land` | verdicts become cells and the arm registry (`cmr land cells …`, `cmr land registry …`) | the verdicts | `cells.csv`, the registry | anywhere |
| `fit` | the difficulty scale, the failure curve per arm, its gates and crossings (`cmr fit all --cells … --fit-dir …`) | `cells.csv` | a fit directory | a CPU machine, hours an arm with the published settings (`cluster/fit.sbatch`) |
| `plot` | the two figures (`cmr plot`) and the two pages (`cmr site`: the shells under `site/` plus the data bundles) | the published tables | `figures/`, `docs/site/` | anywhere |

`docs/data-contract.md` names every file between the stages and its shape; `docs/method.md` defines the quantities
and the estimator; `docs/tasks.md` says how the task sets were built, screened, certified and audited;
`docs/judging.md` and `docs/generate.md` say what the judge and the generation ran with; `docs/plot.md` says what
the figures and the pages show and how they are built; `docs/glossary.md` defines every term once.

## The task sets

Every task was read by its description, tests and reference and given one audit label (regular, tricky,
underspecification or contradiction; `docs/tasks.md`); the regular and tricky tasks are kept. The published fit
stands on the 1,297 tasks that had judged attempts when it was cut: the 1,288 kept tasks of wave 1
and wave 2, and 9 tasks the audit set aside after the cut, listed with their labels under
`tasks_fit_not_kept` in `docs/numbers.json`; a fit on the kept tasks alone is `cmr fit` over their cells.

| set | tasks | kept by the audit | what it is |
|---|---|---|---|
| wave 1 | 430 | 430 | the tasks kept from two public Python benchmarks; shipped as ids, the texts from the pinned harness |
| wave 2 | 869 | 858 | the new tasks in the published fit; 774 as full text, 95 as pointers whose upstream terms do not permit republishing statements |
| wave 2 parked | 893 | 879 | new tasks run with the same protocol but kept out of the fit; 654 as text, 239 as pointers |

`data/tasks/sets.json` is the membership of record with a hash per list; `cmr tasks verify` checks every record and
list against it; `cmr tasks rebuild-restricted` recovers the pointer tasks from their upstream datasets. Where
every task comes from, and under which licence its text travels, is in `data/tasks/attribution.jsonl` and the
table in `DATA-LICENSE.md`.

## What ships of the data, and what does not

Shipped, under `data/`: the task sets as above; the arm registry (every published arm with its model, protocol,
judging settings and extractor), the models, the protocol table and the names of record of the models trained in
this project whose arms the published fit carries — no arm outside the published fit appears in any table, so every
row leads to a published result; the published fit, `data/results/published/3076d2cb247c/`: its cells (failures out of attempts per arm and task), the
difficulty scale with its panel, the crossings table, the gates, and a draw-free summary per arm (the fitted curve
with its band, the per-level crossings and their densities) that the figures and pages read; and the verdict files
of record of every published arm on the wave 1 tasks of the published fit, `data/results/per-attempt/`, one row per
attempt (pass or fail on the base tests and on the extended tests, from which the pass@k figures recompute). Where
a cell was topped up after its verdict file of record was judged, its count in the cells exceeds its rows there, and
the manifest beside the tables says by how much per arm.

Not shipped, with the reason: the text of the models' attempts (several gigabytes; the providers set different
terms on redistributing their models' output, and the judged outcomes suffice to re-fit every curve); the
per-attempt verdicts of wave 2 (several judgings pool into one cell there, and the cells carry the counts); the
posterior draws of the fits (11 MB an arm, regenerated by `cmr fit`); and the task texts whose upstream terms do
not permit republishing them, which ship as pointers.

## Reproducing a published row

1. **Re-fit one arm from the published cells** (CPU only). `<arm>` is an id from the first column of
   `crossings.csv`, for example `Qwen--Qwen2.5-7B-Instruct_temp_0.8`:
   ```
   pip install -e '.[fit]'
   cmr fit inputs --cells data/results/published/3076d2cb247c/cells.csv --axis data/results/published/3076d2cb247c/axis.csv --fit-dir fits/mine
   cmr fit run --inputs fits/mine/inputs/<arm>.npz --out fits/mine/posterior_summary_<arm>.json --eiv on
   cmr fit crossings --results fits/mine --out-dir fits/mine
   ```
   `--eiv on` carries each task's difficulty uncertainty into the fit (the errors-in-variables term, `docs/method.md`),
   as the published fits did. The engine's defaults are the published settings (four chains, two thousand warm-up
   and eight thousand kept draws, target acceptance 0.995); with them a fit takes hours an arm on four cores, and
   the crossings match the published row up to Monte Carlo error, exactly when the pinned libraries are used.
   `--chains 2 --warmup 300 --samples 300` gives a rough answer in minutes.
2. **Re-draw the figures and the pages**: `cmr plot --data data --out figures` and `cmr site --data data --out docs/site`.
3. **Re-generate and re-judge**: `cmr generate` on a GPU machine or through a provider's batch interface, then
   `cmr judge` and `cmr land`; `docs/generate.md` and `docs/judging.md` give the settings every published attempt
   was produced and judged with, and `data/runs/registry/protocols.tsv` the protocol of every arm.

## Tests

`pip install -e '.[test,fit]'` then `pytest tests` runs the unit tests of every stage on the fixture set under
`tests/fixtures/` (a three-task set with a deterministic stand-in for a model) and the end-to-end smoke
(`tests/test_pipeline.py`: generate, judge, land, fit at short chains, plot, site). The judge's tests need the
pinned harness (`pip install -e '.[judge]'`); the engine's own tests run when `CMR_FIT_ENGINE_TESTS=1` is set,
on a cluster node with `cluster/tests.sbatch` or on any machine with the fit extra and some minutes.

## Licences and citation

`LICENSE` (code, MIT), `DATA-LICENSE.md` (tasks, labels and result tables, CC BY 4.0, with the per-source
attribution table), `CITATION.cff`.

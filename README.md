# code-model-reliability

A benchmark of how capable and how reliable code models are, measured on two task sets, wave 1 and wave 2.

- **Capability** is the task difficulty at which a model's failure rate crosses one half.
- **Reliability** is the task difficulty at which its failure rate crosses one in a hundred.

Both are read from a Bayesian failure-versus-difficulty curve fitted to many attempts per task: every model runs
every task 128 times on wave 1 and 32 to 256 times on wave 2 (answers truncated at the output
limit were re-run to completion, so some tasks carry more attempts), every attempt is judged by executable tests, and
the judged counts per task are the data the curves are fitted to. This repository holds the task sets, the generation
and judging code, the fitting engine, the published result tables with the per-task cells behind them, and offline
figure scripts. It is a snapshot import; the sections below say what each part is and how far it has been exercised.

## The task sets

| set | tasks | what it is |
|---|---|---|
| wave 1 | 431 | the tasks kept from two public Python benchmarks after the task audit |
| wave 2 | 869 | the new tasks in the published fits (861 kept by the audit) |
| wave 2 parked | 893 | new tasks run with the same protocol but kept out of the fits for now (885 kept by the audit) |
| wave 1+2 | 1297 | the population the published fit stands on |

The split of the new tasks into wave 2 and wave 2 parked is fixed by a frozen membership list (`tasks/sets.json`, with a
hash of every list); wave 2 never includes the parked tasks, and the new tasks together are 1762.

## What is measured, in one table

The published fit on wave 1+2 covers 59 arms (a model under one generation protocol) on
1297 tasks, 70157 cells of judged attempts, 7.4 million
attempts in all. Its crossings are in `results/served/board_top/crossings_of_record.csv`, one row per arm:

| column | meaning |
|---|---|
| `d50_of_record_z` | capability: the difficulty at which the fitted failure curve crosses one half |
| `d1_of_record_z` | reliability: the difficulty at which the fitted average failure rate crosses one in a hundred |
| `d1_of_record_cri80_lo`, `d1_of_record_cri80_hi` | the 80% credible interval of the reliability crossing |
| `d1_of_record_status` | `point` (the crossing lies inside the observed difficulty range), `bound` (the curve is still above one in a hundred at the easiest task, so the value is a bound), or `unresolved` (the interval is wider than the reporting bandwidth) |

Difficulty is in the fit's internal unit: standard deviations of the task-difficulty scale defined in `docs/method.md`,
larger meaning harder. `figures/capability_vs_reliability.py` draws the table.

## Reproduce

Three levels, from cheap to expensive.

1. **Re-fit from the published cells** (CPU only; about 5.0 hours per arm on four cores with the
   settings the published fits used, `--chains 4 --warmup 2000 --samples 8000 --target-accept 0.995`; the engine's
   defaults are quicker and rougher):
   ```
   pip install -r requirements.txt
   python3 analysis/fitting/cells_to_npz.py --fit board_top --arm <arm> --out /tmp/arm.npz
   uv run analysis/fitting/bayes_full.py --run --eiv on --inputs /tmp/arm.npz --out /tmp/arm.posterior.json \
       --chains 4 --warmup 2000 --samples 8000 --target-accept 0.995
   ```
   `<arm>` is a value of the `arm` column of `cells.csv` (`cells_to_npz.py --list` prints them). The engine's PEP 723
   header pins numpy, scipy, numpyro and jax; `uv run` resolves them. Compare `estimands.d50.median_z` (capability) and
   `estimands_avg.d1.median_z` (the reliability reading of record; `estimands.d1` is the median-task reading) with the
   arm's row in `crossings_of_record.csv`.
2. **Re-draw the figures**: `python3 figures/capability_vs_reliability.py` and
   `python3 figures/failure_vs_difficulty_cells.py --arm <arm>` read `results/` and write PNGs into `figures/`.
3. **Re-generate and re-judge**: `runs/generate/cluster` holds the vLLM job runner and the environment builder that pins
   the judge harness by commit; `runs/generate/api` holds the batch generators for API models (keys from environment
   variables); `runs/judge` holds the judge as invoked. These are the scripts as run on a Slurm cluster and read the
   cluster's host, base directory and environment from variables (`runs/README.md` lists them); they need pointing at
   your own environment before they run.

## Layout

```
docs/            method, data contract, how the new tasks were built, related work, two stand-alone site copies
tasks/           sets.json (the membership of record); wave1, wave2, wave2-parked; labels; certificates; the rebuild script
runs/            the arm registry; generation, judging and landing code
analysis/        the difficulty axis, the fitting engine and its gates, the fitting-method comparison, task-set scripts
results/         per published fit: crossings, gates, meta, manifest, cells; per-task tables; per-attempt verdicts; pass rates
figures/         offline figure scripts
deep-dives/      scripts of the studies behind the published numbers, one folder per question
```

## What ships of each set

- **Wave 1**: task ids and audit labels (`tasks/wave1`, `tasks/labels`); the texts come from the pinned judge
  harness. `results/per-attempt` holds the verdict of every attempt of every published arm on wave 1
  (4.0 million rows; 59 arms on the first source benchmark,
  58 on the second, one arm having run the first only).
- **Wave 2** (`tasks/wave2`): 774 tasks as full text in `tasks-part-*.jsonl.gz` and 95
  (11%) as task ids, content hashes and upstream pointers in `restricted.jsonl`, because their
  upstream source does not permit republishing statements. 866 of the 869 had judged cells
  in the published fit at the snapshot.
- **Wave 2 parked** (`tasks/wave2-parked`): 654 tasks as full text and 239 as pointers
  (238 for the same licence reason, 1 because a random test-input string
  tripped the content scrub).
- `tasks/rebuild_restricted.py` rebuilds and verifies every pointer task from the upstream datasets; `docs/wave2.md`
  describes how the new tasks were acquired, screened, certified and audited.

## Status of this import

Snapshot taken on 16 September 2026 by an allowlist copy and re-cut on 22 September: 2985 files, 128 MB.
Code is as it ran, with the environment it ran in read from variables and working notes removed. The project's
operations code (landing loops, pollers, page composers, store readers) is not included. Scripts are included where they
document a computation of record even when their inputs are not: a script that reads a fit's posterior draws, a study's
intermediate tables or the run store fails on its first read here, and each folder's README says which inputs are not
included. The fitting engine, the figure scripts and the task exports were exercised on this tree; the generation and
judging scripts were not.
Licences: `LICENSE` (code, MIT) and `DATA-LICENSE.md` (tasks and tables, CC BY 4.0, with the per-source attribution
table). Every number in this file and in the other Markdown files is computed from the tree by the build and recorded
in `docs/numbers.json`.

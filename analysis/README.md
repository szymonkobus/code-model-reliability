# Analysis: difficulty, fitting, methods

- `difficulty/` — tables behind the difficulty axis: task statistics per source benchmark, a cross-cut table, and the
  tables of the item-response comparison (`irt/`: per-task parameters and scores, per-model ability from a
  two-parameter fit). `docs/method.md` describes the construction of the axis itself.
- `fitting/` — the estimator of record. `bayes_full.py` is the engine (a self-contained script whose header pins numpy,
  scipy, numpyro and jax; `uv run` resolves them); `gates_summary.py` computes the sampler and concentration gates. The
  scripts that assembled a fit's inputs from the private run store and served the results are operations code and are
  not included; the inputs they produced are the published `cells.csv` tables. The arms excluded from the difficulty
  axis are listed in `results/served/fit_exclusions.json`.
  `cells_to_npz.py` (added for this repository) turns an arm's rows of a published `cells.csv` back into the engine's
  input arrays, so any published arm can be re-fitted:
  ```
  python3 analysis/fitting/cells_to_npz.py --fit board_top --arm Qwen--Qwen2.5-7B-Instruct_temp_0.8 --out /tmp/arm.npz
  uv run analysis/fitting/bayes_full.py --run --eiv on --inputs /tmp/arm.npz --out /tmp/arm.posterior.json \
      --chains 4 --warmup 2000 --samples 8000 --target-accept 0.995
  ```
  With those settings, the ones the published fits used, a fit takes about 5.0 hours per arm on four
  CPU cores; the engine's defaults (four chains of one thousand warm-up and one thousand draws) give a rougher answer in
  a fraction of that.
- `fit-methods/` — what is included of the comparison of fitting schemes that chose the estimator above: the
  extreme-value collapse check, the level-pair plane, the trace analysis and a replication report script.
- `investigations/` — three method studies with their code: the linearity of the capability-reliability relation,
  the mathematics of the failure curve and its crossings, and the experiment-design study of attempts per task
  against tasks per fit.

The scripts that drove the project's operations (its run store, its served pages, its landing loops) are not included, so
a folder here may hold part of a study's code. The scripts of `fit-methods/` and of the three investigations are the
record of each method as it ran: they read a fit's posterior draws, a study's intermediate tables or a sibling data
folder that this repository does not include (the four fit-methods scripts take `analysis/` as their base folder and
look for `data/` and `fits/` there), so they fail on their first read here and document the computation rather than
reproduce it. The published numbers each study produced are in `results/`.

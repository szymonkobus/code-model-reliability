# Method: difficulty, the two crossings, and the fit

This document defines the quantities the result tables report and describes the estimator that produces them. The code
it describes is in `analysis/`.

## Tasks, attempts, cells

A task is a Python function to write, judged by executable tests: the base tests of the source benchmark and an extended
test set (wave 1 uses the extended tests of the two source benchmarks through the pinned judge harness; wave 2 tasks
carry their own base and extended inputs with expected outputs, see `docs/wave2.md`). An attempt passes when every test
passes. A model runs each task many times at a fixed sampling temperature: 128 attempts per task
on wave 1 and 32 to 256 on wave 2; answers truncated at the output limit were re-run to completion, so some tasks carry
more attempts. The judged count for one arm on one task, failures out of attempts, is a **cell**. The per-arm cells of
each published fit are in `results/served/<fit>/cells.csv`; the per-attempt verdicts on wave 1 are in
`results/per-attempt/`.

An **arm** is a model under one generation protocol (temperature, thinking mode, output budget).
`runs/registry/arms.jsonl` lists every arm with its protocol and its judging era, the version of the judge configuration
the arm's attempts were scored under.

## The difficulty scale

Task difficulty is defined from the population of arms, not from any one model: it is the average arm's failure rate on
the task (an equal-weight mean over the arms that ran it, with one Jeffreys pseudo-observation), transformed to a
logit-like scale and standardised, so that difficulty is in standard deviations of the population's spread and larger
means harder. Every task in a fit has a difficulty estimate and an uncertainty (`difficulty_z`, `difficulty_sd` in the
cells table). Arms with a known protocol defect are excluded from the axis population; `results/served/fit_exclusions.json`
lists them with the kind of defect (none at the snapshot; two arms excluded earlier were cleared). The construction and its alternatives are worked out in `analysis/difficulty/`.

## The failure curve

For each arm, the probability of failing a task is modelled as a smooth function of the task's difficulty, with a
per-task deviation: tasks at the same difficulty do not fail at the same rate, and the model carries that spread
explicitly (a between-task dispersion and an intraclass correlation, reported in the crossings table as `tau_median`,
`tau_cri80_lo`, `tau_cri80_hi` and `rho_icc_median`, `rho_icc_cri80_lo`, `rho_icc_cri80_hi`). The curve is a
Gaussian-process prior on the logit failure rate, approximated by a Hilbert-space basis whose size follows the axis
half-width (`m_basis`, `hsgp_L`), fitted by Hamiltonian Monte Carlo. The published fits used four chains with two
thousand warm-up and eight thousand kept draws each at a target acceptance of 0.995; the engine's defaults are smaller
and quicker. The difficulty uncertainty of each task enters the likelihood (the errors-in-variables option `--eiv on`).
The engine is `analysis/fitting/bayes_full.py`; its header pins the numerical libraries so reruns are bit-for-bit
reproducible in the same environment.

## The two crossings

- **Capability** (`d50_of_record_z`): the difficulty at which the arm's fitted failure curve crosses one half. It is the
  single number most like a benchmark score, read on the difficulty scale instead of as a pass rate.
- **Reliability** (`d1_of_record_z`): the difficulty at which the arm's fitted average failure rate crosses one in a
  hundred. Two readings are carried: the average-rate reading (of record) and the median-task reading
  (`d1_median_task_z`), which differ when failures concentrate on few tasks. When the curve is still above one in a
  hundred at the easiest observed task, the crossing is censored and reported as a bound (`d1_of_record_status` is
  `bound`, with `d1_of_record_bound` and `d1_of_record_p_left_censored`); when the 80% interval is wider than the
  reporting bandwidth of one internal unit the status is `unresolved`; otherwise `point`.

Each crossing carries an 80% credible interval from the posterior draws, and mixing diagnostics for the crossing itself
(`crossing_rhat_50`, `crossing_ess_50`, `crossing_rhat_1`, `crossing_ess_1`).

## Gates

A fit is served only if its sampler diagnostics pass: no divergences, split R-hat under 1.01, bulk effective sample size
above 400, and a check that failures are not concentrated on the easiest third of tasks. `results/served/<fit>/gates_summary.json`
records the outcome per arm and `analysis/fitting/gates_summary.py` computes it. A failed gate does not delete the arm;
the crossings table keeps the row, and the site copies in `docs/site` show such arms apart.

## What a re-fit reproduces

`analysis/fitting/cells_to_npz.py` turns an arm's rows of `cells.csv` back into the engine's input arrays, and
`bayes_full.py --run` produces the posterior summary (estimands, draws, curve grid). With the published settings a fit
takes about 5.0 hours per arm on four CPU cores (the median of the sampling times recorded for the
published arms; the longest took 16.1); the crossings then match the published row up to Monte Carlo
error, and exactly when the same library versions are used. The engine's defaults run in a fraction of that with a
rougher answer.

## Sources in this repository

`analysis/difficulty/` (axis and metrics code), `analysis/fitting/` (engine, wave builder, gates), `analysis/fit-methods/`
(the comparison of fitting schemes that chose this estimator), `analysis/investigations/` (the linearity of the
capability-reliability relation, the curve mathematics, the experiment-design study).

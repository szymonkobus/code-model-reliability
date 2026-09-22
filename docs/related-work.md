# Related work and the case for measuring reliability

Most code benchmarks report a pass rate: the share of tasks a model solves, usually at one attempt or as pass@k. A pass
rate answers how capable a model is on the benchmark's tasks. It says little about the question that decides
deployment: when a model almost never fails a kind of work, how often does it still fail, on what, and does that change
as models grow. A model right 99% of the time is deployed or not on what the remaining 1% is.

## What the neighbouring literatures measure

- **Capability benchmarks and scaling laws** study the tasks models mostly fail and how the pass rate moves with scale.
  The reliability question lives at the other end of the difficulty range, on the tasks models mostly solve.
- **Inference-compute and best-of-n studies** show that repeated sampling raises pass@k, which measures how often at
  least one attempt succeeds; reliability is about the attempts that fail when the model was expected to succeed.
- **Evaluation statistics and calibration** work quantifies uncertainty of benchmark scores and the calibration of a
  model's own confidence; the difficulty scale used here is an item-response-style construction (task difficulty from
  the population of models) applied to executable-test outcomes.
- **Rare-event and tail estimation** and **reliability engineering** provide the vocabulary: failure rates at fixed
  tolerances, censoring when no failure is observed, and the distinction between a rate and a worst case.
- **Benchmark design** work on test adequacy and contamination motivates the extended tests, the task audit and the
  content-hash versioning used here.

`docs/papers.bib` lists the references read for this project, grouped by these themes.

## What this benchmark adds

Two numbers on one difficulty scale for every arm: the difficulty at which the failure rate crosses one half
(capability) and the difficulty at which it crosses one in a hundred (reliability), each with an interval, from a fit
that models the spread between tasks at the same difficulty rather than averaging it away. The design choices that
follow from the question: many attempts per task rather than one, so that a one-in-a-hundred rate is observable;
an easy tail of tasks, so that the reliability crossing sits inside the observed range; executable tests with an
extended test set, so that a pass is a program that works rather than one that passes a few examples; a task audit,
so that a residual failure belongs to the model rather than to the task; and a Bayesian curve fitted per arm, so that
the crossing at one in a hundred is estimated with its uncertainty instead of read off a noisy empirical rate.

## What the data show so far

The rare failures of capable models are not noise: they sit in particular tasks and are mostly deterministic wrong
programs, so re-running does not buy the missing reliability. As models grow, each task's success probability
sharpens toward all-or-nothing, and the residual failures increasingly belong to the benchmark rather than to the
model, which is why the task audit is part of the method. The relation between the two crossings across arms is close
to linear on the logit-difficulty scale; whether reliability improves on the same schedule as capability is the question
the published fits are built to keep answering as models are added.

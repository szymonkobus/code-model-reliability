# Method: the difficulty scale, the failure curve and its two crossings

This document states how the published numbers are made, in the order the fit stage computes them: the
difficulty of a task, the failure curve of an arm, the two crossings read from it, and the checks a fit passes.
The code is `src/code_model_reliability/fit/`; every constant named here is a named constant there.

## 1. What is measured

**Capability crossing, D50** — for one model, the fitted curve gives at every difficulty $d$ the share of the
model's answers that fail, $q(d)$; D50 is the difficulty where $q(d) = 50\%$. A position on the difficulty axis,
read in logit. **Reliability crossing, D99** — the difficulty where $q(d) = 1\%$, one answer in a hundred failing.
**Difficulty** of a task — the share of attempts that fail on it across the models of the panel, each model
counted once: the mean of the models' failure rates on the task, shrunk by one pseudo-observation of half a
failure and half a pass over the task's attempts, drawn on the logit scale (equal distances are equal odds
ratios). Results held out for want of a valid verdict do not count; the record of the recipe is the fit's
`panel.json`.

Difficulty is in logit units throughout: a task at $z$ has a panel-average failure rate of
$\mathrm{logistic}(z) = 1 / (1 + e^{-z})$, which the pages print as a percentage from 0 to 100%.

## 2. The difficulty scale (`axis.py`)

For a task with panel arms $a = 1..M$, each with $f_a$ failures of $n_a$ attempts, and $N = \sum_a n_a$:

$$\bar p = \frac{1}{M}\sum_a \frac{f_a}{n_a}, \qquad q = \frac{N\bar p + \tfrac12}{N + 1}, \qquad z = \log\frac{q}{1-q}.$$

The standard error of $z$ is the estimator's own. With $v_a = (f_a + \tfrac12)(n_a - f_a + \tfrac12) /
((n_a+1)^2 (n_a+2))$ for an arm with $0 < f_a < n_a$, and $v_a = q(1-q)/n_a$ for an arm whose own data cannot
estimate a rate (every attempt failed or every attempt passed):

$$\mathrm{Var}(\bar p) = \frac{1}{M^2}\sum_a v_a, \qquad \mathrm{se}_q = \frac{N}{N+1}\sqrt{\mathrm{Var}(\bar p)}, \qquad \mathrm{se}_z = \frac{\mathrm{se}_q}{q(1-q)}.$$

The arms' spread about their mean is part of the quantity, not measurement noise. A count-based position is
reliable within about $\log(2N+1)$ logit of the ends of the scale; beyond that the joint fit places the task
through the errors-in-variables term.

The panel. An arm votes on the scale when it has attempts on at least nine tenths of the set's tasks
(`COVERAGE_THRESHOLD`); nothing else excludes an arm from voting. Every arm with cells is fitted and placed on the
scale whether or not it votes, and an arm that is a fine-tune of another is placed without voting. The published
wave 1+2 scale was set by 51 arms over 1,297 tasks; 59 arms were fitted on it. The panel of a fit is written
beside its axis (`panel.json`: the threshold, the voters, the arms placed without voting, every arm's coverage).

The scale is one scale for every arm of a fit: no arm is placed on a scale built without it as a reading, and a
trend read along the axis is stated with what the scale's construction does to it.

## 3. The failure curve of an arm (`engine.py`)

For one arm and its tasks $t = 1..T$: $f_t$ failures of $n_t$ attempts, and the task's difficulty estimate
$\hat z_t$ with its standard error $s_t$ from the axis.

$$z_t \sim \mathrm{Normal}(\hat z_t, s_t)$$
$$g(z) = \mu_0 + \mu_1 z + \mathrm{GP}(z;\ \eta, \ell)$$
$$u_t = \tau\, u^{\mathrm{raw}}_t, \quad u^{\mathrm{raw}}_t \sim \mathrm{Normal}(0, 1)$$
$$f_t \sim \mathrm{Binomial}\big(n_t,\ \mathrm{logistic}(g(z_t) + u_t)\big)$$

$g$ is the logit failure rate as a smooth function of difficulty: a line plus a squared-exponential Gaussian
process with amplitude $\eta$ and length scale $\ell$, the process approximated by a Hilbert-space basis of $m$
sine functions on $[-L, L]$ (Riutort-Mayol et al. 2023). $u_t$ is the task's own deviation from the curve.
Priors: $\eta \sim \mathrm{HalfNormal}(2)$, $\ell \sim \mathrm{LogNormal}(\log 1.1, 0.5)$, $\mu_0 \sim
\mathrm{Normal}(0, 3)$, $\mu_1 \sim \mathrm{HalfNormal}(3)$, $\tau \sim \mathrm{HalfNormal}(1)$, the basis
weights $\mathrm{Normal}(0, 1)$. The domain is the task range widened by three times the largest standard error
and expanded by one and a half about its centre; $m = \max(40,\ 10\lceil 1.75 L / 4\rceil)$, the adequacy rule
for a squared-exponential kernel at the prior's 2.5th-percentile length scale of 0.4 (60 basis functions on the
wave 1+2 fit, where $L = 13.27$).

Inference is NumPyro's NUTS with four chains of 2,000 warm-up and 8,000 kept draws, target acceptance 0.995,
tree depth 10, seed 20260825 (`rules.py`). The target acceptance is higher than NumPyro's default because at
0.9 the chains diverged on arms whose tasks are nearly all failed or all passed.

Two curves are read from every draw. The **median-task curve** is $\mathrm{logistic}(g(z))$, the failure rate of a
task with no deviation. The **average-rate curve** is $\mathbb{E}_u[\mathrm{logistic}(g(z) + \tau u)]$ with
$u \sim \mathrm{Normal}(0,1)$, by 21-point Gauss-Hermite quadrature: the share of all attempts expected to fail
at difficulty $z$. D50 and D99 are read from the average-rate curve; the median-task D99 is carried beside it.
Beside D99, the same curve's crossings at 3%, 5% and 10% failure (D97, D95, D90) and at 99% failure (D1, the hard
end of the curve) are written.

Each result file carries the per-draw crossings of the two levels of record, the parameters' draws, a table of
crossings at 352 failure-rate levels, the two curves at seven percentiles on a 121-point grid, and the
convergence statistics. The draws make a file of about 11 MB per arm; the published tables and pages read the
draw-free summary (`summaries.py`, about 60 KB per arm) and the crossings table.

## 4. Reading the crossings (`crossings.py`)

Per draw, the curve's crossing of a level is located on a 1,201-point grid over the observed task range and
interpolated in the logit of the rate between grid points. When a curve crosses a level more than once, the
**middle crossing** counts: the crossings of one draw are the sign changes of (rate − level) along the grid, plus
one at the easy end when the curve is already above the level at the easiest grid point (it crossed below the
easiest task) and one at the hard end when it is still below the level at the hardest grid point (it crosses
beyond the hardest task); that list has an odd length and its middle entry is the crossing. An interior middle
gives its position; the easy-edge one is a draw censored below the scale, the hard-edge one a draw censored
above it. A monotone curve gives its one crossing; a curve above the level everywhere is censored below the
scale; a curve that starts above, dips and rises gives the downward crossing. The earlier rule, the first upward
crossing, is kept as `--crossing-rule first` to reproduce older fits.

The number printed is the median over every draw of the crossing, a censored draw counted beyond the end of the
scale it lies past; the 80% interval is the 10th and 90th percentiles taken the same way, so an interval edge
that falls among censored draws prints as the scale's end. The status is **point** unless more than half of the
draws lie beyond one end: then the crossing is a **bound below** — it lies below the easiest task used, more than
half the draws lie below it, and the value reported is that task's difficulty — or a **bound above** — above the
hardest task used, more than half the draws above it, the hardest task's difficulty reported. Every arm has a
number at every level; a wide interval never removes an arm from a figure, a line or a table. The shares of
draws beyond each end and the median over the uncensored draws alone are kept beside each number.

The crossing of a curve at a failure rate the engine did not export exactly (D1 at 99%) is read from the fit's
level table between the two levels bracketing it, linear in the logit of the level, with the same bound rule.

A fit yields many curves, one per draw. The curves drawn on the pages are the pointwise percentiles of the draws'
curves at each difficulty; the printed D50 and D99 are the median over the draws of where each curve crosses the
level. The two summaries agree wherever every draw crosses the level once; they part where a tail runs flat, and
the printed figure is the crossing. The median at each difficulty answers what failure rate to expect at a
difficulty; the median at each failure rate answers at what difficulty the rate reaches a level, which is what
D50 and D99 are.

## 5. Gates and disclosures (`gates.py`)

A fit serves with its gates disclosed; a failed gate marks an arm's row and never removes it. Three gates decide
the verdict: the sampler's divergent transitions as a share of the kept draws, failing above half a percent (a
handful in 32,000 draws does not move a crossing whose chains agree; the engine's stricter count flag, five or
more, is carried beside as a note); rank-normalised split R-hat of the D50 and D99 crossing draws, per chain, at
most 1.01; bulk effective sample size of the same draws at least 400 (judged on files that carry every draw; a
thinned export's sample size is reported, not gated). A level whose crossing is a bound is exempt from the last two, since constant censored
draws have no mixing to measure. The parameters $\eta$, $\ell$, $\tau$ and $\mu_1$ keep their own R-hat and
effective sample size as a disclosure; on small arms with many all-failed tasks their chains mix slowly while
the crossings themselves agree between chains, and the crossings are what is served.

Concentration is a reading, not a gate. On the easy third of the axis's tasks, the share of an arm's failures
carried by the few most-failed tasks (the top 5% of the easy third, at least one task) classes the arm as
diffuse (under 0.3), intermediate (0.3 to 0.5), concentrated (0.5 to 0.8) or extreme (0.8 and above). On an arm
whose failures sit on a handful of easy tasks, the average-rate curve and a curve through typical tasks read
differently near the 1% level; on synthetic arms of the concentrated shape the average-rate curve reads about
2.6% failure where the truth is 1% and about 32% where it is 50%. The regime is written beside the gates so a
reader can weigh the arm's D99.

## 6. Why this estimator

A single failure rate per arm hides where an arm fails. Placing every task on one difficulty scale and fitting
the failure rate against difficulty gives two positions per arm, read on the same scale for every arm: where it
fails half the time and where it fails one time in a hundred.

The curve is a Gaussian process rather than a parametric form because the logit failure rate is not a straight
line in difficulty for every arm, and a parametric curve forces a shape onto the tail where D99 is read. The
per-task deviation $u_t$ is there because tasks of the same difficulty are not equally hard for one arm: without
it the binomial likelihood is overdispersed and the intervals are too narrow. Carrying the difficulty's standard
error (errors in variables) keeps the easy end of the scale, where positions rest on few failures, from biasing
the slope.

D50 and D99 are read from the average-rate curve because the question is the share of attempts that fail at a
difficulty, which averages over tasks; the median-task curve answers a different question (the failure rate of a
typical task) and is kept beside. The two part on arms whose failures concentrate on a few tasks, which the
concentration reading discloses.

The library pins in `pyproject.toml` (numpy, scipy, numpyro, jax) are part of the method: with them a rerun on
the same machine class reproduces the draws bit for bit; across library versions the crossings move by up to
about 0.05 on the scale, within the published intervals but not identical.

## 7. Reproducing a published row

Every published fit directory carries its `cells.csv`, `axis.csv`, `panel.json`, `gates.json`,
`crossings.csv` and `arms/`, and names the engine that produced its rows by the sha256 of the engine file.
To reproduce one arm:

    cmr fit axis   --cells data/results/served/<fit>/cells.csv --out fits/check/axis.csv --panel data/results/served/<fit>/panel.json
    cmr fit inputs --cells data/results/served/<fit>/cells.csv --axis fits/check/axis.csv --fit-dir fits/check --arm <arm>
    cmr fit run    --inputs fits/check/inputs/<arm>.npz --out fits/check/posterior_summary_<arm>.json
    cmr fit gates  --results fits/check --inputs fits/check/inputs --axis fits/check/axis.csv --out fits/check/gates.json
    cmr fit crossings --results fits/check --gates fits/check/gates.json --out-dir fits/check

The axis must equal the published `axis.csv` to the printed precision, and the arm's row must equal the
published one within Monte Carlo error (a different machine class) or exactly (the same class and pins). A
full-length fit of an arm with about 1,300 tasks takes a few hours on 16 cores; `cluster/fit.sbatch` runs a fit's
manifest as a Slurm array. `cmr fit run --self-test` checks the engine itself in minutes: the prior spans under
1% to over 99% failure, and a synthetic arm drawn from the model is recovered.

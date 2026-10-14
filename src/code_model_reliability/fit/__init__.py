"""The difficulty scale, the failure curve per arm, its gates and its two crossings.

``axis``: a task's difficulty is the mean over the panel arms of each arm's failure rate on it, shrunk by one
pseudo-observation of half a failure and half a pass over the task's attempts, on the logit scale, with the
estimator's own standard error; the panel is every arm with attempts on at least nine tenths of the set's
tasks. ``inputs``: an arm's cells and the axis become the engine's arrays. ``engine``: a line plus a
squared-exponential Gaussian process for the logit failure rate, a deviation per task and the difficulty's
standard error in the likelihood, sampled by Hamiltonian Monte Carlo with the settings of record; its numerics
and library pins are those of the fits that produced the published tables. ``gates``: divergences, split R-hat
and effective sample size of the crossing draws, with the concentration reading beside. ``crossings``: D50 and
D99 read from the average-rate curve as the median over every draw with the censored draws beyond the ends of
the scale, their 80% intervals and bound statuses, the median-task D99 beside. ``summaries``: the draw-free
file per arm the figures and pages read.

Reads ``cells.csv``. Writes ``fits/<fit>/``: ``axis.csv`` and ``panel.json``, ``inputs/`` and ``manifest.tsv``,
the posterior summaries, ``gates.json``, ``crossings.csv`` and ``crossings.json``, and ``arms/``. The command
line is ``cmr fit <step>``; see ``command``.
"""

from .command import main  # noqa: F401

__all__ = ["main"]

# Below the floor: do the failure-rate lines continue below one failure in 128?

## The question

With 128 attempts per task, a task with no failure only bounds its failure rate below about 1 in 128. The failure
rate against difficulty looks straight in logit coordinates down to that floor, and D99 is read where the fitted
curve crosses 1 in 100, close to it. Does the relation continue below the floor, where no single task's attempts can
see it?

## The answer

Yes, as far as the tasks allow it to be tested. One arm, Qwen3 4B (`Qwen--Qwen3-4B_temp_0.8`), was run on from 128 to
10,112 attempts per task across wave 1: 78 repeats of the published run under the same protocol, about 5.4 million new
judged attempts over the 542 tasks, every repeat judged under the memory-sound judge configuration; the test reads the
442 tasks kept at that time, about 4.4 million of the new attempts. The prediction was frozen and hashed before any new
attempt was read: per part of wave 1, a straight line in the logit of
the failure rate against difficulty with a beta-binomial scatter layer for the task-to-task spread, fitted on the
128-attempt data with a task-cluster bootstrap. The test window is the difficulty range where the line predicts rates
between one in ten thousand and eight in a thousand; in every populated bin the pooled observed rate lies inside the
line's simultaneous 95% band, and the verdict is HELD on both parts, with and without the five tasks whose verdicts
the judge's limits had moved:

| part of wave 1 | bin | tasks | observed failures of attempts | line's level | band's upper edge |
|---|---|---|---|---|---|
| smaller part | 1 | 7 | 0 of 70,784 | 3 to 9 in 10,000 | 2.3 in 1,000 |
| smaller part | 2 | 6 | 0 of 60,672 | 0.9 to 2.7 in 1,000 | 3.7 in 100 |
| smaller part | 3 | 13 | 10 of 131,456 | 2.7 to 8 in 1,000 | 6.9 in 100 |
| larger part | 1 | 3 | 0 of 30,336 | 0.9 to 2.7 in 1,000 | 2.3 in 10,000 |
| larger part | 2 | 9 | 0 of 91,008 | 2.7 to 8 in 1,000 | 9.6 in 100 |

Of the 247 tasks at zero failures in 128 attempts, 23 showed a failure by 10,112 (rates from 1 in 10,000 to 1.1 in
100); 224 stayed at zero, each with a Jeffreys rate of about 5 in 100,000 per attempt. The heterogeneity persists
below the floor: several mid-difficulty tasks measured a hundred to a thousand times safer than the line's point value,
so a line with a plain binomial band and no scatter layer would have been rejected by the same data. The line
describes the average; individual tasks are near-deterministic. Across the 78 repeats the per-task failure counts are
binomial-consistent (median dispersion ratio 1.0), a bound on how much the judge itself varies between runs.

The claim is bounded by the tasks: no kept task has a line-predicted rate below about 3 in 10,000, so nothing deeper is
tested. The deep attempts cannot be fitted by the published engine as it stands: with per-task rates exact to four
digits the curve and the scatter term become interchangeable and the sampler stalls, which is the same finding by
another route.

## What depends on it

Reading D99 at one failure in a hundred from the fitted curve (`docs/method.md`, sections 3 and 4): the curve's shape
holds below what one task's 128 attempts can resolve, so the crossing read there is a measurement and not an
extrapolation. The per-task deviation term of the model, which lets tasks of the same difficulty differ in failure
rate, is the layer this test needed and the plain line lacked.

## What is here

- `per_task.csv`: one row per task of the frozen frame (442): the task's difficulty on the frozen axis (a snapshot
  taken before the new attempts, with 49 voting arms; not the published axis), the failures and attempts of the
  published 128-attempt run as frozen, and the failures, attempts and repeats of the deep run.
- `frozen_line.json`: per part of wave 1, the frozen two-layer line (intercept, slope, intra-task correlation), the
  plain binomial line beside it, the 200 bootstrap draws, and the test window's bins with their difficulty edges and
  task ids; the seed and the attempts per task.
- `recompute.py` simulates the band from the frozen draws with the study's seed, reads every bin against it, gives the
  verdict, counts the tasks that left the floor, and compares the frozen 128-attempt counts with the arm's published
  cells: they agree on 417 tasks and differ on 2 where a later judge correction moved the cell; 12 parents of folded
  copies pool the copy's attempts and are not compared, and 11 tasks of the frozen frame are not in the published
  fit's cells, the kept set having moved between the frame's cut and the fit's (the script also counts the frame's
  tasks outside the kept list the repository ships, which moves again after a fit is cut).

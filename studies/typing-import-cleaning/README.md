# The typing-import cleaning: a correction applied to two arms before judging

## The question

The two gpt-5 arms (`gpt-5-mini_batch`, `gpt-5-nano_batch`) fail easy wave 1 tasks that most arms of similar
capability pass. Reading their failing attempts on the easy tasks: many refuse an input the hidden tests feed on
purpose (a zero, a negative, a one-element tuple), some give an ordinary wrong answer, and a class of answers opens
with an impossible import line such as `from typing import int`. The typing module exports no such name, so the
program fails at import before any test runs, although the function below the line is usually correct. Is that
failure the model's, or an artefact of how the answer is judged?

## The answer

It is treated as an artefact of the judging and removed before grading. The rule (`typing-builtins-v1`, the code in
`cleaning.py`): in every `from typing import ...` line of an answer, remove the names `int`, `Integer`, `Integral`,
`bool`, `float` and `str`; drop a line that empties, keeping its line break; change nothing else; grade the cleaned
text with the ordinary judge settings. On wave 1 (542 tasks, 128 attempts each, 69,376 attempts per arm):

| arm | attempts carrying such a line | verdicts changed, fail to pass | on the 430 kept tasks | share of all attempts |
|---|---|---|---|---|
| `gpt-5-mini_batch` | 222 | 169 | 137 | 0.24% |
| `gpt-5-nano_batch` | 82 | 60 | 55 | 0.09% |

The 75 attempts that still fail after the cleaning crash or fail for another reason. No other arm carries more than
six such lines. On wave 2 the same cleaning changed 45 attempts of `gpt-5-nano_batch` and 12 of `gpt-5-mini_batch`
on the cells where a verdict before the cleaning exists; 12 further cells of the nano arm (1,920 attempts) and 29 of
the mini arm (5,120 attempts) were judged only under the cleaning, so no earlier verdict exists to count against.

The study also measured what excusing a cause would do to the two arms' reliability crossing on wave 1 under its own
estimator: deleting the import lines moves D99 from 7.5% to 8.3% of the difficulty scale for the nano arm and from
8.4% to 10.0% for the mini arm, while excusing every refusal of an input would move them to 13.7% and 9.4%. Only the
import-line cleaning was adopted; a refusal of an input stays a failure.

## What depends on it

The published cells of the two gpt-5 arms, on wave 1 and wave 2, are graded on the cleaned text, and so are their
crossings. `docs/judging.md` names the typing cleaning among the corrections that live as companion files beside the
verdict files judged by the harness's own evaluator; the judge of this package applies no such cleaning itself.

## What is here

- `cleaning.py`: the rule as code, `clean(program)`; the module is also a command that cleans the `solution` field
  of a samples file. `tests/studies/` tests it on the four shapes of line it meets.
- `carriers.csv`: every wave 1 attempt of the two arms that carried such a line (304 rows): the arm, the task, the
  attempt index, the names removed, the verdict before and after the cleaning, and for an attempt still failing what
  remained (`still crashes`, `another fault remains`).
- `per_task.csv`: per arm and wave 1 task, the attempts and the failures before and after the cleaning.
- `recompute.py` recounts the table above from `carriers.csv`, checks it against the study's record, and compares the
  published cells of the two arms with the cleaned failure counts: they agree on every kept wave 1 task except the
  parents of folded copies, whose published cell pools the copy's attempts, and three tasks where a later correction
  (a float meeting an integer compares within a relative tolerance) moved verdicts after these counts were taken.

# The task audit: which tasks are sound

## The question

A failing attempt measures the model only when the task is sound: its statement, its examples, its reference solution
and its tests have to agree, and the behaviour the tests enforce has to follow from the statement and its examples.
Every task of every set was read for this by readers blind to earlier labels and to each other (they did read the
models' failing attempts, whose mechanisms the full audit takes a census of), and given one of four labels (the method
is in `docs/tasks.md`, section The audit): `regular`, `tricky` (sound, with a trap a careless reading misses),
`underspecification` (the tests require behaviour the statement does not determine) and `contradiction` (the statement,
its examples, the reference or the tests disagree).

## The answer

| set | tasks reviewed | regular | tricky | underspecification | contradiction | kept |
|---|---|---|---|---|---|---|
| wave 1 | 542 | 259 | 171 | 79 | 33 | 430 |
| wave 2 | 869 | 776 | 82 | 10 | 1 | 858 |
| wave 2 parked | 893 | 678 | 201 | 6 | 8 | 879 |

A task is kept when its label is `regular` or `tricky`. Of the 542 original tasks of wave 1, 112 carry a defect label
and leave the measured set; wave 2 loses 11 of 869 and wave 2 parked 14 of 893. Labels moved as later readings landed:
every change is on record in `labels/label_history.jsonl` with the label before and after and the review round, and
the newest change of every task ends at its current label; `recompute.py` counts the changes, the confirmations and
the moves across the keep boundary from the shipped file.

## What depends on it

The measured set of record is the kept tasks of wave 1 and wave 2 together: 430 + 858 = 1,288 tasks.
`data/tasks/sets.json` lists each set's members and kept subset with a hash per sorted list and names the label rule;
`data/tasks/wave-1/kept_tasks.json` carries wave 1's kept ids; every member not kept is listed with its label as the
reason. The labels keep moving as readings land, and a fit is cut from the kept set of its day: the published fit
stands on the tasks kept when it was cut, and a task the audit set aside afterwards stays in its cells until the next
fit (`docs/numbers.json` counts them as `tasks_fit_not_kept` beside `n_tasks_fit` and `n_kept_12`; `recompute.py`
reads them from the cells). A label is per task instance: a reworded copy and its parent are labelled independently.

## What is here

- `recompute.py` recomputes the table above from `data/tasks/labels/labels.jsonl` and checks `sets.json` against it:
  every reviewed task has a label; a task is kept exactly when its label is a keep label; the kept and member lists
  hash to the recorded values; the not-kept lists carry the right reasons; and every task's newest change in
  `labels/label_history.jsonl` ends at its current label. It exits 1 on any mismatch.

The labels and their history ship under `data/tasks/labels/`. A reviewer's justification travels where it carries no
name and no quoted words; the count withheld per file is in `data/tasks/manifest.json`.

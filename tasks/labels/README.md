# Task labels

Every task in both waves was reviewed for defects independently of any model's answers. The review asks whether the
statement, the reference solution and the tests agree, and gives each task one label:

| label | meaning | in the fits |
|---|---|---|
| `regular` | statement, reference and tests agree | yes |
| `tricky` | the task is sound but has a subtlety a careless reading misses (an edge case the tests exercise, a convention the statement does state) | yes |
| `underspecification` | the statement leaves the tested behaviour unspecified | no |
| `contradiction` | the statement contradicts its tests or its reference | no |

The kept set of wave 1 is the set of tasks labelled `regular` or `tricky` (`tasks/wave1/kept_tasks.json` lists them and
the two keeping labels).

- `labels_humaneval.jsonl`, `labels_mbpp.jsonl` — one line per wave-1 task: `benchmark`, `task_id`, `label`.
- `label_history.jsonl` — every label change: the task, the label before and after, and the review round that made it
  (`review_round`). Every change was applied by the same rule: a change decided in a review round is applied
  automatically with its record, for both source benchmarks alike.
- Wave-2 labels live in each task's certificate (`tasks/certificates/certificates.jsonl`, field `audit_label`).

Labels were produced by blind review rounds using several language models as readers, with disputed cases settled by
hand; the screening scripts of the audit that could be included are in `deep-dives/task-audit/`.

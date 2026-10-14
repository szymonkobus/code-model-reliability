# Studies behind the published numbers and rules

A published number or rule of this repository sometimes rests on a study that is not part of the pipeline: a reading
of the tasks, a check of the judge, a test of the method. Each such study has a folder here with a `README.md` that
states the question, the answer, the number or rule in this repository that depends on it, and what the folder holds;
a `recompute.py` that recomputes the study's numbers from the published tables where they can be recomputed and checks
the published tables against the study's record where they cannot; and, where the study's own measurements are the
record (a hand-read category per case, a count the raw replies gave), a small table of them with the arm ids of record.
Nothing here is needed to run the pipeline.

| folder | question | what depends on it |
|---|---|---|
| `audit-labels/` | Is every task sound: do its statement, examples, reference and tests agree? | the kept sets of record (`data/tasks/sets.json`) and which tasks of the published fit they set aside |
| `reworded-copies/` | Are the reworded copies of wave 1 tasks new tasks or re-runs of their parents? | the fold of the word-identical copies into their parents; the reworded copies staying members |
| `typing-import-cleaning/` | Why do the two gpt-5 arms fail easy tasks, and is part of it the judge's doing? | the cleaning applied to those arms' answers before judging; their published cells |
| `rare-failures/` | When a model fails a task it otherwise solves, what went wrong? | the judge's settings and comparison rule; the per-test outcome vector |
| `extraction-errors/` | Is the code we judge the code the model wrote, and how far could it move the numbers? | the extractor of record and the bound on what extraction can move |
| `below-the-floor/` | Do the failure-rate lines continue straight below one failure in 128 attempts? | reading D99 at one failure in a hundred from the fitted curve; the per-task scatter term |

Run a study's script from the repository root with the package installed (`pip install -e .`; the scripts need only
numpy and scipy):

```
python studies/audit-labels/recompute.py
python studies/below-the-floor/recompute.py --data data
```

Every script reads the published tables through `studies/tables.py` (the data directory, the published fit, the sets,
the labels, the registry), prints its reading and exits 1 when a check fails. `tests/studies/` tests the shared pieces.

The tables shipped here name arms by the arm id of the registry (`data/runs/registry/arms.jsonl`) and tasks by the task
id of record; they carry no program text, no model reply and no stamp. The hand-read notes behind the categories
quote model replies and stay out.

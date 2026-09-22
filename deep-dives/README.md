# Deep dives

One folder per question, holding the scripts of the study behind a published number or rule. The studies' written
reports are not part of this import, and neither are the scripts that drove the project's operations (its run store,
its served pages, its landing loops), so a folder may hold part of a study's code. Most of the scripts that remain read
a study's own intermediate tables (a `data/` or `out/` folder beside them, or a results file of another study) that
this repository does not include: they are the record of each computation as it ran and fail on their first read here.
`capable-but-unreliable/` is the plain case: its scripts anchor on their own folder and expect `data/` there (attempt
counts, residuals, traits and behavioural residuals per arm) while the difficulty table they also use is published at
`results/per-task/task_difficulty.csv`. `rare-failures/manifest.jsonl` lists the cases that study examined (case,
benchmark, model, task, failure count, wave).

| folder | question |
|---|---|
| `task-audit/` | Are the tasks sound? The audit that labelled every task and chose the kept set of wave 1 (labels in `tasks/labels/`). |
| `rare-failures/` | Why do capable models fail rarely on tasks they otherwise solve, and are those failures deterministic? |
| `parsing-audit/` | Does the code that was judged equal the code the model answered with, and how far could extraction errors move the numbers? |
| `gpt5-reliability/` | Why do two small API arms fail easy tasks they could pass, and what cleaning rule follows? |
| `deep-rollouts/` | Do the fitted failure lines continue below the censoring floor, tested at ten thousand attempts per task? |
| `capable-but-unreliable/` | Why do arms of similar capability differ in reliability? |
| `mid-capability-spread/` | Why do arms whose capability sits in the middle of the range spread so widely in reliability? |
| `mixture-arm/` | What does a mixture of a strong and a weak model look like on the capability-reliability plane? |
| `twin-study/` | Are paraphrase twins (re-worded copies of wave-1 tasks with the same tests) new data points or re-runs of their parents? |
| `gpt-interventions/` | Can generic prompt instructions stop an arm failing easy tasks it could pass? |
| `gpt-guards-audit/` | How often do refusal-style ("guard") failures occur on easy tasks, and are they judged fairly? |
| `dsv32-think-outlier/` | Why the DeepSeek-V3.2 thinking arm sits off the capability-reliability trend. |
| `r1-outlier/` | Why the DeepSeek-R1 reasoning arm sits off the trend. |

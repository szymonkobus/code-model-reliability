# Glossary

Every term this repository uses in a sense of its own, defined once. Other documents use the term and point here.

- **task** — a Python function to write, judged by executable tests: a prompt (signature and docstring), an entry
  point, a reference solution, base tests and extended tests with expected outputs.
- **attempt** — one answer of one model to one task, at the sampling temperature of its protocol.
- **wave 1** — the tasks kept from two public Python benchmarks after the task audit, used through the judge
  harness at its pinned commit.
- **wave 2** — the new tasks in the published fits; **wave 2 parked** — the new tasks run with the same protocol
  but kept out of the fits; **wave 1+2** — the two measured sets together, the population the published fit stands
  on.
- **the audit** — the reading of every task by its own description, tests and reference, which gave each task one
  label: regular, tricky (sound, but with a trap in its specification), underspecification or contradiction
  (`docs/tasks.md`; the labels file carries these four values).
- **kept** — a task whose audit label is regular or tricky; a task labelled underspecification or contradiction
  is not kept. The published fit stands on every kept task of wave 1 and wave 2 and on the tasks the audit set
  aside after the fit was cut (`docs/numbers.json`, `tasks_fit_not_kept`).
- **arm** — a model under one generation protocol (form, temperature, output limit, thinking budget).
- **form** — how a model answers: plain (a chat model answers directly), thinking (the model reasons at length
  before it answers), completion (a base model continues the prompt with no chat turn).
- **extractor** — the rule that takes the program out of a model's text before judging; its version is named on
  every arm it produced.
- **verdict** — pass or fail of one attempt on the base tests and on the extended tests; an attempt passes only
  when both pass.
- **judging settings** — everything that can move a verdict: the harness commit, the time limit per task, the
  memory limit, the leading-imports rule, the comparison rule.
- **time-out** — an attempt the time limit stopped; counted as a failure and counted apart.
- **cell** — one arm on one task: failures out of attempts.
- **difficulty** — a task's position on one scale defined from the panel of arms: the mean of the arms' failure
  rates on the task, each arm counted once, with one pseudo-observation of half a failure and half a pass over the
  task's attempts, on the logit scale (equal distances are equal odds ratios); larger is harder. The panel that
  votes is recorded beside the axis.
- **D50, capability** — the difficulty at which an arm's fitted failure curve crosses one half.
- **D99, reliability** — the difficulty at which an arm's fitted average failure rate crosses one in a hundred.
  A crossing is named by the success rate it stands at; D97, D95, D90 and D1 (3%, 5%, 10% and 99% failure) are
  carried beside the two.
- **bound** — a crossing that lies outside the fitted range: bound below when the curve is still above the level
  at the easiest task (the value reported is the easiest task's difficulty), bound above when it has not reached
  the level by the hardest task (the hardest task's difficulty). Every arm has a value at every level; a censored
  draw counts past the end it lies beyond.
- **credible interval** — the central 80% range of a fitted quantity over the posterior draws.
- **gate** — a check a fit must pass to be served: no divergences, and on the D50 and D99 draws a split R-hat under
  1.01 and an effective sample size above 400 (a bound level exempt). Whether failures sit on the easiest third of
  tasks is a reading carried beside the gates, never a hold.
- **certificate** — one record per new task admitted to a set: identity, status, audit label, provenance and
  version chain.
- **provenance** — where a task comes from: the upstream dataset and row, or the method that wrote it, with the
  licence its text travels under.
- **pointer task** — a task whose text does not travel because its upstream's terms forbid republishing
  statements; it ships as its id, its content hash and a pointer to the source, and rebuilds from the upstream.
- **reworded copy** — a task re-worded from a wave 1 task with the same tests; reworded copies that proved to be
  re-runs of their parents fold into them in the sets of record.
- **name of record** — the one name a model or a trained run is printed under on every figure, page and table;
  the registry's `names.json` carries it for the models trained in this project. Its **chip** is the short form
  printed beside the base model's name in a table or a legend, and its **position form** the pattern that puts a
  run's step count into the chip.

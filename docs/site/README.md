# Stand-alone copies of two result pages

Two of the project's result pages are included as static sites, each self-contained: every link to another page was
removed (the link text stays), every data file a page fetches is bundled beside it, and working sections were left out.
They are copies for reading with the repository, built from a data cut close to but not identical with the tables in
`results/`; the tables are the reference.

- `capability-vs-reliability/` — the interactive page: where each arm's failure curve crosses the chosen capability and
  reliability levels, one point per arm, with a dataset switch (wave 1, wave 2, wave 1+2, the golden set). Open
  `index.html`; the page reads its data from `data/` relative to itself, so it must be served from a directory (for
  example `python3 -m http.server` in this folder) rather than opened as a bare file, because browsers block `fetch` on
  `file://` URLs. The scripts ship without comments.
- `difficulty/` — the definition pages for task difficulty: `index.html` (the entry), the metrics summary
  (`metrics-report.html`), the definitions report (`report.html`), the synthesis (`synthesis.html`), the derivation of
  the difficulty weighting (`difficulty-weighting.html`, which `jeffreys-diet.html` redirects to), the measures
  catalogue (`measures.html`), the vocabulary tables (`vocab.html`), and an atlas (`atlas.html`) with one data file per
  task in `tasks/`. The long-form versions of the report, the synthesis and the metrics report were working records and
  are not included. Tasks whose upstream permits pointers only carry a pointer sentence in place of their statement in
  the atlas data, like the pointer tasks of `tasks/wave2/`.

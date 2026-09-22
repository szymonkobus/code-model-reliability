# Results

Tables of record for the published fits and the judged outcomes behind them. `docs/data-contract.md` gives every
column; this file says what each folder is for.

- `served/board_top/` — the fit on wave 1+2: 59 arms, 1297 tasks,
  70157 cells. `crossings_of_record.csv` is the headline table (capability and reliability per arm).
- `served/old/` — the fit on wave 1 alone: 59 arms, 431 tasks.
- `served/top/` — the fit on wave 2 alone: 55 arms, 866 tasks.
- `served/golden/` — the fit on the golden set, twelve arms with the most attempts per task, used to check the
  estimator: 12 arms, 1292 tasks.
- `served/serving_*.json` — the pointers that say which fit directory each view of the site copies reads.
- `served/fit_exclusions.json` — the arms excluded from the difficulty axis, with the kind of defect (empty when no
  published arm is excluded, as at this snapshot).
- `per-task/` — task difficulty on wave 1 under both scorers, and the per-arm per-task failure matrix on wave 1.
- `per-attempt/` — one row per attempt of every published arm on wave 1: 4.0 million rows across
  59 arms on the first source benchmark and 58 on the second. No program text.
- `board/board_numbers.jsonl` — pass@k (k = 1, 10, 100) per published arm and source benchmark on the base tests and on
  both test sets, recomputed from the per-attempt verdicts by `runs/land/build_board_numbers.py`.

Every fit folder carries its `cells.csv` (the fit's input), `meta.json` (frame: dataset, counts, axis definition, the
smoothing recipe, engine hash, arms) and `gates_summary.json` (sampler diagnostics per arm). The per-arm posterior draws
are not included; `cells.csv` plus `analysis/fitting` regenerate them with the settings named in `docs/method.md`.

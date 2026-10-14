# The plot stage: the two figures and the two site pages

`cmr plot` draws the two figures of the published results from the published tables, and `cmr site` builds the two
site pages that show the same quantities in a browser. Both read one published fit (`data/results/published/<fit>/`: its
axis, crossings, cells, gates and per-arm summaries) and the arm registry (`data/runs/registry/`), and nothing else;
the figures are written under `figures/` and the pages under `docs/site/`. The module is
`src/code_model_reliability/plot/`. Nothing in it moves a number: the stage draws what the fit stage published, and
`docs/method.md` says how those numbers were made.

## What the two figures show

**Capability against reliability** (`plane.py`): one point per arm at (D50, D99), each with its two 80% credible
intervals drawn as a cross. Both axes are the difficulty scale on the logit transform at one scale, so one logit unit
is the same length across and up and the line y = x runs at 45 degrees; a point on that line would fail outright as
soon as a task exceeded its capability. A crossing the fit could not place inside the task set (a bound) is drawn at
the edge of the scale, faded, and stays out of the trend. A thin trend line is the least-squares fit of D99 on D50
over the arms whose two crossings are points and that are not positions of a training run; its band is the pointwise
80% envelope of a seeded bootstrap that resamples arms and jitters each by its own interval width.

**Failure rate against difficulty** (`curves.py`): one curve per arm, the posterior median of its fitted average
failure rate at every point of the difficulty grid, with the 80% credible band (the 10th to 90th percentile curves)
shaded where the median lies inside the window. Behind the curves sit the arm's own results: its failure rate on each
task, kept on the logit axis by a small prior (half a failure added to the failures and one attempt to the attempts).
The dashed line y = x is where a model fails at the population's own rate, since a task's difficulty is the average
arm's failure rate on it.

## The rules every figure and page follows

- Both axes are logit (`axes.py`): a probability p is drawn at log(p / (1 − p)), so equal distances are equal odds
  ratios; ticks are labelled in percent from one vocabulary, the subset inside the axis's limits.
- The two crossings of record are D50 (capability) and D99 (reliability). The pages' level controls read the other
  levels the tables carry; the figures draw these two.
- One colour per model, families by hue (`style.py`, `palette.json`): a thinking variant keeps its base model's
  colour and draws dashed with an open marker; a fine-tune dotted; a reinforcement-learning run long-dash-dot-dot and
  darker later in training. A training run's marker shape names the failure count the run trains on, and a small
  central dot every other departure from the plain recipe, both read from the run's name of record. Two models of one family that the registry cannot place on distinct rungs (no rank and no size in their model rows) would share a colour, so the figures and the site build stop and name them, as for an arm without a name of record. A variant named after its base model with a middle dot in its name of record (`Qwen3 8B · code fine-tune`) keeps the base model's colour and takes its treatment's line pattern, and never enters the ladder.
- Legends list the arms by family in the palette's order, inside a family from the lightest rung to the darkest, a
  thinking variant right after its plain model. Nothing orders the arms by their numbers: the figures and pages show
  positions with their uncertainty, never a ranking.
- One export (`export.py`): an SVG and a PNG beside each other, the figure as drawn and cropped to its axes and
  legend, with no page title, caption or words about the method; the file is named `<figure>.<names>.svg`, the names
  of record of the arms shown (the first few, then how many more), so a file says what it shows without being opened.
  The number of data points the figure stands on rides on the x-axis label.
- Every arm is labelled by its name of record from the registry. An arm of the fit with no name there stops the
- An arm whose fit failed a sampler check (`FAIL` in the `gate` column of the crossings table) is drawn faded on both figures and both pages and flagged on its chip; it keeps its row in the table and its place in the fitted line. Nothing is withheld, and a table without the column beside a `gates.json` is refused rather than read as all passing.
  figures and the site build, naming the arms: a figure or a page never prints an arm id in place of a name.

## The palette of record

`palette.json` beside `style.py` holds one hue per model family, a lightness ladder from the lightest rung to the
darkest, the rungs pinned to named models, the ramps of the training-run series and the dash patterns. The rules in
`style.py` give any arm its colour, line and mark in this order: its family is the model row's family, else the
first family whose pattern matches the model id; its colour is the family hue at a pinned rung where the palette pins
the model, at its run's ramp position where it is a training run's checkpoint, and otherwise at its rank on the
family's ladder. A new arm gets a colour by these rules without a change to the file; a published arm keeps its colour
of record.

## The two pages

Each page is a static shell under `site/<page>/` (its `index.html`, scripts and stylesheet) plus the shared kit under
`site/kit/` (the state kept in the address, the switch and select controls, the filter row, the chart helpers, the
export function and the stylesheet). A page fetches `data/manifest.json` and the files the manifest names, written by
`site_data.py` from the fit and the registry, and draws them in the browser; it fetches nothing else and carries no
clock, stamp, link or host. A bundle carries data and names of record only, floats rounded to four decimals.

- `capability-vs-reliability/` reads `shared.json` (the arms with their names, colours and marks, the training runs'
  rows and the scale's reach) and `crossings.json` (per arm, under both definitions, D50 and D99 with their densities
  and the crossing at every failure-rate level). Its controls set the two levels (presets, typed values and a sweep of
  the horizontal level), the definition (average rate or median task), the scales, the fitted line (in logit or in the
  axes as set, each dot equal or weighted by the 80% bands, with its interval), the misses against the line, the
  posterior ridges of the crossing draws and the partial models.
- `failure-vs-difficulty/` reads `shared.json` (the tasks on the difficulty scale and the arms), `curves.json` (per arm
  the fitted curve's quantiles on the grid and its two crossings of record), `cells.json` (per arm the failures and
  attempts on every task) and `levels.json` (per arm the crossing at every level). Its controls set the definition,
  what the drawn curve is the median of (the failure rate at each difficulty, or the difficulty at each failure rate),
  the uncertainty band (80% or 90%; 95% only where a fit carries those quantiles), the scales, the task dots, the pin
  that slides every curve to a common crossing, and the partial models; a table below gives each model's crossings
  under the definition chosen.

On both pages the models are chosen by chips grouped by family, a thinking variant beside its base model and the
training runs in their own row; the view's state lives in the address, so an address reproduces a view; a
Definitions fold defines every printed term; the export button downloads the chart as drawn with its legend.

## Building and checking

    cmr plot --data data --out figures [--fit <fit>] [--figure plane|curves|all]
    cmr site --data data --out docs/site [--fit <fit>] [--shells <dir>] [--no-node]

`cmr plot` needs numpy and matplotlib; `cmr site` needs only the standard library, plus node for its script check.
The site build copies what each page's `index.html` names and nothing else, writes the bundles, and refuses a copy in
which an asset is missing, a literal fetch does not resolve, a data file does not parse, a path leaves the page, an
address names a host, or a script fails `node --check`. The same inputs build the same bytes.

The tests under `tests/plot/` run on a fixture that is the published data restricted to four arms and forty tasks (`python3 tests/plot/cut_fixture.py --data data` re-cuts it; every file keeps the export's shape): the reader's shapes
(`test_data.py`), the colours, marks and legend order (`test_style.py`), the two exports under the rules above
(`test_figures.py`), the bundles and the site build (`test_site.py`), and a headless render of both pages at desktop
and phone width with no console error, no failed request and no fail line, the export downloading
(`test_render.py`, run where node and playwright are installed and skipped otherwise).

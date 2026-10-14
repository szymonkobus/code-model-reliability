# The reworded copies: new tasks or re-runs of their parents?

## The question

Wave 2 contains copies of wave 1 tasks whose prompt was rewritten in a named style (formal, conversational,
imperative, narrative) with the entry point, the reference and the tests inherited byte for byte (`docs/tasks.md`,
section Where the new tasks come from). If a model's success depends on the wording, a copy is a new measurement; if
not, it is a repeat of its parent and adds little. Which is it?

## The answer

Mostly re-runs. For each copy, the study took every arm holding both the copy's cell and the parent's, removed what
the arm's strength and the task's difficulty predict, and correlated what is left across arms: whether the same arms
find copy and parent unusually easy or hard. Scaled so that a fresh set of attempts on the parent itself scores one
and an unrelated task of the same difficulty scores zero, the typical reworded copy scores 0.89 (`rerun_score` in
`copies.csv`; the twelve word-identical copies, the control, score about one). By that correlation the 308 copies
compared are worth about 30 independent tasks.

Pass rate against pass rate, the copy and its parent agree: over 16,123 copy-and-arm pairs the two pass rates
correlate at 0.93, and an exact test cannot tell them apart in 86% of pairs. The agreement is partly saturation; on
the informative pairs, where the arm neither nearly always passes nor nearly always fails the parent, 64% are
indistinguishable and 19% differ beyond doubt, so in about one informative cell in three the rewording changed what
the model does. The copy keeps its parent's difficulty: positions correlate at 0.97 and 10 of 287 copies sit more
than one step from the parent. Farther rewordings are only slightly more new: the nearest fifth by prose distance
scores 0.96, the farthest 0.85. Folding every copy's attempts into its parent moves the twelve arms refitted by at
most 0.05 of a step at D50 and 0.20 at D99; dropping the copies altogether, by at most 0.07 and 0.38; both inside the
fits' own uncertainty.

## What depends on it

Two rules of the sets of record. A copy whose prompt is identical to the parent's apart from whitespace is folded into
its parent: fourteen of the copies made were, and are members of no set, their attempts counting in the parent's
published cell; twelve of them had been members and left the sets (`sets.json` lists them under `folded_twins`: 8 from
wave 2, 4 from wave 2 parked), two were members of neither set. The reworded copies stay members of their sets, and
no further reworded copies are generated, since rewording alone never made a fresh task.

## What is here

- `copies.csv`: one row per copy compared (308): the copy and its parent, the set it sits in (`wave_2`,
  `wave_2_parked`, or `none` for the copies outside both lists), its writing style, whether it is word-identical to the
  parent, the prose distance of the rewording (the share of the paraphrasable prose that changed), the re-run score,
  the number of arms compared and the attempts on each side.
- `recompute.py` checks the fold against `sets.json` and the published cells (no folded copy is a member; the parents'
  cells carry the copies' attempts; the word-identical copies of `copies.csv` are the folded ones), then redoes the
  pass-rate comparison from the published fit's `cells.csv` for the reworded copies in it (the 214 kept copies in
  wave 2, over every arm that holds both the copy's cell and the parent's) and the difficulty comparison from its
  `axis.csv`. Its numbers are close to the study's and not identical: the published fit holds the copies in wave 2
  only, the study compared the copies of wave 2 parked as well, and the fit's arms change with the fit.

The re-run score itself needs the arms' residuals on the whole of wave 1 and is not recomputed here; its recipe is in
the answer above and its values are in the table.

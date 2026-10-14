# Extraction errors: is the code we judge the code the model wrote?

## The question

Before judging, the program is taken out of the model's reply: the last fenced block that defines the entry point,
with the earlier blocks it needs. When that step picks a demo block, an earlier draft, or a function without the
helper it calls, the judge grades code the model did not settle on. How often does that happen, and how far could it
move the published numbers?

## The answer

An independent reader (thinking removed; the last fenced block defining the entry point plus the earlier blocks it
needs; the last definition wins; demo lines removed; broken functions dropped whole) was run over every raw reply of
57 arms on wave 1, 3,906,047 judged attempts, and compared with the code that was judged. The two differ, with the
judged code not the model's answer, in 17,766 attempts (0.45%): the function the model wrote was not in the judged
code at all (0.08%), it was judged without a helper or an import it needs (0.08%), or an earlier or duplicate version
of it was judged (0.30%). Both versions were then judged under the pinned judge in one configuration: 6,611 verdicts
change (0.17% of all attempts), 5,911 failures that should have been passes (0.15%) and 700 passes whose later version
fails (0.018%); 75 candidates on two tasks were not re-judged.

With a correct extractor from the start no arm's pass rate moves by more than 1.9 points and no reliability crossing
by more than 1.4 points of the difficulty scale: Kimi-Dev 72B 3.9% to 5.3%, DeepSeek-R1-0528 (thinking) 7.2% to 8.4%,
GPT-5 nano (thinking) 6.7% to 7.8%, Gemini 3.6 Flash (thinking) 29.7% to 30.7%, every other arm less. The share of
attempts judged on the wrong code is concentrated: 8.2% for Gemma 4 12B and 5.6% for DeepSeek-V3.2, under 2% for
every other arm.

## What depends on it

The extractor of record. On this finding the corrected extractor became the one every arm is judged under, the wave 1
attempts were re-extracted and re-judged, and the registry names the extractor version each arm's samples carry
(`generate/extract.py` lists the versions and holds each to its stamp; `data/runs/registry/arms.jsonl` names them per
arm). The numbers above are the raw-store figures measured before that re-judge: they are the bound on what
extraction could have moved, not a description of the published cells, which carry the correction.

## What is here

- `per_arm.csv`: one row per arm (57): the judged attempts on wave 1; the attempts judged on code that was not the
  model's answer and, of these, the verdicts that changed when the model's own code was judged (false fails, false
  passes), the ones that did not, and the ones not re-judged; the pass rate and the two crossings as judged and as
  they would be with the model's own code, D99 and D50 as a percentage of the difficulty scale and in logit units. An
  empty crossing is one that lay below the easiest task. These crossings come from the study's own estimator on the
  438 kept wave 1 tasks of its time, not from the published Bayesian fit; the published tables carry the fit. One arm,
  `Qwen--Qwen3-30B-A3B_think_temp_0.6`, had attempts on one part of wave 1 only when the study ran (20,992 attempts,
  146 kept tasks), so its row rests on those.
- `recompute.py` recomputes the shares and the largest moves from `per_arm.csv` and checks that every arm is an arm
  of record. The raw replies the reader read do not ship, so the per-arm counts are the study's record.

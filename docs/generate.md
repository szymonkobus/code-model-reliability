# The generation stage

`cmr generate` makes a model answer every task of a set many times and writes the answers in the shape the judge
reads. This page says what was run, with which settings, and how to run it again; the settings themselves are
named constants in `src/code_model_reliability/generate/settings.py`, each with the reason for its value.

## What every arm shares

Every model sees the same instruction sentence followed by the task's prompt (the function signature and its
docstring), and gives the same number of attempts per task: 128 on wave 1, and 32 on wave 2 for the open-weight
arms (the fit uses every attempt). Sampling for a plain answer is temperature 0.8 and top-p 0.95, the repeated-
sampling convention for these tasks. The output limit for an answer is 4,096 tokens: an answer still unfinished
there counts as cut by the limit. Wave 1 was first drawn under the judge harness's default limit of
768 tokens and every cut answer was then continued to 4,096, the two parts one attempt.

The prompt forms come from the judge harness at its pinned commit where the harness can express them, and were
written for this project where it cannot:

| form | what the model sees | arms |
|---|---|---|
| plain, chat prompt | the harness's chat prompt: a user turn with the instruction and the task in a bare code fence, then the model's turn opened with the response sentence and an open ```python fence (`prompts.chat_prompt`) | the open-weight chat models |
| plain, generation prompt | the same, with the model's turn opened by the template's own marker with thinking off (a template that marks its turn loses that marker under the harness's cut message) | the Gemma 4 models |
| thinking, two-phase | the user turn and the template's generation prompt with thinking on; the model thinks to a 32,768-token budget and is closed there if it has not closed itself; then the response sentence and the open fence, and the answer | Qwen3 and Olmo 3 thinking models |
| thinking, single-phase | the user turn and the template's generation prompt; trace and answer in one generation under one budget (65,536 tokens; 30,000 for the distilled models), no stop strings, split at the closing tag; a trace that reaches its budget is closed afterwards and answered under 4,096 tokens | the DeepSeek reasoning models and the models trained from them |
| completion | the bare task prompt with one trailing newline; the program is prompt plus completion, whole | base models and the models trained from them |
| API message | one user message with the instruction and the task in a ```python fence; no system prompt and no pre-filled turn | the provider arms |

The thinking forms sample with the makers' recommended settings (temperature 0.6, top-p 0.95; top-k 20 and
min-p 0 for the two-phase form). The provider arms sample as each provider allows: one model at temperature 0.8
with top-p unset, the rest under the provider's default sampling, thinking at the provider's forced temperature or
under adaptive thinking at high effort; their cards are in `generate/api/*.py`. Every difference between the open-weight
arms and the API arms is in the open: the opening of the model's turn, the sampling, the serving stack.

The stop strings end an answer where its program ends: the end-of-text markers, the first line of a
demonstration (`if __name__`, `def main(`, `print(`) and, for the chat forms, the closing fence on its own line.
The completion form stops at a demonstration's first line or four blank lines, never at a definition.

## The extractor

Before judging, the program is taken out of the model's text by one pure function, `generate.extract.extract`.
A version is named by a stamp, the hash of the file's bytes as it ran, and the registry names the stamp each
set's verdict files carry. Five versions stand behind the published verdicts and all five ship, one module per
stamp under `generate/extractors/`; `extract.extract_under(stamp)` gives any of them and `extract.extract` is the
current one. Each module's documentation was rewritten for a reader, so the tests hold its logic to its stamp by
a hash of its syntax tree with comments and docstrings removed, and the fixture of replies records what every
version produced. In order, each version added to the one before it:

| stamp | what it added | which published attempts carry it |
|---|---|---|
| `v2@1f4d747f86f4cf98` | the first published version: the rules listed in the module | most wave 1 verdict files |
| `v2@0b0abd79e863a451` | an assignment is the entry point's definition only when its value can be a function | some wave 1 verdict files |
| `v2@4ab50996111c1be5` | an unclosed thinking tag is left as text instead of swallowing the reply; a reply whose fence lines are stray is read whole once they are removed | a few wave 1 verdict files |
| `v2@90dae7e9e3e530bd` | a fence opener glued to prose is split onto its own line; a decorator line opens a parse segment through its definition | a few wave 1 verdict files |
| `v2@9ac5071166f8adaa` | an unclosed final block whose last line is a whole statement inside a body is read as cut at the token limit | the wave 2 landings (the current version) |

A wave 1 verdict stands as judged under its version; the registry row says which. The judge harness's own sanitizer, which the
generation path applies as it writes a sample, is kept reachable for comparison; it drops a correct generator
function and judges a cut-off reply on its longest parseable span, which is why the attempts were re-extracted from
their raw replies before the re-judge.

## What a run writes

Under `<out>/<set>/<arm>/`: `samples.jsonl` (one `{"task_id", "solution"}` per attempt, in task order and attempt
order), `raw.jsonl` (one row per attempt as the model returned it, with how it ended and, for the thinking forms,
the trace and how it closed) and `generation.json` (every setting the attempts were produced under, the extractor's
stamp, the library pins and the seed). The record names the protocol by the name given to
`--protocol` (`protocol`, for example `plain-chat`; the provider arms carry `api-message`) and by its version token
where it has one (`protocol_version`: `completion-v1` for the completion form, empty otherwise). The two line files are written together, one attempt at a time, and a run
that is interrupted resumes from them. Nothing is rewritten in place; a continuation or an answer phase lands in
its own directory and the land stage puts it in the cut attempt's place.

## Running it

A GPU machine with the environment of `cluster/environment.sh` (the inference engine and tokenizer library at the
pins the attempts were produced with, the harness at its commit):

```
cmr generate run --model Qwen/Qwen2.5-Coder-7B-Instruct --tasks data/tasks/wave2 --protocol plain-chat --attempts 32 --out out/wave2
cmr generate run --model Qwen/Qwen3-8B --tasks humaneval --protocol two-phase-thinking --attempts 128 --out out/wave1
cmr generate continue --model <model> --tasks <set> --protocol plain-chat --source <first pass> --out <dir>
cmr generate answer-phase --model <model> --tasks <set> --source <single-phase run> --out <dir>
```

`--arm <arm>` takes a published arm's settings from `data/runs/registry/protocols.tsv` instead of a named protocol
(the table's `protocol` and `protocol_version` columns are the record's two names);
`cmr generate protocols` prints that table, which the build regenerates from the registry for the arms of the
published fit and no other (a published arm without a row fails the build). An arm's id in the
table is the key the fit's files were produced under: the model stem, the form token and the temperature for the
open-weight arms (with the `@768-marker` suffix on the two generation-prompt variants), and the model name with the
batch token for the provider arms (`claude-sonnet-5_batch`); no table composes an id of its own. `cluster/generate.sbatch` is the Slurm form of one run; everything
about the machine is set inside it. A provider arm runs through the batch cycle:

```
cmr generate api build    --provider anthropic --card claude-sonnet-5 --tasks data/tasks/wave2 --state state/sonnet --attempts 128
cmr generate api submit   --provider anthropic --card claude-sonnet-5 --state state/sonnet
cmr generate api status   --provider anthropic --card claude-sonnet-5 --state state/sonnet
cmr generate api fetch    --provider anthropic --card claude-sonnet-5 --state state/sonnet
cmr generate api finalize --provider anthropic --card claude-sonnet-5 --state state/sonnet --tasks data/tasks/wave2 --out out/wave2/claude-sonnet-5_batch
```

The keys come from the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) and nothing else.

The tests run the stage end to end on a three-task fixture set with a deterministic stand-in for a model
(`--backend standin`), hold the chat prompt byte-equal to the harness's (the tests need the harness installed, the
package's `judge` extra), and hold the extractor to the recorded output of the current published stamp on a
fixture of replies.

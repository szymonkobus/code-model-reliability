# The task sets

The task dataset of the code-model-reliability repository: wave 1 (430 tasks, 430 kept by the audit), wave 2 (869
tasks, 858 kept) and wave 2 parked (893 tasks, 879 kept). Wave 1+2, the kept tasks of wave 1 and wave 2 together
(1288 tasks), is the population the published fit stands on. Every task is a Python function to write, judged by
executable tests: a prompt (signature and docstring), an entry point, a reference solution, base tests and extended
tests. How the sets were built, screened, certified and audited is in `docs/tasks.md`; the file shapes are in
`docs/data-contract.md` (section tasks); the licences are in `DATA-LICENSE.md`.

## Files

- `sets.json` — the members and the kept subset of each set, a sha256 per sorted list, the label rule, the reworded
  copies that folded into their parent, the members not kept with the reason.
- `attribution.jsonl` — one row per task: where it comes from (source set and row, kind, method, reference origin,
  generator), the licence its text travels under, its audit label and status, its content hash.
- `sources.json` — the source sets: what each is, its licence as recorded, how its tasks ship here.
- `certificates.jsonl` — one row per certified task of the pool the new tasks were drawn from, with identity, status,
  audit label, provenance and version chain; no run outcomes.
- `wave-1/kept_tasks.json` — the wave 1 ids kept by the audit; the texts come from the judge harness at its pinned
  commit. `wave-1/plus_inputs_removed.json` — the extended test inputs the judge removes per wave 1 task (a boolean
  at an argument position where no example carries one).
- `wave-2/`, `wave-2-parked/` — the task records with text (`tasks-part-NN.jsonl.gz`: the eight judged fields, the
  content hash, the audit flag, `io_mode`, the provenance, and where they apply the removed extended inputs and the
  declared argument shapes), the pointers for tasks whose text does not travel (`restricted.jsonl`) and a manifest
  with the part hashes.
- `labels/labels.jsonl`, `labels/label_history.jsonl` — the audit label of every task and the label changes.
- `manifest.json` — every file's bytes and sha256, the counts, the identities of the files of record this package
  was exported from, and what was withheld.

`cmr tasks verify` checks every hash and list; `cmr tasks rebuild-restricted --plan` says how to recover the pointer
tasks; `cmr tasks show <task id>` prints one task with its attribution.

## Attribution

| source set | what it is | licence as recorded | how its tasks ship here | wave 1 | wave 2 | wave 2 parked |
|---|---|---|---|---|---|---|
| Code-Contests-Plus (ByteDance-Seed/Code-Contests-Plus, ccplus_1x) | Code-Contests-Plus (ByteDance Seed), the ccplus_1x configuration: Codeforces contest problems with validator-generated tests; the reference is a correct submission from the dataset | cc-by-4.0 (the dataset); upstream: Codeforces problem material, redistributed by the dataset under CC BY 4.0 | full text, with attribution | 0 | 184 | 284 |
| open-r1/codeforces (verifiable) | open-r1/codeforces, the verifiable configuration: Codeforces contest problems; the reference is a Python submission from open-r1/codeforces-submissions | cc-by-4.0 (the dataset); upstream: Codeforces problem material, redistributed by the dataset under CC BY 4.0 | full text, with attribution | 0 | 99 | 184 |
| LeetCodeDataset (newfacade/LeetCodeDataset) | LeetCodeDataset (newfacade): LeetCode problems with starter code, a completion and tests; the reference is the dataset's completion | apache-2.0 (the dataset card) over LeetCode material | identity, tests' hashes and a pointer to the source; the text rebuilds from the upstream | 0 | 65 | 199 |
| LiveCodeBench (livecodebench/code_generation_lite, v6) | LiveCodeBench code_generation_lite v6; the rows used are LeetCode problems, joined by their slug to LeetCodeDataset's completion as the reference | cc (the dataset card) over LeetCode material | identity, tests' hashes and a pointer to the source; the text rebuilds from the upstream | 0 | 30 | 39 |
| EvoEval (evoeval/EvoEval_combine, _creative, _difficult, _subtle, _tool_use) | EvoEval, five subsets: problems derived by generation from HumanEval; the reference is the dataset's canonical solution | apache-2.0 (the dataset) | full text, with attribution | 0 | 30 | 11 |
| LBPP (CohereLabs/lbpp, python) | LBPP (Cohere Labs), the Python split: problems hand-written by competitive programmers; the reference is the dataset's completion | apache-2.0 (the dataset) | full text, with attribution | 0 | 24 | 4 |
| HumanEval (openai/openai_humaneval); wave 1 ships as ids, its reworded copies in wave 2 as text | HumanEval (OpenAI): wave 1's copy with the judge harness's extended inputs; the reworded copies in wave 2 paraphrase its prompts and inherit everything else byte for byte | MIT (the HuggingFace dataset card, read 14 Oct 2026); the evalplus additions under the evalplus repository's licence | full text, with attribution | 144 | 101 | 19 |
| MBPP (google-research-datasets/mbpp); wave 1 ships as ids, its reworded copies in wave 2 as text | MBPP (Google Research): wave 1's copy with the judge harness's extended inputs; the reworded copies in wave 2 paraphrase its prompts and inherit everything else byte for byte | CC-BY-4.0 (the HuggingFace dataset card, read 14 Oct 2026); the evalplus additions under the evalplus repository's licence | full text, with attribution | 286 | 115 | 62 |
| EasyTail: generated for this project by seeded template code | this project's easy-tail generator (easytail_gen_config_v1): a programmatic core by seeded template code (entry point, canonical solution, input generator, base and extended inputs) and a rendered or templated surface | none inherited: the project's own text, solution and tests | full text, under this repository's data licence | 0 | 140 | 2 |
| Targeted: generated for this project by a model and screened | this project's targeted generator (targeted_gen_config_v1): a model-generated specification, reference and input generator, accepted when three independent solutions agree byte for byte, then screened and placed by a ladder of models | none inherited: the project's own text, solution and tests | full text, under this repository's data licence | 0 | 81 | 89 |
| **all** | | | | **430** | **869** | **893** |

Wave 2 ships 774 tasks with text and 95 as pointers; wave 2 parked ships 654 with text and 239
as pointers. A pointer task carries its identity, audit flag and provenance, the reason its text is not here, and its
rebuild recipe: the converter in this repository for its upstream and the inputs a later re-issue removed
(`cmr tasks rebuild-restricted --plan`).

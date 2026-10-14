# Data licence and attribution

The task sets (`data/tasks/`), the audit labels and the result tables (`data/results/`) in this repository are
released under the Creative Commons Attribution 4.0 International licence (CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/), except where a row of the table below records a different upstream
term. The code is licensed separately under `LICENSE` (MIT).

Wave 1 is the kept subset of two published Python benchmarks, used through the judge harness at the commit pinned
in `pyproject.toml`; this repository ships their task ids and audit labels, and the texts come from the harness.
The new tasks were converted from public datasets or written for this project; `data/tasks/attribution.jsonl`
names, per task, the source set, the source row, the derivation and the licence its text travels under, and
`data/tasks/certificates.jsonl` carries each task's provenance as recorded at import. A task whose upstream terms do
not permit republishing statements ships as a pointer (its id, its content hash and the source), and
`cmr tasks rebuild-restricted` recovers it from the upstream dataset.

The table below is generated at every build from `attribution.jsonl` and `sources.json`
(`cmr tasks attribution-table`).

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

Problem statements imported from public datasets are the work of their authors and reach this repository under
the datasets' stated licences. A rights holder who believes a task should not be here can open an issue naming the
task id, and it will be replaced by a pointer.

The result tables contain judged outcomes of model outputs (pass or fail per attempt, counts per task) and fitted
quantities; no generated program text is included.

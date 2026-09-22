# Data licence and attribution

The task sets (tasks/), the result tables (results/) and the per-task labels (tasks/labels/) in this repository are
released under the Creative Commons Attribution 4.0 International licence (CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/), except where a row of the table below records a different upstream
term. Code is licensed separately under LICENSE (MIT).

## Wave 1

Wave 1 is the kept subset of two published Python benchmarks, used through the EvalPlus harness (Apache-2.0) at the
commit pinned in runs/generate/cluster/setup_env.sh. This repository ships their task ids and audit labels only; the
task texts come from the harness.

| Upstream | Licence | What is used |
|---|---|---|
| HumanEval+ (EvalPlus) | MIT | task ids, per-attempt verdicts, cells |
| MBPP+ (EvalPlus) | CC BY 4.0 | task ids, per-attempt verdicts, cells |

## Wave 2 and wave 2 parked

The new tasks were converted from public datasets or generated for this project; tasks/certificates/certificates.jsonl
carries, per task, the upstream dataset, row key, title, URL and the licence as recorded at import time. The same
attribution applies to both sets (tasks/wave2/ and tasks/wave2-parked/).

| Task-id prefix | Upstream dataset | Upstream licence | Redistribution here |
|---|---|---|---|
| ccplus | ByteDance-Seed/Code-Contests-Plus (Hugging Face), config ccplus_1x | CC BY 4.0 over Codeforces problem material | full text, with attribution (one parked task shipped as a pointer, see below) |
| openr1 | open-r1/codeforces (Hugging Face), config verifiable | CC BY 4.0 over Codeforces problem material | full text, with attribution |
| leetcode | newfacade/LeetCodeDataset (Hugging Face) | Apache-2.0 dataset card over LeetCode material; LeetCode's terms restrict republishing statements | ids, content hashes and a rebuild script only (restricted.jsonl in each set folder) |
| lcb | livecodebench/code_generation_lite (Hugging Face), v6 | CC dataset card over LeetCode material; same restriction | ids, content hashes and a rebuild script only |
| lbpp | CohereLabs/lbpp (Hugging Face), python | Apache-2.0 | full text, with attribution |
| evoeval | evoeval/EvoEval_* (Hugging Face) | Apache-2.0 | full text, with attribution |
| HumanEval, Mbpp | re-worded copies of wave-1 tasks with the same tests ("paraphrase twins", docs/wave2.md) | MIT and CC BY 4.0 upstream | full text, with attribution |
| Targeted, EasyTail | written for this project | CC BY 4.0 (this repository) | full text |
| EasyPilot | written for this project: the pilot of the easy tail, certified but in neither set of record | CC BY 4.0 (this repository) | certificates only (no text in the task sets) |

One Codeforces-derived task in wave 2 parked is shipped as a pointer rather than as text because a random string in its
test inputs tripped the content scrub applied before publication; its note in restricted.jsonl says so, and
tasks/rebuild_restricted.py recovers it like the others.

Codeforces problem statements are the work of their authors and of Codeforces; they reach this repository through the
two datasets above under their stated licence. If you are a rights holder and believe a task should not be here, open
an issue naming the task id and it will be replaced by a pointer.

## Results

Result tables contain judged outcomes of model outputs (pass or fail per attempt, counts per task) and fitted
quantities. No generated program text is included.

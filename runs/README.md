# Runs: registry, generation, judging, landing

The code that produced the judged results, as it ran, with everything about the environment it ran in read from
variables:

| variable | stands for |
|---|---|
| `CLUSTER_HOST`, `CLUSTER_BASE`, `CLUSTER_NAME` | the ssh host of the Slurm cluster, the base directory on it, and a name for it in job names |
| `TORCH_BACKEND` | `cu129` on a cluster whose GPU driver predates CUDA 13, else unset |
| `PINNED_VENV` | a prebuilt Python environment to use instead of building one |
| `DURABILITY_ROOT` | the directory that holds the raw API replies the backfill tool joins against |
| `EVALPLUS_HOME` | the directory under which the EvalPlus harness keeps its cache (`.cache/evalplus/`); the task-pipeline screens and twin checks read the harness's task files there; the home directory when unset |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` | API keys |
| `EXTRACTOR_DROPIN`, `EXTRACTOR_V2` | set to `1` to route answer extraction through the drop-in or the second vendored extractor instead of the pinned harness's |
| `<partition>` in the `#SBATCH` lines | the Slurm partition to submit to |

Nothing in this folder runs without pointing those at your own environment; the fitting and figure code in `analysis/`
and `figures/` runs from the published tables alone.

- `registry/` — `arms.jsonl` (one row per arm and benchmark; the join key `arm_id`; the run list of record) and
  `models.jsonl` (model stems, families, parameter counts).
- `generate/cluster/` — the wave-1 job: `submit.sh` and `job.sbatch` run a model with vLLM and judge with the pinned
  harness; `setup_env.sh` builds the environment and pins the harness by commit; `pull.sh` copies results back;
  `qwen3-think/` is the runner for thinking models, kept apart because its prompt handling differs. The job scripts call
  two small helpers that are not part of this import (a repair of a half-written last line of a samples file and a count
  check of the samples file against the expected task and attempt counts); both are described where they are called.
- `generate/api/` — the batch generators for the API arms (`claude_gen.py` for the source benchmarks,
  `claude_gen_external.py`, `openai_gen.py` and `gemini_gen.py` for prompts given per line), the extractor switch
  (`landing_extract.py`), the receipt hasher (`receipt_hashes.py`), the raw-reference backfill (`rawref_backfill.py`) and
  the pinned answer extractors (`vendor/`). Keys from the environment.
- `judge/` — the judge as invoked: `judge_evalplus.py` launches the pinned harness's evaluator with the process-safety
  patch and the per-task limits the judged results were produced under, and `preamble_transform.py` beside it is the
  rule that prepends a prompt's leading import lines to the judged program; `board_evaluate.py` with `board_compare/` is
  the entry for the source benchmarks, applying the adopted comparison rule (whitespace normalisation and a numeric
  tolerance) before the evaluator runs. The launcher's optional switches (a boolean-output filter, typed inputs, an
  input-output mode) import helpers and side files that are not included; the default path needs none of them. The
  cluster loop that fed shards to these entries is operations code and is not included.
- `land/` — the pass-rate builder (`build_board_numbers.py`), which recomputes pass@k from judged result files. The
  registry builder, the arm reader and the one-off correction tools read private stores and are not included; the
  registry ships as data.
- `fail-reruns/` — the re-run of every failing attempt against the full test set, which produced the per-test outcome
  vectors used by the failure studies: the procedure as run. Its inputs (the failure study's consistency tables, the
  working folder's parts archive, cell map and slice rows) are not included, so the scripts document the procedure rather
  than run here; the worklist builder, which read the private judged files, is not included.

The invariant every tool respects: judged files are byte-format-identical to the pinned harness's own output, and a
correction never rewrites a judged file in place; it lands as a companion file beside the file it corrects.

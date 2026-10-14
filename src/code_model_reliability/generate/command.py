"""The command line of the generation stage: ``cmr generate <action> ...``.

Actions:

- ``run``: one model on one task set under one protocol, through the inference engine (``--backend vllm``, on a
  GPU machine) or the deterministic stand-in (``--backend standin``, for tests). The protocol is one of the named protocols
  (``--protocol``) or an arm of the shipped protocol table (``--arm``).
- ``continue``: the attempts a first pass cut, continued to the output limit (plain and completion forms).
- ``answer-phase``: the single-phase attempts whose trace reached its budget, answered from the stored trace.
- ``api``: the batch cycle for a provider arm: ``build``, ``submit``, ``status``, ``fetch``, ``resubmit``,
  ``finalize``.
- ``protocols``: print the shipped protocol table.

Reads the task set and the protocol table. Writes under the output directory given (see ``records``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from . import protocols as PR
from . import settings as S
from .taskset import load_tasks, file_sha256


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cmr generate", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", metavar="<action>")

    def common(p, out_required=True):
        p.add_argument("--tasks", required=True, help="a task file (.jsonl or .jsonl.gz), a directory of parts, or humaneval / mbpp")
        p.add_argument("--set-name", default=None, help="the set's name in the record (default: the file's or directory's name)")
        p.add_argument("--only", default=None, help="a file of task ids to restrict the set to")
        p.add_argument("--out", required=out_required, help="the output directory for this set and arm")
        p.add_argument("--extractor", default="v2", choices=["v2", "harness"], help="the extractor the samples go through")

    run = sub.add_parser("run", help="generate every attempt of one arm on one set")
    common(run)
    run.add_argument("--model", required=True, help="the model id (a repository id or a local directory)")
    group = run.add_mutually_exclusive_group(required=True)
    group.add_argument("--protocol", choices=sorted(PR.PROTOCOLS), help="a protocol by name")
    group.add_argument("--arm", help="an arm of the shipped protocol table")
    run.add_argument("--table", default=None, help="the protocol table (default: data/runs/registry/protocols.tsv)")
    run.add_argument("--attempts", type=int, default=S.ATTEMPTS_PER_TASK)
    run.add_argument("--backend", default="vllm", choices=["vllm", "standin"])
    run.add_argument("--seed", type=int, default=None, help="the sampling seed (default: derived from the run's identity)")
    run.add_argument("--output-limit", type=int, default=None, help="override the protocol's output limit")
    run.add_argument("--thinking-budget", type=int, default=None, help="override the thinking budget (thinking forms)")
    run.add_argument("--answer-budget", type=int, default=None, help="override the answer budget (thinking forms)")
    run.add_argument("--max-model-len", type=int, default=None)
    run.add_argument("--tensor-parallel", type=int, default=int(os.environ.get("SLURM_GPUS_ON_NODE", "1") or 1))
    run.add_argument("--greedy", action="store_true", help="one greedy attempt per task (a check, never a fit row)")
    run.add_argument("--distilled", action="store_true", help="single-phase: the smaller budget of the distilled models")
    run.add_argument("--revision", default=None, help="the model revision to record")

    cont = sub.add_parser("continue", help="continue the attempts a first pass cut")
    common(cont)
    cont.add_argument("--model", required=True)
    cont.add_argument("--protocol", required=True, choices=sorted(PR.PROTOCOLS))
    cont.add_argument("--source", required=True, help="the output directory of the first pass")
    cont.add_argument("--first-pass-limit", type=int, default=S.FIRST_PASS_LIMIT)
    cont.add_argument("--limit", type=int, default=S.ANSWER_LIMIT)
    cont.add_argument("--backend", default="vllm", choices=["vllm", "standin"])
    cont.add_argument("--seed", type=int, default=None)
    cont.add_argument("--tensor-parallel", type=int, default=int(os.environ.get("SLURM_GPUS_ON_NODE", "1") or 1))

    ans = sub.add_parser("answer-phase", help="answer the single-phase attempts whose trace reached its budget")
    common(ans)
    ans.add_argument("--model", required=True)
    ans.add_argument("--source", required=True, help="the output directory of the single-phase run")
    ans.add_argument("--answer-budget", type=int, default=S.ANSWER_LIMIT)
    ans.add_argument("--distilled", action="store_true")
    ans.add_argument("--backend", default="vllm", choices=["vllm", "standin"])
    ans.add_argument("--seed", type=int, default=None)
    ans.add_argument("--tensor-parallel", type=int, default=int(os.environ.get("SLURM_GPUS_ON_NODE", "1") or 1))

    api = sub.add_parser("api", help="the batch cycle for a provider arm")
    api.add_argument("step", choices=["build", "submit", "status", "fetch", "resubmit", "finalize"])
    api.add_argument("--provider", required=True, choices=["anthropic", "openai", "gemini"])
    api.add_argument("--card", required=True, help="the arm's card name (see each provider module)")
    api.add_argument("--state", required=True, help="the state directory for this arm and set")
    api.add_argument("--tasks", default=None)
    api.add_argument("--set-name", default=None)
    api.add_argument("--only", default=None)
    api.add_argument("--attempts", type=int, default=S.ATTEMPTS_PER_TASK)
    api.add_argument("--out", default=None, help="finalize: the output directory")
    api.add_argument("--extractor", default="v2", choices=["v2", "harness"])
    api.add_argument("--allow-partial", action="store_true")
    api.add_argument("--max-batches", type=int, default=None, help="submit: at most this many batches this call")

    tab = sub.add_parser("protocols", help="print the shipped protocol table")
    tab.add_argument("--table", default=None)
    return parser


def _only(path: Optional[str]):
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return [line.split("\t")[0].strip() for line in fh if line.strip()]


def _set_name(args) -> str:
    if args.set_name:
        return args.set_name
    base = os.path.basename(os.path.normpath(args.tasks))
    for suffix in (".jsonl.gz", ".jsonl"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _protocol(args) -> PR.Protocol:
    if getattr(args, "arm", None):
        table = PR.load_table(args.table)
        if args.arm not in table:
            raise SystemExit(f"{args.arm!r} is not in the protocol table")
        p = table[args.arm]
        p.model_id = args.model or p.model_id
        return p
    make = PR.PROTOCOLS[args.protocol]
    if args.protocol == "single-phase-thinking":
        p = make(args.model, distilled=getattr(args, "distilled", False))
    else:
        p = make(args.model)
    if getattr(args, "output_limit", None):
        p.output_limit = args.output_limit
    if getattr(args, "thinking_budget", None):
        p.thinking_budget = args.thinking_budget
    if getattr(args, "answer_budget", None):
        p.answer_budget = args.answer_budget
    if getattr(args, "max_model_len", None):
        p.max_model_len = args.max_model_len
    return p


def _backend(args, protocol: PR.Protocol, tasks, out_dir: str):
    from .inference import leg_seed

    seed = args.seed
    how = "explicit"
    if seed is None:
        seed, how = leg_seed(out_dir, args.tasks if os.path.exists(args.tasks) else None, protocol.model_id)
    print(f"seed: {seed} ({how})", file=sys.stderr)
    if args.backend == "standin":
        from .standin import StandInBackend

        return StandInBackend(tasks, seed=seed), seed
    from .inference import VllmBackend

    window = protocol.max_model_len or S.MAX_MODEL_LEN_WAVE2
    prefix_caching = protocol.geometry == "grouped" or protocol.form == "thinking"
    return VllmBackend(protocol.model_id, window, seed, tensor_parallel=args.tensor_parallel, prefix_caching=prefix_caching), seed


def cmd_run(args) -> int:
    from . import thinking, vllm

    tasks = load_tasks(args.tasks, _only(args.only))
    protocol = _protocol(args)
    set_name = _set_name(args)
    backend, seed = _backend(args, protocol, tasks, args.out)
    attempts = 1 if args.greedy else args.attempts
    if protocol.prompt_style == "two-phase":
        record = thinking.generate_two_phase(tasks, protocol, backend, args.out, attempts, set_name, seed, args.extractor, args.revision)
    elif protocol.prompt_style in ("single-phase", "deepseek-v32-thinking", "deepseek-v32-chat"):
        record = thinking.generate_single_phase(tasks, protocol, backend, args.out, attempts, set_name, seed, args.extractor, args.revision)
    else:
        record = vllm.generate_arm(tasks, protocol, backend, args.out, attempts, set_name, seed, args.extractor, args.greedy, args.revision, args.tasks)
    from .records import check_counts

    check_counts(args.out, tasks, attempts)
    print(f"{record.arm}: {record.n_tasks} tasks x {attempts} attempts -> {args.out}")
    return 0


def cmd_continue(args) -> int:
    from . import vllm

    tasks = load_tasks(args.tasks, _only(args.only))
    protocol = _protocol(args)
    backend, _ = _backend(args, protocol, tasks, args.out)
    n = vllm.continue_cut_attempts(tasks, protocol, backend, args.source, args.out, _set_name(args), args.first_pass_limit, args.limit, args.extractor)
    print(f"{n} attempts continued -> {args.out}")
    return 0


def cmd_answer_phase(args) -> int:
    from . import thinking

    tasks = load_tasks(args.tasks, _only(args.only))
    args.protocol = "single-phase-thinking"
    protocol = _protocol(args)
    backend, _ = _backend(args, protocol, tasks, args.out)
    n = thinking.answer_cut_traces(tasks, protocol, backend, args.source, args.out, args.answer_budget, args.extractor)
    print(f"{n} attempts answered -> {args.out}")
    return 0


def _provider(name: str):
    if name == "anthropic":
        from .api.anthropic import Anthropic

        return Anthropic()
    if name == "openai":
        from .api.openai import OpenAI

        return OpenAI()
    from .api.gemini import Gemini

    return Gemini()


def cmd_api(args) -> int:
    from .api.batch import BatchRun

    provider = _provider(args.provider)
    run = BatchRun(provider, provider.card(args.card), args.state)
    if args.step == "build":
        if not args.tasks:
            raise SystemExit("build needs --tasks")
        tasks = load_tasks(args.tasks, _only(args.only))
        sha = file_sha256(args.tasks) if os.path.isfile(args.tasks) else None
        n = run.build(tasks, args.attempts, _set_name(args), sha)
        print(f"built {n} requests ({len(tasks)} tasks x {args.attempts}) in {args.state}")
    elif args.step == "submit":
        ids = run.submit(max_batches=args.max_batches)
        print(f"submitted {len(ids)} batch(es): {ids}" if ids else "nothing to submit")
    elif args.step == "status":
        for row in run.status():
            print(json.dumps(row))
    elif args.step == "fetch":
        print(json.dumps(run.fetch()))
    elif args.step == "resubmit":
        ids = run.resubmit()
        print(f"resubmitted in {len(ids)} batch(es): {ids}" if ids else "nothing missing")
    elif args.step == "finalize":
        if not (args.tasks and args.out):
            raise SystemExit("finalize needs --tasks and --out")
        tasks = load_tasks(args.tasks, _only(args.only))
        print(json.dumps(run.finalize(tasks, args.out, args.extractor, args.allow_partial)))
    return 0


def cmd_protocols(args) -> int:
    table = PR.load_table(args.table)
    for arm, p in sorted(table.items()):
        print(f"{arm}\t{p.form}\t{p.protocol}\t{p.protocol_version}\t{p.backend}\t{p.prompt_style}\tT={p.temperature}\tlimit={p.output_limit}\tthinking={p.thinking_budget}")
    print(f"{len(table)} arms", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 2
    return {"run": cmd_run, "continue": cmd_continue, "answer-phase": cmd_answer_phase, "api": cmd_api, "protocols": cmd_protocols}[args.action](args)


if __name__ == "__main__":
    sys.exit(main())

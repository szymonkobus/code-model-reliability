"""The command line: ``cmr <stage> ...``, one sub-command per stage plus ``site`` and ``verify``.

Each sub-command hands its arguments to the stage's ``main`` function. A stage that is not yet written says so
and points at the contract it will implement, so a reader can tell what runs today from what is planned.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from . import STAGES, __version__

COMMANDS = {
    "tasks": "load, verify and rebuild the task sets (code_model_reliability.tasks)",
    "generate": "run a model on a task set and write samples in the judge's shape (code_model_reliability.generate)",
    "judge": "run every attempt against its task's tests and write verdicts (code_model_reliability.judge)",
    "land": "turn verdicts into cells and the model registry (code_model_reliability.land)",
    "fit": "build the difficulty scale and fit the failure curve per model (code_model_reliability.fit)",
    "plot": "draw the two figures from the published tables (code_model_reliability.plot)",
    "site": "build the two site pages from the published tables (code_model_reliability.plot.site)",
    "verify": "check the shipped data against its hashes and contracts (code_model_reliability.tasks.verify)",
}

MODULE_FOR = {
    **{s: f"code_model_reliability.{s}" for s in STAGES},
    "site": "code_model_reliability.plot.site",
    "verify": "code_model_reliability.tasks.verify",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cmr", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"code-model-reliability {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<stage>")
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text, add_help=False)
        p.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # The first word names the stage; everything after it is the stage's own command line, passed through untouched
    # (argparse would otherwise read the stage's options, such as --data, as unknown options of this parser).
    if argv and argv[0] in COMMANDS:
        command, rest = argv[0], argv[1:]
    else:
        args = build_parser().parse_args(argv)
        if not args.command:
            build_parser().print_help()
            return 2
        command, rest = args.command, args.args
    module = importlib.import_module(MODULE_FOR[command])
    stage_main = getattr(module, "main", None)
    if stage_main is None:
        print(f"cmr {command}: this stage is not written yet; its contract is docs/data-contract.md", file=sys.stderr)
        return 3
    return int(stage_main(rest) or 0)


if __name__ == "__main__":
    sys.exit(main())

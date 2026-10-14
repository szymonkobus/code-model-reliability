"""``cmr fit <step> ...``: the fit stage's steps in the order they run.

    cmr fit axis       --cells cells.csv --out fits/<fit>/axis.csv            the difficulty scale and its panel
    cmr fit inputs     --cells cells.csv --axis fits/<fit>/axis.csv --fit-dir fits/<fit>
    cmr fit run        --inputs fits/<fit>/inputs/<arm>.npz --out fits/<fit>/posterior_summary_<arm>.json
    cmr fit gates      --results fits/<fit> --inputs fits/<fit>/inputs --axis fits/<fit>/axis.csv --out fits/<fit>/gates.json
    cmr fit crossings  --results fits/<fit> --gates fits/<fit>/gates.json --out-dir fits/<fit>
    cmr fit summaries  --results fits/<fit> --out-dir fits/<fit>/arms
    cmr fit all        --cells cells.csv --fit-dir fits/<fit> [--chains 2 --warmup 300 --samples 300]

``all`` runs every step on one machine, one arm after another; the published fits ran ``run`` as a cluster
array (``cluster/fit.sbatch``) and the reading steps afterwards. ``run`` needs the ``fit`` extra (numpyro and
jax); the other steps need numpy and scipy only, except ``gates``, whose R-hat and effective sample size come
from numpyro's estimators.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

STEPS = {
    "axis": "the difficulty scale from cells, with its panel",
    "inputs": "one inputs file per arm and the fit's manifest",
    "run": "fit one arm (or --self-test)",
    "gates": "the convergence gates and the concentration reading per arm",
    "crossings": "the crossings table",
    "summaries": "draw-free per-arm summaries for the figures and pages",
    "all": "every step in order on one machine",
}


def run_all(argv) -> int:
    ap = argparse.ArgumentParser(prog="cmr fit all", description=STEPS["all"])
    ap.add_argument("--cells", required=True)
    ap.add_argument("--fit-dir", required=True)
    ap.add_argument("--names", default=None, help="a JSON map from arm id to the printed name")
    ap.add_argument("--chains", type=int, default=None)
    ap.add_argument("--warmup", type=int, default=None)
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--min-tasks", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args(argv)
    fit_dir = Path(args.fit_dir)
    from . import axis as axis_mod, crossings as crossings_mod, gates as gates_mod, inputs as inputs_mod, summaries as summaries_mod
    axis_args = ["--cells", args.cells, "--out", str(fit_dir / "axis.csv")]
    if args.threshold is not None:
        axis_args += ["--threshold", str(args.threshold)]
    rc = axis_mod.main(axis_args)
    if rc:
        return rc
    in_args = ["--cells", args.cells, "--axis", str(fit_dir / "axis.csv"), "--fit-dir", str(fit_dir)]
    if args.min_tasks is not None:
        in_args += ["--min-tasks", str(args.min_tasks)]
    rc = inputs_mod.main(in_args)
    if rc:
        return rc
    engine = importlib.import_module("code_model_reliability.fit.engine")
    for name, mode in inputs_mod.read_manifest(fit_dir / "manifest.tsv"):
        out = fit_dir / f"posterior_summary_{name[:-4]}.json"
        run_args = ["--inputs", str(fit_dir / "inputs" / name), "--out", str(out), "--eiv", mode]
        for k in ("chains", "warmup", "samples"):
            v = getattr(args, k)
            if v is not None:
                run_args += [f"--{k}", str(v)]
        rc = engine.main(run_args)
        if rc:
            return rc
    rc = gates_mod.main(["--results", str(fit_dir), "--inputs", str(fit_dir / "inputs"), "--axis", str(fit_dir / "axis.csv"),
                         "--out", str(fit_dir / "gates.json")])
    if rc:
        return rc
    cr_args = ["--results", str(fit_dir), "--gates", str(fit_dir / "gates.json"), "--out-dir", str(fit_dir), "--label", fit_dir.name]
    if args.names:
        cr_args += ["--names", args.names]
    rc = crossings_mod.main(cr_args)
    if rc:
        return rc
    return summaries_mod.main(["--results", str(fit_dir), "--out-dir", str(fit_dir / "arms")])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    step, rest = argv[0], argv[1:]
    if step not in STEPS:
        print(f"cmr fit: unknown step {step!r}; one of {', '.join(STEPS)}", file=sys.stderr)
        return 2
    if step == "all":
        return run_all(rest)
    module = importlib.import_module(f"code_model_reliability.fit.{step if step != 'run' else 'engine'}")
    return int(module.main(rest) or 0)


if __name__ == "__main__":
    sys.exit(main())

"""The pipeline end to end on the fixture set: generate (the stand-in model), judge, land, fit at short chains, plot
and the site build, each stage reading the previous one's files through the contract and nothing else.

The chain runs in minutes on a CPU. A stage whose libraries are absent is skipped with the reason: the judge
needs the pinned harness, the fit's engine needs numpyro and jax; when the harness is absent the expected
verdicts of the fixture stand in for the judge's output so the later stages still run.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib.util
import json
import pathlib
import shutil

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
TASKS = FIXTURES / "tasks" / "fixture_tasks.jsonl"
ARM = "fixture-standin"
ATTEMPTS = 12


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _rows(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Every stage's output directory, built once for the module's tests."""
    root = tmp_path_factory.mktemp("pipeline")
    return {"root": root, "generate": root / "generate" / ARM, "judge": root / "judge" / ARM, "land": root / "land" / ARM,
            "fit": root / "fits" / "fixture-fit", "data": root / "data", "figures": root / "figures", "site": root / "site"}


def test_generate_writes_the_samples_and_the_record(chain):
    from code_model_reliability.generate import command
    from code_model_reliability.generate import records as R

    out = chain["generate"]
    rc = command.main(["run", "--model", "fixture-model", "--tasks", str(TASKS), "--protocol", "plain-chat", "--attempts",
                       str(ATTEMPTS), "--backend", "standin", "--out", str(out), "--seed", "7"])
    assert rc == 0
    samples = list(R.read_rows(out / R.SAMPLES))
    assert len(samples) == 3 * ATTEMPTS and {s["task_id"] for s in samples} == {
        json.loads(l)["task_id"] for l in open(TASKS, encoding="utf-8") if l.strip()}
    record = R.GenerationRecord.read(str(out))
    assert record.n_tasks == 3 and record.attempts_per_task == ATTEMPTS and record.extractor["stamp"].startswith("v2@")


def test_judge_writes_verdicts_with_their_settings(chain):
    from code_model_reliability.generate import records as R

    out = chain["judge"]
    out.mkdir(parents=True, exist_ok=True)
    if _has("evalplus"):
        from code_model_reliability.judge import evaluate, settings

        quick = dataclasses.replace(settings.CURRENT, name="pipeline-test", time_limit_floor_s=1.0, time_limit_factor=4.0,
                                    set_cap_s=4.0, memory_gib=2.0, workers=2)
        record = evaluate.judge(TASKS, chain["generate"] / R.SAMPLES, out, quick, workers=2, per_test_rows=True)
        assert record["settings_id"] == quick.id
    else:
        # the harness is not here: the fixture's expected verdicts stand in, so the later stages still run
        for name in ("verdicts.json", "judging.json", "per_test.jsonl"):
            shutil.copy(FIXTURES / "expected" / name, out / name)
    verdicts = json.load(open(out / "verdicts.json", encoding="utf-8"))
    judging = json.load(open(out / "judging.json", encoding="utf-8"))
    assert set(verdicts["eval"]) == {json.loads(l)["task_id"] for l in open(TASKS, encoding="utf-8") if l.strip()}
    for rows in verdicts["eval"].values():
        assert all(r["base_status"] in ("pass", "fail") and r["plus_status"] in ("pass", "fail") for r in rows)
    assert judging.get("settings_id") or judging.get("id")


def test_land_turns_verdicts_into_cells(chain):
    from code_model_reliability import land

    summary = land.land_arm(chain["judge"], ARM, chain["land"], "wave2")
    cells = _rows(chain["land"] / "cells.csv")
    assert summary["cells"] == len(cells) == 3
    for c in cells:
        assert c["arm"] == ARM and 0 <= int(c["failures"]) <= int(c["attempts"]) and int(c["time_limit_fails"]) <= int(c["failures"])
    assert any(int(c["failures"]) > 0 for c in cells), "the stand-in's seeded rule leaves failures in the cells"
    passk = _rows(chain["land"] / "passk.csv")
    assert passk and all(r["arm"] == ARM for r in passk)


def test_fit_at_short_chains_writes_crossings_and_summaries(chain):
    if not (_has("numpyro") and _has("jax")):
        pytest.skip("the fit's engine needs numpyro and jax (the fit extra)")
    from code_model_reliability.fit import command

    fit_dir = chain["fit"]
    rc = command.main(["all", "--cells", str(chain["land"] / "cells.csv"), "--fit-dir", str(fit_dir), "--chains", "2", "--warmup", "40",
                   "--samples", "40", "--min-tasks", "1", "--threshold", "0"])
    assert rc == 0
    axis = _rows(fit_dir / "axis.csv")
    assert len(axis) == 3 and all(a["task_id"] for a in axis)
    crossings = _rows(fit_dir / "crossings.csv")
    assert [r["arm"] for r in crossings] == [ARM]
    row = crossings[0]
    assert row["d50_status"] and row["d99_status"]
    assert (fit_dir / "gates.json").exists() and (fit_dir / "arms" / f"{ARM}.json").exists()
    summary = json.load(open(fit_dir / "arms" / f"{ARM}.json", encoding="utf-8"))
    assert "curves" in summary and "levels" in summary and "estimands" in summary and "density" in summary


def _write_registry(reg: pathlib.Path) -> None:
    """The smoke's own registry for its one arm, in the contract's shape."""
    reg.mkdir(parents=True, exist_ok=True)
    header = {"schema": "arms-registry", "n_rows": 1}
    row = {"arm": ARM, "model_id": "fixture-model", "model_name": "Fixture model", "family": "Fixture", "form": "plain",
           "protocol": "stand-in", "temperature": 0.8, "attempts_per_task": {"wave2": ATTEMPTS}, "sets": ["wave2"],
           "judging": {"wave2": "pipeline-test"}, "extractor": {"wave2": {"stamps": [], "by_cell": False}}}
    (reg / "arms.jsonl").write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    (reg / "models.jsonl").write_text(json.dumps({"model_id": "fixture-model", "name": "Fixture model", "family": "Fixture",
                                                  "total_params_b": None, "active_params_b": None, "mode": None}) + "\n", encoding="utf-8")
    (reg / "names.json").write_text(json.dumps({"runs": {}, "bases": {}}), encoding="utf-8")
    (reg / "protocols.tsv").write_text("arm\tmodel_id\tform\tprotocol\tbackend\n" + f"{ARM}\tfixture-model\tplain\tstand-in\tstandin\n",
                                       encoding="utf-8")


def test_plot_and_site_build_from_the_fit(chain):
    if not (chain["fit"] / "crossings.csv").exists():
        pytest.skip("the fit step did not run here")
    pytest.importorskip("matplotlib")
    from code_model_reliability import plot
    from code_model_reliability.plot import site

    data = chain["data"]
    published = data / "results" / "published" / chain["fit"].name
    shutil.copytree(chain["fit"], published)
    shutil.copy(chain["land"] / "cells.csv", published / "cells.csv")
    _write_registry(data / "runs" / "registry")
    rc = plot.main(["--data", str(data), "--out", str(chain["figures"]), "--fit", chain["fit"].name])
    assert rc == 0
    exports = list(chain["figures"].glob("*.svg")) + list(chain["figures"].glob("*.png"))
    assert exports, "the export function wrote the figures"
    rc = site.main(["--data", str(data), "--out", str(chain["site"]), "--fit", chain["fit"].name, "--no-node"])
    assert rc == 0
    for page in ("capability-vs-reliability", "failure-vs-difficulty"):
        assert (chain["site"] / page / "index.html").exists() and (chain["site"] / page / "data" / "manifest.json").exists()

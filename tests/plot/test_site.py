"""The site stage on the fixture: the bundles' shapes, the built copies, their checks and their determinism."""

import json
import pathlib

import pytest

from code_model_reliability.plot.site import SiteError, build_site, check_page, shell_assets
from code_model_reliability.plot.site_data import write_bundles

SHELLS = pathlib.Path(__file__).resolve().parents[2] / "site"


def _load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_plane_bundle_shapes(fit, registry, tmp_path):
    write_bundles(fit, registry, tmp_path)
    page = tmp_path / "capability-vs-reliability" / "data"
    man = _load(page / "manifest.json")
    assert set(man["files"]) == {"shared", "crossings"}
    shared = _load(page / man["files"]["shared"])
    cross = _load(page / man["files"]["crossings"])
    assert shared["set"]["label"] == "wave 1+2" and shared["set"]["tasks"] == len(fit.axis)
    assert [c["id"] for c in shared["arms"]] == [a for a in fit.arms if fit.summary(a) is not None] or len(shared["arms"]) == 4
    for c in shared["arms"]:
        assert c["label"] and c["family"] and c["color"].startswith("#") and "partial" in c and "think" in c
    assert shared["families"][:1] == ["Qwen2.5-Coder"]
    flags = {c["id"]: c["gates_failed"] for c in shared["arms"]}
    assert flags["Qwen--Qwen3-8B_temp_0.8"] is True and flags["claude-haiku-4-5_batch"] is False   # the table's gate column, FAIL and pass
    assert isinstance(shared["runs"], list)
    rows = {r["id"]: r for r in cross["rows"]}
    assert set(rows) == {c["id"] for c in shared["arms"]}
    n_lev = len(cross["levels_fail_rate"])
    assert n_lev > 0 and len(cross["density_grid"]) > 0
    for r in rows.values():
        for block in (r["average"], r["median_task"]):
            assert set(block) == {"d50", "d99", "levels"}
            assert block["d50"]["median_z"] is not None
            assert len(block["d50"]["cri80_z"]) == 2
            if block["levels"] is not None:
                assert len(block["levels"]["mid"]) == n_lev
                assert set(block["levels"]["kind"]) <= {-1, 0, 1}


def test_curves_bundle_shapes(fit, registry, tmp_path):
    write_bundles(fit, registry, tmp_path)
    page = tmp_path / "failure-vs-difficulty" / "data"
    man = _load(page / "manifest.json")
    assert set(man["files"]) == {"shared", "curves", "cells", "levels"}
    shared = _load(page / "shared.json")
    curves = _load(page / "curves.json")["arms"]
    cells = _load(page / "cells.json")["arms"]
    levels = _load(page / "levels.json")
    n_tasks = len(shared["tasks"]["id"])
    assert n_tasks == len(fit.axis) == len(shared["tasks"]["z"])
    for c in shared["arms"]:
        cv = curves[c["id"]]
        assert cv["quantiles_pct"] == [5, 10, 25, 50, 75, 90, 95]
        assert len(cv["average"]) == 7 and all(len(row) == len(cv["zgrid"]) for row in cv["average"])
        assert cv["crossings"]["d50"]["status"] in ("point", "bound", "unresolved")
        assert len(cells[c["id"]]["fails"]) == n_tasks == len(cells[c["id"]]["n"])
        blk = levels["arms"][c["id"]]["average"]
        assert blk is not None and len(blk["mid"]) == len(levels["levels_fail_rate"])


def test_shell_assets_reads_scripts_and_styles():
    html = '<link rel="stylesheet" href="kit.css"><script src="kit.js"></script><script src="app.js"></script><script src="kit.js"></script>'
    assert shell_assets(html) == ["kit.css", "kit.js", "app.js"]


def test_site_builds_both_pages(data_dir, tmp_path):
    out = tmp_path / "site"
    report = build_site(data_dir, out, shells=SHELLS, use_node=False)
    for page in ("capability-vs-reliability", "failure-vs-difficulty"):
        files = set(report["pages"][page]["files"])
        assert {"index.html", "kit.js", "kit-viz.js", "kit-export.js", "kit.css", "app.js"} <= files
        assert (out / page / "data" / "manifest.json").exists()
        assert check_page(out / page, use_node=False) == []
        # the built copy holds only what the page names: the shell files and data/
        assert {p.name for p in (out / page).iterdir()} == files | {"data"}
    assert "plane.js" in report["pages"]["capability-vs-reliability"]["files"]
    assert "curves.css" in report["pages"]["failure-vs-difficulty"]["files"]


def test_site_text_names_no_host_or_home(data_dir, tmp_path):
    out = tmp_path / "site"
    build_site(data_dir, out, shells=SHELLS, use_node=False)
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8").replace("http://www.w3.org/", "")   # the SVG namespace is a name
            assert "http://" not in text and "https://" not in text, path
            assert "/home/" not in text, path


def test_site_build_is_deterministic(data_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_site(data_dir, a, shells=SHELLS, use_node=False)
    build_site(data_dir, b, shells=SHELLS, use_node=False)
    for pa in sorted(p for p in a.rglob("*") if p.is_file()):
        pb = b / pa.relative_to(a)
        assert pb.exists() and pa.read_bytes() == pb.read_bytes(), pa


def test_check_page_names_a_missing_asset_and_an_absolute_path(tmp_path):
    page = tmp_path / "failure-vs-difficulty"
    page.mkdir()
    (page / "index.html").write_text('<script src="app.js"></script><script src="gone.js"></script>', encoding="utf-8")
    (page / "app.js").write_text("fetch('/elsewhere/data.json'); fetch(MOUNT + 'data/missing.json');", encoding="utf-8")
    problems = check_page(page, use_node=False)
    assert any("gone.js" in p for p in problems)
    assert any("starting with /" in p for p in problems)
    assert any("data/missing.json" in p for p in problems)
    assert any("manifest" in p for p in problems)


def test_an_arm_without_a_name_of_record_is_refused(fit, registry, tmp_path):
    import dataclasses
    arm = fit.arms[0]
    reg = dataclasses.replace(registry, arms={k: v for k, v in registry.arms.items() if k != arm})
    assert reg.unnamed(fit.arms) == [arm]
    with pytest.raises(ValueError, match="no name of record"):
        write_bundles(fit, reg, tmp_path)
    assert not (tmp_path / "capability-vs-reliability").exists()


def test_build_refuses_a_missing_shell(data_dir, tmp_path):
    with pytest.raises(SiteError):
        build_site(data_dir, tmp_path / "site", shells=tmp_path / "no-shells", use_node=False)

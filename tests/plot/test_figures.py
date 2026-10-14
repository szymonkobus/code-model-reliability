"""The two figures draw from the fixture and export under the plot rules: logit axes, the identity line, one legend row
per drawn arm by its name of record, no title on the export, the quiet count on the axis label."""

import re

import pytest

from code_model_reliability.plot.curves import draw_curves
from code_model_reliability.plot.export import names_part, safe_name
from code_model_reliability.plot.plane import draw_plane, plane_points, trend


def _svg(tmp_path, prefix):
    files = sorted(tmp_path.glob(f"{prefix}.*.svg"))
    assert len(files) == 1, files
    assert files[0].with_suffix(".png").exists()
    return files[0], files[0].read_text(encoding="utf-8")


def test_plane_points_and_trend(fit, registry):
    pts = plane_points(fit, registry)
    assert len(pts) == 4
    assert all(p.in_trend for p in pts)
    assert [p.arm for p in pts if p.gate_failed] == ["Qwen--Qwen3-8B_temp_0.8"]   # a failed gate fades the point and keeps it in the trend
    tr = trend(pts)
    assert tr["n"] == 4 and tr["slope_lo"] <= tr["slope"] <= tr["slope_hi"]


def test_plane_exports_under_the_plot_rules(fit, registry, tmp_path):
    fig, points, tr = draw_plane(fit, registry, tmp_path)
    ax = fig.axes[0]
    assert ax.get_aspect() == 1.0                                   # one logit unit the same length on both axes
    path, svg = _svg(tmp_path, "capability-vs-reliability")
    assert 'id="identity-line"' in svg                               # the line y = x
    for p in points:
        assert f'id="arm:{p.arm}"' in svg
    marks = {l.get_gid(): l for l in ax.lines if (l.get_gid() or "").startswith("arm:")}
    assert marks["arm:Qwen--Qwen3-8B_temp_0.8"].get_alpha() == 0.55 and marks["arm:claude-haiku-4-5_batch"].get_alpha() == 1.0   # faded: the fit failed a sampler check
    for p in points:                                                # every shown point has a legend row by its name of record
        assert p.style.label in svg
    assert "Capability against reliability" not in svg              # the export carries no title
    assert "4 models" in svg and "40 tasks" in svg                   # the quiet count rides on the axis label
    assert re.search(r"D50 — difficulty at which half the attempts fail", svg)
    assert path.name == "capability-vs-reliability.Qwen3 8B · Qwen3 8B (thinking) · Haiku 4.5 · Haiku 4.5 (thinking).svg"   # the names of record whole


def test_curves_export_under_the_plot_rules(fit, registry, tmp_path):
    fig, shown = draw_curves(fit, registry, tmp_path)
    assert len(shown) == 4
    path, svg = _svg(tmp_path, "failure-vs-difficulty")
    assert 'id="identity-line"' in svg
    for arm in shown:
        assert f'id="curve:{arm}"' in svg and f'id="band:{arm}"' in svg
        assert registry.model_name(arm) in svg
    curves = {l.get_gid(): l for l in fig.axes[0].lines if (l.get_gid() or "").startswith("curve:")}
    assert curves["curve:Qwen--Qwen3-8B_temp_0.8"].get_alpha() == 0.55 and curves["curve:claude-haiku-4-5_batch"].get_alpha() == 1.0
    assert "Failure rate against task difficulty" not in svg
    assert "40 tasks" in svg and "4 models" in svg
    ticks = re.findall(r">(\d+(?:\.\d+)?%)<", svg)
    assert "50%" in ticks and "1%" in ticks                          # the percent ticks of the logit vocabulary


def test_names_part_and_safe_name():
    assert names_part(["Haiku 4.5", "Qwen3 8B"]) == "Haiku 4.5 · Qwen3 8B"
    many = [f"Model {i}" for i in range(40)]
    s = names_part(many)
    assert s.endswith("more") and len(s) <= 150 + len(" and 99 more")
    assert safe_name("a/b: c?") == "a-b c"      # refused characters become one dash, never at a segment's end
    assert safe_name("Qwen3 8B · Haiku 4.5 (thinking)") == "Qwen3 8B · Haiku 4.5 (thinking)"


def test_figures_refuse_an_arm_without_a_name_of_record(fit, registry, tmp_path):
    import dataclasses
    reg = dataclasses.replace(registry, arms={k: v for k, v in registry.arms.items() if k != fit.arms[0]})
    with pytest.raises(ValueError, match="no name of record"):
        draw_plane(fit, reg, tmp_path)
    with pytest.raises(ValueError, match="no name of record"):
        draw_curves(fit, reg, tmp_path)
    assert not list(tmp_path.glob("*.svg"))

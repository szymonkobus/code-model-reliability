"""The palette rules: one colour per model, families by hue, the thinking channel, the training runs' marks and the
legend order."""

import json

import pytest

from code_model_reliability.plot import style
from code_model_reliability.plot.style import arm_style, family_of, legend_order, run_marks, shade, styles_for


def test_palette_lists_every_family_with_a_hue():
    pal = style.palette()
    for name, spec in pal["families"].items():
        assert spec["hue"].startswith("#") and len(spec["hue"]) == 7, name
        assert spec["ladder"] is None or all(0 < v < 1 for v in spec["ladder"]), name


def test_colours_of_record(registry):
    s = styles_for(["Qwen--Qwen3-8B_temp_0.8", "Qwen--Qwen3-8B_think_temp_0.6", "claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch"], registry)
    assert s["Qwen--Qwen3-8B_temp_0.8"].color == "#1a1fb2"           # the fourth rung of the family's ladder: Qwen3 8B's place among the base models by size here and by rank in the registry of record
    assert s["claude-haiku-4-5_batch"].color == "#199f6f"            # Claude's first rung of five
    # a thinking variant is the same model: the same colour, a dashed line and an open marker
    assert s["Qwen--Qwen3-8B_think_temp_0.6"].color == s["Qwen--Qwen3-8B_temp_0.8"].color
    assert s["Qwen--Qwen3-8B_think_temp_0.6"].open and s["Qwen--Qwen3-8B_think_temp_0.6"].dash == [4, 2]
    assert not s["Qwen--Qwen3-8B_temp_0.8"].open and s["Qwen--Qwen3-8B_temp_0.8"].dash is None
    assert len({st.color for st in s.values()}) == 2   # two models, two colours


def test_shade_keeps_hue_and_saturation():
    assert shade("#1baf7a", 0.36) == "#199f6f"
    assert shade("#5257e6", 0.40) == "#1a1fb2"


def test_family_by_registry_row_or_pattern():
    assert family_of("Qwen/Qwen3-8B", {"family": "Qwen3"}) == "Qwen3"
    assert family_of("Qwen/Qwen2.5-7B-Instruct", {"family": "Qwen2.5-Instruct"}) == "Qwen2.5"
    assert family_of("claude-sonnet-5", None) == "Claude"
    assert family_of("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", None) == "DeepSeek-R1-Distill"
    assert family_of("Qwen/Qwen3-Coder-30B-A3B-Instruct", None) == "Qwen3-Coder"
    assert family_of("some/unknown-model", None) is None


def test_a_training_run_position_darkens_along_its_ramp(registry):
    """A position of a training run takes its run's ramp at its step. The run's entry is given here in the shape names.json
    gives a run, since the published fit carries no training run and the fixture's names file therefore none."""
    run = {"name_of_record": "R1-Distill Qwen 7B (thinking) · RL, fails 1–7/8, fixed, KL", "base_model": "R1-Distill Qwen 7B (thinking)",
           "what_was_done": "RL, fails 1–7/8, fixed, KL", "chip": "RL, fails 1–7/8, fixed, KL · <steps> steps",
           "position_form": "R1-Distill Qwen 7B (thinking) · RL, fails 1–7/8, fixed, KL · <steps> steps",
           "slug": "r1-distill-qwen-7b-thinking-rl-fails-1-7-8-fixed-kl",
           "positions": [{"step": 50, "arm": "r1d7b-rl-f17-kl-step0050_think_temp_0.6"}, {"step": 100, "arm": "r1d7b-rl-f17-kl-step0100_think_temp_0.6"}]}
    base = dict(registry.arm("Qwen--Qwen3-8B_think_temp_0.6"))
    arms = {p["arm"]: {**base, "arm": p["arm"], "model_id": p["arm"].split("_")[0], "family": "DeepSeek-R1-Distill", "form": "thinking",
                       "model_name": run["position_form"].replace("<steps>", str(p["step"]))} for p in run["positions"]}
    reg = _with(registry, arms=arms, names={**registry.names, "runs": {run["slug"]: run}})
    s = styles_for(list(arms), reg)
    a, b = s["r1d7b-rl-f17-kl-step0050_think_temp_0.6"], s["r1d7b-rl-f17-kl-step0100_think_temp_0.6"]
    assert a.run == "r1-distill-qwen-7b-thinking-rl-fails-1-7-8-fixed-kl" and a.step == 50 and b.step == 100
    assert a.family == "DeepSeek-R1-Distill"
    assert a.lightness > b.lightness                      # later in training is darker
    assert a.marker == "D" and a.dot and a.open            # fails 1–7/8 is the diamond; fixed and the penalty the dot; thinking open
    assert a.dash == [8, 2, 1, 2, 1, 2]                    # the reinforcement-learning line
    assert a.label.endswith("· 50 steps")


CASES = [
    ("DeepSeek-Coder 6.7B · RL, all tasks, 1 redraw · 250 steps", "all tasks", "diamond", True, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 1–2/8, fixed · 250 steps", "fails 1–2/8", "circle", True, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 3–5/8, fixed · 250 steps", "fails 3–5/8", "square", True, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 6–7/8, fixed · 250 steps", "fails 6–7/8", "triangle", True, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 1–2/8, 2 redraws · 250 steps", "fails 1–2/8", "circle", True, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 1–2/8 · 250 steps", "fails 1–2/8", "circle", False, "RL"),
    ("DeepSeek-Coder 6.7B · RL, fails 1–3/32, 1 redraw · 250 steps", "fails 1–3/32", "circle", True, "RL"),
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–2/8, length penalty · 100 steps", "fails 1–2/8", "circle", True, "RL"),
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–7/8, fixed, KL penalty · 50 steps", "fails 1–7/8", "diamond", True, "RL"),
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–2/8, drawn from all tasks, KL penalty · 50 steps", "fails 1–2/8", "circle", True, "RL"),
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–7/8, drawn from all tasks, entropy control, KL penalty · 50 steps", "fails 1–7/8", "diamond", True, "RL"),
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–7/8, fixed, KL · 50 steps", "fails 1–7/8", "diamond", True, "RL"),   # the KL variant without the word penalty
    ("R1-Distill Qwen 7B (thinking) · RL, fails 1–2/8, KL · 100 steps", "fails 1–2/8", "circle", True, "RL"),
    ("DeepSeek-Coder 6.7B · fine-tune, fails 1–2/8, Gemma 4 12B · 240 steps", "fails 1–2/8", "circle", True, "fine-tune"),
    ("DeepSeek-Coder 6.7B · fine-tune, fails 1–2/8, Qwen3 14B passing answers · 240 steps", "fails 1–2/8", "circle", True, "fine-tune"),
]


@pytest.mark.parametrize("name,band,shape,dot,treatment", CASES)
def test_run_marks_read_the_name_of_record(name, band, shape, dot, treatment):
    m = run_marks(name)
    assert m is not None
    assert (m.band, m.shape, m.dot, m.treatment) == (band, shape, dot, treatment)
    assert m.thinking == ("(thinking)" in name)


def test_run_marks_know_the_teacher_and_the_step():
    m = run_marks("DeepSeek-Coder 6.7B · fine-tune, fails 1–2/8, Gemma 4 12B · 240 steps")
    assert m.teacher == "Gemma 4 12B" and m.steps == 240
    assert run_marks("DeepSeek-Coder 6.7B") is None
    assert run_marks("Qwen3 8B (thinking)") is None


def test_legend_order_is_by_family_then_rung_then_variant(registry):
    arms = ["claude-haiku-4-5-thinking_batch", "Qwen--Qwen3-8B_think_temp_0.6", "claude-haiku-4-5_batch", "Qwen--Qwen3-8B_temp_0.8"]
    s = styles_for(arms, registry)
    assert legend_order(s) == ["Qwen--Qwen3-8B_temp_0.8", "Qwen--Qwen3-8B_think_temp_0.6", "claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch"]


def test_an_unknown_family_draws_muted_and_says_so(registry):
    registry.arms["x"] = {"arm": "x", "model_id": "nobody/model-1b", "model_name": "Nobody 1B", "form": "plain"}
    st = arm_style("x", registry)
    assert st.color == style.palette()["muted"]
    assert st.notes


def test_palette_file_is_valid_json_with_the_ground():
    pal = json.loads(style.PALETTE_PATH.read_text(encoding="utf-8"))
    assert pal["ground"] == "#fcfaf3"


def test_two_models_the_registry_cannot_place_on_the_ladder_are_refused(registry):
    """Two Claude models whose model rows carry no rank and no size would land on one rung: one colour for two models
    breaks the plot rules, so the styling refuses them and names them, as it refuses an arm without a name of record."""
    import dataclasses
    base = dict(registry.arm("claude-haiku-4-5_batch"))
    rows = {"claude-sonnet-5_batch": {**base, "arm": "claude-sonnet-5_batch", "model_id": "claude-sonnet-5-99999999", "model_name": "Sonnet 5"},
            "claude-opus-5_batch": {**base, "arm": "claude-opus-5_batch", "model_id": "claude-opus-5-99999999", "model_name": "Opus 5"}}
    reg = dataclasses.replace(registry, arms={**registry.arms, **rows})   # two arms whose model ids join no model row: no rank, no size
    with pytest.raises(ValueError, match="one colour per model") as e:
        styles_for(["claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch", *rows], reg)
    assert "Claude: 2 models" in str(e.value) and "Opus 5" in str(e.value) and "Sonnet 5" in str(e.value)
    # the base model and its thinking form sharing a colour is the rule, not a clash
    s = styles_for(["claude-haiku-4-5_batch", "claude-haiku-4-5-thinking_batch"], registry)
    assert s["claude-haiku-4-5_batch"].color == s["claude-haiku-4-5-thinking_batch"].color


def _with(registry, models=None, arms=None, names=None):
    import dataclasses
    return dataclasses.replace(registry, models={**registry.models, **(models or {})}, arms={**registry.arms, **(arms or {})},
                               names=names if names is not None else registry.names)


def test_the_two_forms_of_one_model_share_a_rank_and_a_rung_while_ranked_models_differ(registry):
    """The registry gives a model's plain and thinking forms one rank (two model rows, the mode column apart): they share
    a rung by design, and models with different ranks take different rungs — the colour of record for a family whose
    models have no size."""
    models = {"claude-opus-5": {"model_id": "claude-opus-5", "name": "Opus 5", "family": "Claude", "rank": 5, "mode": None},
              "claude-opus-5-thinking": {"model_id": "claude-opus-5-thinking", "name": "Opus 5 (thinking)", "family": "Claude", "rank": 5, "mode": "thinking"},
              "claude-haiku-4-5": {"model_id": "claude-haiku-4-5", "name": "Haiku 4.5", "family": "Claude", "rank": 1, "mode": None},
              "claude-sonnet-5": {"model_id": "claude-sonnet-5", "name": "Sonnet 5", "family": "Claude", "rank": 2, "mode": None}}
    base = dict(registry.arm("claude-haiku-4-5_batch"))
    arms = {"claude-opus-5_batch": {**base, "arm": "claude-opus-5_batch", "model_id": "claude-opus-5", "model_name": "Opus 5", "form": "plain"},
            "claude-opus-5-thinking_batch": {**base, "arm": "claude-opus-5-thinking_batch", "model_id": "claude-opus-5-thinking", "model_name": "Opus 5 (thinking)", "form": "thinking"},
            "claude-haiku-4-5_batch": {**base, "model_id": "claude-haiku-4-5"},
            "claude-sonnet-5_batch": {**base, "arm": "claude-sonnet-5_batch", "model_id": "claude-sonnet-5", "model_name": "Sonnet 5", "form": "plain"}}
    reg = _with(registry, models=models, arms=arms)
    s = styles_for(list(arms), reg)
    assert s["claude-opus-5_batch"].color == s["claude-opus-5-thinking_batch"].color
    assert s["claude-opus-5-thinking_batch"].open and s["claude-opus-5-thinking_batch"].dash
    assert len({s[a].color for a in ("claude-haiku-4-5_batch", "claude-sonnet-5_batch", "claude-opus-5_batch")}) == 3
    assert s["claude-haiku-4-5_batch"].lightness > s["claude-sonnet-5_batch"].lightness > s["claude-opus-5_batch"].lightness   # rank 1 the lightest rung


def test_training_run_checkpoints_never_enter_the_family_ladder(registry):
    """A checkpoint row of a training run has a size and no rank; it takes its run's ramp, so it adds no rung to its
    family's ladder and the family keys by rank when its models carry one."""
    from code_model_reliability.plot.style import _family_ranks
    fam = registry.model("Qwen--Qwen3-8B_temp_0.8")["family"]
    pinned = set(style.palette()["pinned"])                            # a pinned model keeps its own rung and leaves the count, as a variant does
    expected = sorted(float(r["rank"]) for mid, r in registry.models.items() if r.get("family") == fam and mid not in pinned and " · " not in r["name"])
    assert _family_ranks(registry, fam) == (expected, "rank")          # the published rows carry the registry's rank
    step = {"Qwen/Qwen3-8B-step0050": {"model_id": "Qwen/Qwen3-8B-step0050", "name": "Qwen3 8B · 50 steps", "family": fam, "total_params_b": 8.2, "mode": None}}
    arm = {"qwen3-8b-run-step0050_temp_0.8": {**registry.arm("Qwen--Qwen3-8B_temp_0.8"), "arm": "qwen3-8b-run-step0050_temp_0.8", "model_id": "Qwen/Qwen3-8B-step0050"}}
    names = {**registry.names, "runs": {**registry.names["runs"], "qwen3-8b-run": {"name_of_record": "Qwen3 8B · run", "base_model": "Qwen3 8B",
                                                                                     "positions": [{"step": 50, "arm": "qwen3-8b-run-step0050_temp_0.8"}]}}}
    reg = _with(registry, models=step, arms=arm, names=names)
    assert _family_ranks(reg, fam) == (expected, "rank")                # the checkpoint's size is not a rung


def test_a_variant_named_after_its_base_model_keeps_the_base_colour_and_leaves_the_ladder(registry):
    """A fine-tune or other variant is named after its base model with a middle dot: it takes the base's rung and
    colour and its treatment's line pattern, and adds no rung to the family's ladder."""
    from code_model_reliability.plot.style import _family_ranks
    fam = registry.model("Qwen--Qwen3-8B_temp_0.8")["family"]
    before = _family_ranks(registry, fam)
    models = {"qwen3-8b-sft-code": {"model_id": "qwen3-8b-sft-code", "name": "Qwen3 8B · code fine-tune", "family": fam, "total_params_b": 8.0, "mode": None}}
    arms = {"qwen3-8b-sft-code_temp_0.8": {**registry.arm("Qwen--Qwen3-8B_temp_0.8"), "arm": "qwen3-8b-sft-code_temp_0.8",
                                           "model_id": "qwen3-8b-sft-code", "model_name": "Qwen3 8B · code fine-tune"}}
    reg = _with(registry, models=models, arms=arms)
    assert _family_ranks(reg, fam) == before                                       # the variant's size 8.0 is not a rung
    s = styles_for(["Qwen--Qwen3-8B_temp_0.8", "qwen3-8b-sft-code_temp_0.8", "Qwen--Qwen3-8B_think_temp_0.6"], reg)
    v, b, th = s["qwen3-8b-sft-code_temp_0.8"], s["Qwen--Qwen3-8B_temp_0.8"], s["Qwen--Qwen3-8B_think_temp_0.6"]
    assert v.color == b.color == th.color
    assert v.dash == style.palette()["lines"]["fine_tune"] and b.dash is None and th.dash == style.palette()["lines"]["thinking"]
    assert v.label == "Qwen3 8B · code fine-tune" and any("variant of Qwen3 8B" in n for n in v.notes)


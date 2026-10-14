"""The gates: the verdict logic, the concentration reading, and the crossing-level statistics on known chains."""

import json

import numpy as np
import pytest

from code_model_reliability.fit import gates


def test_concentration_regimes_by_hand():
    easy = {f"t{i}" for i in range(20)}            # top 5% of 20 easy tasks = 1 task
    tasks = [f"t{i}" for i in range(30)]
    f_diffuse = [1.0] * 20 + [5.0] * 10
    c = gates.concentration(tasks, f_diffuse, easy)
    assert c["share_top5pct_easy_third"] == pytest.approx(1 / 20) and c["regime"] == "diffuse"
    assert c["any_fail_share_easy_third"] == 1.0 and c["n_easy_third_tasks"] == 20
    f_extreme = [20.0] + [0.0] * 19 + [5.0] * 10
    c = gates.concentration(tasks, f_extreme, easy)
    assert c["share_top5pct_easy_third"] == 1.0 and c["regime"] == "extreme"
    f_conc = [6.0] + [0.5] * 8 + [0.0] * 11 + [5.0] * 10
    c = gates.concentration(tasks, f_conc, easy)
    assert c["share_top5pct_easy_third"] == pytest.approx(0.6) and c["regime"] == "concentrated"
    assert gates.concentration(tasks, [0.0] * 30, easy)["regime"] == "no easy-third failures"
    assert gates.concentration(tasks, [1.0] * 30, set())["regime"] == "no easy-third tasks"


def test_easy_third_is_the_lowest_third_of_the_axis():
    z = {f"t{i}": float(i) for i in range(10)}
    assert gates.easy_third(z) == {"t0", "t1", "t2", "t3"}


def test_verdict_from_components():
    cfg = {"chains": 4, "samples": 8000}                        # 32,000 kept draws
    res = {"diagnostics": {"num_divergences": 0}, "config": cfg}
    mixing = {"d50": {"mixes": True, "rhat_ok": True, "ess_ok": True}, "d99": {"mixes": False, "rhat_ok": False, "ess_ok": True}}
    v = gates.verdict(res, mixing)
    assert v["gate"] == "FAIL" and v["gates_failed"] == ["rhat"] and v["divergence_gate"] == "pass"
    bound = {"d50": {"mixes": None, "rhat_ok": False, "ess_ok": False}, "d99": {"mixes": True, "rhat_ok": True, "ess_ok": True}}
    assert gates.verdict(res, bound)["gate"] == "pass"            # a bound level is exempt
    # eleven divergences in 32,000 draws: under the share rule a pass with a note; the engine's count flag says FAIL beside
    v = gates.verdict({"diagnostics": {"num_divergences": 11}, "config": cfg}, bound)
    assert v["gate"] == "pass" and v["divergence_gate"] == "pass_with_note" and v["engine_divergence_flag"] == "FAIL"
    assert v["divergence_share"] == pytest.approx(11 / 32000, abs=1e-6)      # the share is written to six decimals
    # above half a percent of the draws: a failure
    v = gates.verdict({"diagnostics": {"num_divergences": 200}, "config": cfg}, bound)
    assert v["gate"] == "FAIL" and v["gates_failed"] == ["divergences"]
    # with no draw count the engine's count flag decides
    v = gates.verdict({"diagnostics": {"num_divergences": 5}}, bound)
    assert v["gate"] == "FAIL" and v["divergence_share"] is None


def test_crossing_mixing_on_good_and_bad_chains(synthetic_result):
    pytest.importorskip("numpyro")
    good = gates.crossing_mixing(synthetic_result(per_chain=200))
    assert good["d50"]["mixes"] is True and good["d50"]["rhat"] <= gates.GATE_RHAT_MAX and good["d50"]["basis"] == "full"
    assert len(good["d50"]["chain_medians"]) == 4 and good["d50"]["spread"] < 0.2
    bad = gates.crossing_mixing(synthetic_result(per_chain=200, chain_shift=3.0))
    assert bad["d50"]["mixes"] is False and bad["d50"]["rhat"] > gates.GATE_RHAT_MAX and bad["d50"]["spread"] > 2.0
    bound = gates.crossing_mixing(synthetic_result(per_chain=200, left_share_d99=0.7))
    assert bound["d99"]["bound"] is True and bound["d99"]["mixes"] is None


def test_gates_for_fit_writes_a_verdict_per_arm(tmp_path, synthetic_result, write_result):
    pytest.importorskip("numpyro")
    write_result(synthetic_result(per_chain=200), arm="arm-a")
    write_result(synthetic_result(per_chain=200, chain_shift=3.0, seed=1), arm="arm-b")
    inp = tmp_path / "inputs"
    inp.mkdir()
    for arm in ("arm-a", "arm-b"):
        np.savez(inp / f"{arm}.npz", model_id=np.array(arm), z_hat=np.linspace(-3, 3, 60), sd=np.full(60, 0.1),
                 f=np.array([8] + [0] * 19 + [4] * 40), n=np.full(60, 8), task_ids=np.array([f"t{i:02d}" for i in range(60)]))
    out = tmp_path / "gates.json"
    assert gates.main(["--results", str(tmp_path), "--inputs", str(inp), "--out", str(out)]) == 0
    g = json.loads(out.read_text())
    assert g["n_arms"] == 2 and g["n_pass"] == 1
    assert g["arms"]["arm-a"]["gate"] == "pass" and g["arms"]["arm-b"]["gate"] == "FAIL"
    assert g["arms"]["arm-a"]["concentration"]["regime"] in ("extreme", "concentrated")
    assert g["arms"]["arm-b"]["chains_disagree_on"] == ["D50", "D99"]

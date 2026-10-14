"""The engine: its self-test with short chains and a fit of a small synthetic arm end to end.

These need the ``fit`` extra (numpyro and jax) and a few minutes of CPU; they run when CMR_FIT_ENGINE_TESTS=1 is
set (the cluster smoke sets it) and are skipped otherwise, so the light test run stays light.
"""

import json
import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CMR_FIT_ENGINE_TESTS") != "1",
                                reason="engine tests run with CMR_FIT_ENGINE_TESTS=1 (minutes of CPU, numpyro and jax)")


@pytest.fixture(scope="module")
def engine():
    pytest.importorskip("numpyro")
    pytest.importorskip("jax")
    from code_model_reliability.fit import engine as eng
    return eng


def test_self_test_passes_with_short_chains(tmp_path, engine):
    out = tmp_path / "self_test.json"
    assert engine.self_test(str(out), chains=2, warmup=300, samples=300) == 0
    rep = json.loads(out.read_text())
    assert rep["prior_predictive"]["pass"] and rep["synthetic_recovery"]["pass"]


def test_fit_arm_writes_every_block_and_is_deterministic(tmp_path, engine):
    rng = np.random.default_rng(1)
    T = 40
    z = np.sort(rng.uniform(-3, 3, T))
    p = 1 / (1 + np.exp(-(1.2 * z + 0.3)))
    inputs = {"model_id": "synthetic", "z_hat": z, "sd": np.full(T, 0.1), "f": rng.binomial(16, p).astype(np.int64),
              "n": np.full(T, 16, np.int64), "task_ids": [f"t{i}" for i in range(T)]}
    a = engine.fit_arm(inputs, chains=2, warmup=150, samples=150)
    b = engine.fit_arm(inputs, chains=2, warmup=150, samples=150)
    assert a["param_draws"] == b["param_draws"]                       # the same seed, the same draws
    for key in ("estimands", "estimands_avg", "draws", "draws_avg", "draws_avg_full", "levels_table", "levels_table_avg",
                "curves", "linefit", "diagnostics", "param_draws", "grid", "config"):
        assert key in a
    assert set(a["estimands_avg"]) == {"d50", "d99", "d97", "d95", "d90"}
    assert len(a["draws_avg_full"]["d50"]["z"]) == 300 and a["draws_avg_full"]["d50"]["order"] == "chain-major"
    assert a["config"]["crossing_rule"] == "middle" and a["config"]["m_basis"] >= 40
    assert len(a["curves"]["zgrid"]) == 121
    d50 = a["estimands_avg"]["d50"]
    assert d50["median_z"] is not None and d50["cri80_z"][0] < d50["median_z"] < d50["cri80_z"][1]
    assert -1.0 < d50["median_z"] < 0.5                                # the truth is near -0.25 on the logit axis

#!/usr/bin/env python3
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pct(z):
    return round(100 / (1 + math.exp(-z)), 1)


dots = json.loads((HERE / "dots.json").read_text())
panel = dots["Combined (HumanEval+ & MBPP+)"]
fit = dots["_fit"]
cf = json.loads((HERE / "counterfactuals.json").read_text())
six = json.loads((HERE / "counterfactual_six_only.json").read_text())

r1 = panel["deepseek-ai/DeepSeek-R1-0528"]
sonnet_t = panel["claude-sonnet-5-thinking"]
resids = list(fit["residuals"].values())

numbers = {
    "rel_published_pct": pct(cf["V0"]["rel"]),
    "rel_extraction_pct": pct(cf["V1"]["rel"]),
    "rel_six_fixed_pct": pct(six["rel"]),
    "rel_both_pct": pct(cf["V2"]["rel"]),
    "rel_easyband_pct": pct(cf["V3"]["rel"]),
    "rel_sonnet_think_pct": pct(sonnet_t["rel"][1]),
    "cap_r1_pct": pct(r1["cap"][1]),
    "trend_prediction_pct": pct(fit["inter"] + fit["slope"] * r1["cap"][1]),
    "residual_r1": round(fit["residuals"]["deepseek-ai/DeepSeek-R1-0528"], 2),
    "residual_six_fixed": round(six["resid"], 2),
    "residual_spread": round(statistics.pstdev(resids), 2),
    "residual_v32_think": round(
        fit["residuals"]["deepseek-ai/DeepSeek-V3.2-Thinking"], 2),
    "n_models_fit": fit["n"],
}
(HERE / "knowledge" / "numbers.json").write_text(
    json.dumps(numbers, indent=1))
print(json.dumps(numbers, indent=1))

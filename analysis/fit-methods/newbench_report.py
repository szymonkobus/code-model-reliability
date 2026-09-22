import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

BASE = Path(__file__).resolve().parent.parent
df = pd.read_csv(BASE / "fits/newbench_replication.csv")

SPREAD_MIN = 30  # tasks needed on each side of 50% Jeffreys failure


def hinge_params(prow):
    a, b1, b2, z0 = json.loads(prow)
    # 50% failure crossing of the hinge fit
    if a > 0:
        z50 = z0 - a / b1 if b1 > 0 else np.nan
    else:
        z50 = z0 - a / b2 if b2 > 0 else np.nan
    return a, b1, b2, z0, z50


rows = []
for (bench, cfg), g in df.groupby(["bench", "config"]):
    g = g.set_index("family")
    nt = int(g.ntask.iloc[0])
    spread_ok = (g.n_easyside.iloc[0] >= SPREAD_MIN
                 and g.n_hardside.iloc[0] >= SPREAD_MIN)
    a, b1, b2, z0, z50 = hinge_params(g.loc["hinge", "params"])
    fp = json.loads(g.loc["fourpl", "params"])
    q0, q1 = expit(fp[2]), expit(fp[3])
    cv = g.cv_dev
    r = dict(bench=bench, config=cfg, ntask=nt,
             in_pop=bool(g.in_difficulty_pop.iloc[0]),
             n_easy=int(g.n_easyside.iloc[0]),
             n_hard=int(g.n_hardside.iloc[0]), spread_ok=spread_ok,
             cv_logistic=cv["logistic"], cv_hinge=cv["hinge"],
             cv_softknee=cv["softknee"], cv_fourpl=cv["fourpl"],
             d_hinge=(cv["logistic"] - cv["hinge"]) / nt,
             d_softknee=(cv["logistic"] - cv["softknee"]) / nt,
             d_fourpl=(cv["logistic"] - cv["fourpl"]) / nt,
             winner=cv.idxmin(),
             b_easy=b1, b_hard=b2, z0=z0, z50_hinge=z50, hinge_a=a,
             fourpl_q0=q0, fourpl_q1=q1,
             aic_win=g.aic.idxmin(), bic_win=g.bic.idxmin())
    rows.append(r)
S = pd.DataFrame(rows).sort_values(["bench", "config"])
S.to_csv(BASE / "fits/newbench_replication_summary.csv", index=False)

pd.set_option("display.width", 250)
for bench, g in S.groupby("bench"):
    print(f"\n=== {bench} (n configs {len(g)}, spread_ok {g.spread_ok.sum()})")
    cols = ["config", "ntask", "n_hard", "spread_ok", "d_hinge",
            "d_softknee", "d_fourpl", "winner", "b_easy", "b_hard",
            "z0", "z50_hinge", "fourpl_q0", "fourpl_q1", "bic_win"]
    print(g[cols].to_string(index=False,
                            float_format=lambda x: f"{x:.4g}"))

ok = S[S.spread_ok]
print("\n=== HEADLINE (spread_ok configs, n =", len(ok), ")")
print("hinge beats logistic OOS:", (ok.d_hinge > 0).sum(), "/", len(ok),
      " median dCV/task", ok.d_hinge.median().round(4))
print("softknee beats logistic:", (ok.d_softknee > 0).sum(), "/", len(ok),
      " median", ok.d_softknee.median().round(4))
print("fourpl beats logistic:", (ok.d_fourpl > 0).sum(), "/", len(ok),
      " median", ok.d_fourpl.median().round(4))
print("fourpl beats hinge:",
      ((ok.cv_fourpl < ok.cv_hinge)).sum(), "/", len(ok))
print("b_easy > b_hard:", (ok.b_easy > ok.b_hard).sum(), "/", len(ok))
print("b_easy range", ok.b_easy.quantile([0, .5, 1]).round(2).tolist(),
      " b_hard range", ok.b_hard.quantile([0, .5, 1]).round(2).tolist())
print("z0 quantiles", ok.z0.quantile([0, .25, .5, .75, 1]).round(2).tolist())
print("z0 - z50 quantiles",
      (ok.z0 - ok.z50_hinge).quantile([0, .25, .5, .75, 1]).round(2).tolist())
print("fourpl q0 > 0.001:", (ok.fourpl_q0 > 1e-3).sum(), "/", len(ok),
      "; q0 quantiles", ok.fourpl_q0.quantile([0, .5, .9, 1]).round(4).tolist())
print("fourpl q1 quantiles",
      ok.fourpl_q1.quantile([0, .1, .5, 1]).round(4).tolist())
print("CV winner counts:", ok.winner.value_counts().to_dict())
print("BIC winner counts:", ok.bic_win.value_counts().to_dict())

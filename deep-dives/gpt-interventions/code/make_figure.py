#!/usr/bin/env python3
"""The one figure: share of attempts that failed, per condition, on the trap tasks and on the control
tasks (gpt-5-mini). Emitted as an HTML fragment (site/fig/fail_share.html) so the labels keep the page's
font size on a phone, plus the plotted numbers (site/fig/fail_share.json). House palette: trap #2a78d6,
control #eb6834 (validated against the sepia surface); thin bars with rounded data ends, direct labels,
a title tooltip per bar, text in ink tokens, a legend for the two series, and the table below as the table view.
"""
import json, os, html
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "..", "data")
R = json.load(open(os.path.join(D, "results.json"))); S = R["summary"]["gpt-5-mini"]
inter = json.load(open(os.path.join(D, "interventions.json")))
def cap(s): return s[0].upper() + s[1:]
conds = [{"name": "No instruction (the 128-attempt record)", "trap": S["i1"]["trap_baseline_fail_rate"],
          "trap_label": f"about {S['i1']['trap_expected_failures_without_instruction']:.0f} of {S['i1']['trap_attempts']} expected to fail",
          "control": 0.0, "control_label": "0 of 128 fail on each control task"}]
for iid in ["i1", "i2", "i3"]:
    s = S[iid]
    conds.append({"name": cap(inter[iid]["name"]), "trap": s["trap_fail_rate"],
                  "trap_label": f"{s['trap_failures']} of {s['trap_attempts']} attempts failed",
                  "control": s["control_failures"] / s["control_attempts"] if s["control_attempts"] else 0.0,
                  "control_label": f"{s['control_failures']} of {s['control_attempts']} attempts failed"})
SCALE = 50  # bar width = share / 0.5 of the track: a 50% failure share fills the track
out = ['<div class=chart role=img aria-label="Share of attempts that failed, by instruction, trap tasks against control tasks">']
for c in conds:
    out.append(f'<div class=cond><div class=cname>{html.escape(c["name"])}</div>')
    for series, key, lab, cls in [("trap tasks", "trap", c["trap_label"], "trap"), ("control tasks", "control", c["control_label"], "ctrl")]:
        pct = min(c[key] / (SCALE / 100), 1.0) * 100
        out.append(f'<div class=row><div class=track><div class="bar {cls}" style="width:{pct:.1f}%" title="{html.escape(series)}: {html.escape(lab)}"></div></div><div class=val>{html.escape(lab)}</div></div>')
    out.append('</div>')
out.append('<div class=axis><span>0%</span><span>25%</span><span>50% of attempts failed</span></div>')
out.append('<div class=legend><span title="its ten worst easy tasks (the two worst twice), plus five further trap tasks for the third instruction"><i class="sw trap"></i>trap tasks</span><span title="two it always passes"><i class="sw ctrl"></i>control tasks</span></div>')
out.append('</div>')
os.makedirs(os.path.join(HERE, "..", "site", "fig"), exist_ok=True)
p = os.path.join(HERE, "..", "site", "fig", "fail_share.html")
open(p + ".tmp", "w").write("\n".join(out)); os.replace(p + ".tmp", p)
json.dump({"conditions": conds, "scale_full_track_share": SCALE / 100}, open(os.path.join(HERE, "..", "site", "fig", "fail_share.json"), "w"), indent=1)
print("figure ->", p)

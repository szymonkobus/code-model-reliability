# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Lens (a): curve shape of the Bayesian fit of record (average-rate curve) for the set arms.
Reads fitting's posterior summaries (read-only). Slope vs floor: with equal 50% crossings, a straight logit line
predicts the 1% crossing from the slope alone; the gap between that prediction and the fitted 1% crossing is the easy-end floor.
Outputs out/curve_shape.json."""
import json, math, os, csv
import numpy as np
HOME=os.path.expanduser('~')
SET=json.load(open('out/set_of_record.json'))
ptr=json.load(open(SET['pointer'])); rdir=ptr['results_dir']
axis=[float(r['z_hat']) for r in csv.DictReader(open(os.path.dirname(rdir)+'/axis_export.csv'))]
axis=np.array(sorted(axis))
def sig(z): return 1/(1+math.exp(-z))
def tasks_below(z): return int((axis<z).sum())
def logit(p): return math.log(p/(1-p))
out={}
for x in SET['set']+SET['near_boundary']:
    d=json.load(open(f"{rdir}/posterior_summary_{x['stem']}_eivon.json"))
    zg=np.array(d['curves']['zgrid']); qs=d['curves']['quantiles_pct']; A=np.array(d['curves']['average_logit'])  # 7 x 121 logit fail rate
    med=A[qs.index(50)]; lo=A[qs.index(10)]; hi=A[qs.index(90)]
    z50=x['cap_z']; z1=x['rel_z']
    # fitted average curve values at the easiest axis task and at a few difficulty shares
    def at(z): return float(np.interp(z,zg,med))
    easiest=float(axis.min())
    # local slope (logit fail per logit difficulty) around the 1% crossing and between crossings
    def slope_at(z,h=0.5): return (at(z+h)-at(z-h))/(2*h)
    s1=slope_at(z1); s_mid=(at(z50)-at(z1))/(z50-z1) if z50>z1 else None
    # straight-line prediction of the 1% crossing from the 50% crossing and the posterior linefit slope of the average curve
    lf=d['linefit']['average']; b=float(np.median(lf['slope']))
    z1_line=z50-(logit(0.5)-logit(0.01))/b
    # slope measured on the fitted curve between 50% and 10% fail (the steep part), then extrapolated to 1%
    # find z where med crosses logit(0.10)
    def cross(level):
        L=logit(level); idx=np.where(np.diff(np.sign(med-L))!=0)[0]
        if len(idx)==0: return None
        i=idx[0]; return float(zg[i]+(L-med[i])*(zg[i+1]-zg[i])/(med[i+1]-med[i]))
    z10=cross(0.10); z2=cross(0.02)
    s_50_10=(logit(0.5)-logit(0.10))/(z50-z10) if z10 else None
    z1_from_steep=(z10-(logit(0.10)-logit(0.01))/s_50_10) if z10 else None
    out[x['page_id']]=dict(label=x['label'], cap_pct=x['cap_pct'], rel_pct=x['rel_pct'], cap_tasks=x['cap_tasks_below'], rel_tasks=x['rel_tasks_below'],
        fail_at_easiest_task=sig(at(easiest)), fail_at_easiest_task_cri80=[sig(float(np.interp(easiest,zg,lo))),sig(float(np.interp(easiest,zg,hi)))],
        fail_at_1pct_difficulty=sig(at(logit(0.01))), fail_at_5pct_difficulty=sig(at(logit(0.05))), fail_at_10pct_difficulty=sig(at(logit(0.10))),
        slope_at_1pct_crossing=s1, slope_between_crossings=s_mid, linefit_slope_median=b, slope_50_to_10=s_50_10,
        z1_line_pred=z1_line, rel_pct_if_straight_line=100*sig(z1_line), rel_tasks_if_straight_line=tasks_below(z1_line),
        z1_from_steep_part=z1_from_steep, rel_pct_from_steep_part=(100*sig(z1_from_steep) if z1_from_steep else None), rel_tasks_from_steep_part=(tasks_below(z1_from_steep) if z1_from_steep else None),
        z10=z10, z2=z2, tasks_below_10pct_cross=(tasks_below(z10) if z10 else None), tasks_below_2pct_cross=(tasks_below(z2) if z2 else None),
        tau=x['tau'], rho_icc=x['rho_icc'], in_set=(x in SET['set']))
json.dump(out,open('out/curve_shape.json','w'),indent=1)
print(f"{'arm':26s} {'cap%':>5s} {'rel%':>6s} {'rel#':>4s} | {'fail@easiest':>12s} {'fail@1%d':>8s} {'fail@10%d':>9s} | {'slope@1%':>8s} {'slope50-10':>10s} {'linefit':>7s} | {'rel# straight':>13s} {'rel# steep-part':>15s} {'10%#':>5s}")
for k,v in sorted(out.items(), key=lambda kv: kv[1]['rel_pct']):
    print(f"{v['label']:26s} {v['cap_pct']:5.1f} {v['rel_pct']:6.2f} {v['rel_tasks']:4d} | {100*v['fail_at_easiest_task']:11.2f}% {100*v['fail_at_1pct_difficulty']:7.2f}% {100*v['fail_at_10pct_difficulty']:8.2f}% | {v['slope_at_1pct_crossing']:8.2f} {v['slope_50_to_10'] or 0:10.2f} {v['linefit_slope_median']:7.2f} | {v['rel_tasks_if_straight_line']:13d} {v['rel_tasks_from_steep_part'] or 0:15d} {v['tasks_below_10pct_cross'] or 0:5d}" + ("" if v['in_set'] else "  (context)"))

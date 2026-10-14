# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "matplotlib"]
# ///
"""THE FIGURE: the ten set arms' difficulty curves (Bayesian fit of record, average-rate curve: expected failure rate
vs pooled difficulty, with the 80% band) on one plot, no text inside the plot area; legend below. Second variant:
small multiples (one panel per arm, the other nine in grey, same axes). Copy-ready PNG/SVG/PDF under site/fig/.
Colours: a ten-slot categorical palette validated with the dataviz validator on the sepia surface (#faf6ec);
slots assigned in a fixed order to the arms sorted from least to most reliable; thinking arms dashed."""
import json, math, os
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import os as _os, numpy as _np
MX, MY = (_os.environ.get('MODES') or 'logit:logit').split(':')
DEFAULT = (MX == 'logit' and MY == 'logit'); SUF = '' if DEFAULT else f'__x-{MX}__y-{MY}'
def _pct(z): return 100 / (1 + _np.exp(-_np.asarray(z, float)))
TX = (lambda z: _np.asarray(z, float)) if MX == 'logit' else _pct
TY = (lambda z: _np.asarray(z, float)) if MY == 'logit' else _pct
NT = [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]   # ticks on a normal (linear percent) axis
SET=json.load(open('out/set_of_record.json')); ptr=json.load(open(SET['pointer'])); rdir=ptr['results_dir']
PAL=["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4","#008300","#4a3aa7","#e34948","#8e24aa","#a0522d","#4f6d7a","#9c8a1c","#c2185b","#00838f"]   # 14 slots: the window can hold more than ten arms
SURF='#faf6ec'
def nice(label): return label.replace('DS-R1D-','DeepSeek-R1-Distill-').replace('Qwen3-4B-2507','Qwen3-4B-Instruct-2507')
arms=sorted(SET['set'], key=lambda x:x['rel_pct'])   # least -> most reliable
for i,x in enumerate(arms): x['color']=PAL[i%len(PAL)]; x['dash']=('think' in x['stem']); x['name']=nice(x['label'])
curves={}
for x in arms:
    d=json.load(open(f"{rdir}/posterior_summary_{x['stem']}_eivon.json")); c=d['curves']; q=c['quantiles_pct']
    A=np.array(c['average_logit']); curves[x['arm_id']]=dict(z=np.array(c['zgrid']), med=A[q.index(50)], lo=A[q.index(10)], hi=A[q.index(90)])
def sig(z): return 1/(1+np.exp(-z))
def logit(p): return math.log(p/(1-p))
TICKS=[0.1,0.2,0.5,1,2,5,10,20,50,80,90,95,99]
XL=(logit(0.0008), logit(0.995)); YL=(logit(0.0008), logit(0.995))
TKX=TICKS if MX=='logit' else NT; TKY=TICKS if MY=='logit' else NT
def style(ax, minor=True):
    ax.set_facecolor(SURF)
    for s in ('top','right'): ax.spines[s].set_visible(False)
    for s in ('left','bottom'): ax.spines[s].set_color('#cfc5ac'); ax.spines[s].set_linewidth(0.8)
    ax.set_xlim(float(TX(XL[0])), float(TX(XL[1]))); ax.set_ylim(float(TY(YL[0])), float(TY(YL[1])))
    ax.set_xticks([float(TX(logit(t/100))) for t in TKX]); ax.set_yticks([float(TY(logit(t/100))) for t in TKY])
    ax.set_xticklabels([f"{t:g}%" for t in TKX], fontsize=8, color='#52514e'); ax.set_yticklabels([f"{t:g}%" for t in TKY], fontsize=8, color='#52514e')
    ax.tick_params(length=3, color='#cfc5ac')
    ax.grid(True, color='#e6dfcd', linewidth=0.6)
    ax.axhline(float(TY(logit(0.01))), color='#8b8477', linewidth=0.8); ax.axhline(float(TY(logit(0.5))), color='#8b8477', linewidth=0.8)
def draw(ax, x, alpha_band=0.13, lw=1.9, grey=False):
    c=curves[x['arm_id']]; col='#c9c2b1' if grey else x['color']
    if not grey: ax.fill_between(TX(c['z']), TY(c['lo']), TY(c['hi']), color=col, alpha=alpha_band, linewidth=0)
    ax.plot(TX(c['z']), TY(c['med']), color=col, linewidth=(1.0 if grey else lw), linestyle=('--' if (x['dash'] and not grey) else '-'), solid_capstyle='round', zorder=(1 if grey else 3))
    if not grey:
        ax.plot(TX([x['cap_z']]),TY([logit(0.5)]), marker='o', ms=4.5, color=col, mec=SURF, mew=0.8, zorder=4)
        ax.plot(TX([x['rel_z']]),TY([logit(0.01)]), marker='o', ms=4.5, color=col, mec=SURF, mew=0.8, zorder=4)
def legend(fig, ncol=5, y=0.0):
    handles=[Line2D([0],[0], color=x['color'], lw=2.2, linestyle=('--' if x['dash'] else '-')) for x in arms]
    fig.legend(handles, [x['name'] for x in arms], loc='lower center', ncol=ncol, frameon=False, fontsize=9, bbox_to_anchor=(0.5, y), handlelength=2.6, columnspacing=1.4, labelcolor='#1a1a1a')
# ---- one plot ----
fig=plt.figure(figsize=(9.2,7.6), facecolor=SURF); ax=fig.add_axes([0.085,0.20,0.895,0.78]); style(ax)
for x in arms: draw(ax,x)
legend(fig, ncol=4, y=0.005)
for ext in ('png','svg','pdf'): fig.savefig(f'site/fig/curves_ten_arms{SUF}.{ext}', dpi=200, facecolor=SURF)
plt.close(fig)
# ---- small multiples ----
fig,axs=plt.subplots(2,5, figsize=(15,7.3), facecolor=SURF, sharex=True, sharey=True)
fig.subplots_adjust(left=0.05,right=0.995,top=0.99,bottom=0.20,wspace=0.06,hspace=0.10)
for ax,x in zip(axs.flat, arms):
    style(ax)
    for y in arms:
        if y is not x: draw(ax,y,grey=True)
    draw(ax,x,alpha_band=0.18,lw=2.0)
    ax.set_xticklabels([f"{t:g}" if t in (0.1,1,10,50,90,99) else '' for t in TKX], fontsize=7.5, color='#52514e')
    ax.set_yticklabels([f"{t:g}" if t in (0.1,1,10,50,90,99) else '' for t in TKY], fontsize=7.5, color='#52514e')
legend(fig, ncol=5, y=0.005)
for ext in ('png','svg','pdf'): fig.savefig(f'site/fig/curves_small_multiples{SUF}.{ext}', dpi=170, facecolor=SURF)
plt.close(fig)
if not DEFAULT: raise SystemExit(0)   # a twin writes figures only
json.dump([dict(arm_id=x['arm_id'], name=x['name'], color=x['color'], dashed=x['dash'], rel_pct=x['rel_pct'], rel_tasks=x['rel_tasks_below'], cap_pct=x['cap_pct'], cap_tasks=x['cap_tasks_below']) for x in arms], open('site/data/figure_legend.json','w'), indent=1)
print("wrote site/fig/curves_ten_arms.{png,svg,pdf} and curves_small_multiples.{png,svg,pdf}")

# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "matplotlib"]
# ///
import json, math, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); SITE = os.path.join(ROOT, 'site')
F = json.load(open(os.path.join(ROOT, 'data', 'fits.json'))); CF = json.load(open(os.path.join(ROOT, 'data', 'closed_form.json')))
SH = json.load(open(os.path.join(ROOT, 'data', 'shapes.json')))
SF = json.load(open(os.path.join(ROOT, 'data', 'shapes_fits.json'))) if os.path.exists(os.path.join(ROOT, 'data', 'shapes_fits.json')) else {'elements': []}
WAVE1 = f"wave 1 ({F['frame_tasks']} tasks)" if F.get('frame_tasks') else 'wave 1'
def fitted_shape(kind, model, key, val):
    """the Bayesian fit of a modified arm (banked counts changed, fitted like a real arm), if landed"""
    for e in SF.get('elements', []):
        if e['kind'] == kind and e['strong'] == model and e.get(key) == val and e.get('landed') and e.get('cap_pct') and e.get('rel_pct'): return e
    return None
SURFACE, INK, INK2, INK3, GRID = '#faf6ec', '#1a1a1a', '#52514e', '#8b8477', '#e0d9c8'
GREY_DOT = '#b5ae9f'; TRACE = '#2b2a27'
# the capability-vs-reliability page's family palette (plot_difficulty.FAMILY_HUES), thinking arms hollow with the coloured stroke
FAMILY_HUES = {"Qwen2.5-Coder": "#2a78d6", "Qwen2.5-Instruct": "#3a63e8", "Qwen3": "#5257e6", "Claude": "#1baf7a", "GLM": "#8a7ba8", "Kimi": "#0e8291",
               "DeepSeek-Coder": "#b32fd6", "DeepSeek-Coder-V2": "#c93ad6", "DeepSeek-V3": "#dc3ec8", "DeepSeek-R1-Distill": "#e04fd0", "DeepSeek-R1": "#dc3ec8",
               "GPT-5": "#c81e2e", "Gemini": "#ea7410", "Gemma-4": "#d97706"}
SHORT = {'Qwen/Qwen3-32B-Thinking': 'Qwen3-32B thinking', 'Qwen/Qwen2.5-0.5B-Instruct': 'Qwen2.5-0.5B', 'claude-sonnet-5-thinking': 'Sonnet 5 thinking',
         'deepseek-ai/deepseek-coder-1.3b-instruct': 'DeepSeek-Coder 1.3B', 'deepseek-ai/DeepSeek-R1-0528': 'DeepSeek-R1', 'Qwen/Qwen3-0.6B': 'Qwen3-0.6B',
         'openai/gpt-5-mini': 'GPT-5 mini', 'openai/gpt-5-nano': 'GPT-5 nano', 'Qwen/Qwen3-8B': 'Qwen3-8B', 'Qwen/Qwen2.5-7B-Instruct': 'Qwen2.5-7B'}
def lg(p): p = min(max(p / 100.0, 1e-6), 1 - 1e-6); return math.log(p / (1 - p))
def fmt_bad(b):
    p = 100 * b
    return f"{p:.2g}%" if p < 1 else (f"{p:.0f}%" if p >= 9.5 else f"{p:.1f}%")
def arm_style(m):
    r = F['real'][m]; col = FAMILY_HUES.get(r.get('fam') or '', TRACE)
    return col, bool(r.get('think'))
XT = [5, 10, 20, 50, 80, 90, 95]; YT = [0.2, 0.5, 1, 2, 5, 10, 20, 50]
LOGIT_X = F['pairs']['logit_x']

def base_axes(fig, rect, phone=True):
    fs = 9.5 if phone else 11
    ax = fig.add_axes(rect); ax.set_facecolor(SURFACE)
    ax.set_xlim(lg(4.2), lg(97.6)); ax.set_ylim(lg(0.14), lg(45))
    ax.set_xticks([lg(t) for t in XT]); ax.set_xticklabels([f"{t:g}" for t in XT]); ax.set_yticks([lg(t) for t in YT]); ax.set_yticklabels([f"{t:g}" for t in YT])
    ax.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    ax.tick_params(length=0, labelsize=fs)
    ax.set_xlabel('capability: difficulty (%) at which the arm fails half its attempts', color=INK2, fontsize=fs + 0.2)
    ax.set_ylabel('reliability: difficulty (%) at which it fails 1 attempt in 100', color=INK2, fontsize=fs + 0.2)
    ax.set_aspect('equal', adjustable='datalim')
    return ax

def grey_arms(ax, skip, label_gpt5=False, phone=True, nano_above=False):
    for m, r in F['real'].items():
        if r['cap_pct'] is None or r['rel_pct'] is None or r.get('withheld') or m in skip: continue
        hollow = r['status'] != 'point'
        ax.plot(lg(r['cap_pct']), lg(r['rel_pct']), marker='o', ms=3.6 if phone else 4.2, mfc=SURFACE if hollow else GREY_DOT, mec=GREY_DOT, mew=0.9, ls='none', zorder=2)
        if label_gpt5 and m in ('openai/gpt-5-mini', 'openai/gpt-5-nano'):
            off, ha = (((-2, 9), 'right') if nano_above else ((-6, 0), 'right')) if 'nano' in m else ((4 if phone else 6, 0), 'left')   # mini: right of its dot, clear of the trace
            ax.annotate(SHORT[m], (lg(r['cap_pct']), lg(r['rel_pct'])), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=8.6 if phone else 10, color=INK3)

def pair_figure(pi, pair, phone=True):
    big = not phone
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    S, W = pair['strong'], pair['weak']
    grey_arms(ax, skip={S, W}, label_gpt5=(S == 'deepseek-ai/DeepSeek-R1-0528'), phone=phone)
    cf = next(p for p in CF['pairs'] if p['strong'] == S and p['weak'] == W)
    curve = [c for c in cf['curve'] if c['cap_pct'] and c['rel_pct']]
    ax.plot([lg(c['cap_pct']) for c in curve], [lg(c['rel_pct']) for c in curve], color=TRACE, lw=1.7 if phone else 2.0, alpha=0.9, zorder=4, solid_capstyle='round')
    # the logit-spaced mixture rates as small dots, sparse labels
    LABELS = {4.0: (7, -1), 3.0: (7, -1), 2.0: (7, -1), 0.0: (7, -7)}
    if S == 'deepseek-ai/DeepSeek-R1-0528': LABELS.pop(3.0)   # keeps clear of the GPT-5 mini label
    for row in cf['rows']:
        if row['logit_x'] is None or row['cap_pct'] is None or row['rel_pct'] is None: continue
        x, y = lg(row['cap_pct']), lg(row['rel_pct'])
        ax.plot(x, y, marker='o', ms=3.2 if phone else 3.8, mfc=TRACE, mec=SURFACE, mew=0.7, ls='none', zorder=5)
        key = round(row['logit_x'], 2)
        if key in LABELS:
            dx, dy = LABELS[key]
            ax.annotate(fmt_bad(row['badness']), (x, y), xytext=(dx, dy), textcoords='offset points', ha='left', va='center', fontsize=8.4 if phone else 10, color=INK2, zorder=6)
    # the two real arms of the pair, family colours, hollow when thinking; faint thin whiskers for their 80% bands
    for role, m in (('strong', S), ('weak', W)):
        r = F['real'][m]; col, think = arm_style(m); x, y = lg(r['cap_pct']), lg(r['rel_pct'])
        if r.get('cap_cri80_pct'): ax.plot([lg(r['cap_cri80_pct'][0]), lg(r['cap_cri80_pct'][1])], [y, y], color=col, lw=0.7, alpha=0.35, zorder=3)
        if r.get('rel_cri80_pct'): ax.plot([x, x], [lg(r['rel_cri80_pct'][0]), lg(r['rel_cri80_pct'][1])], color=col, lw=0.7, alpha=0.35, zorder=3)
        ax.plot(x, y, marker='o', ms=5.8 if phone else 7, mfc=SURFACE if think else col, mec=col, mew=1.4 if phone else 1.6, ls='none', zorder=7)
        off, ha = ((0, 9 if phone else 10), 'center') if role == 'strong' else ((7, -5), 'left')
        if role == 'strong' and r['cap_pct'] > 88: off, ha = ((-9, 6), 'right')
        ax.annotate(SHORT.get(m, m.split('/')[-1]), (x, y), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=9.2 if phone else 11, color=INK, zorder=8)
    handles = [Line2D([], [], marker='o', color=TRACE, mfc=TRACE, mec=SURFACE, ms=4.5, lw=1.7, label='the mixture arm, from all-bad to all-good'),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=5, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='upper left', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, 'Labels: share of attempts answered by the bad model.', ha='center', va='bottom', fontsize=7.9 if phone else 9.2, color=INK3)
    return fig

def rel_words(r):
    if r > 0.93: return 'reliability barely moves'
    if r > 0.78: return 'reliability down a fifth'
    if r > 0.62: return 'reliability down a third'
    if r > 0.42: return 'reliability halved'
    if r > 0.29: return 'reliability down to a third'
    if r > 0.22: return 'reliability down to a quarter'
    if r > 0.16: return 'reliability down to a fifth'
    if r > 0.075: return 'reliability down to a tenth'
    return 'reliability down to a twentieth'
def cap_words(dpts):
    d = abs(dpts)
    if d < 0.5: return 'capability unchanged'
    if d < 1.5: return 'capability down one point'
    if d < 2.5: return 'capability down two points'
    return f'capability down {round(d)} points'

def noise_figure(pi, pair, phone=True):
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    S, W = pair['strong'], pair['weak']
    grey_arms(ax, skip={S, W}, label_gpt5=(S == 'deepseek-ai/DeepSeek-R1-0528'), phone=phone, nano_above=True)
    cf = next(p for p in CF['pairs'] if p['strong'] == S and p['weak'] == W)
    curve = [c for c in cf['curve'] if c['cap_pct'] and c['rel_pct']]
    ax.plot([lg(c['cap_pct']) for c in curve], [lg(c['rel_pct']) for c in curve], color=TRACE, lw=1.0, alpha=0.3, zorder=3)          # the whole trace, faint
    seg = [c for c in curve if c['badness'] <= 0.10]
    ax.plot([lg(c['cap_pct']) for c in seg], [lg(c['rel_pct']) for c in seg], color=TRACE, lw=2.0 if phone else 2.4, alpha=0.95, zorder=4, solid_capstyle='round')
    seg_sorted = sorted(seg, key=lambda c: c['badness']); arrowhead(ax, [lg(c['cap_pct']) for c in seg_sorted[-6:]], [lg(c['rel_pct']) for c in seg_sorted[-6:]], TRACE, phone)
    rs = F['real'][S]; R0, C0 = rs['rel_pct'], rs['cap_pct']
    for row in cf['noise_rows']:
        if row['cap_pct'] is None or row['rel_pct'] is None: continue
        x, y = lg(row['cap_pct']), lg(row['rel_pct'])
        ax.plot(x, y, marker='o', ms=3.6 if phone else 4.4, mfc=TRACE, mec=SURFACE, mew=0.8, ls='none', zorder=5)
        ax.annotate(f"{100*row['badness']:g}%", (x, y), xytext=(-8, 0), textcoords='offset points', ha='right', va='center', fontsize=8.6 if phone else 10, color=INK2, zorder=6)
    for role, m in (('strong', S), ('weak', W)):
        r = F['real'][m]; col, think = arm_style(m); x, y = lg(r['cap_pct']), lg(r['rel_pct'])
        if role == 'strong':
            if r.get('cap_cri80_pct'): ax.plot([lg(r['cap_cri80_pct'][0]), lg(r['cap_cri80_pct'][1])], [y, y], color=col, lw=0.7, alpha=0.35, zorder=3)
            if r.get('rel_cri80_pct'): ax.plot([x, x], [lg(r['rel_cri80_pct'][0]), lg(r['rel_cri80_pct'][1])], color=col, lw=0.7, alpha=0.35, zorder=3)
        ax.plot(x, y, marker='o', ms=(5.8 if phone else 7) * (1 if role == 'strong' else 0.85), mfc=SURFACE if think else col, mec=col, mew=1.4 if phone else 1.6, ls='none', zorder=7, alpha=1 if role == 'strong' else 0.85)
        off, ha = ((-8, 6), 'right') if role == 'strong' else ((7, -5), 'left')
        ax.annotate(SHORT.get(m, m.split('/')[-1]), (x, y), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=9.2 if phone else 11, color=INK if role == 'strong' else INK2, zorder=8)
    handles = [Line2D([], [], marker='o', color=TRACE, mfc=TRACE, mec=SURFACE, ms=5, lw=2.0, label=f"{SHORT.get(S)} with a growing share of {SHORT.get(W)} answers"),
               Line2D([], [], color=TRACE, lw=1.0, alpha=0.3, label='the same mixture on to all-bad'),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=5, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='upper left', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, "Labels: share of attempts answered by the bad model.", ha='center', va='bottom', fontsize=7.9 if phone else 9.2, color=INK3)
    return fig

def empty_figure(pi, pair, phone=True):
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    S = pair['strong']
    grey_arms(ax, skip={S}, label_gpt5=(S == 'deepseek-ai/DeepSeek-R1-0528'), phone=phone, nano_above=True)
    cf = next(p for p in CF['pairs'] if p['strong'] == S)
    ec = [c for c in cf['empty_curve'] if c['cap_pct'] and c['rel_pct']]
    ax.plot([lg(c['cap_pct']) for c in ec], [lg(c['rel_pct']) for c in ec], color=TRACE, lw=2.0 if phone else 2.4, alpha=0.95, zorder=4, solid_capstyle='round')
    ecs = sorted(ec, key=lambda c: c['badness']); arrowhead(ax, [lg(c['cap_pct']) for c in ecs[-8:]], [lg(c['rel_pct']) for c in ecs[-8:]], TRACE, phone)
    ybot = ax.get_ylim()[0]
    LABEL_SHARES = (0.0009110511944006028, 0.005, 0.0066928509242848554)   # 0.09%, 0.5%, 0.67%: the last shares with a reliability value
    gone = []
    for row in cf['empty_rows']:
        if row['cap_pct'] is None: continue
        x = lg(row['cap_pct'])
        if row['rel_pct'] is not None:
            y = lg(row['rel_pct'])
            ax.plot(x, y, marker='o', ms=3.6 if phone else 4.4, mfc=TRACE, mec=SURFACE, mew=0.8, ls='none', zorder=5)
            if any(abs(row['badness'] - s) < 1e-9 for s in LABEL_SHARES):
                lab = f"{100*row['badness']:.2f}%" if 100 * row['badness'] < 0.1 else f"{100*row['badness']:.2g}%"
                ax.annotate(lab, (x, y), xytext=(-8, 0), textcoords='offset points', ha='right', va='center', fontsize=8.6 if phone else 10, color=INK2, zorder=6)
        elif row['badness'] in (0.01, 0.02, 0.05, 0.10):
            gone.append(row); ax.plot(x, ybot, marker='o', ms=3.6 if phone else 4.4, mfc=TRACE, mec=SURFACE, mew=0.8, ls='none', zorder=5, alpha=0.45, clip_on=False)
    if gone:
        ax.annotate('1%, 2%, 5%, 10%: no reliability value', (lg(max(g['cap_pct'] for g in gone)), ybot), xytext=(-10, 8), textcoords='offset points', ha='right', va='bottom', fontsize=8.6 if phone else 10, color=INK3, zorder=6, annotation_clip=False)
    r = F['real'][S]; col, think = arm_style(S); x, y = lg(r['cap_pct']), lg(r['rel_pct'])
    if r.get('cap_cri80_pct'): ax.plot([lg(r['cap_cri80_pct'][0]), lg(r['cap_cri80_pct'][1])], [y, y], color=col, lw=0.7, alpha=0.35, zorder=3)
    if r.get('rel_cri80_pct'): ax.plot([x, x], [lg(r['rel_cri80_pct'][0]), lg(r['rel_cri80_pct'][1])], color=col, lw=0.7, alpha=0.35, zorder=3)
    ax.plot(x, y, marker='o', ms=5.8 if phone else 7, mfc=SURFACE if think else col, mec=col, mew=1.4 if phone else 1.6, ls='none', zorder=7)
    ax.annotate(SHORT.get(S), (x, y), xytext=(-8, 6), textcoords='offset points', ha='right', va='center', fontsize=9.2 if phone else 11, color=INK, zorder=8)
    handles = [Line2D([], [], marker='o', color=TRACE, mfc=TRACE, mec=SURFACE, ms=4.5, lw=2.0, label=f"{SHORT.get(S)} with a share of empty answers"),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=4, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='upper left', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, "Labels: share of attempts left empty." if phone else "Labels: share of attempts left empty. Faded marks at the bottom edge: no reliability value.", ha='center', va='bottom', fontsize=7.9 if phone else 9.2, color=INK3)
    return fig

def arrowhead(ax, xs, ys, col, phone):
    if len(xs) < 2: return
    ax.annotate('', xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]), arrowprops=dict(arrowstyle='-|>', color=col, lw=1.4 if phone else 1.7, shrinkA=0, shrinkB=0, mutation_scale=9 if phone else 11), zorder=6)

def yx_line(ax, phone, label_at=30):
    lo, hi = ax.get_xlim()[0], ax.get_ylim()[1]
    ax.plot([lo, hi], [lo, hi], ls=(0, (4, 4)), color='#b9b2a3', lw=1.0, zorder=1)
    ax.annotate('reliability = capability', (lg(label_at), lg(label_at)), xytext=(0, 5), textcoords='offset points', ha='center', va='bottom', fontsize=8.2 if phone else 9.4, color=INK3, rotation=45, rotation_mode='anchor')

def sabotage_figure(phone=True):
    """a good model that fails on purpose on every task above a difficulty threshold; the threshold sweeps from the hardest task to the easiest"""
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    sab = SH['sabotage'][0]; m = sab['model']
    grey_arms(ax, skip={m}, phone=phone); yx_line(ax, phone, label_at=33)
    cur = [c for c in sab['curve'] if c['cap_pct'] and c['rel_pct']]
    ax.plot([lg(c['cap_pct']) for c in cur], [lg(c['rel_pct']) for c in cur], color=TRACE, lw=2.0 if phone else 2.4, alpha=0.95, zorder=4, solid_capstyle='round')
    inr = [c for c in cur if c['cap_pct'] >= 5.0 and c['rel_pct'] >= 0.16]   # keep the arrowhead inside the frame
    arrowhead(ax, [lg(c['cap_pct']) for c in inr[-6:]], [lg(c['rel_pct']) for c in inr[-6:]], TRACE, phone)
    LAB = {80, 40, 15, 5} if not phone else {40, 10}
    for r in sab['rows']:
        if r['cap_pct'] is None or r['rel_pct'] is None: continue
        x, y = lg(r['cap_pct']), lg(r['rel_pct'])
        ax.plot(x, y, marker='o', ms=3.4 if phone else 4.2, mfc=TRACE, mec=SURFACE, mew=0.8, ls='none', zorder=5)
        if r['threshold_pct'] in LAB:
            on_diag = abs(r['cap_pct'] - r['rel_pct']) < 0.5
            ax.annotate(f"{r['threshold_pct']}%", (x, y), xytext=((8, -6) if on_diag else (0, -11)), textcoords='offset points', ha='left' if on_diag else 'center', va='top', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
    r = F['real'][m]; col, think = arm_style(m); x, y = lg(r['cap_pct']), lg(r['rel_pct'])
    ax.plot(x, y, marker='o', ms=5.8 if phone else 7, mfc=SURFACE if think else col, mec=col, mew=1.4 if phone else 1.6, ls='none', zorder=7)
    ax.annotate(SHORT.get(m), (x, y), xytext=(0, 10), textcoords='offset points', ha='center', va='center', fontsize=9.2 if phone else 11, color=INK, zorder=8)
    handles = [Line2D([], [], marker='o', color=TRACE, mfc=TRACE, mec=SURFACE, ms=4.5, lw=2.0, label=f"{SHORT.get(m)} failing on purpose above a difficulty"),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=4, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='lower right', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, "Labels: the difficulty above which every task is failed on purpose.", ha='center', va='bottom', fontsize=7.9 if phone else 9.2, color=INK3)
    return fig

def sharpen_figure(phone=True):
    """majority vote over k rollouts per task: the dot moves straight up, by a little"""
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    arms = SH['sharpening']
    grey_arms(ax, skip={s['model'] for s in arms}, phone=phone); yx_line(ax, phone)
    LABEL_ARM = 'claude-sonnet-5-thinking'
    for s in arms:
        m = s['model']; col, think = arm_style(m); r0 = F['real'][m]
        pts = [(r['k'], r['cap_anchored_pct'], r['rel_anchored_pct']) for r in s['rows'] if r['cap_anchored_pct'] and r['rel_anchored_pct']]
        if s.get('served_status') == 'point':   # the construction is meaningless where the served crossing is unresolved (a floor near the 1% level)
            ax.plot([lg(p[1]) for p in pts], [lg(p[2]) for p in pts], color=col, lw=1.0, ls=(0, (1.5, 2.2)), alpha=0.7, zorder=3)
        fitted = [(k, fitted_shape('sharpen', m, 'k', k)) for k in (3, 9, 65)]; fitted = [(k, e) for k, e in fitted if e]
        if fitted:
            xs = [lg(r0['cap_pct'])] + [lg(e['cap_pct']) for k, e in fitted]; ys = [lg(r0['rel_pct'])] + [lg(e['rel_pct']) for k, e in fitted]
            ax.plot(xs, ys, color=col, lw=1.6 if phone else 1.9, alpha=0.9, zorder=4); arrowhead(ax, xs, ys, col, phone)
            for k, e in fitted:
                hollow = e.get('status') != 'point'
                ax.plot(lg(e['cap_pct']), lg(e['rel_pct']), marker='o', ms=3.8 if phone else 4.6, mfc=SURFACE if hollow else col, mec=col if hollow else SURFACE, mew=0.9, ls='none', zorder=5)
                if m == LABEL_ARM: ax.annotate(f"k = {k}" if k == 3 else str(k), (lg(e['cap_pct']), lg(e['rel_pct'])), xytext=(7, 0), textcoords='offset points', ha='left', va='center', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
        x, y = lg(r0['cap_pct']), lg(r0['rel_pct'])
        unresolved = r0.get('status') != 'point'
        ax.plot(x, y, marker='o', ms=5.8 if phone else 7, mfc=SURFACE if (think or unresolved) else col, mec=col, mew=1.4 if phone else 1.6, ls=('none'), zorder=7, alpha=0.75 if unresolved else 1)
        off, ha = ((0, -11), 'center')
        if m == 'claude-sonnet-5-thinking': off, ha = ((-8, -4), 'right')
        if m == 'Qwen/Qwen3-32B-Thinking': off, ha = ((-8, -6), 'right')
        if m == 'Qwen/Qwen3-8B': off, ha = ((-8, -3), 'right')
        if m == 'Qwen/Qwen2.5-7B-Instruct': off, ha = ((8, -3), 'left')
        if m == 'deepseek-ai/DeepSeek-R1-0528': off, ha = ((8, -4) if phone else (8, -8), 'left')   # right of its dot over the GPT-5 mini trace, with a surface halo (no free spot between the traces)
        if m == 'openai/gpt-5-mini': off, ha = ((0, -11), 'center')
        if m == 'openai/gpt-5-nano': off, ha = ((-8, -3), 'right')
        ax.annotate(SHORT.get(m, m.split('/')[-1]) + (' ~' if unresolved else ''), (x, y), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=8.8 if phone else 10.4, color=INK, zorder=8, bbox=dict(boxstyle='round,pad=0.12', fc=SURFACE, ec='none', alpha=0.9) if m == 'deepseek-ai/DeepSeek-R1-0528' else None)
    handles = [Line2D([], [], marker='o', color=INK2, mfc=INK2, mec=SURFACE, ms=4.2, lw=1.8, label='vote over k = 3, 9, 65 rollouts, fitted like a real arm'),
               Line2D([], [], color=INK2, lw=1.0, ls=(0, (1.5, 2.2)), label='what the fitted curve alone predicts'),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=4, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='lower right', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, "Each arm's dot moves as its answers are decided by a majority vote over k rollouts. Hollow: crossing not resolved.", ha='center', va='bottom', fontsize=7.4 if phone else 9.2, color=INK3)
    return fig

def gated_figure(phone=True):
    """majority vote (all rollouts) applied only to tasks at or below difficulty d, d swept from easy to hard"""
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.6 if phone else 11, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig = plt.figure(figsize=(5.4, 6.1) if phone else (8.6, 8.3), dpi=160); fig.patch.set_facecolor(SURFACE)
    ax = base_axes(fig, [0.125, 0.105, 0.855, 0.835] if phone else [0.085, 0.085, 0.9, 0.885], phone=phone)
    arms = SH['gated']; grey_arms(ax, skip={s['model'] for s in arms}, phone=phone); yx_line(ax, phone)
    def is_unres(m): return F['real'][m].get('status') != 'point'
    LABEL_ARM = 'deepseek-ai/DeepSeek-R1-0528'
    for s in arms:
        m = s['model']; col, think = arm_style(m); rows = s['rows_by_k']['all']
        pts = [(r['d_pct'], r['n_tasks'], r['cap_anchored_pct'], r['rel_anchored_pct']) for r in rows if r['cap_anchored_pct'] and r['rel_anchored_pct']]
        r0 = F['real'][m]; rel0 = r0['rel_pct']; top = max(p[3] for p in pts)
        gf = sorted([e for e in SF.get('elements', []) if e['kind'] == 'gated' and e['strong'] == m and e.get('landed') and e.get('cap_pct') and e.get('rel_pct')], key=lambda e: e['d_pct'])
        if not is_unres(m) and not gf:
            # the fitted-curve construction: dotted, only where no fitted gated arm exists yet
            ax.plot([lg(p[2]) for p in pts], [lg(p[3]) for p in pts], color=col, lw=1.0, ls=(0, (1.5, 2.2)), alpha=0.7, zorder=3)
            moving = [p for p in pts if p[3] > rel0 * 1.005 and p[3] < top * 0.995]
            for p in moving:
                ax.plot(lg(p[2]), lg(p[3]), marker='o', ms=2.6 if phone else 3.2, mfc=col, mec=SURFACE, mew=0.6, ls='none', zorder=4, alpha=0.8)
                if m == LABEL_ARM and not gf and p[0] % 2 == 0: ax.annotate(f"{p[0]}%", (lg(p[2]), lg(p[3])), xytext=(7, 0), textcoords='offset points', ha='left', va='center', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
            ax.plot(lg(pts[-1][2]), lg(top), marker='s', ms=3.2 if phone else 3.8, mfc=col, mec=SURFACE, mew=0.6, ls='none', zorder=4, alpha=0.8)
            if m == LABEL_ARM and not gf:
                first_move = next((p for p in pts if p[3] > rel0 * 1.005), None); stop = next((p for p in pts if p[3] >= top * 0.995), None)
                if first_move: ax.annotate(f"d \u2264 {first_move[0] - 1}%", (lg(r0['cap_pct']), lg(rel0)), xytext=(7, -8), textcoords='offset points', ha='left', va='center', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
                if stop: ax.annotate(f"d \u2265 {stop[0]}%", (lg(pts[-1][2]), lg(top)), xytext=(7, 3), textcoords='offset points', ha='left', va='center', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
        if gf:   # the measurement of record: gated arms fitted like real arms
            gxs = [lg(r0['cap_pct'])] + [lg(e['cap_pct']) for e in gf]; gys = [lg(rel0)] + [lg(e['rel_pct']) for e in gf]
            ax.plot(gxs, gys, color=col, lw=1.6 if phone else 1.9, alpha=0.9, zorder=5); arrowhead(ax, gxs, gys, col, phone)
            for e in gf:
                hollow = e.get('status') != 'point'
                ax.plot(lg(e['cap_pct']), lg(e['rel_pct']), marker='D', ms=3.6 if phone else 4.4, mfc=SURFACE if hollow else col, mec=col if hollow else SURFACE, mew=0.9, ls='none', zorder=6)
                D_LAB = {} if phone else {12: ((-7, 0), 'right'), 18: ((7, 0), 'left')}   # the labelled d values and the free side of each point; the 25% endpoint has no free side (the caption carries it), none fit on the phone
                if m == LABEL_ARM and e['d_pct'] in D_LAB:
                    off, ha = D_LAB[e['d_pct']]
                    ax.annotate(f"{e['d_pct']}%", (lg(e['cap_pct']), lg(e['rel_pct'])), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=8.4 if phone else 9.6, color=INK2, zorder=6)
            top_e = max(gf, key=lambda e: e['rel_pct'])
            END = {'openai/gpt-5-nano': ((4, 8), 'left', 'nano'), 'openai/gpt-5-mini': ((7, 3), 'left', 'mini')}   # the two arms that share a colour
            if m in END:
                off, ha, nm = END[m]
                ax.annotate(f"{nm}, d = {top_e['d_pct']}%", (lg(top_e['cap_pct']), lg(top_e['rel_pct'])), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=8.2 if phone else 9.2, color=INK3, zorder=6)
        x, y = lg(r0['cap_pct']), lg(rel0)
        ax.plot(x, y, marker='o', ms=5.8 if phone else 7, mfc=SURFACE if (think or is_unres(m)) else col, mec=col, mew=1.4 if phone else 1.6, ls='none', zorder=7, alpha=0.75 if is_unres(m) else 1)
        off, ha = ((0, -11), 'center')
        if m == 'claude-sonnet-5-thinking': off, ha = ((-8, -4), 'right')
        if m == 'Qwen/Qwen3-32B-Thinking': off, ha = ((-8, -6), 'right')
        if m == 'Qwen/Qwen3-8B': off, ha = ((-8, -3), 'right')
        if m == 'Qwen/Qwen2.5-7B-Instruct': off, ha = ((8, -3), 'left')
        if m == LABEL_ARM: off, ha = ((8, -4) if phone else (8, -8), 'left')   # right of its dot over the GPT-5 mini trace, with a surface halo (no free spot between the traces)
        if m == 'openai/gpt-5-mini': off, ha = ((0, -11), 'center')
        if m == 'openai/gpt-5-nano': off, ha = ((-8, -3), 'right')
        ax.annotate(SHORT.get(m, m.split('/')[-1]) + (' ~' if is_unres(m) else ''), (x, y), xytext=off, textcoords='offset points', ha=ha, va='center', fontsize=8.8 if phone else 10.4, color=INK, zorder=8, bbox=dict(boxstyle='round,pad=0.12', fc=SURFACE, ec='none', alpha=0.9) if m == 'deepseek-ai/DeepSeek-R1-0528' else None)
    handles = [Line2D([], [], marker='D', color=INK2, mfc=INK2, mec=SURFACE, ms=4.2, lw=1.8, label='vote up to difficulty d, fitted like a real arm'),
               Line2D([], [], marker='o', color=INK2, mfc=INK2, mec=SURFACE, ms=3, lw=1.0, ls=(0, (1.5, 2.2)), label='what the fitted curve alone predicts (square: every task voted)'),
               Line2D([], [], marker='o', color=GREY_DOT, mfc=GREY_DOT, mec=GREY_DOT, ms=4, lw=0, label=f'other real arms, {WAVE1}')]
    leg = ax.legend(handles=handles, loc='lower right', frameon=True, fontsize=8.4 if phone else 10, borderpad=0.6, labelspacing=0.4, handlelength=2.0)
    leg.get_frame().set_facecolor('#fffdf6'); leg.get_frame().set_edgecolor(GRID); leg.get_frame().set_alpha(0.94)
    fig.text(0.5, 0.012, "Labels: the difficulty d up to which tasks are decided by the vote." if phone else "Labels: the difficulty d up to which tasks are decided by the vote. Hollow: crossing not resolved.", ha='center', va='bottom', fontsize=7.9 if phone else 9.2, color=INK3)
    return fig

def check_figure():
    """fold-out: fitted mixture arms (markers, thin whiskers) against the exact mixture (line), one panel per pair with fits"""
    plt.rcParams.update({'font.family': ['DejaVu Sans'], 'svg.fonttype': 'none', 'font.size': 9.2, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    pairs = F['pairs']['pairs']; n = len(pairs)
    fig, axes = plt.subplots(1, n, figsize=(3.6 * n, 4.3), dpi=160, sharey=True); fig.patch.set_facecolor(SURFACE)
    for pi, (ax, pair) in enumerate(zip(np.atleast_1d(axes), pairs)):
        ax.set_facecolor(SURFACE); S, W = pair['strong'], pair['weak']
        cf = next(p for p in CF['pairs'] if p['strong'] == S and p['weak'] == W); curve = [c for c in cf['curve'] if c['cap_pct'] and c['rel_pct']]
        ax.plot([lg(c['cap_pct']) for c in curve], [lg(c['rel_pct']) for c in curve], color=TRACE, lw=1.4, alpha=0.8, zorder=3)
        els = sorted([e for e in F['elements'] if e['pair'] == pair['name'] and e['landed'] and e.get('cap_pct') and e.get('rel_pct')], key=lambda e: e['x'])
        col = FAMILY_HUES.get(F['real'][S].get('fam') or '', '#8a2f7a')
        for e in els:
            x, y = lg(e['cap_pct']), lg(e['rel_pct'])
            if e.get('cap_cri80_pct'): ax.plot([lg(e['cap_cri80_pct'][0]), lg(e['cap_cri80_pct'][1])], [y, y], color=col, lw=0.6, alpha=0.3, zorder=4)
            if e.get('rel_cri80_pct'): ax.plot([x, x], [lg(e['rel_cri80_pct'][0]), lg(e['rel_cri80_pct'][1])], color=col, lw=0.6, alpha=0.3, zorder=4)
            ax.plot(x, y, marker='o', ms=4.6 if e['seed'] == 1 else 3.4, mfc=col if e['status'] == 'point' else SURFACE, mec=col, mew=0.9, ls='none', zorder=5)
        for m in (S, W):
            r = F['real'][m]; c2, think = arm_style(m)
            ax.plot(lg(r['cap_pct']), lg(r['rel_pct']), marker='o', ms=8, mfc=SURFACE if think else c2, mec=c2, mew=1.6, ls='none', zorder=6)
        ax.set_xlim(lg(4.2), lg(96.5)); ax.set_ylim(lg(0.14), lg(45))
        ax.set_xticks([lg(t) for t in XT]); ax.set_xticklabels([f"{t:g}" for t in XT]); ax.set_yticks([lg(t) for t in YT]); ax.set_yticklabels([f"{t:g}" for t in YT])
        ax.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True); ax.tick_params(length=0, labelsize=8.6)
        for s in ('top', 'right'): ax.spines[s].set_visible(False)
        ax.set_title(f"{SHORT.get(S)} + {SHORT.get(W)}: {len(els)} fitted", fontsize=9.2, color=INK2, loc='left')
        ax.set_xlabel('capability (%)', color=INK2, fontsize=8.8)
        if pi == 0: ax.set_ylabel('reliability (%)', color=INK2, fontsize=8.8)
    fig.text(0.5, 0.005, 'Line: exact mixture of the two fitted curves. Markers: mixture arms fitted like real arms, thin whiskers = their 80% bands; big rings/dots = the two real arms.', ha='center', va='bottom', fontsize=7.8, color=INK3)
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.2, top=0.92, wspace=0.08)
    return fig

def save_fig(fig, stem):
    fig.savefig(stem + '.svg', facecolor=SURFACE); fig.savefig(stem + '.png', facecolor=SURFACE, dpi=160)
    if not stem.endswith('-phone'):
        os.makedirs(os.path.join(SITE, 'slides'), exist_ok=True); fig.savefig(os.path.join(SITE, 'slides', os.path.basename(stem) + '-print.png'), facecolor=SURFACE, dpi=300)
    plt.close(fig)

NOISE_PAIR = 2
for pi, pair in enumerate(F['pairs']['pairs']):
    for phone in (True, False):
        fig = (noise_figure if pi == NOISE_PAIR else pair_figure)(pi, pair, phone=phone); stem = os.path.join(SITE, f'figure-pair{pi}' + ('-phone' if phone else '-wide'))
        save_fig(fig, stem)
for phone in (True, False):
    fig = empty_figure(NOISE_PAIR, F['pairs']['pairs'][NOISE_PAIR], phone=phone); stem = os.path.join(SITE, 'figure-pair3' + ('-phone' if phone else '-wide'))
    save_fig(fig, stem)
    for name, fn in (('figure-sabotage', sabotage_figure), ('figure-sharpen', sharpen_figure), ('figure-gated', gated_figure)):
        fig = fn(phone=phone); stem = os.path.join(SITE, name + ('-phone' if phone else '-wide'))
        save_fig(fig, stem)
fig = check_figure(); stem = os.path.join(SITE, 'figure-check')
save_fig(fig, stem)
print('figures written; fitted points', F['n_landed'], 'of', F['n_elements'])

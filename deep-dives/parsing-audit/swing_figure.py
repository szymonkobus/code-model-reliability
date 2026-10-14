import json, os, html
HERE = os.path.dirname(os.path.abspath(__file__))
BG, SURF, INK, INK2, GRID, GREY, ACC = "#faf6ec", "#fcfaf3", "#1a1a1a", "#52514e", "#e0d9c8", "#a39c8f", "#0e8190"
W, H = 940, 560; L, R, T, B = 84, 24, 40, 64
E = html.escape


def _short(m): return m.split("/")[-1]


def svg(swing, scen="corrected", min_move=0.05, n_labels=4, stamp="", page="extraction-errors", export=False, xs="logit", ys="logit"):
    global W, H, L, R, T, B
    if export: W, H, L, R, T, B = 960, 640, 90, 30, 40, 62
    else: W, H, L, R, T, B = 940, 560, 84, 24, 40, 64
    AX, TK, LB, TT = (24, 17, 12, 16) if export else (12, 11, 11, 14)
    models = swing["models"]
    legend = [{"label": "moved by a visible amount (arrow: as judged today → with a correct extractor)", "color": ACC, "marker": "circle", "line": False},
              {"label": "no visible move", "color": GREY, "marker": "circle", "line": False},
              {"label": "D99 below the axis floor (a bound, drawn at the frame's edge)", "color": GREY, "marker": "open-triangle", "line": False}]
    meta = (f' data-view="all models, D99 against D50; D50 axis {xs}, D99 axis {ys}" data-stamp="{E(stamp)}"'
            f' data-legend-title="Marks" data-legend-order="given" data-legend=\'{E(json.dumps(legend))}\'')
    import math
    def logit(p): return math.log(p / (1 - p))
    FLOOR_PCT = 0.1                                            # a logit axis reaches down to 0.1% (the convention of record)
    LOGIT_TICKS = (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5)
    xv = [v for r in models.values() for v in (r["official"]["cap_pct"], r[scen]["cap_pct"]) if 0 < v < 100]
    yv = [v for r in models.values() for v in (r["official"]["rel_pct"], r[scen]["rel_pct"]) if 0 < v < 100]
    def frame_logit(vals):
        z = [logit(v / 100) for v in vals]
        lo, hi = min(z) - 0.15, max(z) + 0.15
        return min(lo, logit(FLOOR_PCT / 100) - 0.15), hi        # the floor stays inside the frame so bound marks sit on the drawn edge
    if xs == "logit" and ys == "logit":
        lo, hi = frame_logit(xv + yv); frames = {"x": (lo, hi), "y": (lo, hi)}   # ONE window for both axes: equal scale, D99 = D50 at 45 degrees
    else:
        frames = {"x": frame_logit(xv) if xs == "logit" else (0.0, 100.0), "y": frame_logit(yv) if ys == "logit" else (0.0, 100.0)}
    def Zk(kind, lo, hi):
        if kind == "logit":
            def Z(v):   # clamped logit position; a bound (0 or 100) sits on the frame's edge
                if v <= 0: return lo
                if v >= 100: return hi
                return max(lo, min(hi, logit(v / 100)))
        else:
            def Z(v): return max(0.0, min(100.0, v))            # normal: percent, the axis 0 to 100
        return Z
    Zx = Zk(xs, *frames["x"]); Zy = Zk(ys, *frames["y"])
    PW = W - L - R; PH = H - T - B
    side = min(PW, PH); PW = PH = side                         # a SQUARE plot area: one step spans the same pixels on x and y
    L0 = L + ((W - L - R) - side) / 2
    def X(v): lo_, hi_ = frames["x"]; return L0 + PW * (Zx(v) - lo_) / (hi_ - lo_)
    def Y(v): lo_, hi_ = frames["y"]; return T + PH * (hi_ - Zy(v)) / (hi_ - lo_)
    def ticks_for(kind, lo, hi): return [t for t in LOGIT_TICKS if lo <= logit(t / 100) <= hi] if kind == "logit" else list(range(0, 101, 10))
    XT = ticks_for(xs, *frames["x"]); YT = ticks_for(ys, *frames["y"])
    xmax = ymax = 100.0
    minw = int(round(W * 10 / 11))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif" style="max-width:100%;min-width:{minw}px;height:auto;display:block"{meta}>',
         f'<title>{len(models)} models: as judged today → with a correct extractor from the start</title>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>',
         f'<defs><marker id="pa-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>',
         f'<text x="12" y="22" font-size="{TT}" font-weight="600" fill="{INK}">{len(models)} models: as judged today → with a correct extractor from the start</text>']
    def tl(t): return (f"{t:g}%")
    for t in XT:
        o.append(f'<line x1="{X(t):.1f}" y1="{T}" x2="{X(t):.1f}" y2="{T+PH:.1f}" stroke="{GRID}" stroke-width="0.6"/><text data-role="tick" x="{X(t):.1f}" y="{T+PH+5+TK:.1f}" font-size="{TK}" fill="{INK2}" text-anchor="middle">{tl(t)}</text>')
    for t in YT:
        o.append(f'<line x1="{L0:.1f}" y1="{Y(t):.1f}" x2="{L0+PW:.1f}" y2="{Y(t):.1f}" stroke="{GRID}" stroke-width="0.6"/><text data-role="tick" x="{L0-7:.1f}" y="{Y(t)+TK/3:.1f}" font-size="{TK}" fill="{INK2}" text-anchor="end">{tl(t)}</text>')
    o.append(f'<rect x="{L0:.1f}" y="{T}" width="{PW:.1f}" height="{PH:.1f}" fill="none" stroke="{GRID}" stroke-width="0.8"/>')
    def pct_range(kind, lo, hi): return (100 / (1 + math.exp(-lo)), 100 / (1 + math.exp(-hi))) if kind == "logit" else (0.0, 100.0)
    xr = pct_range(xs, *frames["x"]); yr = pct_range(ys, *frames["y"])
    v_lo = max(xr[0], yr[0], 0.01); v_hi = min(xr[1], yr[1], 99.99); a_, b_ = logit(v_lo / 100), logit(v_hi / 100)
    ref = [100 / (1 + math.exp(-(a_ + (b_ - a_) * k / 160))) for k in range(161)]
    o.append('<path d="' + " ".join(f'{"M" if k == 0 else "L"} {X(v):.1f} {Y(v):.1f}' for k, v in enumerate(ref)) + f'" fill="none" stroke="#8b8477" stroke-width="1" stroke-dasharray="4 3"/>')   # D99 = D50: a straight 45-degree line when both axes share one scale, the same set as a curve otherwise
    o.append(f'<text data-role="axis-title" x="{L0+PW/2:.1f}" y="{H-6}" font-size="{AX}" fill="{INK}" text-anchor="middle">D50</text>')
    o.append(f'<text data-role="axis-title" transform="translate({20 if export else 17},{T+PH/2:.1f}) rotate(-90)" font-size="{AX}" fill="{INK}" text-anchor="middle">D99</text>')
    o.append('<g data-layer="data">')
    still, moved = [], []
    for m, r in models.items():
        a, b = r["official"], r[scen]
        (moved if (abs(b["cap_pct"] - a["cap_pct"]) >= min_move or abs(b["rel_pct"] - a["rel_pct"]) >= min_move) else still).append((m, a, b))
    def point(x, y, bound, fill, r=4.2):
        if bound:   # reliability below the easiest task: only a bound is known
            return f'<path d="M {x:.1f} {y-6:.1f} L {x+5.5:.1f} {y+3.5:.1f} L {x-5.5:.1f} {y+3.5:.1f} Z" fill="none" stroke="{fill}" stroke-width="1.4"/>'
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{SURF}" stroke-width="1.3" opacity="0.9"/>'
    for m, a, b in still:
        o.append(f'<g><title>{E(_short(m))}: capability {a["cap_pct"]:.1f}%, reliability {a["rel_pct"]:.1f}%; no visible move</title>{point(X(a["cap_pct"]), Y(a["rel_pct"]), a["rel_pct"] <= 0, GREY)}</g>')
    labels = []
    for m, a, b in moved:
        x1, y1, x2, y2 = X(a["cap_pct"]), Y(a["rel_pct"]), X(b["cap_pct"]), Y(b["rel_pct"])
        big = abs(b["rel_pct"] - a["rel_pct"]) >= 0.5 or abs(b["cap_pct"] - a["cap_pct"]) >= 0.5
        sw_, op = (1.6, 1.0) if big else (1.1, 0.75)
        o.append(f'<g opacity="{op}"><title>{E(_short(m))}: capability {a["cap_pct"]:.1f}% → {b["cap_pct"]:.1f}%, reliability {a["rel_pct"]:.1f}% → {b["rel_pct"]:.1f}%</title>'
                 f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{ACC}" stroke-width="{sw_}" marker-end="url(#pa-arr)"/>'
                 f'{point(x1, y1, a["rel_pct"] <= 0, ACC, 3.8)}</g>')
        labels.append((m, x2, y2, a, b, abs(b["rel_pct"] - a["rel_pct"])))
    # selective labels, nudged apart vertically when they collide
    labels = sorted(labels, key=lambda t: -t[5])[:n_labels]          # the largest moves of the sorted swing carry a name, by rank, no threshold
    labels.sort(key=lambda t: t[2]); placed = []
    for m, x, y, a, b, _mv in labels:
        text = f'{_short(m)}: D99 {a["rel_pct"]:.1f}% → {b["rel_pct"]:.1f}%'
        est_w = 0.56 * LB * len(text)                             # ~0.56 em per char in the system sans: measure before placing, never clip
        right = x + 9 + est_w <= L0 + PW + 30
        ly = max(y - 8, T + 10)
        for py in placed:
            if abs(ly - py) < 15: ly = py - 15
        ly = max(ly, T + 10)
        placed.append(ly)
        halo = f'paint-order="stroke" stroke="{SURF}" stroke-width="3" stroke-linejoin="round"'   # a surface-colour halo keeps a label legible over neighbouring dots
        if right: o.append(f'<text x="{x+9:.1f}" y="{ly+4:.1f}" font-size="{LB}" fill="{INK}" {halo}>{E(text)}</text>')
        else: o.append(f'<text x="{x-9:.1f}" y="{ly+4:.1f}" font-size="{LB}" fill="{INK}" text-anchor="end" {halo}>{E(text)}</text>')
    o.append("</g>")
    o.append("</svg>")
    return "\n".join(o), len(moved), len(labels)


if __name__ == "__main__":
    sw = json.load(open(os.path.join(HERE, "results", "swing.json")))
    s, n_moved, n_lab = svg(sw); open("/tmp/swing_figure.svg", "w").write(s); print("svg chars", len(s), "moved", n_moved, "labelled", n_lab)

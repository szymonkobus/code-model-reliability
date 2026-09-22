import json, os, html
HERE = os.path.dirname(os.path.abspath(__file__))
BG, SURF, INK, INK2, GRID, GREY, ACC = "#faf6ec", "#fcfaf3", "#1a1a1a", "#52514e", "#e0d9c8", "#a39c8f", "#0e8190"
W, H = 940, 560; L, R, T, B = 84, 24, 40, 64
E = html.escape


def _short(m): return m.split("/")[-1]


def svg(swing, scen="corrected", min_move=0.05, label_move=1.0):
    models = swing["models"]
    xs = [r["official"]["cap_pct"] for r in models.values()] + [r[scen]["cap_pct"] for r in models.values()]
    ys = [r["official"]["rel_pct"] for r in models.values()] + [r[scen]["rel_pct"] for r in models.values()]
    xmax = 100.0; ymax = max(5.0, (max(ys) // 5 + 1) * 5)
    def X(v): return L + (W - L - R) * max(0.0, min(v, xmax)) / xmax
    def Y(v): return T + (H - T - B) * (1 - max(0.0, min(v, ymax)) / ymax)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif" style="max-width:100%;height:auto;display:block">',
         f'<title>{len(models)} models: as judged today → with a correct extractor from the start</title>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>',
         f'<defs><marker id="pa-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>',
         f'<text x="12" y="22" font-size="14" font-weight="600" fill="{INK}">{len(models)} models: as judged today → with a correct extractor from the start</text>']
    for v in range(0, 101, 20):
        o.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{H-B}" stroke="{GRID}" stroke-width="0.6"/><text x="{X(v):.1f}" y="{H-B+16}" font-size="11" fill="{INK2}" text-anchor="middle">{v}%</text>')
    step = 5 if ymax <= 40 else 10
    for v in range(0, int(ymax) + 1, step):
        o.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{W-R}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="0.6"/><text x="{L-7}" y="{Y(v)+4:.1f}" font-size="11" fill="{INK2}" text-anchor="end">{v}%</text>')
    o.append(f'<text x="{(L+W-R)/2:.1f}" y="{H-16}" font-size="12" fill="{INK}" text-anchor="middle">capability: task difficulty at which the model fails half its attempts (%)</text>')
    o.append(f'<text transform="translate(17,{(T+H-B)/2:.1f}) rotate(-90)" font-size="12" fill="{INK}" text-anchor="middle">reliability: task difficulty at which it still fails only 1 attempt in 100 (%)</text>')
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
        if abs(b["rel_pct"] - a["rel_pct"]) >= label_move:      # name only the models whose reliability crossing moves a point or more
            labels.append((m, x2, y2, a, b))
    # selective labels, nudged apart vertically when they collide
    labels.sort(key=lambda t: t[2]); placed = []
    for m, x, y, a, b in labels:
        text = f'{_short(m)}: reliability {a["rel_pct"]:.1f}% → {b["rel_pct"]:.1f}%'
        est_w = 6.2 * len(text)                                   # ~11px sans: measure before placing, never clip
        right = x + 9 + est_w <= W - R - 4
        ly = y - 8
        for py in placed:
            if abs(ly - py) < 14: ly = py - 14
        placed.append(ly)
        if right: o.append(f'<text x="{x+9:.1f}" y="{ly+4:.1f}" font-size="11" fill="{INK}">{E(text)}</text>')
        else: o.append(f'<text x="{x-9:.1f}" y="{ly+4:.1f}" font-size="11" fill="{INK}" text-anchor="end">{E(text)}</text>')
    o.append("</svg>")
    return "\n".join(o), len(moved), len(labels)


if __name__ == "__main__":
    sw = json.load(open(os.path.join(HERE, "results", "swing.json")))
    s, n_moved, n_lab = svg(sw); open("/tmp/swing_figure.svg", "w").write(s); print("svg chars", len(s), "moved", n_moved, "labelled", n_lab)

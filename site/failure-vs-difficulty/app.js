/* app.js — the failure-against-difficulty page: one curve per model, its fitted failure rate against task difficulty.
 *
 * The page reads four files under data/, named by manifest.json: shared.json (the tasks on the difficulty scale; the
 * models with their names, colours and marks; the training runs' rows), curves.json (per model the fitted curve's
 * quantiles on the difficulty grid under the average-rate and the median-task definition, with its crossings of
 * record), cells.json (per model the failures and attempts on every task, drawn as the task dots) and levels.json (per
 * model the crossing at every failure-rate level, the Median difficulty view). The controls' values live in the
 * address (kit.js), so a link reproduces a view; kit-viz.js gives the tooltip and the crosshair, kit-export.js the
 * export with its legend by family. */
'use strict';

if (window.Kit && Kit.setExportLegendFont) Kit.setExportLegendFont(17);

/* ---- constants ---------------------------------------------------------------------------------------------------- */
var W = 960, H = 560, ML = 58, MR = 14, MT = 14, MB = 44;
var PW = W - ML - MR, PH = H - MT - MB;
var K = 1;                                       /* the text and margin factor on a narrow chart */
var EXPORTING = false;
var LOGIT_TICKS = [0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5];
var RAW_TICKS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
var YLIM = [logit(0.002), logit(0.998)];         /* the failure-rate window, 0.2% to 99.8% */
var Y_FLOOR_GAP = 0.15;                          /* room under the window's floor, in logit */
var X_PAD = 0.4;                                 /* room beyond the easiest and the hardest task, in logit */
var DOTS_MAX = 24;                               /* the task dots are offered for this many drawn models or fewer */
var BANDS = { '80': [10, 90], '90': [5, 95], '95': [2.5, 97.5] };   /* a band's edges, as percentiles of the draws */
var PIN_R_RAW = 0.515;                           /* the pinned frame's half-width under the Normal scale, in shares */
var CROSSHAIR_ROWS = 12;
var CONTROL_WORDS = {
  def: { label: 'Definition', options: [{ value: 'average', label: 'Average rate' }, { value: 'median', label: 'Median task' }] },
  curve: { label: 'Curve', options: [{ value: 'rate', label: 'Median failure rate' }, { value: 'difficulty', label: 'Median difficulty' }] },
  band: { label: 'Uncertainty bands', options: [{ value: 'off', label: 'Off' }, { value: '80', label: '80%' }, { value: '90', label: '90%' }, { value: '95', label: '95%' }] },
  xs: { label: 'Horizontal scale' }, ys: { label: 'Vertical scale' },
  scale: [{ value: 'logit', label: 'Logit' }, { value: 'raw', label: 'Normal' }],
  onoff: [{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }],
  dots: { label: 'Task dots' }, pin: { label: 'Pin' },
  partial: { label: 'Partial models', options: [{ value: 'hide', label: 'hidden' }, { value: 'show', label: 'show partial models' }] },
};

function logit(p) { return Math.log(p / (1 - p)); }
function pct(z) { return 100 / (1 + Math.exp(-z)); }
function fmtPct(z, d) { return pct(z).toFixed(d == null ? 1 : d) + '%'; }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

/* ---- the page's data (D), its state (the controls' values, also in the address) and the selection (sel) ----------- */
var D = {};
var MOUNT = (typeof window !== 'undefined' && window.PAGE_MOUNT) || './';
var state = { def: 'average', curve: 'rate', band: '80', xs: 'logit', ys: 'logit', dots: 'off', pin: 'off', partial: 'hide' };
var PIN_LEVEL = 50, PIN_DX = 0;
var sel = null, chips = [], crosshair = null, rearmCrosshair = null;
var XLIM = null;
var bandCtl = null, dotsCtl = null, curveCtl = null, pinBox = null;
var coercing = false, ready = false;
var dataNote = null;
function showDataNote() { var el = document.getElementById('datanote'); if (el) { el.textContent = dataNote || ''; el.hidden = !dataNote; } }
function quietSet(ctl, v) { coercing = true; try { ctl.set(v); } finally { coercing = false; } }
function setDisabled(btn, off) { if (!btn) return; btn.disabled = !!off; btn.setAttribute('aria-disabled', String(!!off)); }

fetch(MOUNT + 'data/manifest.json')
  .then(function (r) { if (!r.ok) throw new Error('manifest: HTTP ' + r.status); return r.json(); })
  .then(function (man) {
    D.man = man;
    var files = man.files || {};
    return Promise.all(['shared', 'curves', 'cells', 'levels'].map(function (k) {
      return fetch(MOUNT + 'data/' + (files[k] || (k + '.json'))).then(function (r) { if (!r.ok) throw new Error(k + ': HTTP ' + r.status); return r.json(); });
    }));
  })
  .then(function (all) {
    D.shared = all[0]; D.curves = all[1]; D.cells = all[2]; D.levels = all[3];
    prepare();
    boot();
  })
  .catch(function (e) {
    var el = document.getElementById('headline');
    if (el) { el.textContent = 'The chart did not draw: ' + String(e && e.message || e); el.setAttribute('role', 'alert'); el.id = 'failline'; }
  });

/* The joins: the levels as logits, the families' order, empty lists where a file carries none. */
function prepare() {
  if (!D.shared.families) D.shared.families = [];
  if (!D.shared.runs) D.shared.runs = [];
  D.shared.arms.forEach(function (c) { if (c.family == null) c.family = ''; });
  if (!D.curves.arms) D.curves.arms = {};
  if (!D.cells.arms) D.cells.arms = {};
  if (!D.levels.arms) D.levels.arms = {};
  D.levels.lev_logit = (D.levels.levels_fail_rate || []).map(function (p) { return logit(p); });
}

/* ---- the models: coverage, partial and hidden states, runs, slugs ----------------------------------------------- */
function coverageOf(c) { var cv = c && c.coverage; if (!cv || !cv.of) return null; return { tasks: Math.min(cv.tasks, cv.of), of: cv.of, share: Math.min(1, cv.tasks / cv.of) }; }
function isPartial(i) { var c = D.shared.arms[i]; return !!(c && c.partial); }
function partialShown() { return state.partial === 'show'; }
function coverageText(c) { var cv = coverageOf(c); return cv && cv.share < 0.9 ? 'attempts on ' + Math.round(cv.share * 100) + '% of this set’s tasks' : ''; }
function partialArms() { return D.shared.arms.map(function (c, i) { return i; }).filter(isPartial); }
function isRun(i) { var c = D.shared && D.shared.arms[i]; return !!(c && c.run); }
function isHidden(i) { return !partialShown() && isPartial(i); }
function hasCurve(i) { var c = D.shared.arms[i]; return !!(c && D.curves.arms[c.id]); }
function capTitle(t) {
  t = String(t || ''); if (t.length <= 300) return t;
  var cut = t.slice(0, 296), k = Math.max(cut.lastIndexOf('; '), cut.lastIndexOf(', '), cut.lastIndexOf(' — '), cut.lastIndexOf('. '));
  if (k < 200) k = cut.lastIndexOf(' ');
  return cut.slice(0, k > 0 ? k : 296).replace(/[;,.\s]+$/, '') + ' …';
}
function slugify(name) {
  var s = String(name || '').trim().toLowerCase();
  s = s.replace(/[·()]/g, ' ').replace(/[^a-z0-9]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  return s;
}
var SLUG_OF = {}, IDX_OF_SLUG = {};
function slugIndex() {
  SLUG_OF = {}; IDX_OF_SLUG = {};
  D.shared.arms.forEach(function (c, i) { var s = slugify(c.label); if (IDX_OF_SLUG[s] !== undefined) s = c.id; SLUG_OF[i] = s; IDX_OF_SLUG[s] = i; });
}
/* The dash of a model's line: the palette's pattern for a run or a thinking model, in chart units. */
function dashOf(c) {
  if (c && c.dash && c.dash.length) return c.dash.map(function (d) { return Math.round(d * 15) / 10; }).join(' ');
  return c && c.think ? '6 3' : '';
}
var SHAPE_OF_LETTER = { o: 'circle', s: 'square', '^': 'triangle', D: 'diamond' };
function markOf(c) { return c && c.marker ? (SHAPE_OF_LETTER[c.marker] || c.marker) : 'circle'; }

/* ---- geometry: logit positions (or, under the Normal scale, shares) to pixels; the pin shifts each curve ----------- */
function xt(z) { return state.xs === 'raw' ? pct(z) / 100 : z; }
function yt(z) { return state.ys === 'raw' ? pct(z) / 100 : z; }
function sameUnits() { return state.xs === state.ys; }
function pinOn() { return state.pin === 'on'; }
function pinR() { return state.xs === 'raw' ? PIN_R_RAW : (YLIM[1] - YLIM[0] + Y_FLOOR_GAP) / 2; }
function xlimT() {
  if (pinOn()) { var r = pinR(); return [-r, r]; }
  return state.xs === 'raw' ? [Math.max(0, pct(XLIM[0]) / 100 - 0.02), Math.min(1, pct(XLIM[1]) / 100 + 0.02)] : XLIM;
}
function ylimT() { return state.ys === 'raw' ? [-0.015, 1.015] : [YLIM[0] - Y_FLOOR_GAP, YLIM[1]]; }
function sx(z) { var L = xlimT(); return ML + (xt(z) - PIN_DX - L[0]) / (L[1] - L[0]) * PW; }
function sy(z) { var L = ylimT(); return MT + (L[1] - yt(z)) / (L[1] - L[0]) * PH; }
function clampY(v) { return Math.min(YLIM[1], Math.max(YLIM[0], v)); }
function inX(z) { var L = xlimT(), v = xt(z) - PIN_DX; return v >= L[0] - 1e-9 && v <= L[1] + 1e-9; }
/* The difficulty at which a curve first rises through the pinned level, by linear interpolation on the grid. */
function pinCross(cv) {
  if (!cv || !cv.zs || !cv.mid) return null;
  var L = logit(PIN_LEVEL / 100), zs = cv.zs, ys = cv.mid;
  for (var k = 1; k < zs.length; k++) {
    if (ys[k - 1] == null || ys[k] == null) continue;
    if (ys[k - 1] < L && ys[k] >= L) return zs[k - 1] + (L - ys[k - 1]) / (ys[k] - ys[k - 1]) * (zs[k] - zs[k - 1]);
  }
  return null;
}
function pinShift(cv) { if (!pinOn()) return 0; var zc = pinCross(cv); return zc == null ? null : xt(zc); }
function pinStepText(s) { var a = Math.abs(s), t = state.xs === 'raw' ? String(Math.round(a * 100)) : String(Math.round(a * 100) / 100); return s === 0 ? '0' : (s > 0 ? '+' : '−') + t; }
function pinSecondText(s) {
  var p = state.xs === 'raw' ? Math.min(1, Math.max(0, PIN_LEVEL / 100 + s)) : 1 / (1 + Math.exp(-(logit(PIN_LEVEL / 100) + s)));
  var v = 100 * p; return ((v > 0 && v < 10) || (v > 90 && v < 100) ? (Math.round(v * 10) / 10).toString() : String(Math.round(v))) + '%';
}
/* The chart's frame: margins grow on a narrow chart; under one unit on both axes the plot keeps equal scales. */
function fitGeometry(chart) {
  var cw = EXPORTING ? W : (chart.getBoundingClientRect().width || W);
  K = Math.min(2.4, Math.max(1, W / cw));
  if (EXPORTING) { ML = 90; MB = 70 + (pinOn() ? 22 : 0); }
  else { ML = Math.round(58 + 40 * (K - 1)); MB = Math.round(44 + 20 * (K - 1)) + (pinOn() ? Math.round(14 * K) : 0); }
  PW = W - ML - MR;
  if (sameUnits()) {
    var xl = xlimT(), yl = ylimT();
    PH = Math.max(120, Math.round(PW * (yl[1] - yl[0]) / (xl[1] - xl[0]))); H = MT + PH + MB;
    chart.setAttribute('data-equal-scale', state.xs);
  } else { H = 560; PH = H - MT - MB; chart.removeAttribute('data-equal-scale'); }
  chart.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
}

/* ---- the curves: the quantile rows under the definition, or the per-level table under Median difficulty ----------- */
function curveBlock(id) {
  var c = D.curves.arms[id]; if (!c) return null;
  var q = state.def === 'average' ? c.average : c.median_task;
  return q ? { zgrid: c.zgrid, qp: c.quantiles_pct || [], q: q } : null;
}
function qIndex(qp, p) { for (var k = 0; k < qp.length; k++) if (Math.abs(qp[k] - p) < 0.01) return k; return -1; }
/* A band level is offered when some drawn model's curve carries both of its edges. */
function bandAvailable(lvl) {
  var e = BANDS[lvl]; if (!e) return false;
  var ids = Object.keys(D.curves.arms);
  for (var k = 0; k < ids.length; k++) { var b = curveBlock(ids[k]); if (b && qIndex(b.qp, e[0]) >= 0 && qIndex(b.qp, e[1]) >= 0) return true; }
  return false;
}
function levelsBlock(id) { var L = D.levels.arms[id]; return L ? (L[state.def === 'average' ? 'average' : 'median_task'] || null) : null; }
function hasLevels() { if (!D.levels.lev_logit.length) return false; var ids = Object.keys(D.levels.arms); for (var k = 0; k < ids.length; k++) if (levelsBlock(ids[k])) return true; return false; }
/* The curve through the per-level table: at each failure-rate level the median crossing (a point crossing only), the
 * band the 80% interval of the crossing where neither end runs off the scale, drawn sideways. */
function levelsCurve(blk, bandOn) {
  if (!blk || !blk.mid) return null;
  var lev = D.levels.lev_logit, zs = [], mid = [], bl = [], blo = [], bhi = [];
  for (var k = 0; k < blk.mid.length && k < lev.length; k++) {
    if (blk.kind[k] !== 0 || blk.mid[k] == null) continue;
    zs.push(blk.mid[k]); mid.push(lev[k]);
    if (bandOn && blk.lo[k] != null && blk.hi[k] != null && !blk.lo_open[k] && !blk.hi_open[k]) { bl.push(lev[k]); blo.push(blk.lo[k]); bhi.push(blk.hi[k]); }
  }
  if (zs.length < 2) return null;
  return { zs: zs, mid: mid, lo: bl.length ? blo : null, hi: bl.length ? bhi : null, bz: { lv: bl, lo: blo, hi: bhi }, horizontal: true, levels: true };
}
function curveFor(i) {
  var c = D.shared.arms[i]; if (!c) return null;
  var lvl = state.band;
  if (state.curve === 'difficulty') { var lc = levelsCurve(levelsBlock(c.id), lvl !== 'off'); if (lc) return lc; }
  var b = curveBlock(c.id); if (!b) return null;
  var m = qIndex(b.qp, 50); if (m < 0) return null;
  var e = lvl !== 'off' ? BANDS[lvl] : null, lo = e ? qIndex(b.qp, e[0]) : -1, hi = e ? qIndex(b.qp, e[1]) : -1;
  return { zs: b.zgrid, mid: b.q[m], lo: lo >= 0 && hi >= 0 ? b.q[lo] : null, hi: lo >= 0 && hi >= 0 ? b.q[hi] : null, levels: false };
}
function curveAt(cv, z) {
  var zs = cv.zs, ys = cv.mid;
  for (var k = 0; k + 1 < zs.length; k++) {
    var a = Math.min(zs[k], zs[k + 1]), b = Math.max(zs[k], zs[k + 1]);
    if (z >= a && z <= b && b > a) { if (ys[k] == null || ys[k + 1] == null) return null; var t = (z - zs[k]) / (zs[k + 1] - zs[k]); return ys[k] + t * (ys[k + 1] - ys[k]); }
  }
  return null;
}
function pathLine(zs, ys) {
  var d = '', pen = false;
  for (var k = 0; k < zs.length; k++) {
    if (ys[k] == null || !inX(zs[k])) { pen = false; continue; }
    d += (pen ? 'L' : 'M') + sx(zs[k]).toFixed(1) + ' ' + sy(clampY(ys[k])).toFixed(1);
    pen = true;
  }
  return d;
}
function pathBand(zs, lo, hi) {
  var segs = [], cur = null;
  for (var k = 0; k < zs.length; k++) {
    if (lo[k] == null || hi[k] == null || !inX(zs[k])) { cur = null; continue; }
    if (!cur) { cur = []; segs.push(cur); }
    cur.push(k);
  }
  return segs.map(function (seg) {
    var up = '', dn = '';
    seg.forEach(function (k, j) {
      up += (j ? 'L' : 'M') + sx(zs[k]).toFixed(1) + ' ' + sy(clampY(hi[k])).toFixed(1);
      dn = 'L' + sx(zs[k]).toFixed(1) + ' ' + sy(clampY(lo[k])).toFixed(1) + dn;
    });
    return up + dn + 'Z';
  }).join('');
}
function pathBandH(lv, lo, hi) {
  var segs = [], cur = null;
  for (var k = 0; k < lv.length; k++) {
    if (lo[k] == null || hi[k] == null) { cur = null; continue; }
    if (!cur) { cur = []; segs.push(cur); }
    cur.push(k);
  }
  return segs.map(function (seg) {
    var up = '', dn = '';
    seg.forEach(function (k, j) {
      up += (j ? 'L' : 'M') + sx(lo[k]).toFixed(1) + ' ' + sy(clampY(lv[k])).toFixed(1);
      dn = 'L' + sx(hi[k]).toFixed(1) + ' ' + sy(clampY(lv[k])).toFixed(1) + dn;
    });
    return up + dn + 'Z';
  }).join('');
}
function bandPath(cv) { return cv.horizontal ? pathBandH(cv.bz.lv, cv.bz.lo, cv.bz.hi) : pathBand(cv.zs, cv.lo, cv.hi); }

/* ---- the axes ------------------------------------------------------------------------------------------------------ */
function axisGrid(TS, TK) {
  var grid = '', narrow = K > 1.5, L0 = xlimT();
  var keep = (narrow && L0[1] - L0[0] > 8) ? [1, 10, 50, 90, 99] : [1, 5, 10, 20, 50, 80, 90, 95, 99];
  var thin = function (v) { return (narrow || EXPORTING) && keep.indexOf(v) < 0; };
  var zOf = function (v) { return logit(Math.min(0.9999, Math.max(0.0001, v / 100))); };
  var xticks = state.xs === 'raw' ? RAW_TICKS : LOGIT_TICKS, yticks = state.ys === 'raw' ? RAW_TICKS : LOGIT_TICKS;
  if (pinOn()) {
    var rT = pinR(), stepT = state.xs === 'raw' ? 0.1 : 1, nT = Math.floor(rT / stepT + 1e-9), LT = xlimT();
    for (var qT = -nT; qT <= nT; qT++) {
      var sT = qT * stepT;
      if (sT <= LT[0] || sT >= LT[1]) continue;
      var pxT = ML + (sT - LT[0]) / (LT[1] - LT[0]) * PW;
      grid += '<line x1="' + pxT.toFixed(1) + '" y1="' + MT + '" x2="' + pxT.toFixed(1) + '" y2="' + (MT + PH) + '" stroke="' + (qT === 0 ? '#b9b2a1' : '#e0d9c8') + '" stroke-width="' + (qT === 0 ? '1' : '0.6') + '"/>';
      if ((narrow || EXPORTING) && qT % 2 !== 0) continue;
      grid += '<text data-role="tick" x="' + pxT.toFixed(1) + '" y="' + (MT + PH + 6 + 11 * K * TK) + '" text-anchor="middle" fill="#52514e" font-size="' + (11 * K * TK) + '">' + pinStepText(sT) + '</text>'
        + '<text data-role="tick" x="' + pxT.toFixed(1) + '" y="' + (MT + PH + 6 + 11 * K * TK + 13 * K * TK) + '" text-anchor="middle" fill="#8b8477" font-size="' + (10 * K * TK) + '">' + pinSecondText(sT) + '</text>';
    }
  } else xticks.forEach(function (v) {
    var z = zOf(v), L = xlimT();
    if (xt(z) <= L[0] || xt(z) >= L[1]) return;
    grid += '<line x1="' + sx(z) + '" y1="' + MT + '" x2="' + sx(z) + '" y2="' + (MT + PH) + '" stroke="#e0d9c8" stroke-width="0.6"/>';
    if (thin(v)) return;
    grid += '<text data-role="tick" x="' + sx(z) + '" y="' + (MT + PH + 6 + 11 * K * TK) + '" text-anchor="middle" fill="#52514e" font-size="' + (11 * K * TK) + '">' + v + '%</text>';
  });
  yticks.forEach(function (v) {
    var z = zOf(v), L = ylimT();
    if (yt(z) <= L[0] || yt(z) >= L[1]) return;
    grid += '<line x1="' + ML + '" y1="' + sy(z) + '" x2="' + (ML + PW) + '" y2="' + sy(z) + '" stroke="#e0d9c8" stroke-width="0.6"/>';
    if (thin(v)) return;
    grid += '<text data-role="tick" x="' + (ML - 6) + '" y="' + (sy(z) + 4 * K * TK) + '" text-anchor="end" fill="#52514e" font-size="' + (11 * K * TK) + '">' + v + '%</text>';
  });
  var xTitle = pinOn() ? 'difficulty, relative to the pin' + (narrow ? '' : (state.xs === 'raw' ? ' (percentage points)' : ' (logit steps)')) : 'task difficulty' + ((narrow || state.xs === 'raw') ? '' : ' (logit)');
  grid += '<text data-role="axis-title" x="' + (ML + PW / 2) + '" y="' + (H - 6) + '" text-anchor="middle" fill="#52514e" font-size="' + (12 * K * TS) + '">' + xTitle + '</text>'
    + '<text data-role="axis-title" transform="rotate(-90)" x="' + (-(MT + PH / 2)) + '" y="' + (12 * K * TS) + '" text-anchor="middle" fill="#52514e" font-size="' + (12 * K * TS) + '">failure rate' + ((narrow || state.ys === 'raw') ? '' : ' (logit)') + '</text>';
  return grid;
}
/* The diagonal: a failure rate equal to the task's difficulty, the average over the models that define the scale. */
function identityPath() {
  if (pinOn()) return '';
  var lo = Math.max(XLIM[0], YLIM[0]), hi = Math.min(XLIM[1], YLIM[1]); if (hi <= lo) return '';
  var zs = [], ys = [];
  for (var k = 0; k <= 40; k++) { var z = lo + (hi - lo) * k / 40; zs.push(z); ys.push(z); }
  return '<path d="' + pathLine(zs, ys) + '" fill="none" stroke="#b9b2a1" stroke-width="0.9" stroke-dasharray="3 3" data-role="identity"/>';
}

/* ---- render -------------------------------------------------------------------------------------------------------- */
function shownArm(i) { return !isHidden(i) && hasCurve(i); }
function visibleArms() { return Array.from(sel).filter(shownArm).sort(function (a, b) { return a - b; }); }
function render() {
  if (!ready) return;
  var chart = document.getElementById('chart');
  mountExport();
  var visible = visibleArms();
  if (curveCtl) {
    var noLv = !hasLevels();
    setDisabled(curveCtl.element.querySelector('button[data-value="difficulty"]'), noLv);
    if (noLv && state.curve === 'difficulty') { state.curve = 'rate'; quietSet(curveCtl, 'rate'); }
  }
  if (bandCtl) {
    ['80', '90', '95'].forEach(function (lv) { setDisabled(bandCtl.element.querySelector('button[data-value="' + lv + '"]'), !bandAvailable(lv)); });
    if (state.band !== 'off' && !bandAvailable(state.band)) { var best = ['95', '90', '80'].filter(bandAvailable)[0] || 'off'; state.band = best; quietSet(bandCtl, best); }
  }
  if (dotsCtl) {
    setDisabled(dotsCtl.element.querySelector('button[data-value="on"]'), visible.length > DOTS_MAX);
    if (state.dots === 'on' && visible.length > DOTS_MAX) { state.dots = 'off'; quietSet(dotsCtl, 'off'); }
  }
  PIN_DX = 0;
  fitGeometry(chart);
  var TS = EXPORTING ? 2 : 1, TK = EXPORTING ? 1.5 : 1;
  var grid = axisGrid(TS, TK), ident = identityPath();
  var dots = '', bands = '', curves = '', drawn = [], unpinned = [];
  var zsT = D.shared.tasks ? D.shared.tasks.z : [];
  visible.forEach(function (i) {
    var c = D.shared.arms[i], cv = curveFor(i); if (!cv) return;
    var sh = pinShift(cv); if (sh == null) { unpinned.push(i); return; } PIN_DX = sh;
    drawn.push(i);
    var faded = isPartial(i) || c.gates_failed;
    if (state.dots === 'on') {
      var dd = D.cells.arms[c.id];
      if (dd && dd.fails) for (var t = 0; t < zsT.length; t++) {
        if (dd.fails[t] == null || dd.n[t] == null) continue;
        var rate = (dd.fails[t] + 0.5) / (dd.n[t] + 1);
        dots += '<circle cx="' + sx(zsT[t]).toFixed(1) + '" cy="' + sy(clampY(logit(rate))).toFixed(1) + '" r="2" fill="#8b8477" fill-opacity="0.38" data-t="' + t + '" data-i="' + i + '"/>';
      }
    }
    if (cv.lo && cv.hi) bands += '<path d="' + bandPath(cv) + '" fill="' + c.color + '" fill-opacity="0.10" data-i="' + i + '"/>';
    curves += '<path d="' + pathLine(cv.zs, cv.mid) + '" fill="none" stroke="' + c.color + '" stroke-width="1.6"' + (dashOf(c) ? ' stroke-dasharray="' + dashOf(c) + '"' : '')
      + (faded ? ' stroke-opacity="0.5"' : '') + ' data-i="' + i + '" data-label="' + esc(c.label) + (cv.levels ? ' — median difficulty at each failure rate' : '') + '"/>';
  });
  PIN_DX = 0;
  chart.innerHTML = '<defs><clipPath id="plotclip"><rect x="' + ML + '" y="' + MT + '" width="' + PW + '" height="' + PH + '"/></clipPath></defs>'
    + grid + '<g clip-path="url(#plotclip)">' + ident + '<g>' + dots + '</g><g>' + bands + '</g><g id="curveg">' + curves + '</g></g>';
  narrate(drawn, unpinned);
  crossingsTable(visible);
  paintChips();
  if (rearmCrosshair) rearmCrosshair();
}

/* The line under the chart: what is drawn, in the words of the controls. */
function defWords() { return state.def === 'average' ? 'average rate' : 'median task'; }
function curveWords() { return state.curve === 'difficulty' ? 'median difficulty at each failure rate' : 'median failure rate at each difficulty'; }
function bandWords() { return state.band === 'off' ? 'uncertainty bands off' : state.band + '% uncertainty bands'; }
function countWords(n) { return n + (n === 1 ? ' model' : ' models'); }
function narrate(drawn, unpinned) {
  var el = document.getElementById('narrate'); if (!el) return;
  var parts = [defWords(), curveWords(), bandWords(), countWords(drawn.length) + ' drawn'];
  if (state.dots === 'on') parts.push('task dots on');
  if (pinOn()) parts.push('pinned at ' + PIN_LEVEL + '% failure' + (unpinned.length ? ' (' + countWords(unpinned.length) + ' never reach' + (unpinned.length === 1 ? 's' : '') + ' that rate and ' + (unpinned.length === 1 ? 'is' : 'are') + ' not drawn)' : ''));
  el.textContent = parts.join(' · ');
  var hl = document.getElementById('headline');
  if (hl && hl.id === 'headline') hl.textContent = 'One curve per model: its fitted failure rate against task difficulty on the ' + D.shared.set.label + ' tasks, the task dots the rates observed.';
}

/* ---- the crossings table: D50 and D99 per drawn model under the definition chosen ------------------------------- */
function crossingOfRecord(id, which) {
  var cv = D.curves.arms[id], cr = cv && cv.crossings; if (!cr) return null;
  if (state.def === 'average') return cr[which] || null;
  return which === 'd99' ? (cr.d99_median_task || null) : null;
}
/* The crossing at one failure rate from the per-level table under the definition (the median-task D50 has no row of
 * record of its own). */
function levelReading(id, p) {
  var blk = levelsBlock(id), lev = D.levels.levels_fail_rate || []; if (!blk) return null;
  var k = -1; for (var j = 0; j < lev.length; j++) if (Math.abs(lev[j] - p) < 1e-9) { k = j; break; }
  if (k < 0 || blk.mid[k] == null) return null;
  var kind = blk.kind[k];
  return { z: blk.mid[k], lo: blk.lo[k], hi: blk.hi[k], status: kind === 0 ? 'point' : 'bound', bound_z: kind === 0 ? null : (kind < 0 ? blk.zg[0] : blk.zg[1]), side: kind };
}
function crossingCell(id, which) {
  var r = crossingOfRecord(id, which) || levelReading(id, which === 'd50' ? 0.5 : 0.01);
  var name = which === 'd50' ? 'D50' : 'D99';
  if (!r) return { text: '*', title: 'no ' + name + ' in the tables under this definition' };
  if (r.status === 'unresolved') return { text: '*', title: 'not resolved' + (r.z != null ? ': the fit’s median ' + fmtPct(r.z) : '') + ((r.lo != null && r.hi != null) ? ', band ' + fmtPct(r.lo) + ' to ' + fmtPct(r.hi) : '') };
  if (r.status === 'bound') {
    var zb = r.bound_z != null ? r.bound_z : r.z;
    var above = r.side != null ? r.side > 0 : (zb != null && zb > (XLIM[0] + XLIM[1]) / 2);
    return { text: zb == null ? '*' : (above ? '≥ ' : '≤ ') + pct(zb).toFixed(1), title: above ? 'a bound: the crossing lies beyond the hardest task, so the scale’s end is printed' : 'a bound: the crossing lies below the easiest task, so the scale’s start is printed' };
  }
  return { text: r.z == null ? '*' : pct(r.z).toFixed(1), title: (r.lo != null && r.hi != null) ? '80% uncertainty band ' + pct(r.lo).toFixed(1) + ' to ' + pct(r.hi).toFixed(1) + ' (difficulty %)' : '' };
}
function crossingsTable(visible) {
  var box = document.getElementById('crossings'); if (!box) return;
  box.textContent = '';
  if (!visible.length) return;
  var rate = state.def === 'average' ? 'average failure rate' : 'median task’s failure rate';
  var p = document.createElement('p');
  p.textContent = 'D50 is the difficulty at which the fitted ' + rate + ' crosses 50%, D99 where it crosses 1%: each the median over the fit’s draws of the draw’s own crossing, its uncertainty band the 10th to 90th percentiles of those crossings. '
    + (state.curve === 'difficulty' ? 'The drawn curve passes through these numbers. ' : 'The drawn curve is the median of the draws’ curves at each difficulty, so where it crosses a level can differ from the printed number. ')
    + 'Positions in difficulty %; each number’s hover carries its band; ≤ or ≥ marks a crossing at the scale’s end; * where the tables hold no number.';
  box.appendChild(p);
  var t = document.createElement('table');
  t.innerHTML = '<tr><th>model</th><th>D50</th><th>D99</th></tr>';
  var anyUnresolved = false;
  visible.forEach(function (i) {
    var c = D.shared.arms[i], tr = document.createElement('tr'), td0 = document.createElement('td');
    var key = document.createElement('span'); key.className = 'legendkey'; key.style.background = c.color; td0.appendChild(key);
    td0.appendChild(document.createTextNode(c.label)); tr.appendChild(td0);
    ['d50', 'd99'].forEach(function (which) {
      var td = document.createElement('td'), cell = crossingCell(c.id, which);
      td.className = 'num'; td.textContent = cell.text; if (cell.title) td.title = cell.title;
      if (/^not resolved/.test(cell.title || '')) anyUnresolved = true;
      tr.appendChild(td);
    });
    t.appendChild(tr);
  });
  box.appendChild(t);
  if (anyUnresolved) {
    var lg = document.createElement('p');
    lg.textContent = 'A crossing whose 80% uncertainty band is wider than one difficulty step, or lies partly beyond the set’s easiest or hardest task, is not resolved and prints *; its hover carries the fit’s median and band.';
    box.appendChild(lg);
  }
}

/* ---- the chips: one per model, by family in the palette's order; a row per training run ---------------------------- */
function famRank(f) { var i = (D.shared.families || []).indexOf(f); return i < 0 ? 1e6 : i; }
function famOrder(indices) {
  return indices.slice().sort(function (a, b) {
    var fa = famRank(D.shared.arms[a].family), fb = famRank(D.shared.arms[b].family);
    return fa !== fb ? fa - fb : a - b;
  });
}
function defaultSel() { var s = new Set(); D.shared.arms.forEach(function (_, i) { if (!isRun(i)) s.add(i); }); return s; }
function writeSel() {
  if (!Object.keys(SLUG_OF).length) slugIndex();
  var dflt = defaultSel(), same = sel.size === dflt.size && Array.from(sel).every(function (i) { return dflt.has(i); });
  Kit.state.set('sel', same ? null : Array.from(sel).sort(function (p, q) { return p - q; }).map(function (i) { return SLUG_OF[i] || D.shared.arms[i].id; }).join(','), null);
}
function chipTitle(i) {
  var c = D.shared.arms[i], words = [];
  if (c.think) words.push('thinking form — a dashed line');
  if (c.run) words.push(c.run_name + ' · ' + c.step + ' steps');
  if (c.gates_failed) words.push('the fit failed a sampler check; the curve is drawn faded');
  if (!hasCurve(i)) words.push('no fitted curve for this model: not drawn');
  var base = words.join(' · ');
  if (isPartial(i)) return partialShown() ? capTitle((base ? base + ' · ' : '') + 'partial model (' + coverageText(c) + '), drawn faded') : capTitle('partial model (' + coverageText(c) + '), hidden; the Partial models switch shows it');
  return base ? capTitle(base) : '';
}
function refreshPartialChips() {
  chips.forEach(function (b) {
    var i = +b.dataset.idx; if (!D.shared.arms[i]) return;
    if (isPartial(i)) {
      if (partialShown()) { b.disabled = false; b.removeAttribute('aria-disabled'); b.classList.remove('partial'); b.classList.add('partialshown'); }
      else { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.classList.add('partial'); b.classList.remove('partialshown'); }
    }
    b.title = chipTitle(i);
  });
}
function buildChips() {
  var box = document.getElementById('chips');
  var allBtn = document.createElement('button');
  allBtn.className = 'util'; allBtn.textContent = 'all';
  allBtn.onclick = function () { D.shared.arms.forEach(function (_, i) { if (!isHidden(i) && !isRun(i)) sel.add(i); }); writeSel(); render(); };
  var noneBtn = document.createElement('button');
  noneBtn.className = 'util'; noneBtn.textContent = 'none';
  noneBtn.onclick = function () { D.shared.arms.forEach(function (c, i) { if (!c.run) sel.delete(i); }); writeSel(); render(); };
  box.appendChild(allBtn); box.appendChild(noneBtn);

  var mainIdx = [];
  D.shared.arms.forEach(function (c, i) { if (!c.run) mainIdx.push(i); });
  var fams = [];
  famOrder(mainIdx).forEach(function (i) {
    var c = D.shared.arms[i], f = fams.find(function (x) { return x.name === c.family; });
    if (!f) { f = { name: c.family, members: [] }; fams.push(f); }
    f.members.push(i);
  });
  var makeChip = function (i) {
    var c = D.shared.arms[i], b = document.createElement('button');
    b.className = 'chip'; if (c.think) b.classList.add('think');
    if (isPartial(i)) b.classList.add('partial');
    if (c.run) b.classList.add('run');
    if (c.gates_failed) { b.classList.add('flagged'); var fg = document.createElement('span'); fg.className = 'flag'; fg.textContent = '⚑'; fg.setAttribute('aria-label', 'the fit failed a sampler check'); b.appendChild(fg); }
    b.style.color = c.color; b.style.borderColor = c.color;
    b.insertBefore(document.createTextNode(c.label), b.firstChild); b.dataset.idx = i; b.dataset.label = c.label;
    b.onclick = function () { if (sel.has(i)) sel.delete(i); else sel.add(i); writeSel(); render(); };
    chips.push(b); return b;
  };
  fams.forEach(function (f) {
    var nm = document.createElement('button');
    nm.className = 'fam'; nm.style.color = D.shared.arms[f.members[0]].color; nm.textContent = f.name; nm.title = 'select or clear every ' + f.name + ' model';
    nm.onclick = function () {
      var anyOff = f.members.some(function (i) { return !sel.has(i) && !isHidden(i); });
      f.members.forEach(function (i) { if (anyOff) { if (!isHidden(i)) sel.add(i); } else sel.delete(i); });
      writeSel(); render();
    };
    box.appendChild(nm);
    f.members.forEach(function (i) { box.appendChild(makeChip(i)); });
  });

  /* one row per training run: its name, all and none, the base model's chip as checkpoint 0, the positions by step */
  var rbox = document.getElementById('chips-runs');
  if (rbox) {
    rbox.innerHTML = '';
    var byId = {}; D.shared.arms.forEach(function (c, i) { byId[c.id] = i; });
    (D.shared.runs || []).forEach(function (R) {
      var idx = R.positions.map(function (p) { return byId[p.id]; }).filter(function (i) { return i !== undefined; });
      if (!idx.length) return;
      var line = document.createElement('div'); line.className = 'chips chips-run'; line.dataset.run = R.key;
      var lab = document.createElement('span'); lab.className = 'runlabel'; lab.style.color = R.color || '#52514e'; lab.textContent = R.name; line.appendChild(lab);
      var rAll = document.createElement('button'); rAll.className = 'util'; rAll.textContent = 'all'; rAll.onclick = function () { idx.forEach(function (i) { sel.add(i); }); writeSel(); render(); }; line.appendChild(rAll);
      var rNone = document.createElement('button'); rNone.className = 'util'; rNone.textContent = 'none'; rNone.onclick = function () { idx.forEach(function (i) { sel.delete(i); }); writeSel(); render(); }; line.appendChild(rNone);
      if (R.base_id !== undefined && R.base_id !== null && byId[R.base_id] !== undefined) {
        var bi = byId[R.base_id], bc = makeChip(bi); bc.classList.add('run'); bc.dataset.dual = '1';
        var fl = bc.querySelector('.flag'); bc.textContent = 'checkpoint 0'; if (fl) bc.appendChild(fl);
        bc.title = D.shared.arms[bi].label + ' — the model the run started from, the same curve as its chip in the list above';
        line.appendChild(bc);
      }
      idx.forEach(function (i) { var ch = makeChip(i); ch.textContent = (D.shared.arms[i].step != null ? D.shared.arms[i].step + ' steps' : D.shared.arms[i].label); line.appendChild(ch); });
      rbox.appendChild(line);
    });
  }
}
function paintChips() {
  chips.forEach(function (b) {
    var i = +b.dataset.idx;
    b.classList.toggle('off', !sel.has(i));
    b.setAttribute('aria-pressed', sel.has(i) ? 'true' : 'false');
    b.classList.toggle('nofit', !hasCurve(i));
    if (b.dataset.dual) return;
    b.title = chipTitle(i);
  });
}

/* ---- export: the chart as drawn with a legend by family ----------------------------------------------------------- */
var exportMounted = false;
function mountExport() {
  if (exportMounted) return;
  var box = document.getElementById('exportrow'); if (!box || !window.Kit || !Kit.exportButton) return;
  exportMounted = true;
  Kit.exportButton(box, exportOptions);
}
function exportLegend() {
  var rows = [];
  famOrder(visibleArms()).forEach(function (i) {
    var c = D.shared.arms[i]; if (!document.querySelector('#curveg path[data-i="' + i + '"]')) return;
    var row = { label: c.label + (isPartial(i) ? ' (partial)' : ''), family: c.family || undefined, color: c.color, dash: dashOf(c), width: 1.6, marker: 'none' };
    if (c.run) { row.marker = (c.think ? 'open-' : '') + markOf(c); row.dot = !!c.dot; row.open = !!c.think; }
    rows.push(row);
  });
  return rows;
}
function exportView() {
  var parts = [defWords(), curveWords(), bandWords()];
  if (state.dots === 'on') parts.push('task dots');
  if (pinOn()) parts.push('pinned at ' + PIN_LEVEL + '% failure');
  if (state.xs === 'raw' || state.ys === 'raw') parts.push((state.xs === 'raw' ? 'x' : '') + (state.xs === 'raw' && state.ys === 'raw' ? ' and ' : '') + (state.ys === 'raw' ? 'y' : '') + ' in normal spacing');
  return parts.join(' · ');
}
function exportOptions() {
  var chart = document.getElementById('chart');
  EXPORTING = true; render();
  var legend = exportLegend(), view = exportView();
  var restore = function () { EXPORTING = false; render(); };
  if (window.queueMicrotask) queueMicrotask(restore); else Promise.resolve().then(restore);
  return { svg: chart, legend: legend, title: 'failure-vs-difficulty ' + (D.shared.set.label || ''), page: '', view: view, stamp: '', crop: null, boldAxisTitles: true };
}

/* ---- hover: the task dots' counts, and a crosshair reading every drawn curve at one difficulty ------------------- */
function buildCrosshair() {
  var box = document.getElementById('chartbox');
  box.addEventListener('pointermove', function (ev) {
    var t = ev.target;
    if (t.tagName === 'circle' && t.dataset.t != null) {
      var ti = +t.dataset.t, ci = +t.dataset.i, c = D.shared.arms[ci], dd = D.cells.arms[c.id] || { fails: [], n: [] };
      Kit.tooltip.show(ev.clientX, ev.clientY, [
        { key: c.color, value: dd.fails[ti] + ' of ' + dd.n[ti], label: 'failures · ' + c.label },
        { key: null, value: fmtPct(D.shared.tasks.z[ti]), label: 'task difficulty' },
        { key: null, value: D.shared.tasks.id[ti], label: 'task' },
      ], null);
      ev.stopPropagation();
    }
  }, true);
  function arm() {
    if (crosshair) crosshair.destroy();
    var r = box.getBoundingClientRect(), scale = r.width / W;
    var gridP = [], LG = xlimT();
    for (var q = 0; q <= 60; q++) gridP.push(LG[0] + (LG[1] - LG[0]) * q / 60);
    var xs = gridP.map(function (s) { return (ML + (s - LG[0]) / (LG[1] - LG[0]) * PW) * scale; });
    crosshair = Kit.crosshair({
      container: box, xs: xs,
      readout: function (k) {
        var s = gridP[k];
        var zOf = function (cv) {
          var v = s; if (pinOn()) { var sh = pinShift(cv); if (sh == null) return null; v = s + sh; }
          return state.xs === 'raw' ? logit(Math.min(0.9999, Math.max(0.0001, v))) : v;
        };
        var rows = [], visible = visibleArms();
        visible.slice(0, CROSSHAIR_ROWS).forEach(function (i) {
          var cv = curveFor(i); if (!cv) return;
          var z = zOf(cv), v = z == null ? null : curveAt(cv, z);
          rows.push({ key: D.shared.arms[i].color, value: v == null ? 'outside the fitted range' : fmtPct(v), label: D.shared.arms[i].label });
        });
        if (visible.length > CROSSHAIR_ROWS) rows.push({ key: null, value: '+' + (visible.length - CROSSHAIR_ROWS), label: 'more models (narrow the chips)' });
        var zT = state.xs === 'raw' ? logit(Math.min(0.9999, Math.max(0.0001, s))) : s;
        return { title: pinOn() ? 'from the pin ' + pinStepText(s) + (state.xs === 'raw' ? ' points' : '') : 'difficulty ' + fmtPct(zT), rows: rows };
      },
    });
  }
  rearmCrosshair = arm;
  window.addEventListener('resize', arm);
}

/* ---- boot: the selection from the address, the controls, the chips --------------------------------------------- */
function boot() {
  XLIM = [D.shared.axis.lo - X_PAD, D.shared.axis.hi + X_PAD];
  sel = new Set();
  var selParam = Kit.state.get('sel', null), selRewrite = false;
  if (selParam !== null && selParam !== '') {
    slugIndex();
    var byKey = {}; D.shared.arms.forEach(function (c, i) { byKey[c.id] = i; byKey[SLUG_OF[i]] = i; byKey[slugify(c.label)] = i; });
    var bad = [];
    selParam.split(',').forEach(function (k) { if (byKey[k] !== undefined) { sel.add(byKey[k]); if (SLUG_OF[byKey[k]] !== k) selRewrite = true; } else if (k) bad.push(k); });
    if (bad.length) selRewrite = true;
    if (!sel.size) { sel = defaultSel(); selRewrite = true; }
    if (Kit.state.get('partial', 'hide') !== 'show' && sel.size && Array.from(sel).every(isPartial)) {
      dataNote = 'the link named only partial models, which are hidden; every shown model is drawn';
      defaultSel().forEach(function (i) { if (!isPartial(i)) sel.add(i); }); selRewrite = true;
    }
    if (selRewrite) writeSel();
  } else sel = defaultSel();

  var setLineEl = document.getElementById('setline');
  if (setLineEl) setLineEl.textContent = D.shared.set.label + ' · ' + D.shared.set.models + ' models · ' + Number(D.shared.set.tasks).toLocaleString('en-US') + ' tasks';
  var row = Kit.filterRow('#controls'); row.classList.add('kit-static');

  Kit.switchControl({ mount: document.getElementById('armsbar') || row, key: 'partial', label: CONTROL_WORDS.partial.label, options: CONTROL_WORDS.partial.options, dflt: 'hide',
    onchange: function (v) { state.partial = v === 'show' ? 'show' : 'hide'; refreshPartialChips(); if (ready && !coercing) render(); } });
  if (!partialArms().length) { var psw = document.querySelector('.kit-switch[data-key="partial"]'); if (psw) psw.style.display = 'none'; }
  showDataNote();
  Kit.switchControl({ mount: row, key: 'def', label: CONTROL_WORDS.def.label, options: CONTROL_WORDS.def.options, dflt: 'average',
    onchange: function (v) { state.def = v === 'median' ? 'median' : 'average'; if (ready && !coercing) render(); } });
  curveCtl = Kit.switchControl({ mount: row, key: 'curve', label: CONTROL_WORDS.curve.label, options: CONTROL_WORDS.curve.options, dflt: 'rate',
    onchange: function (v) { state.curve = v === 'difficulty' ? 'difficulty' : 'rate'; if (ready && !coercing) render(); } });
  bandCtl = Kit.switchControl({ mount: row, key: 'band', label: CONTROL_WORDS.band.label, options: CONTROL_WORDS.band.options, dflt: '80',
    onchange: function (v) { state.band = v; if (ready && !coercing) render(); } });
  [['xs', CONTROL_WORDS.xs.label], ['ys', CONTROL_WORDS.ys.label]].forEach(function (ax) {
    Kit.switchControl({ mount: row, key: ax[0], label: ax[1], options: CONTROL_WORDS.scale, dflt: 'logit',
      onchange: function (v) { state[ax[0]] = v === 'raw' ? 'raw' : 'logit'; if (ready && !coercing) render(); } });
  });
  dotsCtl = Kit.switchControl({ mount: row, key: 'dots', label: CONTROL_WORDS.dots.label, options: CONTROL_WORDS.onoff, dflt: 'off',
    onchange: function (v) { state.dots = v === 'on' ? 'on' : 'off'; if (ready && !coercing) render(); } });
  Kit.switchControl({ mount: row, key: 'pin', label: CONTROL_WORDS.pin.label, options: CONTROL_WORDS.onoff, dflt: 'off',
    onchange: function (v) { state.pin = v === 'on' ? 'on' : 'off'; if (pinBox) pinBox.style.display = state.pin === 'on' ? '' : 'none'; if (ready && !coercing) render(); } });
  var lev0 = parseFloat(Kit.state.get('pinlev', '50'));
  PIN_LEVEL = isFinite(lev0) ? Math.max(0.5, Math.min(99.5, lev0)) : 50;
  pinBox = document.createElement('label'); pinBox.className = 'pinlevel'; pinBox.style.display = state.pin === 'on' ? '' : 'none';
  pinBox.appendChild(document.createTextNode('at '));
  var pinIn = document.createElement('input'); pinIn.type = 'number'; pinIn.min = '0.5'; pinIn.max = '99.5'; pinIn.step = 'any'; pinIn.value = String(PIN_LEVEL);
  pinIn.setAttribute('aria-label', 'the pinned failure rate, in percent');
  pinIn.addEventListener('change', function () {
    var n = parseFloat(pinIn.value);
    if (!isFinite(n)) { pinIn.value = String(PIN_LEVEL); return; }
    PIN_LEVEL = Math.max(0.5, Math.min(99.5, n)); pinIn.value = String(PIN_LEVEL);
    Kit.state.set('pinlev', String(PIN_LEVEL), '50'); render();
  });
  pinBox.appendChild(pinIn); pinBox.appendChild(document.createTextNode(' % failure'));
  row.appendChild(pinBox);

  buildChips(); refreshPartialChips();
  buildCrosshair();
  ready = true;
  render();
}

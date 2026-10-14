/* plane.js — the capability-against-reliability plane: one point per model at (D50, D99), both on the difficulty scale.
 *
 * The page reads two files: shared.json (the models with their names, colours and marks; the training runs' rows; the
 * scale's reach) and crossings.json (per model, under the average-rate and the median-task definition, the crossing of
 * its fitted failure curve at every failure-rate level, with the 80% credible interval, and the densities of D50 and
 * D99). The horizontal position is the crossing at the x level (50% by default, D50), the vertical the crossing at the
 * y level (1% by default, D99); the levels are the page's controls and part of its address. A crossing that lies below
 * the easiest task or beyond the hardest is a bound: drawn as an open chevron at the scale's end, with its band, and
 * kept out of the fitted line. The fitted line is least squares of y on x over the point crossings; its band comes from
 * a seeded bootstrap. This file holds the geometry, the readers of the crossing tables and the renderers; app.js wires
 * the controls, chips.js the model chips, levels.js the level controls. The page's state lives in its address (kit.js).
 */
'use strict';

var W = 860, H = 720, ML = 62, MR = 16, MT = 40, MB = 46;
var PW = W - ML - MR, PH = H - MT - MB;
var EXPORTING = false, LIMX = null, LIMY = null, EXT = null, NO_RATCHET = false;
var CROP = null;
var CHART_VH_GAP = 170;
var EXPORT_TITLE_PX = 46, EXPORT_TICK_PX = 24;
var NARROW = false, FS = 12, FT = 11, DR = 5, UPX = 1;

var LOGIT_TICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5];
var AXIS_FLOOR_PCT = 0.1;
var LOGIT_TICKS_EXPORT = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5, 99.8, 99.9];
var LOGIT_TICKS_FINE = [0.05, 0.07, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 60, 70, 80, 85, 90, 93, 95, 97, 98, 99, 99.3, 99.5, 99.7, 99.8, 99.9];
var RAW_TICKS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
var EXPORT_TIER_Y = null, EXPORT_FLOOR_Y = null;
var K_MAX = 99.5 / 0.2, K_LADDER_MAX = 50, K_CHIPS = [2, 4, 8, 10, 16, 32, 50];
var dragK0 = null;

var CONTROL_WORDS = {
  def: { label: 'Definition', options: [{ value: 'average', label: 'Average rate' }, { value: 'median', label: 'Median task' }] },
  partial: { label: 'Partial models', options: [{ value: 'hide', label: 'hidden' }, { value: 'show', label: 'show partial models' }] },
  xs: { label: 'Horizontal scale' }, ys: { label: 'Vertical scale' }, scale: [{ value: 'logit', label: 'Logit' }, { value: 'raw', label: 'Normal' }],
  onoff: [{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }],
  kp: { label: 'K paths' }, lad: { label: 'K ladders' }, w: { label: 'Whiskers' }, resid: { label: 'Misses against the line' },
  fitci: { label: 'Fit interval', options: [{ value: 'plain', label: '95%, dots exact' }, { value: 'honest', label: '80% with measurement error' }] },
  line: { label: 'Fitted line', options: [{ value: 'off', label: 'Off' }, { value: 'steps', label: 'In logit' }, { value: 'axes', label: 'In the axes as set' }] },
  lw: { label: 'Line weighting', options: [{ value: 'equal', label: 'Each dot equal' }, { value: 'bands', label: 'By the 80% uncertainty bands' }] },
  more: 'More controls',
  view: { label: 'View', options: [{ value: 'scatter', label: 'Scatter' }, { value: 'ridges', label: 'Posterior ridges' }] },
};

function logit(p) { return Math.log(p / (1 - p)); }
function pct(z) { return 100 / (1 + Math.exp(-z)); }
function fmtPct(z, d) { return pct(z).toFixed(d == null ? 1 : d) + '%'; }
function fmtLev(v) { return String(+(+v).toFixed(2)); }

/* The page's data (D), its state (state: the controls' values, also written to the address) and the selection (sel). */
var D = {};
var MOUNT = (typeof window !== 'undefined' && window.PAGE_MOUNT) || './';
var state = { view: 'scatter', def: 'average', line: 'steps', lw: 'equal', resid: 'off', lad: 'off', fitci: 'honest',
              w: 'on', xs: 'logit', ys: 'logit', a: 50, c: 1, kp: 'off', partial: 'hide' };
var sel = null, chips = [], playTimer = null;
var LIM = null;
var dataNote = null;
function showDataNote() { var el = document.getElementById('datanote'); if (el) { el.textContent = dataNote || ''; el.hidden = !dataNote; } }

/* ---- the models: coverage, partial and hidden states, runs ---------------------------------------------------- */
function coverageOf(c) { var cv = c && c.coverage; if (!cv || !cv.of) return null; return { tasks: Math.min(cv.tasks, cv.of), of: cv.of, share: Math.min(1, cv.tasks / cv.of) }; }
function isPartial(i) { var c = D.shared.arms[i]; return !!(c && c.partial); }
function partialShown() { return state.partial === 'show'; }
function coverageText(c) { var cv = coverageOf(c); return cv && cv.share < 0.9 ? 'attempts on ' + Math.round(cv.share * 100) + '% of this set’s tasks' : ''; }
function partialArms() { return D.shared.arms.map(function (c, i) { return i; }).filter(isPartial); }
function isRun(i) { var c = D.shared && D.shared.arms[i]; return !!(c && c.run); }
function isHidden(i) { return !partialShown() && isPartial(i); }
function mainArms() { return D.shared.arms.filter(function (c) { return !c.run; }); }
function runOf(i) { var c = D.shared.arms[i]; if (!c || !c.run) return null; for (var k = 0; k < D.shared.runs.length; k++) if (D.shared.runs[k].key === c.run) return D.shared.runs[k]; return null; }
function markShape(i) { var c = D.shared.arms[i]; var m = c && c.marker; return { o: 'circle', s: 'square', '^': 'triangle', D: 'diamond' }[m] || m || 'circle'; }
function runMarkOf(i) { var c = D.shared.arms[i]; if (!c || !c.run || !window.Kit || typeof Kit.runMarks !== 'function') return null; try { return Kit.runMarks(c.label || '') || null; } catch (e) { return null; } }
function capTitle(t) {
  t = String(t || ''); if (t.length <= 300) return t;
  var cut = t.slice(0, 296), k = Math.max(cut.lastIndexOf('; '), cut.lastIndexOf(', '), cut.lastIndexOf(' — '), cut.lastIndexOf('. '));
  if (k < 200) k = cut.lastIndexOf(' ');
  return cut.slice(0, k > 0 ? k : 296).replace(/[;,.\s]+$/, '') + ' …';
}

/* ---- geometry: the plane maps logit positions (or, under the Normal scale, shares) to pixels ---------------------- */
function layout() {
  if (EXPORTING) {
    NARROW = false; W = 970; ML = 150; MR = 40; MT = 50; MB = 105; DR = 6; PW = W - ML - MR; UPX = 1; FS = EXPORT_TICK_PX; FT = 11;
    var LX = limT(state.xs === 'raw', 'x'), LY = limT(state.ys === 'raw', 'y');
    PH = state.xs === state.ys && LIMX && LIMY ? Math.round(PW * (LY[1] - LY[0]) / (LX[1] - LX[0])) : PW;
    H = PH + MT + MB; TRK.x0 = ML; TRK.x1 = ML + PW; TRK.y = 18; return;
  }
  var cb = document.getElementById('chartbox'), w = cb ? cb.clientWidth : 860;
  NARROW = w > 0 && w < 600;
  var deskW = Math.max(860, Math.min(1600, Math.round(w || 860)));
  W = NARROW ? 380 : deskW; ML = NARROW ? 56 : 62; MR = NARROW ? 24 : 16; MT = NARROW ? 52 : 40; MB = NARROW ? 44 : 46;
  DR = NARROW ? 5 : 4.5;
  PW = W - ML - MR; PH = PW; H = PH + MT + MB;
  var hAvail = Math.max(360, (window.innerHeight || 900) - CHART_VH_GAP), rw = w > 0 ? Math.min(w, hAvail * W / H) : W;
  UPX = rw > 0 ? W / rw : 1;
  if (!NARROW) DR = Math.max(4.5, 4 * UPX);
  FS = NARROW ? 13 : Math.max(12, Math.ceil(11.5 * UPX)); FT = NARROW ? 13 : Math.max(11, Math.ceil(10.5 * UPX));
  TRK.x0 = ML; TRK.x1 = ML + PW; TRK.y = NARROW ? 22 : 18;
}
function tf(z, raw) { return raw ? pct(z) / 100 : z; }
function limT(raw, ax) {
  var B = (ax === 'y' ? LIMY : LIMX) || LIM;
  return raw ? [Math.max(0, pct(B[0]) / 100 - 0.02), Math.min(1, pct(B[1]) / 100 + 0.02)] : B;
}
function sx(z) { var raw = state.xs === 'raw', L = limT(raw, 'x'); return ML + (tf(z, raw) - L[0]) / (L[1] - L[0]) * PW; }
function sy(z) { var raw = state.ys === 'raw', L = limT(raw, 'y'); return MT + (L[1] - tf(z, raw)) / (L[1] - L[0]) * PH; }
function clampZ(v) { return Math.min(LIM[1], Math.max(LIM[0], v)); }
function inAxes() { return state.line === 'axes'; }
function FX(z) { return inAxes() && state.xs === 'raw' ? tf(z, true) : z; }
function FY(z) { return inAxes() && state.ys === 'raw' ? tf(z, true) : z; }
function pxF(v) { if (!(inAxes() && state.xs === 'raw')) return sx(v); var L = limT(true, 'x'); return ML + (v - L[0]) / (L[1] - L[0]) * PW; }
function pyF(v) { if (!(inAxes() && state.ys === 'raw')) return sy(clampZ(v)); var L = limT(true, 'y'); v = Math.min(L[1], Math.max(L[0], v)); return MT + (L[1] - v) / (L[1] - L[0]) * PH; }
function fmtY(v) { return inAxes() && state.ys === 'raw' ? (100 * v).toFixed(1) + '%' : v.toFixed(2); }
function ySpanF() { if (inAxes() && state.ys === 'raw') { var L = limT(true, 'y'); return L[1] - L[0]; } var B = LIMY || LIM; return B[1] - B[0]; }
function extAdd(zx, zy) {
  if (!EXT) EXT = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
  if (zx != null && isFinite(zx)) { if (zx < EXT.x0) EXT.x0 = zx; if (zx > EXT.x1) EXT.x1 = zx; }
  if (zy != null && isFinite(zy)) { if (zy < EXT.y0) EXT.y0 = zy; if (zy > EXT.y1) EXT.y1 = zy; }
}
/* The on-screen window: one common range for both axes around the drawn points (equal scales keep the diagonal honest),
 * padded by 6%, never beyond the scale's reach; null when the points fill the frame. */
function cropRange(ext, lim) {
  if (!(ext && isFinite(ext.x0) && isFinite(ext.y0) && ext.x1 >= ext.x0 && ext.y1 >= ext.y0)) return null;
  var lo = Math.min(ext.x0, ext.y0), hi = Math.max(ext.x1, ext.y1); if (hi - lo < 1) { var mid = (lo + hi) / 2; lo = mid - 0.5; hi = mid + 0.5; } var pad = (hi - lo) * 0.06;
  var r = [Math.max(lim[0], lo - pad), Math.min(lim[1], hi + pad)];
  return r[1] - r[0] >= (lim[1] - lim[0]) - 1e-9 ? null : r;
}

/* ---- the readers: a model's crossing at a failure-rate level, from its per-level table --------------------------- */
function crossRow(i) { return D.crossById[D.shared.arms[i].id] || null; }
function defBlock(r) { return r ? (state.def === 'average' ? r.average : r.median_task) : null; }
/* A bound: the crossing lies at the scale's end; the reading keeps its band and says so. */
function asEdgePoint(rd) {
  if (!rd || (rd.kind !== 'lo-bound' && rd.kind !== 'hi-bound')) return rd;
  var low = rd.kind === 'lo-bound';
  return Object.assign({}, rd, { lo: low ? rd.z : rd.lo, hi: low ? rd.hi : rd.z, lo_open: low ? true : !!rd.lo_open, hi_open: low ? !!rd.hi_open : true,
    extra: (low ? 'the curve crosses this level below the easiest tasks: the bottom of the scale, a bound' : 'the curve crosses this level beyond the hardest tasks: the top of the scale, a bound') + ' — drawn with its band, out of the fitted line' });
}
/* The crossing at a level, read off the per-level table by linear interpolation between the two nearest levels: the
 * posterior median with its 80% interval; a level the table marks as censored on either side is a bound; a band end
 * whose draws run past the scale is open. */
function readLevels(lt, levLogit) {
  var LV = D.cross.lev_logit;
  if (!lt || !LV) return { z: null, kind: 'none', lo: null, hi: null, extra: 'no level table for this model' };
  if (levLogit < LV[0] - 1e-9) return { z: lt.zg[0], lo: null, hi: null, kind: 'lo-bound', extra: 'level below the table range' };
  if (levLogit > LV[LV.length - 1] + 1e-9) return { z: lt.zg[1], lo: null, hi: null, kind: 'hi-bound', extra: 'level above the table range' };
  var lo_i = 0, hi_i = LV.length - 1;
  while (hi_i - lo_i > 1) { var mm = (lo_i + hi_i) >> 1; if (LV[mm] < levLogit) lo_i = mm; else hi_i = mm; }
  var j = hi_i, j0 = lo_i;
  if (lt.kind[j0] !== 0 || lt.kind[j] !== 0) {
    var jj = lt.kind[j0] !== 0 ? j0 : j, k = lt.kind[jj];
    return { z: k === -1 ? lt.zg[0] : lt.zg[1], lo: (lt.lo && lt.lo[jj] != null) ? lt.lo[jj] : null, hi: (lt.hi && lt.hi[jj] != null) ? lt.hi[jj] : null,
             lo_open: !!(lt.lo_open && lt.lo_open[jj]), hi_open: !!(lt.hi_open && lt.hi_open[jj]), kind: k === -1 ? 'lo-bound' : 'hi-bound',
             extra: k === -1 ? 'crossing at or before the fitted range' : 'level not reached within the fitted range' };
  }
  var t = (levLogit - LV[j0]) / (LV[j] - LV[j0]);
  function ip(a) { return a[j0] + t * (a[j] - a[j0]); }
  if (lt.p_left && lt.p_right && lt.p_left[j0] !== null && lt.p_left[j] !== null && lt.p_right[j0] !== null && lt.p_right[j] !== null) {
    var plh = ip(lt.p_left), prh = ip(lt.p_right);
    if (plh >= 0.5 || prh >= 0.5) {
      var lowB = plh >= prh;
      return { z: lowB ? lt.zg[0] : lt.zg[1], lo: (lt.lo && lt.lo[j0] != null) ? lt.lo[j0] : null, hi: (lt.hi && lt.hi[j0] != null) ? lt.hi[j0] : null,
               lo_open: !!(lt.lo_open && (lt.lo_open[j0] || lt.lo_open[j])), hi_open: !!(lt.hi_open && (lt.hi_open[j0] || lt.hi_open[j])),
               kind: lowB ? 'lo-bound' : 'hi-bound',
               extra: (lowB ? 'crossing below the easiest tasks' : 'crossing beyond the hardest tasks') + ' (' + Math.round((lowB ? plh : prh) * 100) + '% of draws beyond the scale)' };
    }
  }
  var pc = null;
  if (lt.p_left[j0] !== null && lt.p_right[j0] !== null) pc = ip(lt.p_left) + ip(lt.p_right);
  var rlo = ip(lt.lo), rhi = ip(lt.hi), lopen = !!(lt.lo_open[j0] || lt.lo_open[j]), hopen = !!(lt.hi_open[j0] || lt.hi_open[j]);
  if (lt.p_left && lt.p_left[j0] !== null && lt.p_left[j] !== null && ip(lt.p_left) > 0.10) { rlo = lt.zg[0]; lopen = true; }
  if (lt.p_right && lt.p_right[j0] !== null && lt.p_right[j] !== null && ip(lt.p_right) > 0.10) { rhi = lt.zg[1]; hopen = true; }
  return { z: ip(lt.mid), lo: rlo, hi: rhi, kind: 'point', hi_open: hopen, lo_open: lopen,
           extra: '80% uncertainty band (crossing draws, ' + (state.def === 'average' ? 'average rate' : 'median task') + ')'
             + (pc !== null ? ' · ' + Math.round(pc * 100) + '% of draws censored' : '')
             + ((lt.hi_open[j0] || lt.hi_open[j]) ? ' · the uncertainty band’s upper end reaches the censored edge (open)' : '') };
}
function reading(i, levLogit) {
  var r = crossRow(i);
  if (!r) return { z: null, kind: 'none', lo: null, hi: null, extra: 'no fit for this model' };
  return asEdgePoint(readLevels(defBlock(r).levels, levLogit));
}
/* The table read at one level for the ridges: {z, lo, hi}, or null where the level is censored or outside the table. */
function tableAt(lt, levLogit) {
  var LV = D.cross && D.cross.lev_logit; if (!lt || !LV || !LV.length) return null;
  if (levLogit < LV[0] - 1e-9 || levLogit > LV[LV.length - 1] + 1e-9) return null;
  var lo_i = 0, hi_i = LV.length - 1;
  while (hi_i - lo_i > 1) { var mm = (lo_i + hi_i) >> 1; if (LV[mm] < levLogit) lo_i = mm; else hi_i = mm; }
  if (lt.kind[lo_i] !== 0 || lt.kind[hi_i] !== 0) return null;
  var t = (levLogit - LV[lo_i]) / (LV[hi_i] - LV[lo_i]);
  var ip = function (a) { return a && a[lo_i] != null && a[hi_i] != null ? a[lo_i] + t * (a[hi_i] - a[lo_i]) : null; };
  return { z: ip(lt.mid), lo: ip(lt.lo), hi: ip(lt.hi) };
}
function ridgeCentre(r, lev) {
  var b = defBlock(r), t = tableAt(b.levels, logit(lev)); if (t && t.z != null) return t.z;
  var c = lev === 0.5 ? b.d50 : b.d99; return c ? c.median_z : -Infinity;
}

/* ---- the marks ---------------------------------------------------------------------------------------------------- */
function markPath(shape, X, Y, r) {
  var Xs = X.toFixed(1), Ys = Y.toFixed(1), head = 'M' + Xs + ' ' + Ys, f = function (v) { return (+v).toFixed(1); };
  switch (shape) {
    case 'square': { var s = r * 0.9; return head + 'm-' + f(s) + ' -' + f(s) + 'h' + f(2 * s) + 'v' + f(2 * s) + 'h-' + f(2 * s) + 'Z'; }
    case 'triangle': return head + 'm0 -' + f(r * 1.3) + 'l' + f(r * 1.15) + ' ' + f(r * 2) + 'l-' + f(r * 2.3) + ' 0Z';
    case 'diamond': { var dd = r * 1.3; return head + 'm0 -' + f(dd) + 'l' + f(dd) + ' ' + f(dd) + 'l-' + f(dd) + ' ' + f(dd) + 'l-' + f(dd) + ' -' + f(dd) + 'Z'; }
    default: return head + 'm-' + r + ' 0a' + r + ' ' + r + ' 0 1 0 ' + (2 * r) + ' 0a' + r + ' ' + r + ' 0 1 0 -' + (2 * r) + ' 0Z';
  }
}

/* ---- the selection in the address: every chip's state is a slug of its name of record ----------------------------- */
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

/* ---- the fitted line: least squares, its bootstrap band and the weighted alternative ------------------------------- */
function mulberry32(seed) {
  var t = seed >>> 0;
  return function () {
    t = (t + 0x6D2B79F5) >>> 0;
    var r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}
function fitLine(xs, ys) {
  var n = xs.length;
  if (n < 3) return null;
  var mx = 0, my = 0;
  for (var i = 0; i < n; i++) { mx += xs[i]; my += ys[i]; }
  mx /= n; my /= n;
  var sxy = 0, sxx = 0, syy = 0;
  for (i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) * (xs[i] - mx); syy += (ys[i] - my) * (ys[i] - my); }
  if (sxx < 1e-9 || syy < 1e-9) return null;
  var b = sxy / sxx, a = my - b * mx, rss = 0;
  for (i = 0; i < n; i++) { var e = ys[i] - a - b * xs[i]; rss += e * e; }
  return { b: b, a: a, r: sxy / Math.sqrt(sxx * syy), s: Math.sqrt(rss / Math.max(1, n - 2)) };
}
var fitCache = {};
/* York's weighted fit: each dot weighted by its two interval widths (errors in both variables). */
function yorkFit(xs, ys, sig, level, mg) {
  var n = xs.length; if (n < 3 || !sig) return null;
  var base = fitLine(xs, ys); if (!base) return null;
  var wx = [], wy = [], i;
  for (i = 0; i < n; i++) { var s0 = Math.max(sig[i][0], 1e-6), s1 = Math.max(sig[i][1], 1e-6); wx.push(1 / (s0 * s0)); wy.push(1 / (s1 * s1)); }
  var b = base.b, Wt = new Array(n), U = new Array(n), V = new Array(n), beta = new Array(n), Xb = 0, Yb = 0, it;
  for (it = 0; it < 100; it++) {
    var sw = 0; Xb = 0; Yb = 0;
    for (i = 0; i < n; i++) { Wt[i] = wx[i] * wy[i] / (wx[i] + b * b * wy[i]); sw += Wt[i]; Xb += Wt[i] * xs[i]; Yb += Wt[i] * ys[i]; }
    Xb /= sw; Yb /= sw;
    var num = 0, den = 0;
    for (i = 0; i < n; i++) { U[i] = xs[i] - Xb; V[i] = ys[i] - Yb; beta[i] = Wt[i] * (U[i] / wy[i] + b * V[i] / wx[i]); num += Wt[i] * beta[i] * V[i]; den += Wt[i] * beta[i] * U[i]; }
    if (!(Math.abs(den) > 0)) return null;
    var bn = num / den; if (!isFinite(bn)) return null;
    var done = Math.abs(bn - b) < 1e-10; b = bn; if (done) break;
  }
  var a = Yb - b * Xb, sw2 = 0, xa = 0, xadj = new Array(n);
  for (i = 0; i < n; i++) { Wt[i] = wx[i] * wy[i] / (wx[i] + b * b * wy[i]); sw2 += Wt[i]; xadj[i] = Xb + beta[i]; xa += Wt[i] * xadj[i]; }
  xa /= sw2;
  var su = 0; for (i = 0; i < n; i++) { var u = xadj[i] - xa; su += Wt[i] * u * u; }
  if (!(su > 0)) return null;
  var vb = 1 / su, va = 1 / sw2 + xa * xa * vb, cab = -xa * vb, z = level === 80 ? 1.2816 : 1.96, rss = 0, chi = 0;
  for (i = 0; i < n; i++) { var e = ys[i] - a - b * xs[i]; rss += e * e; chi += Wt[i] * e * e; }
  var red = chi / Math.max(1, n - 2), k = Math.max(1, Math.sqrt(red)), hw = z * Math.sqrt(vb);
  var out = { b: b, a: a, r: base.r, s: Math.sqrt(rss / Math.max(1, n - 2)), level: level, lo: b - hw * k, hi: b + hw * k, lo0: b - hw, hi0: b + hw, weighted: true, iterations: it + 1, red: red, widen: k };
  mg = mg == null ? 0.15 : mg;
  var gx0 = Math.min.apply(null, xs) - mg, gx1 = Math.max.apply(null, xs) + mg;
  out.band = { xs: [], up: [], dn: [] };
  for (var gi = 0; gi <= 24; gi++) {
    var gx = gx0 + (gx1 - gx0) * gi / 24, sd = k * Math.sqrt(Math.max(0, va + gx * gx * vb + 2 * gx * cab)), yh = a + b * gx;
    out.band.xs.push(gx); out.band.up.push(yh + z * sd); out.band.dn.push(yh - z * sd);
  }
  return out;
}
function gaussRnd(rnd) {
  var u = 0, v = 0;
  while (u === 0) u = rnd();
  while (v === 0) v = rnd();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
/* The least-squares line with a seeded bootstrap over the dots (two thousand resamples): the slope's interval and the
 * pointwise band, at 80% with each dot jittered by its own measurement error, or at 95% with the dots taken as exact. */
function bootFit(xs, ys, key, sig, mg) {
  if (key && fitCache[key]) return fitCache[key];
  var base = fitLine(xs, ys);
  if (!base) return null;
  var honest = !!sig;
  var rnd = mulberry32(20260825), slopes = [], lines = [];
  for (var b = 0; b < 2000; b++) {
    var bx = [], by = [];
    for (var i = 0; i < xs.length; i++) {
      var k = Math.floor(rnd() * xs.length);
      var jx = honest ? gaussRnd(rnd) * sig[k][0] : 0;
      var jy = honest ? gaussRnd(rnd) * sig[k][1] : 0;
      bx.push(xs[k] + jx); by.push(ys[k] + jy);
    }
    var f = fitLine(bx, by);
    if (f) { slopes.push(f.b); lines.push([f.b, f.a]); }
  }
  slopes.sort(function (a, b2) { return a - b2; });
  var q = function (arr, p) { return arr[Math.max(0, Math.min(arr.length - 1, Math.round(p * (arr.length - 1))))]; };
  var pl = honest ? 0.10 : 0.025, ph = honest ? 0.90 : 0.975;
  base.level = honest ? 80 : 95;
  base.lo = q(slopes, pl); base.hi = q(slopes, ph);
  var ints = lines.map(function (l) { return l[1]; }).sort(function (u, v) { return u - v; });
  base.aLo = q(ints, pl); base.aHi = q(ints, ph);
  mg = mg == null ? 0.15 : mg;
  var gx0 = Math.min.apply(null, xs) - mg, gx1 = Math.max.apply(null, xs) + mg;
  base.band = { xs: [], up: [], dn: [] };
  for (var gi = 0; gi <= 24; gi++) {
    var gx = gx0 + (gx1 - gx0) * gi / 24;
    var vals = lines.map(function (l) { return l[0] * gx + l[1]; }).sort(function (u, v) { return u - v; });
    base.band.xs.push(gx); base.band.up.push(q(vals, ph)); base.band.dn.push(q(vals, pl));
  }
  if (key) { var ks = Object.keys(fitCache); if (ks.length > 400) delete fitCache[ks[0]]; fitCache[key] = base; }
  return base;
}
function residStats(f, xs, ys, labels) {
  var span = ySpanF() || 1, es = [], fv = [], big = -1, bi = 0, w5 = 0, w10 = 0, ss = 0;
  for (var i = 0; i < xs.length; i++) {
    var v = f.a + f.b * xs[i], e = ys[i] - v; es.push(e); fv.push(v); ss += e * e;
    if (Math.abs(e) > big) { big = Math.abs(e); bi = i; }
    if (Math.abs(e) / span <= 0.05) w5++;
    if (Math.abs(e) / span <= 0.10) w10++;
  }
  return { span: span, es: es, fv: fv, rmsPct: 100 * Math.sqrt(ss / Math.max(1, xs.length)) / span, bigPct: 100 * (es[bi] || 0) / span, bigLabel: labels[bi] || '', w5: w5, w10: w10, n: xs.length };
}
function sgn(v) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1); }
/* The inset of misses against the line: the residual of each dot against its fitted value (a bow shows curvature). */
function residPanel(RS, cols, x0, y0) {
  var fmin = Math.min.apply(null, RS.fv), fmax = Math.max.apply(null, RS.fv), emax = Math.max.apply(null, RS.es.map(Math.abs)) || 1, pad = 10;
  var t1 = 'misses vs fitted, ±' + (100 * emax / RS.span).toFixed(0) + '% of the y scale · ' + RS.w5 + '/' + RS.n + ' within ±5%';
  var t2 = 'typical ' + RS.rmsPct.toFixed(1) + '%, largest ' + sgn(RS.bigPct) + '% (' + RS.bigLabel + ')';
  var RW = Math.max(NARROW ? 150 : 230, Math.ceil(Math.max(t1.length, t2.length) * 11 * 0.56) + 2 * pad), RH = NARROW ? 90 : 120;
  var X = function (v) { return x0 + pad + (fmax > fmin ? (v - fmin) / (fmax - fmin) : 0.5) * (RW - 2 * pad); };
  var Y = function (e) { return y0 + 16 + RH / 2 - (e / emax) * (RH / 2 - pad - 16); };
  var out = '<g id="residpanel" pointer-events="none"><rect x="' + x0 + '" y="' + y0 + '" width="' + RW + '" height="' + RH + '" rx="6" fill="#fcfaf3" fill-opacity="0.94" stroke="#d9d2c2"/>'
    + '<text x="' + (x0 + pad) + '" y="' + (y0 + 12) + '" font-size="11" fill="#52514e">' + t1 + '</text>'
    + '<text x="' + (x0 + pad) + '" y="' + (y0 + 24) + '" font-size="10" fill="#52514e">' + t2 + '</text>'
    + '<line x1="' + (x0 + pad) + '" y1="' + Y(0).toFixed(1) + '" x2="' + (x0 + RW - pad) + '" y2="' + Y(0).toFixed(1) + '" stroke="#8b8477" stroke-dasharray="3 2"/>';
  for (var i = 0; i < RS.es.length; i++) out += '<circle cx="' + X(RS.fv[i]).toFixed(1) + '" cy="' + Y(RS.es[i]).toFixed(1) + '" r="3" fill="' + (cols[i] || '#52514e') + '" opacity="0.85" data-resid/>';
  return out + '</g>';
}

/* ---- the axes ----------------------------------------------------------------------------------------------------- */
function pctLadder(lo, hi) {
  var steps = [20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01], t = [];
  for (var s = 0; s < steps.length; s++) {
    var st = steps[s]; t = [];
    for (var k = Math.floor(lo / st) + 1; k * st < hi; k++) { var v = +(k * st).toFixed(2); if (v > 0 && v < 100) t.push(v); }
    if (t.length >= 3) return t;
  }
  return t;
}
function floorIn(tier, zmin, stepUnder) {
  var fb = null;
  tier.forEach(function (v) { var zt = logit(v / 100); if (zt <= zmin + 1e-9 && (fb === null || zt > fb.z)) fb = { z: zt, v: v }; });
  if (fb === null && stepUnder && tier.length >= 2) { var st = +(tier[1] - tier[0]).toFixed(2), v0 = +(Math.floor(pct(zmin) / st) * st).toFixed(2); if (v0 > 0) fb = { z: logit(v0 / 100), v: v0 }; }
  return fb;
}
/* The export's ticks on one axis: the shared vocabulary where three or more fall inside the window, else the finer
 * ladder, else percent steps; the vertical axis prints the ladder its floor tick came from. */
function exportTicks(ax) {
  var raw = (ax === 'x' ? state.xs : state.ys) === 'raw', L = limT(raw, ax);
  var lo = raw ? L[0] * 100 : pct(L[0]), hi = raw ? L[1] * 100 : pct(L[1]);
  var inside = function (set) { return set.filter(function (v) { return v > lo && v < hi; }); };
  var t;
  if (ax === 'y' && !raw && EXPORT_TIER_Y) t = inside(EXPORT_TIER_Y);
  else { t = inside(raw ? RAW_TICKS : LOGIT_TICKS_EXPORT); if (!raw && t.length < 3) t = inside(LOGIT_TICKS_FINE); if (t.length < 3) t = pctLadder(lo, hi); }
  if (ax === 'y' && !raw && EXPORT_FLOOR_Y !== null && t.indexOf(EXPORT_FLOOR_Y) < 0 && EXPORT_FLOOR_Y > lo && EXPORT_FLOOR_Y < hi) t.push(EXPORT_FLOOR_Y);
  return t;
}
function axisGrid(xOnly, hOverride) {
  var g = '';
  var plotBot = (hOverride ? hOverride - MB : MT + PH);
  var LT = EXPORTING ? LOGIT_TICKS_EXPORT : LOGIT_TICKS, zoomed = EXPORTING && LIMX && LIMY;
  var xt = zoomed ? exportTicks('x') : (state.xs === 'raw' ? RAW_TICKS : LT);
  var yt2 = xOnly ? [] : (zoomed ? exportTicks('y') : (state.ys === 'raw' ? RAW_TICKS : LT));
  if (NARROW) {
    var keepL = [1, 5, 20, 50, 80, 95, 99];
    xt = xt.filter(function (v) { return state.xs === 'raw' ? (v % 20 === 0 && v > 0) : keepL.indexOf(v) >= 0; });
    yt2 = yt2.filter(function (v) { return state.ys === 'raw' ? v % 20 === 0 : keepL.indexOf(v) >= 0; });
  }
  var zOf = function (v) { return logit(Math.min(0.9999, Math.max(0.0001, v / 100))); };
  xt.forEach(function (v) {
    var z = zOf(v), L = limT(state.xs === 'raw', 'x');
    if (tf(z, state.xs === 'raw') <= L[0] || tf(z, state.xs === 'raw') >= L[1]) return;
    g += '<line x1="' + sx(z) + '" y1="' + MT + '" x2="' + sx(z) + '" y2="' + plotBot + '" stroke="#e0d9c8" stroke-width="0.6"/>'
      + '<text x="' + sx(z) + '" y="' + (plotBot + FS + 5) + '" text-anchor="middle" fill="#52514e" font-size="' + FS + '" data-role="tick">' + v + '%</text>';
  });
  yt2.forEach(function (v) {
    var z = zOf(v), L = limT(state.ys === 'raw', 'y');
    if (tf(z, state.ys === 'raw') <= L[0] || tf(z, state.ys === 'raw') >= L[1]) return;
    g += '<line x1="' + ML + '" y1="' + sy(z) + '" x2="' + (ML + PW) + '" y2="' + sy(z) + '" stroke="#e0d9c8" stroke-width="0.6"/>'
      + '<text x="' + (ML - 6) + '" y="' + (sy(z) + Math.round(FS / 3)) + '" text-anchor="end" fill="#52514e" font-size="' + FS + '" data-role="tick">' + v + '%</text>';
  });
  return g;
}
/* The axes' names: D50 and D99 at the default levels, D<100 minus level> otherwise. */
function dName(axis) { var lev = axis === 'x' ? +state.a : +state.c; return 'D' + fmtLev(100 - lev); }
function axisShort(axis) { return dName(axis) + (state.def === 'median' ? ' (median task)' : ''); }
function axisName(axis) {
  var lev = axis === 'x' ? +state.a : +state.c;
  if (state.def !== 'average') return 'D' + fmtLev(100 - lev) + ' (median task, posterior median)';
  var base = 'D' + fmtLev(100 - lev) + ' (average rate, posterior median)';
  if (lev === 50 && axis === 'x') return 'Capability: ' + base;
  if (lev === 1 && axis === 'y') return 'Reliability: ' + base;
  return base;
}
/* A title that would overrun its band is cut with an ellipsis; the whole text rides in a <title>. */
function fitTitle(text, maxUnits, fontSize) {
  var perChar = fontSize * 0.55, full = text;
  if (text.length * perChar > maxUnits) text = text.replace(/\s*\([^)]*\)/g, '');
  if (text.length * perChar > maxUnits) text = text.slice(0, Math.max(8, Math.floor(maxUnits / perChar) - 1)) + '…';
  return text === full ? text : text + '</text><title>' + full.replace(/</g, '&lt;') + '</title><text style="display:none">';
}

/* ---- the level track above the plot: the two levels as draggable knobs ---------------------------------------------- */
var TRK = { x0: ML, x1: ML + PW, y: 18, lo: logit(0.002), hi: logit(0.995) };
function trkX(levLogit) { return TRK.x0 + (levLogit - TRK.lo) / (TRK.hi - TRK.lo) * (TRK.x1 - TRK.x0); }
function trkLev(px) { var t = Math.max(0, Math.min(1, (px - TRK.x0) / (TRK.x1 - TRK.x0))); return TRK.lo + t * (TRK.hi - TRK.lo); }
function levelTrack() {
  var ink = '#52514e';
  var xa = trkX(logit(state.a / 100)), xc = trkX(logit(state.c / 100));
  return '<g id="lvltrack">'
    + '<line x1="' + TRK.x0 + '" y1="' + TRK.y + '" x2="' + TRK.x1 + '" y2="' + TRK.y + '" stroke="#cfc5ac" stroke-width="2"/>'
    + '<text x="' + (TRK.x0 - 6) + '" y="' + (TRK.y + 4) + '" text-anchor="end" font-size="' + FT + '" fill="#8b8477">levels</text>'
    + '<circle data-handle="c" class="handle" cx="' + xc + '" cy="' + TRK.y + '" r="' + (NARROW ? 16 : 12) + '" fill="transparent"/>'
    + '<circle class="knob" data-knob="c" pointer-events="none" cx="' + xc + '" cy="' + TRK.y + '" r="5" fill="#fcfaf3" stroke="' + ink + '" stroke-width="1.6"/>'
    + '<text data-handle="c" class="handle" x="' + xc + '" y="' + (TRK.y - 6) + '" text-anchor="middle" font-size="' + FT + '" fill="' + ink + '">y ' + state.c + '%</text>'
    + '<circle data-handle="a" class="handle" cx="' + xa + '" cy="' + TRK.y + '" r="' + (NARROW ? 16 : 12) + '" fill="transparent"/>'
    + '<circle class="knob" data-knob="a" pointer-events="none" cx="' + xa + '" cy="' + TRK.y + '" r="5" fill="#fcfaf3" stroke="' + ink + '" stroke-width="1.6"/>'
    + '<text data-handle="a" class="handle" x="' + xa + '" y="' + (TRK.y + 16) + '" text-anchor="middle" font-size="' + FT + '" fill="' + ink + '">x ' + state.a + '%</text>'
    + '</g>';
}
function updateTrack() {
  var tg = document.getElementById('trackg');
  tg.style.display = '';
  var structure = NARROW ? 'n' : 'w';
  if (!tg.hasChildNodes() || tg.dataset.structure !== structure) { tg.innerHTML = levelTrack(); tg.dataset.structure = structure; return; }
  var xa = trkX(logit(state.a / 100)), xc = trkX(logit(state.c / 100));
  tg.querySelectorAll('[data-handle], [data-knob]').forEach(function (el) { var key = el.dataset.handle || el.dataset.knob; el.setAttribute('cx', key === 'a' ? xa : xc); });
  tg.querySelectorAll('text').forEach(function (t) {
    var txt = t.textContent;
    if (txt.charAt(0) === 'y' && txt.indexOf('%') > 0) { t.setAttribute('x', xc); t.textContent = 'y ' + state.c + '%'; }
    else if (txt.charAt(0) === 'x' && txt.indexOf('%') > 0) { t.setAttribute('x', xa); t.textContent = 'x ' + state.a + '%'; }
  });
}

/* ---- the scatter: every selected model at its two crossings, the whiskers, the fitted line and its band ----------- */
var lastMoved = null, lockNote = null, inputNote = null, undrawn = [];
var beyondFrame = 0, beyondArms = [], unresolvedN = 0, partialShownN = 0;
var lastFit = null, lastFitN = 0, lastFitText = '';
function renderScatter() {
  foldSweepTools(); phoneFold();
  if (playBtn) { playBtn.disabled = false; playBtn.title = ''; }
  layout();
  var chart = document.getElementById('chart');
  chart.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  var la = logit(state.a / 100), lc = logit(state.c / 100);
  var out = axisGrid();
  var clipAt = out.length; EXT = null;
  /* the diagonal y = x: a model on it fails at the y level as soon as a task passes its x level */
  var dg = '', GX = LIMX || LIM, GY = LIMY || LIM, G0 = Math.max(GX[0], GY[0]), G1 = Math.min(GX[1], GY[1]);
  var zoomedExport = EXPORTING && LIMX && LIMY;
  for (var t = 0; t <= 40 && G1 > G0 && !zoomedExport; t++) { var z = G0 + (G1 - G0) * t / 40; dg += (t ? 'L' : 'M') + sx(z).toFixed(1) + ' ' + sy(z).toFixed(1); }
  if (dg) out += '<path d="' + dg + '" fill="none" stroke="#cfc5ac" stroke-width="0.8" stroke-dasharray="3.3 2.7" data-diagonal/>';

  var visible = Array.from(sel).filter(function (i) { return !isHidden(i); }).sort(function (a, b) { return a - b; });
  var drawnArms = [];
  /* K paths: for each model, the curve of its (x, y) pair as the two levels move together at a fixed ratio K = x/y */
  if (state.kp === 'on') {
    var K = state.a / state.c, tgrid = D.cross.lev_logit, trails = '';
    visible.forEach(function (i) {
      var cc = D.shared.arms[i], tp = '', pen = false;
      for (var ti = 0; ti < tgrid.length; ti += 2) {
        var pxl = pct(tgrid[ti]), pyl = pxl / K;
        if (pyl < 0.2 || pyl > 99.5 || pxl < 0.2 || pxl > 99.5) { pen = false; continue; }
        var tx = reading(i, logit(pxl / 100)), ty = reading(i, logit(pyl / 100));
        if (tx.kind !== 'point' || ty.kind !== 'point' || tx.z == null || ty.z == null) { pen = false; continue; }
        tp += (pen ? 'L' : 'M') + sx(clampZ(tx.z)).toFixed(1) + ' ' + sy(clampZ(ty.z)).toFixed(1);
        pen = true;
      }
      if (tp) trails += '<path d="' + tp + '" fill="none" stroke="' + cc.color + '" stroke-width="0.9" opacity="0.3" data-trail="' + i + '"/>';
    });
    out += '<g id="ktrails">' + trails + '</g>';
  }
  /* K ladders: at a model's x position, its y crossing as the y level falls from x/1 to x/K, with rungs at the K chips */
  if (state.lad === 'on') {
    var lads = '', LN = 26;
    visible.forEach(function (i) {
      var cc2 = D.shared.arms[i], rx0 = reading(i, la);
      if (rx0.kind !== 'point' || rx0.z == null) return;
      var X0 = sx(clampZ(rx0.z)), lp = '', pen = false;
      for (var li = 0; li < LN; li++) {
        var kk = Math.pow(2, li / (LN - 1) * Math.log2(K_LADDER_MAX)), pyl = state.a / kk;
        if (pyl < 0.2) break;
        var ry0 = reading(i, logit(pyl / 100));
        if (ry0.kind !== 'point' || ry0.z == null) { pen = false; continue; }
        lp += (pen ? 'L' : 'M') + X0.toFixed(1) + ' ' + sy(clampZ(ry0.z)).toFixed(1);
        pen = true;
      }
      var rungs = '';
      K_CHIPS.forEach(function (kk) {
        var pyl = state.a / kk; if (pyl < 0.2) return;
        var ry1 = reading(i, logit(pyl / 100)); if (ry1.kind !== 'point' || ry1.z == null) return;
        var Y1 = sy(clampZ(ry1.z));
        rungs += 'M' + (X0 - 3).toFixed(1) + ' ' + Y1.toFixed(1) + 'L' + (X0 + 3).toFixed(1) + ' ' + Y1.toFixed(1);
      });
      if (lp) lads += '<path d="' + lp + rungs + '" fill="none" stroke="' + cc2.color + '" stroke-width="0.9" opacity="0.35" stroke-dasharray="1.5 2" data-ladder="' + i + '"/>';
    });
    out += '<g id="ladders">' + lads + '</g>';
  }

  var fx = [], fy = [], fsig = [], fl = [], fcol = [], marks = ''; undrawn = []; beyondFrame = 0; beyondArms = []; partialShownN = 0; unresolvedN = 0;
  visible.forEach(function (i) {
    var c = D.shared.arms[i];
    var part = isPartial(i), col = part ? '#8b8477' : c.color;
    var rx = reading(i, la), ry = reading(i, lc);
    if (rx.z == null || ry.z == null) { undrawn.push(c.label + ' (' + ((rx.z == null ? rx.extra : ry.extra) || 'no crossing at this pair') + ')'); return; }
    if (rx.z > LIM[1] || rx.z < LIM[0]) rx = Object.assign({}, rx, { kind: rx.z > LIM[1] ? 'hi-bound' : 'lo-bound', beyond: true });
    if (ry.z > LIM[1] || ry.z < LIM[0]) ry = Object.assign({}, ry, { kind: ry.z > LIM[1] ? 'hi-bound' : 'lo-bound', beyond: true });
    if (rx.beyond || ry.beyond) { beyondFrame++; beyondArms.push(i); }
    if (part) partialShownN++;
    var X = sx(clampZ(rx.z)), Y = sy(clampZ(ry.z));
    extAdd(clampZ(rx.z), clampZ(ry.z));
    var full = rx.kind === 'point' && ry.kind === 'point';
    drawnArms.push({ i: i, id: c.id, label: c.label, color: col, x: rx.z, y: ry.z, kindX: rx.kind, kindY: ry.kind, point: full, beyond: !!(rx.beyond || ry.beyond), open: !!c.think, run: !!c.run, partial: part, X: X, Y: Y });
    var fade = full ? 1 : 0.4;
    if (c.gates_failed) fade = Math.min(fade, 0.55);
    if (part) fade = Math.min(fade, 0.45);
    var d = '', openMarks = '';
    if (state.w === 'on') {
      if (rx.lo != null && rx.hi != null) { extAdd(clampZ(rx.lo), null); extAdd(clampZ(rx.hi), null); }
      if (ry.lo != null && ry.hi != null) { extAdd(null, clampZ(ry.lo)); extAdd(null, clampZ(ry.hi)); }
      if (rx.lo != null && rx.hi != null) d += 'M' + sx(clampZ(rx.lo)).toFixed(1) + ' ' + Y.toFixed(1) + 'L' + sx(clampZ(rx.hi)).toFixed(1) + ' ' + Y.toFixed(1);
      if (ry.lo != null && ry.hi != null) d += 'M' + X.toFixed(1) + ' ' + sy(clampZ(ry.lo)).toFixed(1) + 'L' + X.toFixed(1) + ' ' + sy(clampZ(ry.hi)).toFixed(1);
      /* an open whisker end: the band runs past the scale */
      if (rx.hi_open && rx.hi != null) openMarks += '<path d="M' + sx(clampZ(rx.hi)).toFixed(1) + ' ' + Y.toFixed(1) + 'm-1 -4l4 4l-4 4" fill="none" stroke-linejoin="round" stroke-linecap="round" stroke="' + col + '" stroke-width="1.3"/>';
      if (ry.hi_open && ry.hi != null) openMarks += '<path d="M' + X.toFixed(1) + ' ' + sy(clampZ(ry.hi)).toFixed(1) + 'm-4 1l4 -4l4 4" fill="none" stroke-linejoin="round" stroke-linecap="round" stroke="' + col + '" stroke-width="1.3"/>';
      if (rx.lo_open && rx.lo != null) openMarks += '<path d="M' + sx(clampZ(rx.lo)).toFixed(1) + ' ' + Y.toFixed(1) + 'm1 -4l-4 4l4 4" fill="none" stroke-linejoin="round" stroke-linecap="round" stroke="' + col + '" stroke-width="1.3"/>';
      if (ry.lo_open && ry.lo != null) openMarks += '<path d="M' + X.toFixed(1) + ' ' + sy(clampZ(ry.lo)).toFixed(1) + 'm-4 -1l4 4l4 -4" fill="none" stroke-linejoin="round" stroke-linecap="round" stroke="' + col + '" stroke-width="1.3"/>';
    }
    var Xs = X.toFixed(1), Ys = Y.toFixed(1), mark;
    if (full) {
      var shp = markShape(i), rm = runMarkOf(i), dot = !!(c.run && rm && rm.dot);
      mark = '<path d="' + markPath(shp, X, Y, DR) + '" fill="' + (c.think ? '#fcfaf3' : col) + '" stroke="' + (c.think ? col : '#fcfaf3') + '" stroke-width="1.3" data-mark data-shape="' + shp + '"'
        + (c.run ? ' data-run="' + String(c.run).replace(/[^a-z0-9._-]/gi, '') + '" data-arm="' + String(c.id).replace(/[^a-z0-9._\/-]/gi, '') + '"' : '') + (dot ? ' data-dot="1"' : '') + ' data-i="' + i + '"/>'
        + (dot ? '<circle cx="' + Xs + '" cy="' + Ys + '" r="1.7" fill="' + (c.think ? col : '#fcfaf3') + '" data-dot-mark data-i="' + i + '"/>' : '');
    } else {
      /* a bound: an open chevron at the scale's end, pointing to the side the crossing lies beyond */
      var pt = ry.kind === 'hi-bound' ? 'm-5 3l5 -8l5 8' : ry.kind === 'lo-bound' ? 'm-5 -3l5 8l5 -8' : rx.kind === 'hi-bound' ? 'm-3 -5l8 5l-8 5' : 'm3 -5l-8 5l8 5';
      mark = '<path d="M' + Xs + ' ' + Ys + pt + '" fill="none" stroke="' + col + '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" data-mark data-shape="bound"'
        + (c.run ? ' data-run="' + String(c.run).replace(/[^a-z0-9._-]/gi, '') + '" data-arm="' + String(c.id).replace(/[^a-z0-9._\/-]/gi, '') + '"' : '') + ' data-i="' + i + '"/>';
    }
    marks += '<g opacity="' + fade + '" data-i="' + i + '">'
      + '<circle class="hit" data-export="omit" cx="' + Xs + '" cy="' + Ys + '" r="' + (NARROW ? 15 : 9) + '" fill="transparent" stroke="none"/>'
      + (d ? '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.1" opacity="0.55"/>' : '')
      + openMarks + mark + '</g>';
    /* the fitted line's population: point crossings on both axes, released models only, partial models out */
    if (full && !part && !isRun(i)) {
      fx.push(FX(rx.z)); fy.push(FY(ry.z)); fl.push(c.label); fcol.push(col);
      var zx = 1.2816, zy = 1.2816;
      var hwx = Math.max(rx.lo != null && !rx.lo_open ? Math.abs(FX(rx.z) - FX(rx.lo)) : -1, rx.hi != null && !rx.hi_open ? Math.abs(FX(rx.hi) - FX(rx.z)) : -1);
      var hwy = Math.max(ry.lo != null && !ry.lo_open ? Math.abs(FY(ry.z) - FY(ry.lo)) : -1, ry.hi != null && !ry.hi_open ? Math.abs(FY(ry.hi) - FY(ry.z)) : -1);
      fsig.push(hwx >= 0 && hwy >= 0 ? [hwx / zx, hwy / zy] : null);
    }
  });

  var fitNum = '', fitTxt = 'fit: needs three or more point crossings';
  var sweeping = dragActive || !!playTimer;
  var headFit = null, headN = 0, f = null, RS = null, hc = fcol;
  if (fx.length >= 3) {
    var fkey = [state.def, state.fitci, state.line, state.xs, state.ys, state.lw, state.a, state.c, Array.from(sel).join('.')].join('|');
    var hx = fx, hy = fy, hsig = null, hl = fl, dropped = 0; hc = fcol;
    if (state.fitci === 'honest' || state.lw === 'bands') {
      hx = []; hy = []; hsig = []; hl = []; hc = [];
      for (var qi = 0; qi < fx.length; qi++) {
        if (fsig[qi]) { hx.push(fx[qi]); hy.push(fy[qi]); hsig.push(fsig[qi]); hl.push(fl[qi]); hc.push(fcol[qi]); }
        else dropped++;
      }
    }
    var mgF = inAxes() && state.xs === 'raw' ? 0.03 : 0.15;
    f = (sweeping && !fitCache[fkey]) || hx.length < 3 ? null
        : state.lw === 'bands' ? (fitCache[fkey] || (fitCache[fkey] = yorkFit(hx, hy, hsig, state.fitci === 'honest' ? 80 : 95, mgF)))
        : bootFit(hx, hy, fkey, hsig, mgF);
    RS = f ? residStats(f, hx, hy, hl) : null;
    if (!f && sweeping) fitTxt = 'fit: paused while the levels move — recomputed when they stop';
    if (f) {
      var gx = [Math.min.apply(null, hx) - mgF, Math.max.apply(null, hx) + mgF];
      if (state.line !== 'off') {
        var bp = '';
        for (var bi = 0; bi < f.band.xs.length; bi++) bp += (bi ? 'L' : 'M') + pxF(f.band.xs[bi]).toFixed(1) + ' ' + pyF(f.band.up[bi]).toFixed(1);
        for (var bj = f.band.xs.length - 1; bj >= 0; bj--) bp += 'L' + pxF(f.band.xs[bj]).toFixed(1) + ' ' + pyF(f.band.dn[bj]).toFixed(1);
        out += '<path d="' + bp + 'Z" fill="' + (state.fitci === 'honest' ? '#d9c8a8' : '#cfc5ac') + '" opacity="0.35" stroke="none" data-fitband/>';
        var fp = '';
        for (var t2 = 0; t2 <= 24; t2++) { var zx2 = gx[0] + (gx[1] - gx[0]) * t2 / 24; fp += (t2 ? 'L' : 'M') + pxF(zx2).toFixed(1) + ' ' + pyF(f.a + f.b * zx2).toFixed(1); }
        out += '<path d="' + fp + '" fill="none" stroke="#8b8477" stroke-width="1.1" data-fitline/>';
      }
      var droppedTxt = dropped ? '; ' + dropped + ' dot' + (dropped > 1 ? 's' : '') + ' dropped (no usable whisker width)' : '';
      var modeTxt = state.lw === 'bands' ? 'weighted by the dots’ 80% uncertainty bands on both axes (tighter counts more; the default line is the unweighted one)' + (f.widen > 1.05 ? '; interval widened ' + f.widen.toFixed(1) + '× for scatter beyond the uncertainty bands' : '') + droppedTxt
                  : state.fitci === 'honest' ? 'with each dot’s measurement error' + droppedTxt : 'dots taken as exact';
      var spaceTxt = inAxes() ? 'in the axes as set' : (state.xs === 'raw' || state.ys === 'raw') ? 'in logit (drawn as the curve it maps to on the linear axis)' : 'in logit';
      fitNum = 'slope ' + f.b.toFixed(2) + ' [' + f.lo.toFixed(2) + ', ' + f.hi.toFixed(2) + '], R ' + f.r.toFixed(2);
      fitTxt = 'line ' + spaceTxt + ' over ' + hx.length + ' point crossings; ' + modeTxt
        + (inAxes() ? '; intercept ' + fmtY(f.a) : '')
        + (state.resid === 'on' ? '; misses: typical ' + RS.rmsPct.toFixed(1) + '% of the y scale, largest ' + sgn(RS.bigPct) + '% (' + RS.bigLabel + '), ' + RS.w5 + ' of ' + RS.n + ' models within ±5%, ' + RS.w10 + ' within ±10%' : '')
        + (state.line === 'off' ? ' (not drawn: Fitted line is Off)' : '');
      headFit = f; headN = hx.length;
    }
  }
  headline(headN, headFit, fx.length, sweeping); fitCaption(headFit, headN);
  refreshBeyondChips();
  var drawnN = visible.length - undrawn.length - beyondArms.length - unresolvedN;
  var plx = ML + 8, ply = MT + 8;
  out += (f && RS && state.resid === 'on' && state.line !== 'off' ? residPanel(RS, hc, plx, ply) : '');
  if (EXPORTING) out = out.slice(0, clipAt) + '<clipPath id="expclip"><rect x="' + ML + '" y="' + MT + '" width="' + PW + '" height="' + PH + '"/></clipPath><g clip-path="url(#expclip)">' + out.slice(clipAt) + '</g>';
  var tyx = EXPORTING ? 44 : NARROW ? 11 : 15, tfs = EXPORTING ? EXPORT_TITLE_PX : NARROW ? 13 : Math.max(FS + 1, Math.ceil(13 * UPX));
  var ytt = axisShort('y'), tfsY = tfs;
  if (EXPORTING) { var needY = ytt.length * tfs * 0.56; if (needY > PH * 0.96) tfsY = Math.max(28, Math.floor(tfs * PH * 0.96 / needY)); }
  out += '<text x="' + (ML + PW / 2) + '" y="' + (H - 6) + '" text-anchor="middle" fill="#52514e" font-size="' + tfs + '"' + (EXPORTING ? ' font-weight="700"' : '') + ' data-role="axis-title">' + fitTitle(axisShort('x'), W - 20, tfs) + '</text>'
    + '<text x="' + tyx + '" y="' + (MT + PH / 2) + '" text-anchor="middle" fill="#52514e" font-size="' + tfsY + '"' + (EXPORTING ? ' font-weight="700"' : '') + ' transform="rotate(-90 ' + tyx + ' ' + (MT + PH / 2) + ')" data-role="axis-title">' + ytt + '</text>';
  var body = '<g id="marks">' + marks + '</g>';
  /* the quiet count: the number of models drawn, small type in the plot's corner */
  out += '<text x="' + (ML + PW - 6) + '" y="' + (MT + PH - 10) + '" text-anchor="end" font-size="' + (EXPORTING ? EXPORT_TICK_PX : FT) + '" fill="#52514e" data-count>n = ' + drawnN + '</text>';
  document.getElementById('plotg').innerHTML = out + (EXPORTING ? '<g clip-path="url(#expclip)">' + body + '</g>' : body);
  updateTrack();
  lastFit = headFit; lastFitN = headN; lastFitText = fitNum ? fitNum + ' · ' + fitTxt : fitTxt;
  setLine();
  paintChips();
  var k = state.a / state.c;
  document.getElementById('kOut').textContent = 'K = ' + (k >= 100 ? k.toFixed(0) : k.toFixed(1));
  var kb = document.getElementById('kBound');
  var slotNotes = [inputNote, lockNote].filter(Boolean).join(' · ');
  if (kb) kb.textContent = slotNotes ? slotNotes : Math.abs(k - 1) <= 1e-6 ? 'K at 1×: the levels coincide' : k < 1 ? 'K below 1×: the horizontal level lies under the vertical level' : '';
}

/* ---- the ridges: per model the density of the two crossings over the difficulty scale ----------------------------- */
function renderRidges() {
  if (playBtn) { playBtn.disabled = true; playBtn.title = 'the sweep moves the scatter; switch the view back to use it'; }
  var chart = document.getElementById('chart');
  var visible = Array.from(sel).filter(function (i) { return !isHidden(i); }).sort(function (a, b) { return a - b; });
  var rows = visible.filter(function (i) { return !!crossRow(i); }).map(function (i) { return { i: i, r: crossRow(i) }; });
  var g = D.cross.density_grid;
  layout();
  var rh = 24, RML = NARROW ? 120 : 195;
  var Hr = MT + (rows.length + 1) * rh + MB;
  chart.setAttribute('viewBox', '0 0 ' + W + ' ' + Hr);
  var rzx = function (z) { var L = limT(state.xs === 'raw'); return RML + (tf(z, state.xs === 'raw') - L[0]) / (L[1] - L[0]) * (W - RML - MR); };
  var out = '';
  var rxt = state.xs === 'raw' ? RAW_TICKS : LOGIT_TICKS;
  rxt.forEach(function (v) {
    var z = logit(Math.min(0.9999, Math.max(0.0001, v / 100))), L = limT(state.xs === 'raw');
    if (tf(z, state.xs === 'raw') <= L[0] || tf(z, state.xs === 'raw') >= L[1]) return;
    out += '<line x1="' + rzx(z) + '" y1="' + MT + '" x2="' + rzx(z) + '" y2="' + (Hr - MB) + '" stroke="#e0d9c8" stroke-width="0.6"/>'
      + '<text x="' + rzx(z) + '" y="' + (Hr - MB + 17) + '" text-anchor="middle" fill="#52514e" font-size="11">' + v + '%</text>';
  });
  out += '<text x="' + (RML + (W - RML - MR) / 2) + '" y="' + (Hr - 6) + '" text-anchor="middle" fill="#52514e" font-size="12">task difficulty</text>';
  rows.forEach(function (row, k) {
    var y0 = MT + (k + 1) * rh, c = D.shared.arms[row.i], b = defBlock(row.r);
    var drawnY = null;
    /* at the default levels the density of the crossing draws is drawn whole (filled for x, outlined for y); at other
     * levels the 80% band with its median from the per-level table */
    [[state.a / 100, true], [state.c / 100, false]].forEach(function (Q) {
      var lev = Q[0], filled = Q[1], baked = filled ? Math.abs(lev - 0.5) < 1e-9 : Math.abs(lev - 0.01) < 1e-9;
      var blk = baked ? (filled ? b.d50 : b.d99) : null;
      if (!filled) drawnY = blk && blk.density ? blk : null;
      if (blk && blk.density) {
        var kd = blk.density, mx = Math.max.apply(null, kd) || 1, d = '', pen = false, z0 = null, zN = null;
        for (var jj = 0; jj < g.length; jj++) {
          if (g[jj] < LIM[0] || g[jj] > LIM[1]) continue;
          if (z0 === null) z0 = g[jj];
          zN = g[jj];
          d += (pen ? 'L' : 'M') + rzx(g[jj]).toFixed(1) + ' ' + (y0 - (kd[jj] / mx) * (rh * 0.92)).toFixed(1);
          pen = true;
        }
        if (!pen) return;
        if (filled) { d += 'L' + rzx(zN).toFixed(1) + ' ' + y0.toFixed(1) + 'L' + rzx(z0).toFixed(1) + ' ' + y0.toFixed(1) + 'Z'; out += '<path d="' + d + '" fill="' + c.color + '" fill-opacity="0.45" stroke="none" data-mark/>'; }
        else out += '<path d="' + d + '" fill="none" stroke="' + c.color + '" stroke-width="1.2"' + (c.think ? ' stroke-dasharray="5 3"' : '') + ' data-mark/>';
        return;
      }
      var t = tableAt(b.levels, logit(lev));
      if (!t || t.z == null) return;
      var lo = t.lo != null ? Math.max(LIM[0], Math.min(LIM[1], t.lo)) : t.z, hi = t.hi != null ? Math.max(LIM[0], Math.min(LIM[1], t.hi)) : t.z, zc = Math.max(LIM[0], Math.min(LIM[1], t.z));
      var h = filled ? rh * 0.5 : rh * 0.7, yb = y0 - (filled ? rh * 0.62 : rh * 0.72);
      out += filled
        ? '<rect x="' + rzx(lo).toFixed(1) + '" y="' + yb.toFixed(1) + '" width="' + Math.max(1.5, rzx(hi) - rzx(lo)).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + c.color + '" fill-opacity="0.45" stroke="none" data-mark/>'
        : '<rect x="' + rzx(lo).toFixed(1) + '" y="' + yb.toFixed(1) + '" width="' + Math.max(1.5, rzx(hi) - rzx(lo)).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="none" stroke="' + c.color + '" stroke-width="1.2"' + (c.think ? ' stroke-dasharray="5 3"' : '') + ' data-mark/>';
      out += '<line x1="' + rzx(zc).toFixed(1) + '" y1="' + yb.toFixed(1) + '" x2="' + rzx(zc).toFixed(1) + '" y2="' + (yb + h).toFixed(1) + '" stroke="' + c.color + '" stroke-width="1.6"/>';
    });
    var ltxt = c.label + (drawnY && drawnY.p_censored > 0.05 ? ' · ' + Math.round(drawnY.p_censored * 100) + '% cens.' : '');
    out += '<text x="' + (RML - 6) + '" y="' + (y0 - 3) + '" text-anchor="end" font-size="9.5" fill="#52514e"' + (ltxt.length > 34 ? ' textLength="' + (RML - 14) + '" lengthAdjust="spacingAndGlyphs"' : '') + '>' + ltxt + '</text>';
  });
  document.getElementById('plotg').innerHTML = out;
  document.getElementById('trackg').style.display = 'none';
  var bakedX = Math.abs(state.a - 50) < 1e-9, bakedY = Math.abs(state.c - 1) < 1e-9;
  lastFit = null; lastFitN = 0;
  lastFitText = 'the spread of the same crossings the dots mark, across the fitted draws (' + (state.def === 'average' ? 'average-rate' : 'median-task') + ' definition): filled = the crossing at the x level ' + state.a + '%, outlined = at the y level ' + state.c + '% — '
    + (bakedX && bakedY ? 'the densities of the crossing draws; a censored draw is not in a shape (the label notes the share)' : 'the 80% uncertainty band with its median at levels other than 50% and 1%; densities at 50% and 1%')
    + ' · ' + visible.length + ' of ' + D.shared.arms.length + ' models · move x or y and the view follows';
  setLine();
  paintChips();
}

/* ---- the export: the plot as drawn with a legend of every shown model by its name of record ------------------------ */
var exportMounted = false;
function mountExport() {
  if (exportMounted) return;
  var box = document.getElementById('exportrow'); if (!box || !window.Kit || !Kit.exportButton) return;
  exportMounted = true;
  Kit.exportButton(box, exportOptions);
}
function exportLegend() {
  var rows = [];
  famOrder(Array.from(sel).filter(function (i) { return !isHidden(i); })).forEach(function (i) {
    var m = document.querySelector('#marks path[data-mark][data-i="' + i + '"]'); if (!m) return;
    var c = D.shared.arms[i], grey = isPartial(i);
    var d = m.getAttribute('d') || '', fill = m.getAttribute('fill') || 'none', stroke = m.getAttribute('stroke') || c.color, sw = m.getAttribute('stroke-width') || '1.3', da = m.getAttribute('stroke-dasharray') || '';
    var op = m.parentNode && m.parentNode.getAttribute ? m.parentNode.getAttribute('opacity') : null;
    var dot = m.getAttribute('data-dot') === '1', dotFill = fill === '#fcfaf3' ? stroke : '#fcfaf3';
    var mark = function (cx, cy) {
      return '<path d="' + d.replace(/^M[-\d.]+ [-\d.]+/, 'M' + cx + ' ' + cy) + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"' + (da ? ' stroke-dasharray="' + da + '"' : '') + (op && +op < 1 ? ' opacity="' + op + '"' : '') + '/>'
        + (dot ? '<circle cx="' + cx + '" cy="' + cy + '" r="1.7" fill="' + dotFill + '"/>' : '');
    };
    rows.push({ label: c.label + (grey ? ' (partial)' : ''), family: c.family, color: grey ? '#8b8477' : c.color, line: false, marker: mark });
  });
  return rows;
}
function exportOptions() {
  var chart = document.getElementById('chart');
  var tight = state.view !== 'ridges' && EXT && isFinite(EXT.x0) && isFinite(EXT.y0) && isFinite(EXT.x1) && isFinite(EXT.y1) && EXT.x1 >= EXT.x0 && EXT.y1 >= EXT.y0;
  EXPORT_TIER_Y = null; EXPORT_FLOOR_Y = null;
  if (tight) {
    /* the export is cropped to the drawn points: a window per axis around the points with 2% room, the vertical axis
     * continued down to the nearest tick under the lowest point, the two windows kept within a factor of two */
    var padX = Math.max(0.05, (EXT.x1 - EXT.x0) * 0.02), padY = Math.max(0.05, (EXT.y1 - EXT.y0) * 0.02);
    LIMX = [Math.max(LIM[0], EXT.x0 - padX), Math.min(LIM[1], EXT.x1 + padX)];
    LIMY = [Math.max(LIM[0], EXT.y0 - padY), Math.min(LIM[1], EXT.y1 + padY)];
    if (state.ys !== 'raw') {
      var lo = pct(LIMY[0]), hi = pct(LIMY[1]), tiers = [LOGIT_TICKS_EXPORT, LOGIT_TICKS_FINE, pctLadder(lo, hi)], pick = null, floor = null;
      for (var ti = 0; ti < tiers.length && !pick; ti++) {
        var isPct = ti === tiers.length - 1, tier = tiers[ti], n = tier.filter(function (v) { return v > lo && v < hi; }).length, fb = floorIn(tier, EXT.y0, isPct);
        var reach = fb ? EXT.y0 - fb.z : 0;
        if ((n >= 3 && reach <= Math.max(0.15, 0.25 * (EXT.y1 - EXT.y0))) || isPct) { pick = tier; floor = fb; }
      }
      EXPORT_TIER_Y = pick;
      if (floor) { LIMY[0] = Math.max(LIM[0], Math.min(LIMY[0], floor.z - 0.06)); EXPORT_FLOOR_Y = floor.v; }
    }
    if (state.xs === state.ys) {
      var rawB = state.xs === 'raw';
      var spanOf = function (B) { var L = rawB ? [Math.max(0, pct(B[0]) / 100 - 0.02), Math.min(1, pct(B[1]) / 100 + 0.02)] : B; return L[1] - L[0]; };
      var widenTo = function (B, want) {
        var lo2 = 0, hi2 = LIM[1] - LIM[0];
        for (var k = 0; k < 40; k++) { var d = (lo2 + hi2) / 2, C = [Math.max(LIM[0], B[0] - d), Math.min(LIM[1], B[1] + d)]; if (spanOf(C) < want) lo2 = d; else hi2 = d; }
        return [Math.max(LIM[0], B[0] - hi2), Math.min(LIM[1], B[1] + hi2)];
      };
      var sxp = spanOf(LIMX), syp = spanOf(LIMY);
      if (syp / sxp > 2) LIMX = widenTo(LIMX, syp / 2); else if (syp / sxp < 0.5) LIMY = widenTo(LIMY, sxp / 0.5);
    }
    if (state.ys !== 'raw') {
      var lo3 = pct(LIMY[0]), hi3 = pct(LIMY[1]), have = (EXPORT_TIER_Y || []).filter(function (v) { return v > lo3 && v < hi3; }).length;
      if (have < 2) {
        var tiers2 = [LOGIT_TICKS_EXPORT, LOGIT_TICKS_FINE, pctLadder(lo3, hi3)], pick2 = null;
        for (var tj = 0; tj < tiers2.length && !pick2; tj++) { var n2 = tiers2[tj].filter(function (v) { return v > lo3 && v < hi3; }).length; if (n2 >= 3 || tj === tiers2.length - 1) pick2 = tiers2[tj]; }
        EXPORT_TIER_Y = pick2;
      }
    }
  }
  EXPORTING = true; render();
  var legend = state.view === 'ridges' ? [] : exportLegend();
  var restore = function () { EXPORTING = false; LIMX = null; LIMY = null; EXPORT_TIER_Y = null; EXPORT_FLOOR_Y = null; NO_RATCHET = true; try { render(); } finally { NO_RATCHET = false; } };
  if (window.queueMicrotask) queueMicrotask(restore); else Promise.resolve().then(restore);
  return { svg: chart, legend: legend, title: 'capability-vs-reliability ' + (D.shared.set.label || ''), page: '', view: axisShort('y') + ' against ' + axisShort('x'), stamp: '', crop: null, boldAxisTitles: true };
}

/* ---- hover: a model's two readings with their bands --------------------------------------------------------------- */
var tipPinned = false;
function hoverWire() {
  var box = document.getElementById('chartbox');
  function showFor(ev) {
    var g = ev.target.closest ? ev.target.closest('[data-i]') : null;
    if (!g || state.view !== 'scatter') { if (ev.type === 'pointerdown' || !tipPinned) { tipPinned = false; Kit.tooltip.hide(); } return; }
    if (ev.type === 'pointerdown' && ev.pointerType === 'touch') tipPinned = true;
    var i = +g.dataset.i, c = D.shared.arms[i];
    var rx = reading(i, logit(state.a / 100)), ry = reading(i, logit(state.c / 100));
    function fmt(r) {
      if (r.z == null) return 'no reading at this level';
      var v = fmtPct(r.z);
      if (r.kind === 'lo-bound') return '≤ ' + v;
      if (r.kind === 'hi-bound') return '≥ ' + v;
      return v + ((r.lo != null && r.hi != null) ? ' [' + fmtPct(r.lo) + ', ' + fmtPct(r.hi) + ']' : '');
    }
    Kit.tooltip.show(ev.clientX, ev.clientY, [
      { key: c.color, value: fmt(rx), label: axisName('x') + (c.gates_failed ? ' · the fit failed a sampler check' : '') },
      { key: c.color, value: fmt(ry), label: axisName('y') },
      { key: null, value: '', label: rx.extra },
      { key: null, value: '', label: ry.extra === rx.extra ? '' : ry.extra },
    ].concat(coverageText(c) ? [{ key: null, value: isPartial(i) ? 'partial' : '', label: coverageText(c) }] : []), c.label);
  }
  box.addEventListener('pointermove', showFor);
  box.addEventListener('pointerdown', showFor);
  box.addEventListener('pointerleave', function () { if (!tipPinned) Kit.tooltip.hide(); });
  document.addEventListener('pointerdown', function (ev) { if (tipPinned && !box.contains(ev.target)) { tipPinned = false; Kit.tooltip.hide(); } });
}

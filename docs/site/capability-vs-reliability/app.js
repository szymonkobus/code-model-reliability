


(function () {
'use strict';

var W = 860, H = 720, ML = 62, MR = 16, MT = 40, MB = 46;
var PW = W - ML - MR, PH = H - MT - MB;


var EXPORTING = false, LIMX = null, LIMY = null, EXT = null, NO_RATCHET = false;
var CHART_VH_GAP = 170;
var EXPORT_TITLE_PX = 26, EXPORT_TICK_PX = 18;
function extAdd(zx, zy) {
  if (!EXT) EXT = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
  if (zx != null && isFinite(zx)) { if (zx < EXT.x0) EXT.x0 = zx; if (zx > EXT.x1) EXT.x1 = zx; }
  if (zy != null && isFinite(zy)) { if (zy < EXT.y0) EXT.y0 = zy; if (zy > EXT.y1) EXT.y1 = zy; }
}
var NARROW = false, FS = 12, FT = 11, DR = 5, UPX = 1;


function layout() {
  if (EXPORTING) {
    NARROW = false; W = 900; ML = 90; MR = 30; MT = 40; MB = 62; DR = 4.5; PW = W - ML - MR; UPX = 1; FS = EXPORT_TICK_PX; FT = 11;


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
var LOGIT_TICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5];
var AXIS_FLOOR_PCT = 0.1;
var LOGIT_TICKS_EXPORT = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 80, 90, 95, 98, 99, 99.5, 99.8, 99.9];


var K_MAX = 99.5 / 0.2, K_LADDER_MAX = 50, K_CHIPS = [2, 4, 8, 10, 16, 32, 50];
var dragK0 = null;
var RAW_TICKS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
function logit(p) { return Math.log(p / (1 - p)); }
function pct(z) { return 100 / (1 + Math.exp(-z)); }
function fmtPct(z, d) { return pct(z).toFixed(d == null ? 1 : d) + '%'; }


var D = {};
var MOUNT = './';
fetch(MOUNT + 'data/manifest.json')
  .then(function (r) { if (!r.ok) throw new Error('manifest: HTTP ' + r.status); return r.json(); })
  .catch(function (e) {
    var why = String(e && e.message || e); why = /HTTP \d+/.test(why) ? why.replace(/^manifest: /, '') : 'not readable as data';
    setHeld('The data manifest is missing or unreadable (' + why + '); nothing is drawn.', 'manifest');
    return new Promise(function () {});
  })
  .then(function (man) {
    D.man = man;


    var ds = man.datasets || { board: { files: man.files, label: DATASETS.board ? DATASETS.board.label : '', fingerprint: man.fingerprint, frame: man.frame } };
    Object.keys(DATASETS).forEach(function (k) { DATASETS[k].available = !!ds[k]; });
    var DEFAULT_DATA = (window.MIRROR_DEFAULT && ds[window.MIRROR_DEFAULT]) ? window.MIRROR_DEFAULT : ds.board_top ? 'board_top' : ds.board ? 'board'
                     : (Object.keys(DATASETS).filter(function (k) { return ds[k]; })[0] || Object.keys(DATASETS)[0]);
    D.defaultData = DEFAULT_DATA;
    var want = Kit.state.get('data', DEFAULT_DATA);
    var ALIASES = { boardfocused: 'board_top', focused: 'top' };
    var RETIRED = { math500: 'MATH-500', aime: 'AIME' };
    if (ALIASES[want]) { want = ALIASES[want]; Kit.state.set('data', want, null); }
    if (!DATASETS[want] && /^golden-/.test(want) && ds[want]) { want = want.slice(7); Kit.state.set('arms', 'golden', 'all'); Kit.state.set('data', want, DEFAULT_DATA); }
    relabel();
    if (!DATASETS[want] || !ds[want]) {
      dataNote = (DATASETS[want] ? 'dataset \u201c' + DATASETS[want].label + '\u201d is not part of this copy \u2014 ' + DATASETS[want].reason
                                 : RETIRED[want] && !DATASETS[want] ? RETIRED[want] + ' is not on this page (coding sets only)'
                                 : 'dataset \u201c' + String(want).slice(0, 40) + '\u201d is not one of ' + Object.keys(DATASETS).join(' | ')) + '; showing ' + DATASETS[DEFAULT_DATA].label;
      want = DEFAULT_DATA; Kit.state.set('data', null, null);
    }


    var armsWant = Kit.state.get('arms', 'all'), armsKey = armsWant === 'golden' ? 'golden-' + want : want;
    if (armsWant !== 'all' && armsWant !== 'golden') { dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + 'arms=' + String(armsWant).slice(0, 40) + ' is not one of all | golden; showing all models'; armsWant = 'all'; armsKey = want; Kit.state.set('arms', null, null); }
    else if (armsWant === 'golden' && !ds[armsKey]) { dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + 'the golden set is not part of this copy for \u201c' + DATASETS[want].label + '\u201d; showing all models'; armsWant = 'all'; armsKey = want; Kit.state.set('arms', null, null); }
    state.data = want; state.arms = armsWant; D.dsId = armsKey; D.dataId = want; D.ds = ds[armsKey]; D.golden = armsWant === 'golden'; D.allDs = ds;
    var files = ds[armsKey].files;
    return Promise.all(['shared', 'chain_average', 'chain_median', 'bayes', 'bayes_prev'].map(function (k) {
      return files[k] ? fetch(MOUNT + 'data/' + files[k]).then(function (r) { return r.json(); }) : Promise.resolve(null);
    }).concat([Promise.resolve(null)]));
  }).then(function (all) {
    D.shared = all[0]; D.avg = all[1]; D.med = all[2]; D.bay = all[3]; D.bayPrev = all[4] || null;
    D.runRaw = all[5] || null;


    var WITHDRAWN = {};
    (D.shared.withdrawn || []).forEach(function (id) { WITHDRAWN[id] = 1; });
    Object.keys(D.shared.fit_excluded || {}).forEach(function (id) { WITHDRAWN[id] = 1; });
    D.shared.configs = D.shared.configs.filter(function (c) { return !WITHDRAWN[c.id]; });
    ['avg', 'med', 'bay'].forEach(function (k) { if (D[k]) D[k].rows = D[k].rows.filter(function (r) { return !WITHDRAWN[r.cfg || r.id]; }); });
    D.shared.fit_excluded = null;
    [D.shared.capC, D.shared.capC_z, D.shared.capC_j].forEach(function (CB) { if (CB && CB.excluded) Object.keys(WITHDRAWN).forEach(function (id) { delete CB.excluded[id]; }); });


    D.avgById = {}; D.medById = {}; D.bayById = {};
    D.avg.rows.forEach(function (r) { D.avgById[r.cfg] = r; });
    if (D.med) D.med.rows.forEach(function (r) { D.medById[r.cfg] = r; });
    if (D.bay) D.bay.rows.forEach(function (r) { D.bayById[r.cfg] = r; });
    D.bayPrevById = {};
    if (D.bayPrev && D.bayPrev.rows && D.bay) { D.bayPrev.rows.forEach(function (r) { D.bayPrevById[r.cfg] = r; }); D.bayPrev.lev_logit = D.bayPrev.lev_fail.map(function (p) { return Math.log(p / (1 - p)); }); }


    if (D.bay && (!D.bay.lev_fail || !D.bay.rows[0].levels
        || !D.bay.rows[0].levels_avg)) {
      document.body.insertAdjacentText('afterbegin',
        'The data files predate this version of the page.');
      throw new Error('bayes artifact predates the average chain');
    }

    if (D.bay) D.bay.lev_logit = D.bay.lev_fail.map(function (p) {
      return Math.log(p / (1 - p));
    });

    D.unfitted = {}; (D.bay && D.bay.unfitted || []).forEach(function (id) { D.unfitted[id] = true; });
    var missing = D.shared.configs.filter(function (c) {
      return !D.avgById[c.id] || (D.med && !D.medById[c.id]) || (D.bay && !D.bayById[c.id] && !D.unfitted[c.id]);
    });
    if (missing.length) {
      document.body.insertAdjacentText('afterbegin',
        'DATA JOIN FAILURE: ' + missing.length
        + ' models missing from a chain artifact — refusing '
        + 'to render rather than mislabel.');
      throw new Error('join failure: '
        + missing.map(function (c) { return c.id; }).join(','));
    }
    boot();
  });


var HOUSE_DATASETS = {


  board_top: { label: 'wave 1+2', hover: 'wave 1+2, on one difficulty axis', available: false, reason: 'this set is not part of this copy' },
  board: { label: 'wave 1', hover: 'wave 1', available: true, reason: 'wave 1 are always served' },
  top: { label: 'wave 2', hover: 'wave 2 (the parked tasks are not in it)', available: false, reason: 'this set is not part of this copy' },
  'new': { label: 'wave 2 + parked', hover: 'wave 2 + parked', available: false, reason: 'this set is not part of this copy' },
  all: { label: 'wave 1+2 + parked', hover: 'wave 1+2 + parked, on one difficulty axis', available: false, reason: 'no single axis covers wave 1 and wave 2' },


};


var CODING_KEYS = ['board_top', 'top', 'board', 'new', 'all'];
function mirrorMap(m) { var o = {}; Object.keys(m).forEach(function (k) { var e = m[k] || {}; o[k] = { label: e.label || k, short: e.short || String(e.label || k).split(' (')[0], hover: e.hover || '', available: false, reason: e.reason || 'this set is not part of this copy' }; }); return o; }
var DATASETS = window.MIRROR_DATASETS ? mirrorMap(window.MIRROR_DATASETS) : HOUSE_DATASETS;
var CADENCE = 'a static copy: the numbers are as built';
function shortMap() { var F = { board_top: 'wave 1+2', top: 'wave 2', board: 'wave 1', 'new': 'wave 2', all: 'wave 1+2 + parked' }, o = {}; Object.keys(DATASETS).forEach(function (k) { o[k] = DATASETS[k].short || F[k] || DATASETS[k].label; }); return o; }
function plainTs(ts) {
  var s = String(ts || ''), m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:?\d{2})?)?/.exec(s), MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  if (!m) return s;
  if (!m[4]) return (+m[3]) + ' ' + MON[+m[2] - 1];
  var d = new Date(m[1] + '-' + m[2] + '-' + m[3] + 'T' + m[4] + ':' + m[5] + ':' + (m[6] || '00') + (m[7] || 'Z'));
  if (!isFinite(d)) return (+m[3]) + ' ' + MON[+m[2] - 1];
  var g = {}; new Intl.DateTimeFormat('en', { timeZone: 'UTC', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d).forEach(function (x) { g[x.type] = x.value; });
  return (+g.day) + ' ' + MON[+g.month - 1];
}
function relabel() {
  Object.keys(DATASETS).forEach(function (k) {
    if (CODING_KEYS.indexOf(k) >= 0) return; var e = D.man && D.man.datasets && D.man.datasets[k];
    if (e && e.label) { DATASETS[k].label = e.label; DATASETS[k].frameLabel = e.label; DATASETS[k].short = String(e.label).split(' (')[0]; } });
  if (!CODING_KEYS.every(function (k) { return DATASETS[k]; })) return;


  function f(v) { return v == null ? null : String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  var C = D.man && D.man.counts_of_record;
  if (C && C.wave1 != null) {
    DATASETS.board.label = 'wave 1 (' + f(C.wave1) + ' tasks)'; DATASETS.board.short = 'wave 1';
    DATASETS.top.label = 'wave 2 (' + f(C.wave2) + ' tasks)'; DATASETS.top.short = 'wave 2';
    DATASETS.board_top.label = 'wave 1+2 (' + f(C.wave12) + ' tasks)'; DATASETS.board_top.short = 'wave 1+2';
    DATASETS['new'].label = 'wave 2 + parked (' + f(C.new_total) + ' tasks)'; DATASETS['new'].short = 'wave 2 + parked';
    DATASETS.all.label = 'wave 1+2 + parked (' + f(C.all) + ' tasks)'; DATASETS.all.short = 'all waves';


    DATASETS.board.hover = 'wave 1';
    DATASETS.top.hover = 'wave 2 (the parked tasks are not in it)';
    DATASETS.board_top.hover = 'wave 1+2, on one difficulty axis';
    DATASETS['new'].hover = 'wave 2 + parked';
    DATASETS.all.hover = 'wave 1+2 + parked, on one difficulty axis';
    return;
  }
  function n(k) { var st = D.allDs && (D.allDs[k] || D.allDs['golden-' + k]); var fr = st && st.frame; return fr ? (fr.tasks_on_axis != null ? fr.tasks_on_axis : fr.tasks) : null; }
  var rb = n('board'), rt = n('top'), rn = n('new'), ra = n('all');
  var nb = f(rb), nt = f(rt), nn = f(rn), na = f(ra), nbt = (rb && rt) ? f(rb + rt) : null;
  if (nbt) { DATASETS.board_top.label = 'wave 1+2 (' + nbt + ' tasks)'; DATASETS.board_top.short = 'wave 1+2'; }
  if (nt) { DATASETS.top.label = 'wave 2 (' + nt + ' tasks)'; DATASETS.top.short = 'wave 2'; }
  if (nb) { DATASETS.board.label = 'wave 1 (' + nb + ' tasks)'; DATASETS.board.short = 'wave 1'; }
  if (nn) { DATASETS['new'].label = 'wave 2 + parked (' + nn + ' tasks)'; DATASETS['new'].short = 'wave 2 + parked'; }
  if (na) { DATASETS.all.label = 'wave 1+2 + parked (' + na + ' tasks)'; DATASETS.all.short = 'wave 1+2 + parked'; }
  DATASETS.board_top.hover = 'wave 1+2, on one difficulty axis'; DATASETS.top.hover = 'wave 2 (the parked tasks are not in it)'; DATASETS.board.hover = 'wave 1'; DATASETS['new'].hover = 'wave 2 + parked'; DATASETS.all.hover = 'wave 1+2 + parked, on one difficulty axis';
}


function coverageOf(c) { var cv = c && c.coverage; if (!cv || !cv.of) return null; return { tasks: Math.min(cv.tasks, cv.of), of: cv.of, share: Math.min(1, cv.tasks / cv.of) }; }
function isPartial(i) { var cv = coverageOf(D.shared.configs[i]); return !!cv && cv.share < 0.9; }
function partialShown() { return state.partial === 'show'; }
function coverageText(c) { var cv = coverageOf(c); return cv ? 'attempts on ' + Math.round(cv.share * 100) + '% of this set\u2019s tasks' : ''; }
function partialArms() { return D.shared.configs.map(function (c, i) { return i; }).filter(function (i) { return isPartial(i) && !isWithheld(i); }); }


var WITHHELD = {};
function isWithheld(i) { var c = D.shared.configs[i]; return !!(c && WITHHELD[c.id]); }
function isHidden(i) { return isWithheld(i) || (!partialShown() && isPartial(i)) || (isRun(i) && (!runShown(runOf(i)) || state.src !== 'bayes')); }
function withheldArms() { return D.shared.configs.map(function (c, i) { return i; }).filter(isWithheld); }
function armNote(c) { var d = c && c.disclosure; return (d && !/^covers \d/.test(d)) ? d : ''; }
function underCredit(c) { var u = D.bay && D.bay.disclosures && D.bay.disclosures.pool_cells_undercredit; if (!u || !c) return null; var ids = (u.affected_arms || []).map(function (k) { return String(k).replace(/\s*\(.*\)\s*$/, ''); }); var hit = ids.indexOf(c.id) >= 0 || ids.indexOf(String(c.id).split('/').pop()) >= 0 || (c.board_id && ids.indexOf(c.board_id) >= 0); return hit ? u : null; }
function cleanedScope(c) { var sc = D.bay && D.bay.cleaned_scope; return (sc && c && sc[c.id]) || ''; }
function asGraded(c) { return !!(c && /removed before grading|cleaning/i.test(armNote(c)) && D.bay && !((D.bay.cleaned_arms || []).indexOf(c.id) >= 0)); }
function refreshPartialChips() {
  chips.forEach(function (b) { var i = +b.dataset.idx, c = D.shared.configs[i]; if (!c) return;
    var words = [];
    if (c.think) words.push('thinking mode \u2014 open marker on the chart');
    if (c.run) { var Rw = runOf(i) || RUN; if (Rw) words.push((c.display_name || Rw.name + ' \u2014 ' + c.label) + ': ' + Rw.clause); }
    if (c.alongside) words.push('positioned on the served axis, not shaping it \u2014 its fit from the ' + c.alongside + ' series, read alongside the board fit set');
    if (c.gates_failed) words.push('flagged fit: ' + (c.gate_flag || 'the fit failed a sampler gate'));
    var base = words.join(' \u00b7 ');
    if (isWithheld(i)) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.classList.add('partial'); b.classList.remove('partialshown'); b.title = 'not shown: ' + WITHHELD[c.id]; return; }
    if (isPartial(i)) {
      if (partialShown()) { b.disabled = false; b.removeAttribute('aria-disabled'); b.classList.remove('partial'); b.classList.add('partialshown'); b.title = (base ? base + ' \u00b7 ' : '') + 'partial: ' + coverageText(c) + ', shown greyed'; }
      else { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.classList.add('partial'); b.classList.remove('partialshown'); b.title = 'partial model, hidden; the Partial models switch shows it' + (coverageText(c) ? ' \u2014 ' + coverageText(c) : ''); }
    } else if (coverageText(c)) { b.title = (base ? base + ' \u00b7 ' : '') + coverageText(c); } else if (base) { b.title = base; }
  });
}
var dataNote = null;
function showDataNote() { var el = document.getElementById('datanote'); if (el) { el.textContent = dataNote || ''; el.hidden = !dataNote; } }
var state = { data: 'board', arms: 'all', view: 'scatter', def: 'average', src: 'house', xdef: 'crossing', move: 'off',
              line: 'steps', lw: 'equal', resid: 'off', hold: 'k', lad: 'off', fitci: 'plain',
              w: 'on', wd: 'adj', xs: 'logit', ys: 'logit',
              a: 50, c: 1, kp: 'off', partial: 'hide', run: 'show' };
var sel = null, chips = [], srcMount = null, playTimer = null;
var LIM = null;

function houseName() {
  return state.def === 'average' ? 'Local-logistic crossings'
                                 : 'Binned-median crossings';
}


function tf(z, raw) { return raw ? pct(z) / 100 : z; }
function limT(raw, ax) {
  var B = (ax === 'y' ? LIMY : LIMX) || LIM;
  return raw ? [Math.max(0, pct(B[0]) / 100 - 0.02),
                Math.min(1, pct(B[1]) / 100 + 0.02)]
             : B;
}
function sx(z) {
  var raw = state.xs === 'raw', L = limT(raw, 'x');
  return ML + (tf(z, raw) - L[0]) / (L[1] - L[0]) * PW;
}
function sy(z) {
  var raw = state.ys === 'raw', L = limT(raw, 'y');
  return MT + (L[1] - tf(z, raw)) / (L[1] - L[0]) * PH;
}
function clampZ(v) { return Math.min(LIM[1], Math.max(LIM[0], v)); }


function inAxes() { return state.line === 'axes'; }
function FX(z) { return inAxes() && state.xs === 'raw' ? tf(z, true) : z; }
function FY(z) { return inAxes() && state.ys === 'raw' ? tf(z, true) : z; }
function pxF(v) { if (!(inAxes() && state.xs === 'raw')) return sx(v); var L = limT(true, 'x'); return ML + (v - L[0]) / (L[1] - L[0]) * PW; }
function pyF(v) { if (!(inAxes() && state.ys === 'raw')) return sy(clampZ(v)); var L = limT(true, 'y'); v = Math.min(L[1], Math.max(L[0], v)); return MT + (L[1] - v) / (L[1] - L[0]) * PH; }
function fmtY(v) { return inAxes() && state.ys === 'raw' ? (100 * v).toFixed(1) + '%' : v.toFixed(2); }


function ySpanF() { if (inAxes() && state.ys === 'raw') { var L = limT(true, 'y'); return L[1] - L[0]; } var B = LIMY || LIM; return B[1] - B[0]; }
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
function sgn(v) { return (v > 0 ? '+' : v < 0 ? '\u2212' : '') + Math.abs(v).toFixed(1); }
function residPanel(RS, cols, x0, y0) {
  var fmin = Math.min.apply(null, RS.fv), fmax = Math.max.apply(null, RS.fv), emax = Math.max.apply(null, RS.es.map(Math.abs)) || 1, pad = 10;
  var t1 = 'misses vs fitted, \u00b1' + (100 * emax / RS.span).toFixed(0) + '% of the y scale \u00b7 ' + RS.w5 + '/' + RS.n + ' within \u00b15%';
  var t2 = 'typical ' + RS.rmsPct.toFixed(1) + '%, largest ' + sgn(RS.bigPct) + '% (' + RS.bigLabel + ')';

  var RW = Math.max(NARROW ? 150 : 230, Math.ceil(Math.max(t1.length, t2.length) * 11 * 0.56) + 2 * pad), RH = NARROW ? 90 : 120;
  var X = function (v) { return x0 + pad + (fmax > fmin ? (v - fmin) / (fmax - fmin) : 0.5) * (RW - 2 * pad); };
  var Y = function (e) { return y0 + 16 + RH / 2 - (e / emax) * (RH / 2 - pad - 16); };
  var out = '<g id="residpanel" data-critical-text pointer-events="none"><rect x="' + x0 + '" y="' + y0 + '" width="' + RW + '" height="' + RH + '" rx="6" fill="#fcfaf3" fill-opacity="0.94" stroke="#d9d2c2"/>'
    + '<text x="' + (x0 + pad) + '" y="' + (y0 + 12) + '" font-size="11" fill="#52514e">' + t1 + '</text>'
    + '<text x="' + (x0 + pad) + '" y="' + (y0 + 24) + '" font-size="10" fill="#52514e">' + t2 + '</text>'
    + '<line x1="' + (x0 + pad) + '" y1="' + Y(0).toFixed(1) + '" x2="' + (x0 + RW - pad) + '" y2="' + Y(0).toFixed(1) + '" stroke="#8b8477" stroke-dasharray="3 2"/>';
  for (var i = 0; i < RS.es.length; i++) out += '<circle cx="' + X(RS.fv[i]).toFixed(1) + '" cy="' + Y(RS.es[i]).toFixed(1) + '" r="3" fill="' + (cols[i] || '#52514e') + '" opacity="0.85" data-resid/>';
  return out + '</g>';
}


function tabAt(lo, w, gidx) {
  if (!w || !w.length) return null;
  var t = gidx - lo;
  if (t < 0 || t > w.length - 1) return null;
  var k = Math.floor(t);
  if (k >= w.length - 1) return w[w.length - 1];
  return w[k] + (t - k) * (w[k + 1] - w[k]);
}
function gidxOf(levLogit) {
  var g = D.avg.lev_grid;
  return (levLogit - g[0]) / (g[1] - g[0]);
}

function arrAt(arr, gidx) {
  var k = Math.floor(gidx);
  if (k < 0 || k >= arr.length - 1) return null;
  var a = arr[k], b = arr[k + 1];
  if (a == null || b == null) return null;
  return a + (gidx - k) * (b - a);
}


function readAvg(i, lev) {
  var r = D.avgById[D.shared.configs[i].id];
  var g = gidxOf(lev);
  var z = tabAt(r.lo, r.z, g);
  var adj = state.wd === 'adj';
  var L = adj ? tabAt(r.loLd, r.zLd, g) : tabAt(r.loL, r.zL, g);
  var Hh = adj ? tabAt(r.loHd, r.zHd, g) : tabAt(r.loH, r.zH, g);
  if (z == null) {

    var below = g < r.lo;
    return { z: below ? D.shared.reachable.floor_z
                      : D.shared.reachable.top_z,
             lo: null, hi: null,
             kind: below ? 'lo-bound' : 'hi-bound',
             extra: 'crossing outside the observed range' };
  }
  return { z: z, lo: L, hi: Hh, kind: 'point',
           extra: 'rho ' + r.rho + ' · design effect x' + r.deff };
}
function readMed(i, lev) {
  var r = D.medById[D.shared.configs[i].id];
  var g = gidxOf(lev);
  var z = arrAt(r.mid, g);
  if (z != null) {
    var k = Math.round(g);
    var df = r.dfrac[Math.max(0, Math.min(r.dfrac.length - 1, k))];
    return { z: z, lo: arrAt(r.L, g), hi: arrAt(r.H, g),
             kind: 'point',
             extra: 'defined in ' + Math.round(df * 100)
                    + '% of resamples' };
  }

  var lofin = null;
  for (var k2 = 0; k2 < r.mid.length; k2++)
    if (r.mid[k2] != null) { lofin = k2; break; }
  if (lofin != null && g < lofin && r.lo_bound)
    return { z: r.lo_bound[0], lo: null, hi: null, kind: 'lo-bound',
             extra: 'at or before the first measurable bin (its '
                    + 'median task has 0 failures below here)' };
  if (r.hi_bound)
    return { z: r.hi_bound[0], lo: null, hi: null, kind: 'hi-bound',
             extra: r.hi_bound[2] === 'ceiling-bin'
               ? 'at or before this bin the median task already '
                 + 'fails ALL attempts'
               : 'level not reached within the observed range' };
  return { z: null, kind: 'none', lo: null, hi: null, extra: '' };
}


function prevFitName() {

  var fl = D.ds && D.ds.flip, w = String((fl && fl.from_wave) || (D.bayPrev && D.bayPrev.fit_set && D.bayPrev.fit_set.wave_id) || '');
  var m = /(\d{4})(\d{2})(\d{2})T\d{4}Z/.exec(w), MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var set = (DATASETS[D.dataId] && (DATASETS[D.dataId].short || DATASETS[D.dataId].label)) || 'this set';
  return m ? 'the ' + (+m[3]) + ' ' + MONTHS[+m[2] - 1] + ' cut of ' + set : 'the previous cut of ' + set;
}
function readBayes(i, levLogit) { return readBayesRow(D.bayById[D.shared.configs[i].id], levLogit, D.bay); }
function readBayesRow(r, levLogit, B) {


  var lt = state.def === 'average' ? r.levels_avg : r.levels;
  var LV = B.lev_logit;


  if (levLogit < LV[0] - 1e-9)
    return { z: lt.zg[0], lo: null, hi: null, kind: 'lo-bound',
             extra: 'level below the table range' };
  if (levLogit > LV[LV.length - 1] + 1e-9)
    return { z: lt.zg[1], lo: null, hi: null, kind: 'hi-bound',
             extra: 'level above the table range' };
  var lo_i = 0, hi_i = LV.length - 1;
  while (hi_i - lo_i > 1) {
    var mm = (lo_i + hi_i) >> 1;
    if (LV[mm] < levLogit) lo_i = mm; else hi_i = mm;
  }
  var j = hi_i, j0 = lo_i;
  if (lt.kind[j0] !== 0 || lt.kind[j] !== 0) {

    var k = lt.kind[lt.kind[j0] !== 0 ? j0 : j];
    return { z: k === -1 ? lt.zg[0] : lt.zg[1], lo: null, hi: null,
             kind: k === -1 ? 'lo-bound' : 'hi-bound',
             extra: k === -1
               ? 'crossing at or before the fitted range'
               : 'level not reached within the fitted range' };
  }
  var t = (levLogit - LV[j0]) / (LV[j] - LV[j0]);
  function ip(a) { return a[j0] + t * (a[j] - a[j0]); }
  var pc = null;
  if (lt.p_left[j0] !== null && lt.p_right[j0] !== null)
    pc = ip(lt.p_left) + ip(lt.p_right);
  var interimNote = r.interim ? 'interim fit, landed ' + plainTs(r.interim.landed) : null;
  return { z: ip(lt.mid), lo: ip(lt.lo), hi: ip(lt.hi), kind: 'point',
           hi_open: lt.hi_open[j0] || lt.hi_open[j],
           lo_open: lt.lo_open[j0] || lt.lo_open[j],
           extra: (interimNote ? interimNote + ' \u00b7 ' : '') + (state.def === 'average'
               ? (r.avg_source === 'exact' ? '80% credible band (crossing draws, average-rate)' : B.whisker_label_avg) : B.whisker_label)
             + (pc !== null
                ? ' · ' + Math.round(pc * 100) + '% of draws censored'
                : '')
             + ((lt.hi_open[j0] || lt.hi_open[j])
                ? ' · upper band end reaches the censored edge (open)'
                : '') };
}
function armFlag(i) {
  var f = D.shared.artifact_flags;
  return f && f.by_cfg[D.shared.configs[i].id] || null;
}


var CAP_KEYS = {


  capC: { block: function () { return D.shared && D.shared.capC; }, fallback: 'Capability (uniform)', clause0: 'population weighted evenly along the failure level, 0 to 1 (Beta(1,1))', short: 'Capability (uniform)' },
  capC_z: { block: function () { return D.shared && D.shared.capC_z; }, fallback: 'Capability (Haldane)', clause0: 'population weighted evenly per difficulty step over the tasks\u2019 range (Beta(0,0), cut at the easiest and hardest task)', short: 'Capability (Haldane)' },
  capC_j: { block: function () { return D.shared && D.shared.capC_j; }, fallback: 'Capability (Jeffreys)', clause0: 'population weighted by the arcsine law along the failure level, heavier at both ends (Beta(\u00bd,\u00bd), no range cut)', short: 'Capability (Jeffreys)' }
};
Object.keys(CAP_KEYS).forEach(function (k) {
  CAP_KEYS[k].name = function () { var b = CAP_KEYS[k].block(); return (b && b.name) || CAP_KEYS[k].fallback; };
  CAP_KEYS[k].clause = function () {
    var b = CAP_KEYS[k].block(), d = b && b.distribution;
    return (typeof d === 'string' && d) || (d && typeof d.plain === 'string' && d.plain) || (b && b.marginal_plain) || CAP_KEYS[k].clause0;
  };
});
function isCap() { return !!CAP_KEYS[state.xdef]; }
function capBlock() { var k = CAP_KEYS[state.xdef]; return k ? k.block() : null; }
function reading(i, levLogit, axis) {
  if (axis === 'x' && isCap()) {
    var CB = capBlock(), bc = CB.by_cfg[D.shared.configs[i].id];
    if (!bc) {
      var why = (CB.excluded || {})[D.shared.configs[i].id] || 'not in the Capability-C population';
      return { z: null, kind: 'none', lo: null, hi: null, extra: 'excluded from the Capability-C population \u2014 ' + why };
    }


    return { z: bc.z, lo: bc.ci80_z ? bc.ci80_z[0] : null,
             hi: bc.ci80_z ? bc.ci80_z[1] : null, kind: 'point',
             extra: 'Capability C = ' + bc.C
               + (bc.ci80_C
                  ? ' [' + bc.ci80_C[0] + ', ' + bc.ci80_C[1]
                    + '] 80% bootstrap interval (difficulty chain)'
                  : ' (mean solve chance, calibrated pool), placed at '
                    + 'its capability C position on the difficulty scale') };
  }
  if (state.src === 'bayes') {
    var cid = D.shared.configs[i].id;
    if (D.unfitted[cid] || !D.bayById[cid]) {
      return { z: null, kind: 'none', lo: null, hi: null, extra: 'awaiting its Bayesian fit' };
    }
    var rb = readBayes(i, levLogit);
    if (underCredit(D.shared.configs[i])) rb.extra = (rb.extra ? rb.extra + ' \u00b7 ' : '') + 'passes on wave 2 were counted as failures at this cut: crossings read less capable and less reliable until the re-fit on corrected counts';
    if (cleanedScope(D.shared.configs[i])) rb.extra = (rb.extra ? rb.extra + ' \u00b7 ' : '') + 'cleaned fit, partial: ' + cleanedScope(D.shared.configs[i]);
    if (asGraded(D.shared.configs[i])) rb.extra = (rb.extra ? rb.extra + ' \u00b7 ' : '') + 'Bayesian fit on the attempts as first graded; a cleaned fit follows';
    return rb;
  }
  return state.def === 'average' ? readAvg(i, levLogit)
                                 : readMed(i, levLogit);
}


var RUNS = [];
var RUN = null;
function runSets(raw) { if (!raw) return []; if (raw.sets && raw.sets.length) return raw.sets; return raw.configs ? [raw] : []; }
function normId(id) { return String(id).replace(/_temp_[0-9.]+$/, '').replace(/_batch$/, '').replace(/--/g, '/'); }
function mergeRunSet(raw) {
  RUNS = []; RUN = null; state.runs = state.runs || {};
  if (!raw || !D.shared || !D.bay || !D.bay.rows) return;
  var axis = D.shared.axis && D.shared.axis.axis_id;
  var byNorm = {}; D.shared.configs.forEach(function (c) { if (!c.run) byNorm[normId(c.id)] = c; });
  var have = {}; D.shared.configs.forEach(function (c) { have[c.id] = true; });
  var haveRow = {}; D.bay.rows.forEach(function (r) { haveRow[r.cfg] = true; });
  runSets(raw).forEach(function (rs, k) {
    if (!rs || !rs.configs || !rs.configs.length) return;
    var set = rs.set || {}; if (set.axis_id && axis && set.axis_id !== axis) return;

    var R = { key: set.series || set.key || ('run' + k), name: set.name || 'run', clause: set.clause || '', tag: set.tag || '',
              hue: set.hue || null, ramp: set.ramp || [], dash: set.dash || '', think: !!set.think, withheld: set.withheld || [], stateKey: set.state_key || (k === 0 ? 'run' : 'run_' + String(set.key || k).replace(/[^a-z0-9]/gi, '')), idx: [], folded: [] };
    var rowsById = {}; (rs.rows || []).forEach(function (r) { rowsById[r.cfg] = r; });
    rs.configs.forEach(function (c) {
      if (have[c.id]) return;
      var twin = byNorm[normId(c.id)];
      if (twin) {
        var r = rowsById[c.id];
        if (r && !haveRow[twin.id]) { var r2 = {}; Object.keys(r).forEach(function (kk) { r2[kk] = r[kk]; }); r2.cfg = twin.id; r2.alongside = R.key; delete r2.run; D.bay.rows.push(r2); haveRow[twin.id] = true; if (D.bayById) D.bayById[twin.id] = r2; }
        twin.run = true; twin.series = R.key; twin.board_label = twin.label; twin.label = c.label || twin.label; twin.display_name = c.display_name || twin.display_name; twin.fam = c.fam || twin.fam;
        twin.step = c.step; twin.index = c.index; if (c.color) twin.color = c.color; twin.think = !!c.think; twin.alongside = R.name;
        if (c.gates_failed) { twin.gates_failed = true; twin.gate_flag = c.gate_flag; if (!twin.disclosure) twin.disclosure = c.gate_flag; }
        R.idx.push(D.shared.configs.indexOf(twin)); R.folded.push(twin.id); return;
      }
      c.run = true; c.series = R.key; if (c.gates_failed && !c.disclosure) c.disclosure = c.gate_flag;
      have[c.id] = true; D.shared.configs.push(c); R.idx.push(D.shared.configs.length - 1);
      var row = rowsById[c.id]; if (row && !haveRow[c.id]) { row.run = true; row.series = R.key; D.bay.rows.push(row); haveRow[c.id] = true; if (D.bayById) D.bayById[c.id] = row; }
    });
    if (R.idx.length || R.folded.length || R.withheld.length) { RUNS.push(R); state.runs[R.stateKey] = Kit.state.get(R.stateKey, 'show') === 'hide' ? 'hide' : 'show'; }
  });
  RUN = RUNS[0] || null;
}
function isRun(i) { var c = D.shared && D.shared.configs[i]; return !!(c && c.run); }
function runOf(i) { var c = D.shared && D.shared.configs[i]; if (!c || !c.run) return null; var ck = c.series || c.run_key; for (var k = 0; k < RUNS.length; k++) if (RUNS[k].key === ck) return RUNS[k]; return RUN; }
function runShown(R) { R = R || RUN; return !!R && state.runs[R.stateKey] !== 'hide'; }
function runOnPlane(R) { return runShown(R) && state.src === 'bayes'; }
function anyRunOnPlane() { return RUNS.some(function (R) { return R.idx.length && runOnPlane(R); }); }
function mainConfigs() { return D.shared.configs.filter(function (c) { return !c.run; }); }
function mainRows() { return D.bay && D.bay.rows ? D.bay.rows.filter(function (r) { return !r.run && !r.alongside; }) : []; }
function boot() {
  mergeRunSet(D.runRaw);
  var g = D.avg.lev_grid;


  LIM = D.shared.limits
    ? [D.shared.limits.lo - 0.15, D.shared.limits.hi + 0.15]
    : [D.shared.reachable.floor_z - 0.35,
       D.shared.reachable.top_z + 0.35];
  var zFloor = logit(AXIS_FLOOR_PCT / 100) - 0.15;
  if (LIM[0] > zFloor) LIM[0] = zFloor;

  sel = new Set();
  var selParam = Kit.state.get('sel', null), selRewrite = false;
  if (selParam !== null && selParam !== '') {


    var keyOf = function (c) { return c.board_id || c.id; };
    var byKey = {}; D.shared.configs.forEach(function (c, i) { byKey[keyOf(c)] = i; byKey[c.id] = i; });
    if (/^[\d.]+$/.test(selParam)) {
      var rebound = [];
      selParam.split('.').forEach(function (t) { var i = +t; if (i >= 0 && i < D.shared.configs.length) { sel.add(i); rebound.push(keyOf(D.shared.configs[i])); } });
      dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + 'link re-bound: the selection was stored by chip position (' + selParam + '), which differs between datasets; it now carries model ids (' + rebound.join(', ') + ')';
      selRewrite = true;
    } else {
      var bad = [];
      selParam.split(',').forEach(function (k) { if (byKey[k] !== undefined) sel.add(byKey[k]); else if (k) bad.push(k); });
      if (bad.length) { dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + 'sel: ' + bad.length + ' entr' + (bad.length > 1 ? 'ies are' : 'y is') + ' not a model of this dataset (' + bad.slice(0, 4).join(', ') + ') \u2014 dropped'; selRewrite = true; }
    }
    var dropped = withheldArms().filter(function (i) { return sel.has(i); });
    if (dropped.length) { dropped.forEach(function (i) { sel.delete(i); }); selRewrite = true; dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + dropped.map(function (i) { return D.shared.configs[i].label; }).join(', ') + ' is not shown (see the notes)'; }
    if (!sel.size) { D.shared.configs.forEach(function (_, i) { if (!isWithheld(i) && !isRun(i)) sel.add(i); }); selRewrite = true; }
    if (Kit.state.get('partial', 'hide') !== 'show' && sel.size && Array.from(sel).every(isPartial)) {
      dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + 'the link named only partial models, which are hidden; every shown model is drawn';
      D.shared.configs.forEach(function (_, i) { if (!isPartial(i) && !isWithheld(i) && !isRun(i)) sel.add(i); }); selRewrite = true;
    }
    if (selRewrite) writeSel();
  } else {
    D.shared.configs.forEach(function (_, i) { if (!isWithheld(i) && !isRun(i)) sel.add(i); });
  }
  state.a = +Kit.state.get('a', 50);
  state.c = +Kit.state.get('c', 1);


  var miss = (D.ds && D.ds.missing) || {};
  var LIMITS = [['def', 'median', !!D.med, 'average', miss.chain_median || 'no median-task chain for this dataset'],
                ['src', 'bayes', !!D.bay, 'house', miss.bayes || 'no Bayesian crossing tables for this dataset'],
                ['view', 'ridges', !!D.bay, 'scatter', miss.bayes || 'no posterior ridges for this dataset']];
  LIMITS.forEach(function (L) {
    if (L[2]) return;
    if (Kit.state.get(L[0], null) === L[1]) { Kit.state.set(L[0], null, null); dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + L[0] + '=' + L[1] + ' is not available under \u201c' + (DATASETS[D.dsId] || DATASETS[D.dataId]).label + '\u201d \u2014 ' + L[4] + '; showing ' + L[3]; }
  });
  relabel();
  var row = Kit.filterRow('#controls');
  row.classList.add('kit-static');
  var dataSw = Kit.switchControl({ mount: row, key: 'data', label: 'Dataset',
    options: Object.keys(DATASETS).map(function (k) { return { value: k, label: DATASETS[k].label }; }),
    dflt: D.defaultData || (D.allDs.board_top ? 'board_top' : 'board'),
    onchange: function (v) {
      var ds = DATASETS[v] || DATASETS[D.defaultData] || DATASETS.board;
      if (!ds.available) { if (dataSw) dataSw.set(D.dataId); return; }
      if (v !== D.dataId && DATASETS[v]) location.reload();
    } });
  if (dataSw.value() !== D.dataId) dataSw.set(D.dataId);
  Object.keys(DATASETS).forEach(function (k) { if (DATASETS[k].hover && DATASETS[k].available) { var hb = document.querySelector('.kit-switch[data-key="data"] button[data-value="' + k + '"]'); var fr = D.allDs[k] && D.allDs[k].frame; if (hb) hb.title = DATASETS[k].hover; } });
  var armsSw = Kit.switchControl({ mount: document.getElementById('armsbar') || row, key: 'arms', label: 'Models',
    options: [{ value: 'all', label: 'all models' }, { value: 'golden', label: 'golden set (12)' }],
    dflt: 'all',
    onchange: function (v) {
      if (v === 'golden' && !D.allDs['golden-' + D.dataId]) { if (armsSw) armsSw.set(state.arms); return; }
      if (v !== state.arms) location.reload();
    } });
  if (armsSw.value() !== state.arms) armsSw.set(state.arms);
  if (!D.allDs['golden-' + D.dataId]) { var gb = document.querySelector('.kit-switch[data-key="arms"] button[data-value="golden"]'); if (gb) { gb.disabled = true; gb.setAttribute('aria-disabled', 'true'); gb.title = 'golden set (12): no golden bundle for this dataset yet'; } }
  var partialSw = Kit.switchControl({ mount: document.getElementById('armsbar') || row, key: 'partial', label: 'Partial models',
    options: [{ value: 'hide', label: 'hidden' }, { value: 'show', label: 'show partial models' }],
    dflt: 'hide',
    onchange: function (v) { state.partial = v === 'show' ? 'show' : 'hide'; Kit.state.set('partial', state.partial, 'hide'); refreshPartialChips(); render(); } });
  if (!partialArms().length) { var psw = document.querySelector('.kit-switch[data-key="partial"]'); if (psw) psw.style.display = 'none'; }
  RUNS.forEach(function (R) {
    if (!R.idx.length) return;
    var runSw = Kit.switchControl({ mount: document.getElementById('armsbar') || row, key: R.stateKey, label: R.name,
      options: [{ value: 'show', label: 'shown' }, { value: 'hide', label: 'hidden' }], dflt: 'show',
      onchange: function (v) { state.runs[R.stateKey] = v === 'hide' ? 'hide' : 'show'; Kit.state.set(R.stateKey, state.runs[R.stateKey], 'show'); render(); frameLine(); } });
    if (runSw.value() !== state.runs[R.stateKey]) runSw.set(state.runs[R.stateKey]);
  });
  showDataNote();
  Object.keys(DATASETS).forEach(function (k) {
    if (DATASETS[k].available) return;
    var b = row.querySelector('.kit-switch[data-key="data"] button[data-value="' + k + '"]');
    if (b) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.title = DATASETS[k].label + ': ' + DATASETS[k].reason; }
  });
  Kit.switchControl({ mount: row, key: 'view', label: 'View',
    options: [{ value: 'scatter', label: 'Scatter' },
              { value: 'ridges', label: 'Posterior ridges' }],
    dflt: 'scatter',
    onchange: function (v) { state.view = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'def', label: 'Definition',
    options: [{ value: 'average', label: 'Average rate' },
              { value: 'median', label: 'Median task' }],
    dflt: 'average',
    onchange: function (v) {
      state.def = v;
      if (srcMount) buildSrcSwitch();
      if (sel) render();
    } });


  var CAPC_REASON = 'Capability C is computed for wave 1 only; choose Dataset = wave 1 to use it';
  var xdefSw = Kit.switchControl({ mount: row, key: 'xdef', label: 'Capability axis',
    options: [{ value: 'crossing', label: 'D50' },
              { value: 'capC', label: CAP_KEYS.capC.name() },
              { value: 'capC_z', label: CAP_KEYS.capC_z.name() },
              { value: 'capC_j', label: CAP_KEYS.capC_j.name() }],
    dflt: 'crossing',
    onchange: function (v) {
      if (CAP_KEYS[v] && !CAP_KEYS[v].block()) { if (xdefSw) xdefSw.set('crossing'); return; }
      state.xdef = v;
      syncXdefLock();
      if (sel) render();
    } });
  Object.keys(CAP_KEYS).forEach(function (k) {
    var capBtn = row.querySelector('.kit-switch[data-key="xdef"] button[data-value="' + k + '"]');
    if (CAP_KEYS[k].block()) { if (capBtn) capBtn.title = CAP_KEYS[k].clause(); return; }
    var why = k === 'capC' ? CAPC_REASON : 'this view (' + CAP_KEYS[k].clause() + ') is not part of this copy for this set';
    if (capBtn) { capBtn.disabled = true; capBtn.setAttribute('aria-disabled', 'true'); capBtn.title = why; }
    if (Kit.state.get('xdef', 'crossing') === k) {
      Kit.state.set('xdef', null, null); if (xdefSw) xdefSw.set('crossing');
      dataNote = (dataNote ? dataNote + ' \u00b7 ' : '') + CAP_KEYS[k].name() + ' is not computed for this set (' + why + '); showing the fitted 50% crossing';
    }
  });
  srcMount = document.createElement('span');
  row.appendChild(srcMount);
  buildSrcSwitch();

  LIMITS.forEach(function (L) {
    if (L[2]) return;
    var b = row.querySelector('.kit-switch[data-key="' + L[0] + '"] button[data-value="' + L[1] + '"]');
    if (b) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.title = L[4]; }
  });
  showDataNote();


  Kit.switchControl({ mount: row, key: 'kp', label: 'K paths',
    options: [{ value: 'off', label: 'Off' },
              { value: 'on', label: 'On' }],
    dflt: 'off',
    onchange: function (v) { state.kp = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'lad', label: 'K ladders',
    options: [{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }],
    dflt: 'off',
    onchange: function (v) { state.lad = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'w', label: 'Whiskers',
    options: [{ value: 'off', label: 'Off' },
              { value: 'on', label: 'On' }],
    dflt: 'on',
    onchange: function (v) { state.w = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'wd', label: 'Whisker widths',
    options: [{ value: 'adj', label: 'Correlation-adjusted' },
              { value: 'ind', label: 'Independence' }],
    dflt: 'adj',
    onchange: function (v) { state.wd = v; if (sel) render(); } });


  Kit.switchControl({ mount: row, key: 'fitci', label: 'Fit CI',
    options: [{ value: 'plain', label: '95%, dots exact' },
              { value: 'honest', label: '80% with measurement error' }],
    dflt: 'plain',
    onchange: function (v) { state.fitci = v; if (sel) render(); } });
  if (D.bayPrev) {

    Kit.switchControl({ mount: row, key: 'move', label: 'Move from ' + prevFitName(),
      options: [{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }],
      dflt: 'off',
      onchange: function (v) { state.move = v; if (sel) render(); } });
  }


  if (Kit.state.get('space', null) === 'uniform') { Kit.state.set('xs', 'raw', 'logit'); Kit.state.set('ys', 'raw', 'logit'); Kit.state.set('space', null, null); }
  ['xs', 'ys'].forEach(function (k) { var v0 = Kit.state.get(k, null); if (v0 !== null && v0 !== 'raw' && v0 !== 'logit') Kit.state.set(k, null, null); });
  var lv0 = Kit.state.get('line', null); if (lv0 !== null && lv0 !== 'off' && lv0 !== 'steps' && lv0 !== 'axes') Kit.state.set('line', null, null);
  var lw0 = Kit.state.get('lw', null); if (lw0 !== null && lw0 !== 'equal' && lw0 !== 'bands') Kit.state.set('lw', null, null);
  var rs0 = Kit.state.get('resid', null); if (rs0 !== null && rs0 !== 'off' && rs0 !== 'on') Kit.state.set('resid', null, null);
  else if (Kit.state.get('space', null) !== null) Kit.state.set('space', null, null);
  var sb = document.getElementById('spacebar'), moreDet = document.getElementById('morecontrols');
  if (!moreDet && sb) {
    moreDet = document.createElement('details'); moreDet.id = 'morecontrols'; moreDet.className = 'about';
    moreDet.innerHTML = '<summary>More controls</summary><div class="kit-filter-row kit-static" id="moreswitches"></div><div class="kit-filter-row kit-static" id="morelevels"></div>';
    sb.parentNode.insertBefore(moreDet, sb); moreDet.appendChild(sb);
  }
  [['xs', 'Horizontal scale'], ['ys', 'Vertical scale']].forEach(function (ax) {
    Kit.switchControl({ mount: sb,
      key: ax[0], label: ax[1],
      options: [{ value: 'logit', label: 'Logit' },
                { value: 'raw', label: 'Linear' }],
      dflt: 'logit',
      onchange: function (v) {
        state[ax[0]] = v === 'raw' ? 'raw' : 'logit';
        if (sel) render();
      } });
  });
  state.xs = Kit.state.get('xs', 'logit') === 'raw' ? 'raw' : 'logit'; state.ys = Kit.state.get('ys', 'logit') === 'raw' ? 'raw' : 'logit';


  Kit.switchControl({ mount: sb, key: 'line', label: 'Fitted line',
    options: [{ value: 'off', label: 'Off' }, { value: 'steps', label: 'In logit' }, { value: 'axes', label: 'In the axes as set' }],
    dflt: 'steps',
    onchange: function (v) { state.line = (v === 'off' || v === 'axes') ? v : 'steps'; if (sel) render(); } });
  var lv = Kit.state.get('line', 'steps'); state.line = (lv === 'off' || lv === 'axes') ? lv : 'steps';


  Kit.switchControl({ mount: sb, key: 'lw', label: 'Line weighting',
    options: [{ value: 'equal', label: 'Each dot equal' }, { value: 'bands', label: 'By the 80% bands' }],
    dflt: 'equal',
    onchange: function (v) { state.lw = v === 'bands' ? 'bands' : 'equal'; if (sel) render(); } });
  state.lw = Kit.state.get('lw', 'equal') === 'bands' ? 'bands' : 'equal';


  Kit.switchControl({ mount: sb, key: 'resid', label: 'Misses against the line',
    options: [{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }],
    dflt: 'off',
    onchange: function (v) { state.resid = v === 'on' ? 'on' : 'off'; if (sel) render(); } });
  state.resid = Kit.state.get('resid', 'off') === 'on' ? 'on' : 'off';
  var mvSw = document.querySelector('#chartcontrols .kit-switch[data-key="move"]'); if (mvSw) sb.appendChild(mvSw);


  var sn = document.createElement('p'); sn.id = 'spacenote'; sn.style.cssText = 'font-size:.85rem;color:#52514e;margin:.4rem 0 0;max-width:80ch';

  sn.textContent = 'Straight scale by definition: ' + CAP_KEYS.capC_z.name() + ' \u2014 linear; ' + CAP_KEYS.capC.name() + ', ' + CAP_KEYS.capC_j.name() + ' and ' + dName('x') + ' \u2014 logit.';
  sb.appendChild(sn);

  buildLevels();
  state.xdef = Kit.state.get('xdef', 'crossing');
  state.move = Kit.state.get('move', 'off') === 'on' ? 'on' : 'off';
  state.partial = Kit.state.get('partial', 'hide') === 'show' ? 'show' : 'hide';
  state.runs = state.runs || {};


  state.src = (function () { var v = Kit.state.get('src', bayesDefault() ? 'bayes' : 'house'); return v === 'bayes' && D.bay ? 'bayes' : 'house'; })();
  buildChips(); refreshPartialChips();
  hoverWire();
  wireDrag();
  render();
}

var srcCtl = null;


function bayesDefault() { return !!(D.bay && D.shared && D.bay.rows.length * 2 >= D.shared.configs.length); }
function buildSrcSwitch() {
  srcMount.textContent = '';
  srcCtl = Kit.switchControl({ mount: srcMount, key: 'src',
    label: 'Crossing estimator',
    options: [{ value: 'house', label: houseName() },
              { value: 'bayes', label: 'Bayesian (posterior)' }],
    dflt: bayesDefault() ? 'bayes' : 'house',
    onchange: function (v) {
      var was = state.src;
      state.src = v;
      if (sel && v !== was) { render(); frameLine(); }
    } });
}


function syncMissingChains() {
  if (!D || !D.shared) return;
  var miss = (D.ds && D.ds.missing) || {};
  [['src', 'bayes', !!D.bay, miss.bayes || 'no Bayesian crossing tables for this dataset'],
   ['view', 'ridges', !!D.bay, miss.bayes || 'no posterior ridges for this dataset'],
   ['def', 'median', !!D.med, miss.chain_median || 'no median-task chain for this dataset']].forEach(function (L) {
    var b = document.querySelector('.kit-switch[data-key="' + L[0] + '"] button[data-value="' + L[1] + '"]'); if (!b) return;
    if (L[2]) { if (b.dataset.missTitle) { b.disabled = false; b.removeAttribute('aria-disabled'); b.title = ''; delete b.dataset.missTitle; } }
    else { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.title = L[3]; b.dataset.missTitle = '1'; }
  });
}


var rafId = 0;
function scheduleRender() {
  if (rafId) return;
  rafId = requestAnimationFrame(function () { rafId = 0; render(); });
}


var elA, elC, playBtn, holdSw = null;
function buildLevels() {
  var box = document.getElementById('levels');
  function num(label, key, val, onset) {
    var lab = document.createElement('label');
    lab.innerHTML = '<b>' + label + '</b> ';
    var inp = document.createElement('input');
    inp.type = 'number'; inp.min = '0.1'; inp.max = '99.5';
    inp.step = 'any'; inp.value = val;
    inp.addEventListener('change', function () {
      var raw = inp.value, n = parseFloat(raw), prevA = state.a, prevC = state.c, prev = state[key];
      var name = key === 'a' ? 'x' : 'y';
      if (raw === '' || !isFinite(n)) {
        inputNote = (raw === '' ? 'typed ' + name + ' is empty or not a number' : 'typed ' + name + ' \u201c' + raw + '\u201d is not a level') + '; ' + name + ' kept at ' + prev + '%';
        inp.value = prev; render(); return;
      }
      var v = Math.max(0.1, Math.min(99.5, n));
      inputNote = v !== n ? 'typed ' + name + ' ' + n + '% is outside the 0.1\u201399.5% grid; set to ' + v + '%' : null;
      onset(v);
      var got = state[key];
      if (got !== r2(v)) inputNote = (inputNote ? inputNote + ' \u00b7 ' : '') + 'typed ' + name + ' ' + v + '% became ' + got + '%';
      var other = key === 'a' ? 'y' : 'x', otherPrev = key === 'a' ? prevC : prevA, otherNow = key === 'a' ? state.c : state.a;
      if (otherNow !== otherPrev) inputNote = (inputNote ? inputNote + ' \u00b7 ' : '') + other + ' ' + (otherNow > otherPrev ? 'raised' : 'lowered') + ' to ' + otherNow + '%';
      render();
    });
    lab.appendChild(inp);
    lab.appendChild(document.createTextNode(' %'));
    box.appendChild(lab);
    return inp;
  }
  elA = num('Horizontal level (failure rate)', 'a', state.a, function (v) {
    applyLevel('a', v);
    Kit.state.set('a', String(state.a), '50');
    Kit.state.set('c', String(state.c), '1'); render();
  });
  elC = num('Vertical level (failure rate)', 'c', state.c, function (v) {
    applyLevel('c', v);
    Kit.state.set('a', String(state.a), '50');
    Kit.state.set('c', String(state.c), '1'); render();
  });
  [[50, 1], [50, 5], [20, 1], [50, 20]].forEach(function (p) {
    var b = document.createElement('button');
    b.className = 'preset'; b.dataset.a = String(p[0]); b.dataset.c = String(p[1]);
    b.textContent = 'D' + fmtLev(100 - p[0]) + ' / D' + fmtLev(100 - p[1]);
    b.title = 'level pair preset: x ' + p[0] + '%, y ' + p[1] + '%';
    b.onclick = function () { setLevels(p[0], p[1]); };
    box.appendChild(b);
  });
  syncPresets();
  playBtn = document.createElement('button');
  playBtn.id = 'playBtn';
  playBtn.textContent = playLabel();
  playBtn.onclick = togglePlay;
  box.appendChild(playBtn);
  var kOut = document.createElement('span');
  kOut.id = 'kOut';
  box.appendChild(kOut);
  var kBound = document.createElement('span');
  kBound.id = 'kBound';
  box.appendChild(kBound);

  var holdMount = document.createElement('span');
  holdMount.id = 'holdMount';
  box.appendChild(holdMount);
  state.hold = 'c'; holdSw = null; Kit.state.set('hold', null, null);
  var kl = document.createElement('label');
  kl.innerHTML = '<b>fold K</b> ';
  var ks = document.createElement('input');
  ks.type = 'range'; ks.id = 'kSlider'; ks.min = String(-Math.ceil(Math.log2(K_MAX) * 100) / 100);
  ks.max = String(Math.ceil(Math.log2(K_MAX) * 100) / 100); ks.step = '0.01';
  ks.value = String(Math.log2(state.a / state.c));
  ks.setAttribute('aria-label', 'fold K, log2 scale');
  ks.style.width = '9rem';
  ks.addEventListener('input', function () {
    setK(Math.pow(2, +ks.value)); scheduleRender();
  });
  ks.addEventListener('change', function () {
    Kit.state.set('a', String(state.a), '50');
    Kit.state.set('c', String(state.c), '1'); render();
  });
  kl.appendChild(ks);
  box.appendChild(kl);
  K_CHIPS.forEach(function (kk) {
    var b = document.createElement('button');
    b.className = 'preset kchip';
    b.textContent = kk + '\u00d7';
    b.title = 'set the fold K = ' + kk;
    b.onclick = function () {
      setK(kk);
      Kit.state.set('a', String(state.a), '50');
      Kit.state.set('c', String(state.c), '1'); render();
    };
    box.appendChild(b);
  });
}
function clampLev(v) { return Math.max(0.2, Math.min(99.5, v)); }
function r2(v) { return Math.round(v * 100) / 100; }


var lastMoved = null, lockNote = null, inputNote = null, undrawn = [];
var beyondFrame = 0, beyondArms = [];
function refreshBeyondChips() {
  var B = {}; beyondArms.forEach(function (i) { B[i] = true; });
  chips.forEach(function (b) { var i = +b.dataset.idx; if (B[i]) { b.classList.add('beyond'); b.dataset.beyondTitle = '1'; b.title = 'not drawn: its crossing lies beyond the hardest task at these levels'; } else if (b.dataset.beyondTitle) { b.classList.remove('beyond'); delete b.dataset.beyondTitle; b.title = ''; refreshPartialChips(); } });
}
var partialShownN = 0;
function playLabel() {
  return '\u25b6 sweep x (y stays)';
}


function fitTitle(text, maxUnits, fontSize) {
  var perChar = fontSize * 0.55, full = text;
  if (text.length * perChar > maxUnits) text = text.replace(/\s*\([^)]*\)/g, '');
  if (text.length * perChar > maxUnits) text = text.slice(0, Math.max(8, Math.floor(maxUnits / perChar) - 1)) + '\u2026';
  return text === full ? text : text + '</text><title>' + full.replace(/</g, '&lt;') + '</title><text style="display:none">';
}
function applyLevel(key, v, K0) {
  lastMoved = key; if (key === 'a') lockNote = null;
  if (dragActive) inputNote = null;
  v = clampLev(v);
  var K = K0 || (state.a / state.c);


  if (key === 'a') state.a = v; else state.c = v;
  state.a = r2(state.a); state.c = r2(state.c);
  elA.value = state.a; elC.value = state.c;
}


function setK(K) {
  K = Math.max(1 / K_MAX, Math.min(K_MAX, K));
  state.a = r2(clampLev(K * state.c));
  elA.value = state.a; elC.value = state.c;
  var ks = document.getElementById('kSlider');
  if (ks) ks.value = Math.log2(state.a / state.c);
}


function heldRing(key, x, ink) {
  return '<circle class="heldring" data-ring="' + key + '" pointer-events="none" cx="' + x + '" cy="' + TRK.y
    + '" r="9" fill="none" stroke="' + ink + '" stroke-width="1" stroke-dasharray="2 2"><title>' + HELD_TIP + '</title></circle>';
}
function held(key) {
  return false;
}
var HELD_TIP = 'held fixed against the other controls (other handle, fold K, play); drag or type it to move it directly — at the 1x/50x K bound the other level follows';
function syncHoldUI() {
  if (!elA) return;
  if (playBtn && !playTimer) playBtn.textContent = playLabel();
  elA.disabled = isCap();
  elC.disabled = false;
  elA.parentElement.title = isCap() ? 'no horizontal level: the Capability view is level-free' : held('a') ? HELD_TIP : '';
  elC.parentElement.title = held('c') ? HELD_TIP : '';
  var ks = document.getElementById('kSlider');
  if (ks && !dragKey) ks.value = Math.log2(state.a / state.c);
}
function setLevels(a, c) {
  lastMoved = null; lockNote = null; inputNote = null;
  state.a = a; state.c = c;
  elA.value = a; elC.value = c;
  Kit.state.set('a', String(a), '50');
  Kit.state.set('c', String(c), '1');
  render();
}
function togglePlay() {
  if (playTimer) {
    clearInterval(playTimer); playTimer = null;
    playBtn.textContent = playLabel();
    Kit.state.set('a', String(state.a), '50');
    Kit.state.set('c', String(state.c), '1');
    render();
    return;
  }


  var K = state.a / state.c, dir = 1;
  var lo = Math.max(0.2, pct(D.shared.reachable.floor_z));
  playBtn.textContent = 'stop the sweep';
  if (state.hold === 'a') {
    var lk = 0;
    playTimer = setInterval(function () {
      lk += dir * 0.06;
      if (lk >= Math.log2(K_LADDER_MAX)) { dir = -1; lk = Math.log2(K_LADDER_MAX); }
      if (lk <= 0) { dir = 1; lk = 0; }
      setK(Math.pow(2, lk));
      scheduleRender();
    }, 140);
    return;
  }
  if (state.hold === 'c') {
    var aLo = logit(0.2 / 100), aHi = logit(99.5 / 100);
    playTimer = setInterval(function () {
      var cur = logit(state.a / 100), next = cur + dir * 0.12;
      if (next >= aHi) { dir = -1; next = cur; }
      if (next <= aLo) { dir = 1; next = cur; }
      state.a = r2(pct(next)); elA.value = state.a;
      scheduleRender();
    }, 140);
    return;
  }
  var hi = Math.min(99.5 / K, 99.5);
  playTimer = setInterval(function () {
    var cur = logit(state.c / 100), next = cur + dir * 0.12;
    if (next >= logit(hi / 100)) { dir = -1; next = cur; }
    if (next <= logit(lo / 100)) { dir = 1; next = cur; }
    var c = r2(pct(next)), a = r2(Math.min(99.5, K * c));
    if (a < 0.1 || c < 0.1) return;
    state.c = c; state.a = a;
    elC.value = c; elA.value = a;
    scheduleRender();
  }, 140);
}


function syncXdefLock() {
  var on = isCap();
  var reason = 'the Capability view is level-free — the horizontal level, K paths and '
    + 'the K sweep apply to crossing definitions only';
  if (elA) {
    elA.disabled = on;
    elA.parentElement.style.opacity = on ? .45 : 1;
    elA.parentElement.title = on ? reason : '';
  }
  document.querySelectorAll('#levels .preset').forEach(function (b) {
    b.disabled = on; b.style.opacity = on ? .45 : 1;
    b.title = on ? reason : '';
  });
  if (playBtn) {
    playBtn.disabled = on; playBtn.style.opacity = on ? .45 : 1;
    playBtn.title = on ? reason : '';
  }
  ['kp', 'lad', 'hold'].forEach(function (key) {
    var sw = document.querySelector('.kit-switch[data-key="' + key + '"]');
    if (!sw) return;
    sw.classList.toggle('inert', on);
    sw.title = on ? reason : '';
    sw.querySelectorAll('button').forEach(function (b) { b.disabled = on; });
  });
  var ks2 = document.getElementById('kSlider');
  if (ks2) { ks2.disabled = on; ks2.parentElement.style.opacity = on ? .45 : 1; }
  syncHoldUI();
}
function syncWdLock() {
  var sw = document.querySelector('.kit-switch[data-key="wd"]');
  if (!sw) return;
  var inert = state.src === 'bayes' || state.def === 'median';
  sw.classList.toggle('inert', inert);
  sw.style.display = inert ? 'none' : '';
  sw.title = !inert ? ''
    : state.src === 'bayes'
      ? 'widths apply to the average-rate frequentist whiskers only '
        + '— whiskers: the 80% band of the fit\u2019s uncertainty (finite attempts and the spread across tasks)'
      : 'widths apply to the average-rate chain only — median-task '
        + 'whiskers are bootstrap band quantiles';
  sw.querySelectorAll('button').forEach(function (b) {
    b.disabled = inert;
  });
}


function writeSel() {
  var all = sel.size === D.shared.configs.length;
  Kit.state.set('sel', all ? null : Array.from(sel).sort(function (p, q) { return p - q; }).map(function (i) { var c = D.shared.configs[i]; return c.board_id || c.id; }).join(','), null);
}


function capKey(i) {
  if (isRun(i) && (state.src !== 'bayes' || !D.bayById || !D.bayById[D.shared.configs[i].id])) return -1e9;
  if (state.view === 'ridges' && D.bay) {
    var rr = D.bayById[D.shared.configs[i].id]; if (!rr) return Infinity;
    var cz = ridgeCentre(rr, state.a / 100); return cz == null || !isFinite(cz) ? Infinity : cz;
  }
  var rx = reading(i, logit(state.a / 100), 'x');
  if (!rx) return Infinity;
  if (rx.kind === 'point') return rx.z;
  if (rx.kind === 'lo-bound') return (LIM ? LIM[0] : -50) - 1;
  if (rx.kind === 'hi-bound') return (LIM ? LIM[1] : 50) + 1;
  return Infinity;
}
function capOrder(indices) {
  return indices.slice().sort(function (a, b) {
    var ka = capKey(a), kb = capKey(b); ka = isFinite(ka) ? ka : 1e9; kb = isFinite(kb) ? kb : 1e9;
    if (ka !== kb) return ka - kb;
    return D.shared.configs[a].label < D.shared.configs[b].label ? -1 : 1;
  });
}
function famOrder(indices) {
  if (window.Kit && Kit.legendByFamily) {
    var rows = indices.map(function (i) { var c = D.shared.configs[i]; return { i: i, label: c.label, family: c.fam }; });
    return Kit.legendByFamily(rows).map(function (r) { return r.i; });
  }
  return indices.slice().sort(function (a, b) { return a - b; });
}
function buildChips() {
  var box = document.getElementById('chips');
  var fams = [];
  D.shared.configs.forEach(function (c, i) {
    var f = fams.find(function (x) { return x.name === c.fam; });
    if (!f) { f = { name: c.fam, members: [] }; fams.push(f); }
    f.members.push(i);
  });
  var allBtn = document.createElement('button');
  allBtn.className = 'util'; allBtn.textContent = 'all';
  allBtn.onclick = function () {
    D.shared.configs.forEach(function (_, i) { if (!isHidden(i) && !isRun(i)) sel.add(i); });
    writeSel(); render();
  };
  var noneBtn = document.createElement('button');
  noneBtn.className = 'util'; noneBtn.textContent = 'none';
  noneBtn.onclick = function () { D.shared.configs.forEach(function (c, i) { if (!c.run) sel.delete(i); }); writeSel(); render(); };
  box.appendChild(allBtn); box.appendChild(noneBtn);


  var mainIdx = [], runIdx = [];
  D.shared.configs.forEach(function (c, i) { (c.run ? runIdx : mainIdx).push(i); });
  var ordered = capOrder(mainIdx);
  var famKey = function (f) { return Math.max.apply(null, f.members.map(function (i) { var k = capKey(i); return isFinite(k) ? k : -1e9; })); };
  var isRunFam = function (f) { return f.members.length && isRun(f.members[0]); };
  fams.filter(function (f) { return !isRunFam(f); }).sort(function (p, q) { return famKey(p) - famKey(q); }).forEach(function (f) {
    var nm = document.createElement('button');
    nm.className = 'fam'; nm.style.color = D.shared.configs[f.members[0]].color; nm.textContent = f.name; nm.title = 'select or clear every ' + f.name + ' model';
    nm.onclick = function () {
      var anyOff = f.members.some(function (i) { return !sel.has(i) && (!isHidden(i)); });
      f.members.forEach(function (i) { if (anyOff) { if (!isHidden(i)) sel.add(i); } else sel.delete(i); });
      writeSel(); render();
    };
    box.appendChild(nm);
  });
  var makeChip = function (i) {
    var c = D.shared.configs[i], b = document.createElement('button');
    b.className = 'chip'; if (c.think) { b.classList.add('think'); b.title = 'thinking mode \u2014 open marker on the chart'; }
    if (isPartial(i) || isWithheld(i)) b.classList.add('partial');
    if (c.run) { var Rc = runOf(i) || RUN; b.classList.add('run'); b.title = (c.display_name || Rc.name + ' \u2014 ' + c.label) + ': ' + Rc.clause; }
    if (c.alongside) { b.title = (b.title ? b.title + ' \u00b7 ' : '') + 'positioned on the served axis, not shaping it \u2014 its fit from the ' + c.alongside + ' series, read alongside the board fit set'; }
    if (c.gates_failed) { b.classList.add('flagged'); var fg = document.createElement('span'); fg.className = 'flag'; fg.textContent = '\u2691'; fg.setAttribute('aria-label', 'flagged fit'); b.title = (b.title ? b.title + ' \u00b7 ' : '') + 'flagged fit: ' + (c.gate_flag || 'the fit failed a sampler gate'); b.appendChild(fg); }
    b.style.color = c.color; b.style.borderColor = c.color;
    b.insertBefore(document.createTextNode(c.label), b.firstChild); b.dataset.idx = i;
    b.onclick = function () { if (sel.has(i)) sel.delete(i); else sel.add(i); writeSel(); render(); };
    chips.push(b); return b;
  };
  ordered.forEach(function (i) { box.appendChild(makeChip(i)); });


  var rbox = document.getElementById('chips-runs');
  if (rbox) {
    rbox.innerHTML = '';
    RUNS.forEach(function (R) {
      if (!R.idx.length && !R.withheld.length) return;
      var line = document.createElement('div'); line.className = 'chips chips-run'; line.id = 'chips-run-' + R.key.replace(/[^a-z0-9]/gi, '-'); line.dataset.run = R.key; line.dataset.stateKey = R.stateKey;
      var lab = document.createElement('span'); lab.className = 'runlabel'; lab.style.color = R.hue || (R.idx.length ? D.shared.configs[R.idx[0]].color : '#52514e'); lab.textContent = R.name; lab.title = R.clause; line.appendChild(lab);
      if (R.idx.length) {
        var rAll = document.createElement('button'); rAll.className = 'util'; rAll.textContent = 'all'; rAll.onclick = function () { R.idx.forEach(function (i) { sel.add(i); }); writeSel(); render(); }; line.appendChild(rAll);
        var rNone = document.createElement('button'); rNone.className = 'util'; rNone.textContent = 'none'; rNone.onclick = function () { R.idx.forEach(function (i) { sel.delete(i); }); writeSel(); render(); }; line.appendChild(rNone);
        R.idx.forEach(function (i) { line.appendChild(makeChip(i)); });
      }
      if (R.withheld.length) {
        var note = document.createElement('span'); note.className = 'runnote'; note.setAttribute('data-critical-text', '');
        note.textContent = 'Not shown: ' + R.withheld.map(function (w) { return (w.display_name || w.label || w.id) + ' \u2014 ' + w.reason; }).join('; ') + '.';
        line.appendChild(note);
      }
      line.hidden = !runOnPlane(R);
      rbox.appendChild(line);
    });
  }
}
function foldSweepTools() {


  var lv = document.getElementById('levels'); if (!lv || !playBtn || !playBtn.parentNode) return;
  var det = document.getElementById('sweeptools');
  if (!det) {
    det = document.createElement('details'); det.id = 'sweeptools'; det.className = 'about';
    det.innerHTML = '<summary id="sweepsum"></summary>';
    var rowEl = document.createElement('div'); rowEl.className = 'kit-filter-row kit-static'; rowEl.id = 'sweeprow'; det.appendChild(rowEl);
    var hm = document.getElementById('holdMount'); if (hm) rowEl.appendChild(hm);
    lv.querySelectorAll('.preset.kchip').forEach(function (b) { rowEl.appendChild(b); });
    rowEl.appendChild(playBtn);
    var kb = document.getElementById('kBound'); if (kb) rowEl.appendChild(kb);
    lv.appendChild(det);
  }
  var rowEl2 = document.getElementById('sweeprow');
  var hm2 = document.getElementById('holdMount'); if (hm2 && hm2.parentNode !== rowEl2) rowEl2.appendChild(hm2);
  var ksl2 = document.getElementById('kSlider'), kll = ksl2 && ksl2.closest('label');
  if (kll) { if (det.parentNode === lv) { if (kll.nextSibling !== det) lv.insertBefore(kll, det); } else if (kll.parentNode !== lv) lv.appendChild(kll); }
  lv.querySelectorAll(':scope > .preset.kchip').forEach(function (b) { rowEl2.appendChild(b); });
  if (playBtn.parentNode !== rowEl2) rowEl2.appendChild(playBtn);
  var kb2 = document.getElementById('kBound'); if (kb2 && kb2.parentNode !== rowEl2) rowEl2.appendChild(kb2);
  var on = document.querySelector('.kit-switch[data-key="hold"] button[aria-pressed="true"]');
  var sum = document.getElementById('sweepsum'), txt = 'Sweep and hold · held fixed: ' + (on ? on.textContent.trim() : ({ k: 'K', a: 'horizontal level', c: 'vertical level' })[state.hold] || state.hold);
  if (sum && sum.textContent !== txt) sum.textContent = txt;
}

var phoneFolded = false;
function phoneFold() {


  if (!(window.matchMedia && window.matchMedia('(max-width:600px)').matches)) return;
  var cc = document.getElementById('chartcontrols'); if (!cc) return;
  var more = document.getElementById('morecontrols');
  if (!more) {
    var SHORT = { data: shortMap(), xdef: { crossing: 'D50', capC: CAP_KEYS.capC.short, capC_z: CAP_KEYS.capC_z.short, capC_j: CAP_KEYS.capC_j.short }, xs: { logit: 'logit', raw: 'linear' }, ys: { logit: 'logit', raw: 'linear' }, line: { off: 'Off', steps: 'logit', axes: 'axes as set' }, lw: { equal: 'each dot equal', bands: 'by the 80% bands' }, resid: { off: 'Off', on: 'On' }, src: { house: 'local-logistic', bayes: 'Bayesian' }, def: { average: 'average', median: 'median task' } };
    Object.keys(SHORT).forEach(function (k) { document.querySelectorAll('.kit-switch[data-key="' + k + '"] button').forEach(function (b) { if (SHORT[k][b.dataset.value]) b.textContent = SHORT[k][b.dataset.value]; }); });
    more = document.createElement('details'); more.id = 'morecontrols'; more.className = 'about'; more.innerHTML = '<summary>More controls</summary>';
    var moreRow = document.createElement('div'); moreRow.className = 'kit-filter-row kit-static'; moreRow.id = 'moreswitches'; more.appendChild(moreRow);
    var lvRow = document.createElement('div'); lvRow.className = 'kit-filter-row kit-static'; lvRow.id = 'morelevels'; more.appendChild(lvRow);
    cc.appendChild(more);
  }
  var msw = document.getElementById('moreswitches'), mlv = document.getElementById('morelevels');
  ['view', 'kp', 'lad', 'w', 'wd', 'fitci', 'move'].forEach(function (k) { var sw = document.querySelector('#chartcontrols .kit-switch[data-key="' + k + '"]'); if (sw && sw.parentNode !== msw) msw.appendChild(sw); });
  var lv = document.getElementById('levels');
  if (lv) {
    lv.querySelectorAll('.preset:not(.kchip)').forEach(function (b) { if (b.parentNode !== mlv) mlv.appendChild(b); });
    var st = document.getElementById('sweeptools'); if (st && st.parentNode !== more) more.appendChild(st);
  }
  phoneFolded = true;
}

function paintChips() {
  RUNS.forEach(function (R) { var rsw = document.querySelector('.kit-switch[data-key="' + R.stateKey + '"]'); if (rsw) rsw.style.display = state.src === 'bayes' ? '' : 'none'; });
  var box = document.getElementById('chips'), byIdx = {}; chips.forEach(function (b) { byIdx[+b.dataset.idx] = b; });
  var idxs = chips.map(function (b) { return +b.dataset.idx; });
  capOrder(idxs.filter(function (i) { return !isRun(i); })).forEach(function (i) { if (byIdx[i] && byIdx[i].parentNode === box) box.appendChild(byIdx[i]); });
  RUNS.forEach(function (R) { var line = document.querySelector('.chips-run[data-run="' + R.key + '"]'); if (line) line.hidden = !runOnPlane(R); });
  var recompose = false;
  chips.forEach(function (b) {
    b.classList.toggle('off', !sel.has(+b.dataset.idx));
    b.setAttribute('aria-pressed', sel.has(+b.dataset.idx) ? 'true' : 'false');
    var cfgId = D.shared.configs[+b.dataset.idx] && D.shared.configs[+b.dataset.idx].id;
    var nofit = (state.src === 'bayes' && !!D.bay && !D.bayById[cfgId]) || (isRun(+b.dataset.idx) && state.src !== 'bayes');
    b.classList.toggle('nofit', nofit);
    var cfgC = D.shared.configs[+b.dataset.idx] || {};
    if (nofit) { b.title = (isRun(+b.dataset.idx) && state.src !== 'bayes' ? 'awaiting its Bayesian fit' : 'awaiting its Bayesian fit \u2014 not drawn under the Bayesian estimator') + (cfgC.gates_failed ? ' \u00b7 flagged fit: ' + (cfgC.gate_flag || 'the fit failed a sampler gate') : ''); b.dataset.nofit = '1'; }
    else if (b.dataset.nofit) { b.title = ''; delete b.dataset.nofit; recompose = true; }
  });
  if (recompose) refreshPartialChips();
}


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
  for (i = 0; i < n; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) * (xs[i] - mx);
    syy += (ys[i] - my) * (ys[i] - my);
  }
  if (sxx < 1e-9 || syy < 1e-9) return null;
  var b = sxy / sxx, a = my - b * mx, rss = 0;
  for (i = 0; i < n; i++) { var e = ys[i] - a - b * xs[i]; rss += e * e; }
  return { b: b, a: a, r: sxy / Math.sqrt(sxx * syy), s: Math.sqrt(rss / Math.max(1, n - 2)) };
}
var fitCache = {};


function yorkFit(xs, ys, sig, level, mg) {
  var n = xs.length; if (n < 3 || !sig) return null;
  var base = fitLine(xs, ys); if (!base) return null;
  var wx = [], wy = [], i;
  for (i = 0; i < n; i++) { var s0 = Math.max(sig[i][0], 1e-6), s1 = Math.max(sig[i][1], 1e-6); wx.push(1 / (s0 * s0)); wy.push(1 / (s1 * s1)); }
  var b = base.b, W = new Array(n), U = new Array(n), V = new Array(n), beta = new Array(n), Xb = 0, Yb = 0, it;
  for (it = 0; it < 100; it++) {
    var sw = 0; Xb = 0; Yb = 0;
    for (i = 0; i < n; i++) { W[i] = wx[i] * wy[i] / (wx[i] + b * b * wy[i]); sw += W[i]; Xb += W[i] * xs[i]; Yb += W[i] * ys[i]; }
    Xb /= sw; Yb /= sw;
    var num = 0, den = 0;
    for (i = 0; i < n; i++) { U[i] = xs[i] - Xb; V[i] = ys[i] - Yb; beta[i] = W[i] * (U[i] / wy[i] + b * V[i] / wx[i]); num += W[i] * beta[i] * V[i]; den += W[i] * beta[i] * U[i]; }
    if (!(Math.abs(den) > 0)) return null;
    var bn = num / den; if (!isFinite(bn)) return null;
    var done = Math.abs(bn - b) < 1e-10; b = bn; if (done) break;
  }
  var a = Yb - b * Xb, sw2 = 0, xa = 0, xadj = new Array(n);
  for (i = 0; i < n; i++) { W[i] = wx[i] * wy[i] / (wx[i] + b * b * wy[i]); sw2 += W[i]; xadj[i] = Xb + beta[i]; xa += W[i] * xadj[i]; }
  xa /= sw2;
  var su = 0; for (i = 0; i < n; i++) { var u = xadj[i] - xa; su += W[i] * u * u; }
  if (!(su > 0)) return null;
  var vb = 1 / su, va = 1 / sw2 + xa * xa * vb, cab = -xa * vb, z = level === 80 ? 1.2816 : 1.96, rss = 0, chi = 0;
  for (i = 0; i < n; i++) { var e = ys[i] - a - b * xs[i]; rss += e * e; chi += W[i] * e * e; }


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
function bootFit(xs, ys, key, sig, mg) {
  if (key && fitCache[key]) return fitCache[key];
  var base = fitLine(xs, ys);
  if (!base) return null;
  var honest = !!sig;
  var rnd = mulberry32(20260828), slopes = [], lines = [];
  for (var b = 0; b < 200; b++) {
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
  var q = function (arr, p) {
    return arr[Math.max(0, Math.min(arr.length - 1,
      Math.round(p * (arr.length - 1))))];
  };
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
    var vals = lines.map(function (l) { return l[0] * gx + l[1]; })
      .sort(function (u, v) { return u - v; });
    base.band.xs.push(gx);
    base.band.up.push(q(vals, ph)); base.band.dn.push(q(vals, pl));
  }
  if (key) {
    var ks = Object.keys(fitCache);
    if (ks.length > 400) delete fitCache[ks[0]];
    fitCache[key] = base;
  }
  return base;
}


function syncPresets() {
  document.querySelectorAll('#levels .preset:not(.kchip), #morelevels .preset:not(.kchip)').forEach(function (b) {
    var on = b.dataset.a !== undefined && +b.dataset.a === +state.a && +b.dataset.c === +state.c;
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}
var heldTimer = null;
function render() {
  syncPresets(); syncMissingChains();
  if (!elA || !sel) return;
  mountExport();
  syncWdLock();
  syncXdefLock();
  if (state.view === 'ridges') { renderRidges(); renderOpusFold(); return; }
  renderScatter(); renderOpusFold();
}

function axisGrid(xOnly, hOverride) {
  var g = '';
  var plotBot = (hOverride ? hOverride - MB : MT + PH);
  var LT = EXPORTING ? LOGIT_TICKS_EXPORT : LOGIT_TICKS;
  var xt = state.xs === 'raw' ? RAW_TICKS : LT;
  var yt2 = xOnly ? []
    : (state.ys === 'raw' ? RAW_TICKS : LT);
  if (NARROW) {
    var keepL = [1, 5, 20, 50, 80, 95, 99];
    xt = xt.filter(function (v) { return state.xs === 'raw' ? (v % 20 === 0 && v > 0) : keepL.indexOf(v) >= 0; });
    yt2 = yt2.filter(function (v) { return state.ys === 'raw' ? v % 20 === 0 : keepL.indexOf(v) >= 0; });
  }
  var zOf = function (v) {
    return logit(Math.min(0.9999, Math.max(0.0001, v / 100)));
  };
  xt.forEach(function (v) {
    var z = zOf(v), L = limT(state.xs === 'raw', 'x');
    if (tf(z, state.xs === 'raw') <= L[0]
        || tf(z, state.xs === 'raw') >= L[1]) return;
    g += '<line x1="' + sx(z) + '" y1="' + MT + '" x2="' + sx(z)
      + '" y2="' + plotBot + '" stroke="#e0d9c8" stroke-width="0.6"/>'
      + '<text x="' + sx(z) + '" y="' + (plotBot + FS + 5)
      + '" text-anchor="middle" fill="#52514e" font-size="' + FS + '" data-role="tick">'
      + v + '%</text>';
  });
  yt2.forEach(function (v) {
    var z = zOf(v), L = limT(state.ys === 'raw', 'y');
    if (tf(z, state.ys === 'raw') <= L[0]
        || tf(z, state.ys === 'raw') >= L[1]) return;
    g += '<line x1="' + ML + '" y1="' + sy(z) + '" x2="' + (ML + PW)
      + '" y2="' + sy(z) + '" stroke="#e0d9c8" stroke-width="0.6"/>'
      + '<text x="' + (ML - 6) + '" y="' + (sy(z) + Math.round(FS / 3))
      + '" text-anchor="end" fill="#52514e" font-size="' + FS + '" data-role="tick">'
      + v + '%</text>';
  });
  return g;
}


function axisShort(axis) {
  if (axis === 'x' && isCap()) return CAP_KEYS[state.xdef].name();

  return dName(axis) + (state.def === 'median' ? ' (median task)' : '');
}


function dName(axis) {
  var lev = axis === 'x' ? +state.a : +state.c;
  return 'D' + fmtLev(100 - lev);
}
function fmtLev(v) { return String(+(+v).toFixed(2)); }
function axisName(axis) {
  if (axis === 'x' && isCap())
    return 'Capability C — mean solve chance on the calibrated pool '
      + '(metrics-report definition, counting estimator; ' + CAP_KEYS[state.xdef].clause() + ')';
  if (state.src === 'bayes') {
    var blev = axis === 'x' ? +state.a : +state.c;
    if (state.def !== 'average')
      return 'Median-task ' + blev + '% crossing (posterior median)';


    var interim = (D.bay.estimator_version_avg || '')
      .indexOf('band inversion') >= 0;
    var bbase = 'average-rate ' + blev
      + '% crossing (posterior median'
      + (interim ? ', band-inverted' : '') + ')';
    if (blev === 50 && axis === 'x') return 'Capability: ' + bbase;
    if (blev === 1 && axis === 'y') return 'Reliability: ' + bbase;
    return bbase.charAt(0).toUpperCase() + bbase.slice(1);
  }
  var lev = axis === 'x' ? state.a : state.c;
  var isAvg = state.def === 'average';
  var tag = isAvg ? ' (local-logistic)' : ' (binned medians)';
  var base = (isAvg ? 'average-rate ' : 'median-task ')
    + (+lev) + '% crossing';
  if (isAvg && +lev === 50 && axis === 'x')
    return 'Capability: ' + base + tag;
  if (isAvg && +lev === 1 && axis === 'y')
    return 'Reliability: ' + base + tag;
  return base.charAt(0).toUpperCase() + base.slice(1) + tag;
}


var TRK = { x0: ML, x1: ML + PW, y: 18,
            lo: logit(0.002), hi: logit(0.995) };
function trkX(levLogit) {
  return TRK.x0 + (levLogit - TRK.lo) / (TRK.hi - TRK.lo)
    * (TRK.x1 - TRK.x0);
}
function trkLev(px) {
  var t = Math.max(0, Math.min(1,
    (px - TRK.x0) / (TRK.x1 - TRK.x0)));
  return TRK.lo + t * (TRK.hi - TRK.lo);
}
function levelTrack() {


  var ink = '#52514e';
  var xa = trkX(logit(state.a / 100));
  var xc = trkX(logit(state.c / 100));
  return '<g id="lvltrack">'
    + '<line x1="' + TRK.x0 + '" y1="' + TRK.y + '" x2="' + TRK.x1
    + '" y2="' + TRK.y + '" stroke="#cfc5ac" stroke-width="2"/>'
    + '<text x="' + (TRK.x0 - 6) + '" y="' + (TRK.y + 4)
    + '" text-anchor="end" font-size="' + FT + '" fill="#8b8477">levels'
    + '</text>'
    + '<circle data-handle="c" class="handle" cx="' + xc + '" cy="'
    + TRK.y + '" r="' + (NARROW ? 15 : 9) + '" fill="transparent"/>'
    + '<circle class="knob" data-knob="c" pointer-events="none" cx="' + xc
    + '" cy="' + TRK.y + '" r="5" fill="#fcfaf3" stroke="' + ink
    + '" stroke-width="1.6"/>' + (held('c') ? heldRing('c', xc, ink) : '')
    + '<text x="' + xc + '" y="' + (TRK.y - 6)
    + '" text-anchor="middle" font-size="' + FT + '" fill="' + ink + '">y '
    + state.c + '%</text>'
    + (isCap()
      ? '<text x="' + (TRK.x0 + 6) + '" y="' + (TRK.y + 16) + '" font-size="' + FT + '" fill="#8b8477">no horizontal level (the Capability view is level-free)</text>'
      : '<circle data-handle="a" class="handle" cx="' + xa + '" cy="'
    + TRK.y + '" r="' + (NARROW ? 15 : 9) + '" fill="transparent"/>'
    + '<circle class="knob" data-knob="a" pointer-events="none" cx="' + xa
    + '" cy="' + TRK.y + '" r="5" fill="' + ink + '"/>' + (held('a') ? heldRing('a', xa, ink) : '')
    + '<text x="' + xa + '" y="' + (TRK.y + 16)
    + '" text-anchor="middle" font-size="' + FT + '" fill="' + ink + '">x '
    + state.a + '%</text>') + '</g>';
}


function updateTrack() {
  var tg = document.getElementById('trackg');
  tg.style.display = '';
  var structure = state.hold + '|' + state.xdef + '|' + (NARROW ? 'n' : 'w');
  if (!tg.hasChildNodes() || tg.dataset.structure !== structure) {
    tg.innerHTML = levelTrack();
    tg.dataset.structure = structure;
    return;
  }
  var xa = trkX(logit(state.a / 100));
  var xc = trkX(logit(state.c / 100));
  tg.querySelectorAll('[data-handle], [data-knob], [data-ring]').forEach(function (el) {
    var key = el.dataset.handle || el.dataset.knob || el.dataset.ring;
    el.setAttribute('cx', key === 'a' ? xa : xc);
  });
  tg.querySelectorAll('text').forEach(function (t) {
    var txt = t.textContent;
    if (txt.charAt(0) === 'y' && txt.indexOf('%') > 0) {
      t.setAttribute('x', xc); t.textContent = 'y ' + state.c + '%';
    } else if (txt.charAt(0) === 'x' && txt.indexOf('%') > 0) {
      t.setAttribute('x', xa); t.textContent = 'x ' + state.a + '%';
    }
  });
}

var dragKey = null;
var dragActive = false;
function wireDrag() {
  var svg = document.getElementById('chart');


  svg.addEventListener('touchstart', function (ev) {
    var h = ev.target.closest ? ev.target.closest('[data-handle]') : null;
    if (h && !(h.dataset.handle === 'a' && isCap())) ev.preventDefault();
  }, { passive: false });
  svg.addEventListener('pointerdown', function (ev) {
    var h = ev.target.closest ? ev.target.closest('[data-handle]')
                              : null;
    if (!h) return;
    if (h.dataset.handle === 'a' && isCap()) return;
    dragKey = h.dataset.handle;
    dragK0 = state.a / state.c;
    dragActive = true;
    svg.setPointerCapture(ev.pointerId);
    ev.preventDefault();
  });
  svg.addEventListener('pointermove', function (ev) {
    if (!dragKey) return;
    var r = svg.getBoundingClientRect();
    var px = (ev.clientX - r.left) / r.width * W;
    var v = Math.round(pct(trkLev(px)) * 10) / 10;
    v = Math.max(0.2, Math.min(99.5, v));


    applyLevel(dragKey, v, dragK0);
    scheduleRender();
  });
  function release(ev) {
    if (!dragKey) return;
    dragKey = null;
    dragActive = false;
    Kit.state.set('a', String(state.a), '50');
    Kit.state.set('c', String(state.c), '1');
    try { svg.releasePointerCapture(ev.pointerId); } catch (e) {}
    render();
  }
  svg.addEventListener('pointerup', release);
  svg.addEventListener('pointercancel', release);
}

function renderScatter() {
  foldSweepTools(); phoneFold();
  if (playBtn) { playBtn.disabled = false; playBtn.title = ''; }
  layout();
  var chart = document.getElementById('chart');
  chart.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  var la = logit(state.a / 100), lc = logit(state.c / 100);
  var out = axisGrid();
  var clipAt = out.length; EXT = null;

  var dg = '', GX = LIMX || LIM, GY = LIMY || LIM, G0 = Math.max(GX[0], GY[0]), G1 = Math.min(GX[1], GY[1]);
  for (var t = 0; t <= 40 && G1 > G0; t++) {
    var z = G0 + (G1 - G0) * t / 40;
    dg += (t ? 'L' : 'M') + sx(z).toFixed(1) + ' ' + sy(z).toFixed(1);
  }
  if (dg) out += '<path d="' + dg + '" fill="none" stroke="#cfc5ac" '
    + 'stroke-width="0.8" stroke-dasharray="3.3 2.7"/>';

  var visible = Array.from(sel).filter(function (i) { return !isHidden(i); }).sort(function (a, b) { return a - b; });


  if (state.kp === 'on' && !isCap()) {
    var K = state.a / state.c;
    var tgrid = state.src === 'bayes' ? D.bay.lev_logit
                                      : D.avg.lev_grid;
    var trails = '';
    visible.forEach(function (i) {
      var cc = D.shared.configs[i];
      var tp = '', pen = false;
      for (var ti = 0; ti < tgrid.length; ti += 2) {
        var pxl = pct(tgrid[ti]);
        var pyl = pxl / K;
        if (pyl < 0.2 || pyl > 99.5 || pxl < 0.2 || pxl > 99.5) {
          pen = false; continue;
        }
        var tx = reading(i, logit(pxl / 100), 'x');
        var ty = reading(i, logit(pyl / 100), 'y');
        if (tx.kind !== 'point' || ty.kind !== 'point'
            || tx.z == null || ty.z == null) { pen = false; continue; }
        tp += (pen ? 'L' : 'M') + sx(clampZ(tx.z)).toFixed(1) + ' '
            + sy(clampZ(ty.z)).toFixed(1);
        pen = true;
      }
      if (tp)
        trails += '<path d="' + tp + '" fill="none" stroke="'
          + cc.color + '" stroke-width="0.9" opacity="0.3" '
          + 'data-chain-val data-trail="' + i + '"/>';
    });
    out += '<g id="ktrails">' + trails + '</g>';
  }


  if (state.lad === 'on' && !isCap()) {
    var lads = '', LN = 26;
    visible.forEach(function (i) {
      var cc2 = D.shared.configs[i];
      var rx0 = reading(i, la, 'x');
      if (rx0.kind !== 'point' || rx0.z == null) return;
      var X0 = sx(clampZ(rx0.z));
      var lp = '', pen = false;
      for (var li = 0; li < LN; li++) {
        var kk = Math.pow(2, li / (LN - 1) * Math.log2(K_LADDER_MAX));
        var pyl = state.a / kk;
        if (pyl < 0.2) break;
        var ry0 = reading(i, logit(pyl / 100), 'y');
        if (ry0.kind !== 'point' || ry0.z == null) { pen = false; continue; }
        lp += (pen ? 'L' : 'M') + X0.toFixed(1) + ' '
            + sy(clampZ(ry0.z)).toFixed(1);
        pen = true;
      }
      var rungs = '';
      K_CHIPS.forEach(function (kk) {
        var pyl = state.a / kk;
        if (pyl < 0.2) return;
        var ry1 = reading(i, logit(pyl / 100), 'y');
        if (ry1.kind !== 'point' || ry1.z == null) return;
        var Y1 = sy(clampZ(ry1.z));
        rungs += 'M' + (X0 - 3).toFixed(1) + ' ' + Y1.toFixed(1)
               + 'L' + (X0 + 3).toFixed(1) + ' ' + Y1.toFixed(1);
      });
      if (lp)
        lads += '<path d="' + lp + rungs + '" fill="none" stroke="'
          + cc2.color + '" stroke-width="0.9" opacity="0.35" '
          + 'stroke-dasharray="1.5 2" data-chain-val data-ladder="' + i
          + '"/>';
    });
    out += '<g id="ladders">' + lads + '</g>';
  }

  var fx = [], fy = [], fsig = [], fl = [], fcol = [], marks = ''; undrawn = []; beyondFrame = 0; beyondArms = []; partialShownN = 0;
  var moves = '', moveN = 0; D.moves = {};
  visible.forEach(function (i) {
    var c = D.shared.configs[i];
    var part = isPartial(i), col = part ? '#8b8477' : c.color;
    var rx = reading(i, la, 'x'), ry = reading(i, lc, 'y');
    if (rx.z == null || ry.z == null) { undrawn.push(c.label + ' (' + ((rx.z == null ? rx.extra : ry.extra) || 'no ' + (state.def === 'average' ? 'average-rate' : 'median-task') + ' crossing at this pair: the level lies outside this model\u2019s observed range') + ')'); return; }
    if (rx.z > LIM[1] || rx.z < LIM[0]) { rx = Object.assign({}, rx, { kind: rx.z > LIM[1] ? 'hi-bound' : 'lo-bound', beyond: true }); }
    if (ry.z > LIM[1] || ry.z < LIM[0]) { ry = Object.assign({}, ry, { kind: ry.z > LIM[1] ? 'hi-bound' : 'lo-bound', beyond: true }); }
    if (rx.beyond || ry.beyond) { beyondFrame++; beyondArms.push(i); return; }
    if (part) partialShownN++;
    var X = sx(clampZ(rx.z)), Y = sy(clampZ(ry.z));
    extAdd(clampZ(rx.z), clampZ(ry.z));
    var full = rx.kind === 'point' && ry.kind === 'point';
    if (full && state.src === 'bayes' && state.move === 'on' && D.bayPrev && !isCap() && D.bayPrevById[c.id]) {
      var pr = D.bayPrevById[c.id], px = readBayesRow(pr, la, D.bayPrev), py = readBayesRow(pr, lc, D.bayPrev);
      if (px.kind === 'point' && py.kind === 'point' && px.z >= LIM[0] && px.z <= LIM[1] && py.z >= LIM[0] && py.z <= LIM[1]) {
        var PX = sx(px.z), PY = sy(py.z), ddx = X - PX, ddy = Y - PY, len = Math.sqrt(ddx * ddx + ddy * ddy);
        var pctOf = function (z) { return 100 / (1 + Math.exp(-z)); }, sg = function (v) { return (v > 0 ? '+' : '') + v.toFixed(1); };
        D.moves[c.id] = { dx: sg(pctOf(rx.z) - pctOf(px.z)), dy: sg(pctOf(ry.z) - pctOf(py.z)) };
        if (len >= 3) {
          extAdd(px.z, py.z);
          var ux = ddx / len, uy = ddy / len, hx = X - ux * (DR + 1), hy = Y - uy * (DR + 1);
          moves += '<line x1="' + PX.toFixed(1) + '" y1="' + PY.toFixed(1) + '" x2="' + (hx - ux * 5).toFixed(1) + '" y2="' + (hy - uy * 5).toFixed(1) + '" stroke="' + col + '" stroke-width="1.2" opacity="0.6" data-move data-i="' + i + '"/>'
            + '<path d="M' + hx.toFixed(1) + ' ' + hy.toFixed(1) + 'L' + (hx - ux * 7 + uy * 3.2).toFixed(1) + ' ' + (hy - uy * 7 - ux * 3.2).toFixed(1) + 'L' + (hx - ux * 7 - uy * 3.2).toFixed(1) + ' ' + (hy - uy * 7 + ux * 3.2).toFixed(1) + 'Z" fill="' + col + '" opacity="0.6" data-move/>';
          moveN++;
        }
      }
    }
    var fade = full ? 1 : 0.4;
    var flg = armFlag(i);
    if (flg) fade = 0.3;
    if (c.gates_failed) fade = Math.min(fade, 0.55);
    if (part) fade = Math.min(fade, 0.45);
    var standIn = false, fitEx = false;
    var d = '', openMarks = '';
    if (state.w === 'on') {
      if (rx.lo != null && rx.hi != null) { extAdd(clampZ(rx.lo), null); extAdd(clampZ(rx.hi), null); }
      if (ry.lo != null && ry.hi != null) { extAdd(null, clampZ(ry.lo)); extAdd(null, clampZ(ry.hi)); }
      if (rx.lo != null && rx.hi != null)
        d += 'M' + sx(clampZ(rx.lo)).toFixed(1) + ' ' + Y.toFixed(1)
           + 'L' + sx(clampZ(rx.hi)).toFixed(1) + ' ' + Y.toFixed(1);
      if (ry.lo != null && ry.hi != null)
        d += 'M' + X.toFixed(1) + ' ' + sy(clampZ(ry.lo)).toFixed(1)
           + 'L' + X.toFixed(1) + ' ' + sy(clampZ(ry.hi)).toFixed(1);


      if (rx.hi_open && rx.hi != null)
        openMarks += '<path d="M' + sx(clampZ(rx.hi)).toFixed(1) + ' '
          + Y.toFixed(1) + 'm4 0l-7 4l0 -8Z" fill="none" stroke="'
          + col + '" stroke-width="1.1"/>';
      if (ry.hi_open && ry.hi != null)
        openMarks += '<path d="M' + X.toFixed(1) + ' '
          + sy(clampZ(ry.hi)).toFixed(1)
          + 'm0 -4l4 7l-8 0Z" fill="none" stroke="'
          + col + '" stroke-width="1.1"/>';
      if (rx.lo_open && rx.lo != null)
        openMarks += '<path d="M' + sx(clampZ(rx.lo)).toFixed(1) + ' '
          + Y.toFixed(1) + 'm-4 0l7 4l0 -8Z" fill="none" stroke="'
          + col + '" stroke-width="1.1"/>';
      if (ry.lo_open && ry.lo != null)
        openMarks += '<path d="M' + X.toFixed(1) + ' '
          + sy(clampZ(ry.lo)).toFixed(1)
          + 'm0 4l4 -7l-8 0Z" fill="none" stroke="'
          + col + '" stroke-width="1.1"/>';
    }


    var Xs = X.toFixed(1), Ys = Y.toFixed(1), mark;
    if (full || rx.kind === 'censored-partial'
        || ry.kind === 'censored-partial') {
      mark = '<path d="M' + Xs + ' ' + Ys
        + 'm-' + DR + ' 0a' + DR + ' ' + DR + ' 0 1 0 ' + (2 * DR) + ' 0a' + DR + ' ' + DR + ' 0 1 0 -' + (2 * DR) + ' 0Z" fill="'
        + (c.think ? '#fcfaf3' : col) + '" stroke="'
        + (c.think ? col : '#fcfaf3')
        + '" stroke-width="1.3" data-mark data-chain-val data-i="' + i + '"/>'
        + (flg ? '<circle cx="' + X + '" cy="' + Y + '" r="7" fill="none" '
            + 'stroke="#b3261e" stroke-dasharray="2 2" stroke-width="1.2" '
            + 'data-flag/>' : '')
;
    } else {
      var pt = ry.kind === 'hi-bound'
          ? 'm0 -6l5 10l-10 0Z'
        : ry.kind === 'lo-bound' ? 'm0 6l5 -10l-10 0Z'
        : rx.kind === 'hi-bound' ? 'm6 0l-10 5l0 -10Z'
                                 : 'm-6 0l10 5l0 -10Z';
      mark = '<path d="M' + Xs + ' ' + Ys + pt
        + '" fill="none" stroke="' + col
        + '" stroke-width="1.4" data-mark data-chain-val data-i="' + i + '"/>';
    }
    mark += (standIn ? '<circle cx="' + X + '" cy="' + Y + '" r="8" fill="none" stroke="#8b8477" stroke-dasharray="3 2" stroke-width="1.1" data-standin/>' : '')
      + (fitEx ? '<circle cx="' + X + '" cy="' + Y + '" r="9" fill="none" stroke="#8b8477" stroke-dasharray="1.5 2.5" stroke-width="1.2" data-fitexcluded/>' : '');
    marks += '<g opacity="' + fade + '" data-i="' + i + '">'
      + '<circle class="hit" data-export="omit" cx="' + Xs + '" cy="' + Ys + '" r="' + (NARROW ? 15 : 9) + '" fill="transparent" stroke="none"/>'
      + (d ? '<path d="' + d + '" fill="none" stroke="' + col
      + '" stroke-width="1.1" opacity="0.55" data-chain-val/>' : '')
      + openMarks + mark + '</g>';
    if (full && !fitEx && !part && !isRun(i)) {
      fx.push(FX(rx.z)); fy.push(FY(ry.z)); fl.push(c.label); fcol.push(col);


      var zx = (state.src === 'bayes' || isCap()) ? 1.2816 : 1.96;
      var zy = state.src === 'bayes' ? 1.2816 : 1.96;
      var hwx = Math.max(rx.lo != null ? Math.abs(FX(rx.z) - FX(rx.lo)) : -1,
                         rx.hi != null ? Math.abs(FX(rx.hi) - FX(rx.z)) : -1);
      var hwy = Math.max(ry.lo != null ? Math.abs(FY(ry.z) - FY(ry.lo)) : -1,
                         ry.hi != null ? Math.abs(FY(ry.hi) - FY(ry.z)) : -1);
      fsig.push(hwx >= 0 && hwy >= 0 ? [hwx / zx, hwy / zy] : null);
    }
  });


  var fitTxt = 'fit: needs 3+ ' + (state.src === 'bayes'
    ? 'in-range posterior dots' : 'fully measured dots');
  var sweeping = dragActive || !!playTimer;
  var headFit = null, headN = 0;
  if (fx.length >= 3) {
    var fkey = [state.def, state.src, state.wd, state.xdef, state.fitci, state.line, state.xs, state.ys, state.lw,
                state.a, state.c, Array.from(sel).join('.')].join('|');


    var hx = fx, hy = fy, hsig = null, hl = fl, hc = fcol, dropped = 0;
    if (state.fitci === 'honest' || state.lw === 'bands') {
      hx = []; hy = []; hsig = []; hl = []; hc = [];
      for (var qi = 0; qi < fx.length; qi++) {
        if (fsig[qi]) { hx.push(fx[qi]); hy.push(fy[qi]); hsig.push(fsig[qi]); hl.push(fl[qi]); hc.push(fcol[qi]); }
        else dropped++;
      }
    }


    var mgF = inAxes() && state.xs === 'raw' ? 0.03 : 0.15;
    var f = (sweeping && !fitCache[fkey]) || hx.length < 3 ? null
            : state.lw === 'bands' ? (fitCache[fkey] || (fitCache[fkey] = yorkFit(hx, hy, hsig, state.fitci === 'honest' ? 80 : 95, mgF)))
            : bootFit(hx, hy, fkey, hsig, mgF);
    var RS = f ? residStats(f, hx, hy, hl) : null;
    if (!f && sweeping)
      fitTxt = 'fit: paused while the levels move — recomputes when they stop';
    if (f) {
      var mgx = inAxes() && state.xs === 'raw' ? 0.03 : 0.15;
      var gx = [Math.min.apply(null, hx) - mgx, Math.max.apply(null, hx) + mgx];
      if (state.line !== 'off') {

      var bp = '';
      for (var bi = 0; bi < f.band.xs.length; bi++)
        bp += (bi ? 'L' : 'M') + pxF(f.band.xs[bi]).toFixed(1) + ' '
            + pyF(f.band.up[bi]).toFixed(1);
      for (var bj = f.band.xs.length - 1; bj >= 0; bj--)
        bp += 'L' + pxF(f.band.xs[bj]).toFixed(1) + ' '
            + pyF(f.band.dn[bj]).toFixed(1);
      out += '<path d="' + bp + 'Z" fill="'
        + (state.fitci === 'honest' ? '#d9c8a8' : '#cfc5ac')
        + '" opacity="0.35" stroke="none" data-chain-val="def src xdef fitci" '
        + 'data-fitband/>';
      var fp = '';
      for (var t2 = 0; t2 <= 24; t2++) {
        var zx2 = gx[0] + (gx[1] - gx[0]) * t2 / 24;
        fp += (t2 ? 'L' : 'M') + pxF(zx2).toFixed(1) + ' '
            + pyF(f.a + f.b * zx2).toFixed(1);
      }
      out += '<path d="' + fp + '" fill="none" stroke="#8b8477" '
        + 'stroke-width="1.1" data-chain-val data-fitline/>';
      }
      var droppedTxt = dropped ? '; ' + dropped + ' dot' + (dropped > 1 ? 's' : '') + ' dropped (no usable whisker width)' : '';
      var modeTxt = state.lw === 'bands' ? 'weighted by the dots\u2019 80% bands on both axes (tighter counts more; the default line is the unweighted one)' + (f.widen > 1.05 ? '; interval widened ' + f.widen.toFixed(1) + '\u00d7 for scatter beyond the bands' : '') + droppedTxt
                  : state.fitci === 'honest' ? 'with each dot\u2019s measurement error' + droppedTxt : 'dots taken as exact';
      var spaceTxt = inAxes() ? 'in the axes as set' : (state.xs === 'raw' || state.ys === 'raw') ? 'in logit (drawn as the curve it maps to on the linear axis)' : 'in logit';

      fitTxt = 'line ' + spaceTxt + ' over ' + hx.length + (state.src === 'bayes' ? ' in-range posterior-median dots' : ' fully measured dots') + ': slope ' + f.b.toFixed(2) + ', range ' + f.lo.toFixed(2) + ' to ' + f.hi.toFixed(2) + ' (' + f.level + '%), R ' + f.r.toFixed(2) + '; band = pointwise ' + f.level + '% envelope; ' + modeTxt
        + (inAxes() ? '; intercept ' + fmtY(f.a) : '')
        + (state.resid === 'on' ? '; misses: typical ' + RS.rmsPct.toFixed(1) + '% of the y scale, largest ' + sgn(RS.bigPct) + '% (' + RS.bigLabel + '), ' + RS.w5 + ' of ' + RS.n + ' models within \u00b15%, ' + RS.w10 + ' within \u00b110%' : '')
        + (state.line === 'off' ? ' (not drawn: Fitted line is Off)' : '');
      headFit = f; headN = hx.length;
    }
  }
  headline(headN, headFit, fx.length, sweeping);
  fitCaption(headFit, headN);


  var pfs = NARROW ? 15 : Math.round(14 * Math.max(1, UPX)), pfs2 = NARROW ? 12 : Math.round(12 * Math.max(1, UPX)), plx = ML + 8, ply = MT + 8;
  refreshBeyondChips();
  var drawnN = visible.length - undrawn.length - beyondArms.length, totalN = D.shared.configs.length;


  var pl1 = f ? 'slope ' + f.b.toFixed(2) + ' [' + f.lo.toFixed(2) + ', ' + f.hi.toFixed(2) + ']\u2003R: ' + f.r.toFixed(2) : (sweeping ? 'fit paused while the levels move' : NARROW ? 'no fit: under 3 fully measured models' : 'no fit: fewer than three fully measured models');
  var pl2 = f ? '' : (drawnN + ' of ' + totalN + ' models drawn');
  var pl3 = '';
  var plw = Math.max(pl1.length * pfs, pl2.length * pfs2, pl3.length * pfs2) * 0.56 + 18, plh = (pfs + 6) + ((pl2 || pl3) ? (pl3 ? 2 : 1) * (pfs2 + 4) : 0) + 8;
  var plMax = W - MR - plx - 4; if (plw > plMax) { var shrink = plMax / plw; pfs = Math.max(Math.ceil(11 * UPX), Math.floor(pfs * shrink)); pfs2 = Math.max(Math.ceil(11 * UPX), Math.floor(pfs2 * shrink)); plw = plMax; plh = (pfs + 6) + ((pl2 || pl3) ? (pl3 ? 2 : 1) * (pfs2 + 4) : 0) + 8; }
  out += (state.line === 'off' ? '' : '<g id="fitpanel" data-critical-text data-chain-val="def src xdef fitci line xs ys s l sel" pointer-events="none">'
    + '<rect x="' + plx + '" y="' + ply + '" width="' + plw.toFixed(0) + '" height="' + plh + '" rx="6" fill="#fcfaf3" fill-opacity="0.94" stroke="#d9d2c2"/>'
    + '<text x="' + (plx + 9) + '" y="' + (ply + pfs + 4) + '" font-size="' + pfs + '" fill="#1f1e1b" font-weight="600" style="font-variant-numeric:tabular-nums">' + pl1 + '</text>'
    + (pl2 ? '<text x="' + (plx + 9) + '" y="' + (ply + pfs + pfs2 + 9) + '" font-size="' + pfs2 + '" fill="#52514e" style="font-variant-numeric:tabular-nums">' + pl2 + '</text>' : '')
    + (pl3 ? '<text x="' + (plx + 9) + '" y="' + (ply + pfs + 2 * pfs2 + 14) + '" font-size="' + pfs2 + '" fill="#52514e">' + pl3 + '</text>' : '')
    + '</g>')
    + (partialShownN ? '<text x="' + (ML + 8) + '" y="' + (MT + PH - (beyondFrame ? 22 : 8)) + '" font-size="' + (NARROW ? 12 : 11) + '" fill="#52514e" data-critical-text>partial model' + (partialShownN > 1 ? 's' : '') + ' shown greyed, not in the fit: ' + partialShownN + '</text>' : '')
    + (f && RS && state.resid === 'on' && state.line !== 'off' ? residPanel(RS, hc, plx, ply + plh + 6) : '')
    + (beyondFrame ? '<text x="' + (ML + 8) + '" y="' + (MT + PH - 8) + '" font-size="' + (NARROW ? 12 : 11) + '" fill="#52514e" data-critical-text>not drawn: ' + beyondFrame + ' model' + (beyondFrame > 1 ? 's' : '') + ' whose crossing lies beyond the hardest task</text>' : '');


  if (EXPORTING) out = out.slice(0, clipAt) + '<clipPath id="expclip"><rect x="' + ML + '" y="' + MT + '" width="' + PW + '" height="' + PH + '"/></clipPath>'
    + '<g clip-path="url(#expclip)">' + out.slice(clipAt) + '</g>';


  var tyx = EXPORTING ? 20 : NARROW ? 11 : 15, tfs = EXPORTING ? EXPORT_TITLE_PX : NARROW ? 13 : Math.max(FS + 1, Math.ceil(13 * UPX));
  out += '<text x="' + (ML + PW / 2) + '" y="' + (H - 6)
    + '" text-anchor="middle" fill="#52514e" font-size="' + tfs + '" data-role="axis-title" '
    + 'data-chain-val="def src">' + fitTitle(axisShort('x'), W - 20, tfs) + '</text>'
    + '<text x="' + tyx + '" y="' + (MT + PH / 2) + '" text-anchor="middle" '
    + 'fill="#52514e" font-size="' + tfs + '" transform="rotate(-90 ' + tyx + ' '
    + (MT + PH / 2) + ')" data-role="axis-title" data-chain-val="def src">' + axisShort('y') + '</text>';
  if (moveN) out += '<text x="' + (ML + 8) + '" y="' + (MT + PH - 8 - (beyondFrame ? 14 : 0)) + '" font-size="' + (NARROW ? 12 : 11) + '" fill="#52514e" data-chain-val="src move">arrows: moves from ' + prevFitName() + '</text>';
  var body = (moveN ? '<g id="moves">' + moves + '</g>' : '') + '<g id="marks">' + marks + '</g>';
  document.getElementById('plotg').innerHTML = out + (EXPORTING ? '<g clip-path="url(#expclip)">' + body + '</g>' : body);
  updateTrack();


  if (!EXPORTING && !NO_RATCHET) ['headline', 'narrate', 'notes', 'fitline', 'kBound', 'vocabnote', 'framebar'].forEach(function (id) {
    var el = document.getElementById(id); if (!el) return;
    if (sweeping) { if (!el.style.height) { el.style.height = el.offsetHeight + 'px'; el.style.overflow = 'hidden'; } }
    else {
      el.style.height = ''; el.style.overflow = '';


      var h = el.offsetHeight; if (h > (el._ratchet || 0)) { el._ratchet = h; el.style.minHeight = h + 'px'; }
    }
  });
  var fitEl = document.getElementById('fitline');
  fitEl.innerHTML =
    '<span data-chain-val="def src xdef">' + fitTxt + '</span>'
    + ' <span style="color:#8b8477">· open triangles point toward '
    + 'the uncertain side (a bound, not a measurement); faded = at '
    + 'least one coordinate is a bound</span>';
  narrate(visible, fx.length);
  vocabNote();
  notes();
  stamp();
  paintChips();
  var k = state.a / state.c;


  var xb = document.querySelector('.kit-switch[data-key="xdef"] button[data-value="crossing"]'); if (xb && xb.textContent !== dName('x')) xb.textContent = dName('x');
  document.getElementById('kOut').textContent =
    isCap() ? 'K n/a (the Capability view is level-free)'
      : 'K = ' + (k >= 100 ? k.toFixed(0) : k.toFixed(1));
  var kb = document.getElementById('kBound');
  var slotNotes = [inputNote, lockNote].filter(Boolean).join(' \u00b7 ');
  if (kb) kb.textContent = slotNotes ? slotNotes : isCap() ? ''
    : Math.abs(k - 1) <= 1e-6 ? 'K at 1\u00d7: the levels coincide' : k < 1 ? 'K below 1\u00d7: the horizontal level lies under the vertical level' : '';
}


var exportMounted = false;
function mountExport() {
  if (exportMounted) return;
  var box = document.getElementById('exportrow'); if (!box || !window.Kit || !Kit.exportButton) return;
  exportMounted = true;
  Kit.exportButton(box, exportOptions);
}
function exportView() {
  var ds = DATASETS[state.data] || {}, parts = [ds.label || String(state.data || '')];
  parts.push(axisShort('y') + ' against ' + axisShort('x'));
  var sp = function (v) { return v === 'raw' ? 'linear' : 'logit'; };
  parts.push(state.xs === state.ys ? sp(state.xs) + ' axes' : 'horizontal ' + sp(state.xs) + ', vertical ' + sp(state.ys));
  parts.push(state.src === 'bayes' ? 'Bayesian crossing estimator' : 'local-logistic crossing estimator');
  if (state.line !== 'off') parts.push('fitted line ' + (inAxes() ? 'in the axes as set' : 'in logit') + (state.lw === 'bands' ? ', weighted by the bands' : ''));
  return parts.join(' \u00b7 ');
}
function exportLegend() {
  var rows = [];
  famOrder(Array.from(sel).filter(function (i) { return !isHidden(i) && !isRun(i); })).forEach(function (i) {
    var m = document.querySelector('#marks path[data-mark][data-i="' + i + '"]'); if (!m) return;
    var c = D.shared.configs[i], grey = isPartial(i);
    var d = m.getAttribute('d') || '', fill = m.getAttribute('fill') || 'none', stroke = m.getAttribute('stroke') || c.color, sw = m.getAttribute('stroke-width') || '1.3';
    var op = m.parentNode && m.parentNode.getAttribute ? m.parentNode.getAttribute('opacity') : null;
    var mark = function (cx, cy) {
      return '<path d="' + d.replace(/^M[-\d.]+ [-\d.]+/, 'M' + cx + ' ' + cy) + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"' + (op && +op < 1 ? ' opacity="' + op + '"' : '') + '/>';
    };
    rows.push({ label: (c.display_name || c.label) + (grey ? ' (partial)' : '') + (c.gates_failed ? ' (flagged fit)' : ''), family: c.fam, color: grey ? '#8b8477' : c.color, line: false, marker: mark });
  });
  RUNS.forEach(function (R) {
    var drawn = R.idx.filter(function (i) { return sel.has(i) && !isHidden(i) && document.querySelector('#marks path[data-mark][data-i="' + i + '"]'); });
    if (!drawn.length) return;
    var cs = drawn.map(function (i) { return D.shared.configs[i]; });
    var stepWord = function (c) { return c.step == null ? 'final' : String(c.step); };
    var steps = cs.filter(function (c) { return c.step != null; }), fin = cs.some(function (c) { return c.step == null; });
    var lab = R.name + (steps.length ? ', ' + (steps.length === 1 ? 'step ' + stepWord(steps[0]) : steps.length + ' steps ' + stepWord(steps[0]) + '\u2013' + stepWord(steps[steps.length - 1])) : '') + (fin ? (steps.length ? ' and the final' : ', the final') : '') + (cs.some(function (c) { return c.gates_failed; }) ? ' (a flagged fit among them)' : '');
    rows.push({ label: lab, family: cs[0].fam, color: cs[cs.length - 1].color, ramp: cs.length > 1 ? cs.map(function (c) { return c.color; }) : null, dash: R.dash || '', line: false, marker: R.think ? 'open-circle' : 'circle' });
  });
  return rows;
}
function exportOptions() {
  var chart = document.getElementById('chart'), f = D.shared.frame || {}, ds = DATASETS[state.data] || {};
  var tight = state.view !== 'ridges' && EXT && isFinite(EXT.x0) && isFinite(EXT.y0) && EXT.x1 > EXT.x0 && EXT.y1 > EXT.y0;
  if (tight) {
    var padX = Math.max(0.05, (EXT.x1 - EXT.x0) * 0.02), padY = Math.max(0.05, (EXT.y1 - EXT.y0) * 0.02);
    LIMX = [Math.max(LIM[0], EXT.x0 - padX), Math.min(LIM[1], EXT.x1 + padX)];
    LIMY = [Math.max(LIM[0], EXT.y0 - padY), Math.min(LIM[1], EXT.y1 + padY)];

    var tickBelow = function (zmin) { var best = null; LOGIT_TICKS_EXPORT.forEach(function (t) { var zt = logit(t / 100); if (zt <= zmin + 1e-9 && (best === null || zt > best)) best = zt; }); return best; };
    if (state.ys !== 'raw') { var tb = tickBelow(EXT.y0); if (tb !== null) LIMY[0] = Math.max(LIM[0], Math.min(LIMY[0], tb - 0.06)); }

    if (state.xs === state.ys) {
      var rawB = state.xs === 'raw';
      var spanOf = function (B) { var L = rawB ? [Math.max(0, pct(B[0]) / 100 - 0.02), Math.min(1, pct(B[1]) / 100 + 0.02)] : B; return L[1] - L[0]; };
      var widenTo = function (B, want) {
        var lo = 0, hi = LIM[1] - LIM[0];
        for (var k = 0; k < 40; k++) { var d = (lo + hi) / 2, C = [Math.max(LIM[0], B[0] - d), Math.min(LIM[1], B[1] + d)]; if (spanOf(C) < want) lo = d; else hi = d; }
        return [Math.max(LIM[0], B[0] - hi), Math.min(LIM[1], B[1] + hi)];
      };
      var sxp = spanOf(LIMX), syp = spanOf(LIMY);
      if (syp / sxp > 2) LIMX = widenTo(LIMX, syp / 2); else if (syp / sxp < 0.5) LIMY = widenTo(LIMY, sxp / 0.5);
    }
  }
  EXPORTING = true; render();
  var legend = state.view === 'ridges' ? [] : exportLegend();

  var restore = function () { EXPORTING = false; LIMX = null; LIMY = null; NO_RATCHET = true; try { render(); } finally { NO_RATCHET = false; } };
  if (window.queueMicrotask) queueMicrotask(restore); else Promise.resolve().then(restore);
  var parts = new Intl.DateTimeFormat('en', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  var pick = function (t) { return (parts.find(function (q) { return q.type === t; }) || {}).value || ''; };
  var slug = String(ds.label || state.data || 'view').split(' (')[0].replace(/\+/g, '-').replace(/[^\w-]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  return { svg: chart, legend: legend, title: 'Capability vs reliability', page: 'capability-vs-reliability', view: exportView(),
    stamp: (f.build_ts || f.runs_window) ? 'data as of ' + plainTs(f.build_ts || f.runs_window) : '', fileBase: 'capability-vs-reliability_' + slug + '_' + pick('year') + '-' + pick('month') + '-' + pick('day'), crop: null };
}


var OPUS_PAIR = ['claude-opus-5', 'claude-opus-5-thinking'];
function tableAt(lt, levLogit) {
  var LV = D.bay && (D.bay.lev_logit || (D.bay.lev_fail || []).map(logit)); if (!lt || !LV || !LV.length) return null;
  if (levLogit < LV[0] - 1e-9 || levLogit > LV[LV.length - 1] + 1e-9) return null;
  var lo_i = 0, hi_i = LV.length - 1;
  while (hi_i - lo_i > 1) { var mm = (lo_i + hi_i) >> 1; if (LV[mm] < levLogit) lo_i = mm; else hi_i = mm; }
  if (lt.kind[lo_i] !== 0 || lt.kind[hi_i] !== 0) return null;
  var t = (levLogit - LV[lo_i]) / (LV[hi_i] - LV[lo_i]);
  var ip = function (a) { return a && a[lo_i] != null && a[hi_i] != null ? a[lo_i] + t * (a[hi_i] - a[lo_i]) : null; };
  return { z: ip(lt.mid), lo: ip(lt.lo), hi: ip(lt.hi) };
}
function renderOpusFold() {
  var fold = document.getElementById('opusfold'), fig = document.getElementById('opusfig'), txt = document.getElementById('opustext');
  if (!fold || !fig || !txt || !D || !D.shared) return;
  var idx = OPUS_PAIR.map(function (id) { var k = -1; D.shared.configs.forEach(function (c, i) { if (c.id === id) k = i; }); return k; });
  var rows = idx.map(function (i) { return (i >= 0 && D.bay && D.bayById && D.bayById[D.shared.configs[i].id]) || null; });
  if (idx[0] < 0 || idx[1] < 0 || !rows[0] || !rows[1] || !D.bay.kde_grid) { fold.hidden = true; return; }
  fold.hidden = false;
  var l1 = logit(0.01), g = D.bay.kde_grid;
  var arms = idx.map(function (i, k) { var c = D.shared.configs[i], r = rows[k]; return { c: c, r: r, avg: tableAt(r.levels_avg, l1), ridge: r.d1 }; });
  var zs = [];
  arms.forEach(function (a) { if (a.avg && a.avg.z != null) zs.push(a.avg.lo != null ? a.avg.lo : a.avg.z, a.avg.hi != null ? a.avg.hi : a.avg.z); if (a.ridge) zs.push(a.ridge.cri80_z[0], a.ridge.cri80_z[1]); });
  if (!zs.length) { fold.hidden = true; return; }
  var zlo = Math.min.apply(null, zs) - 0.6, zhi = Math.max.apply(null, zs) + 0.6;
  var W = 860, H = 240, ML2 = 150, MR2 = 24, MT2 = 28, RH = 74, xw = W - ML2 - MR2;
  var X = function (z) { return ML2 + (z - zlo) / (zhi - zlo) * xw; };
  var out = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="Claude Opus 5 and Claude Opus 5 thinking: the ridge and the scatter readings of the 1% crossing on one difficulty axis">';
  [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98].forEach(function (v) { var z = logit(v / 100); if (z < zlo || z > zhi) return;
    out += '<line x1="' + X(z).toFixed(1) + '" y1="' + MT2 + '" x2="' + X(z).toFixed(1) + '" y2="' + (MT2 + 2 * RH) + '" stroke="#e0d9c8" stroke-width="0.6"/>'
         + '<text x="' + X(z).toFixed(1) + '" y="' + (MT2 + 2 * RH + 16) + '" text-anchor="middle" font-size="11" fill="#52514e">' + v + '%</text>'; });
  out += '<text x="' + (ML2 + xw / 2) + '" y="' + (H - 6) + '" text-anchor="middle" font-size="12" fill="#52514e">difficulty at which failures reach 1% (percent of the scale); further right = more reliable</text>';
  arms.forEach(function (a, k) {
    var y0 = MT2 + (k + 1) * RH - 12, col = a.c.color, dash = a.c.think ? ' stroke-dasharray="5 3"' : '';
    var kd = a.ridge.kde, mx = Math.max.apply(null, kd) || 1, d = '', pen = false;
    for (var j = 0; j < g.length; j++) { if (g[j] < zlo || g[j] > zhi) continue; d += (pen ? 'L' : 'M') + X(g[j]).toFixed(1) + ' ' + (y0 - (kd[j] / mx) * (RH * 0.78)).toFixed(1); pen = true; }
    if (pen) out += '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.4"' + dash + '/>';
    var zm = a.ridge.median_z;
    out += '<line x1="' + X(zm).toFixed(1) + '" y1="' + (y0 - RH * 0.84).toFixed(1) + '" x2="' + X(zm).toFixed(1) + '" y2="' + y0 + '" stroke="' + col + '" stroke-width="1" stroke-dasharray="2 2"/>'
         + '<text x="' + X(zm).toFixed(1) + '" y="' + (y0 - RH * 0.86).toFixed(1) + '" text-anchor="middle" font-size="10" fill="' + col + '">ridge ' + fmtPct(zm, 0) + '</text>';
    if (a.avg && a.avg.z != null) {
      if (a.avg.lo != null && a.avg.hi != null) out += '<line x1="' + X(a.avg.lo).toFixed(1) + '" y1="' + (y0 + 12) + '" x2="' + X(a.avg.hi).toFixed(1) + '" y2="' + (y0 + 12) + '" stroke="' + col + '" stroke-width="2"/>';
      out += a.c.think ? '<circle cx="' + X(a.avg.z).toFixed(1) + '" cy="' + (y0 + 12) + '" r="5.5" fill="#fcfaf3" stroke="' + col + '" stroke-width="1.8"/>'
                       : '<circle cx="' + X(a.avg.z).toFixed(1) + '" cy="' + (y0 + 12) + '" r="5.5" fill="' + col + '" stroke="#fcfaf3" stroke-width="1"/>';
      out += '<text x="' + (X(a.avg.z) + 9).toFixed(1) + '" y="' + (y0 + 16) + '" font-size="10" fill="' + col + '">scatter ' + fmtPct(a.avg.z, 0) + '</text>';
    }
    out += '<text x="' + (ML2 - 8) + '" y="' + (y0 - 4) + '" text-anchor="end" font-size="12" fill="#52514e">' + a.c.label + '</text>'
         + '<line x1="' + ML2 + '" y1="' + y0 + '" x2="' + (W - MR2) + '" y2="' + y0 + '" stroke="#c9c2b2" stroke-width="0.6"/>';
  });
  out += '<text x="' + ML2 + '" y="16" font-size="11" fill="#52514e">line = the spread of the median-task 1% crossing across the fitted draws · dot with bar = the dot drawn on the scatter view (average-rate 1% crossing, 80% band)</text></svg>';
  fig.innerHTML = out;
  var A = arms[0], B = arms[1];
  if (!A.avg || A.avg.z == null || !B.avg || B.avg.z == null) { txt.textContent = 'One of the two models has no average-rate 1% crossing inside its fitted range at this dataset, so the two readings cannot be compared here.'; return; }
  var P = function (z) { return fmtPct(z, 0); };
  var band = function (a) { return a.lo != null && a.hi != null ? P(a.lo) + '–' + P(a.hi) : 'no band'; };
  var moreAvg = A.avg.z > B.avg.z ? A : B, lessAvg = moreAvg === A ? B : A;
  var moreRidge = A.ridge.median_z > B.ridge.median_z ? A : B, lessRidge = moreRidge === A ? B : A;
  var overlap = A.avg.lo != null && B.avg.lo != null && Math.max(A.avg.lo, B.avg.lo) <= Math.min(A.avg.hi, B.avg.hi);
  var tA = A.r.tau && A.r.tau.median, tB = B.r.tau && B.r.tau.median;
  var wide = tA != null && tB != null ? (tA > tB ? A : B) : null;
  var spread = wide ? ' The ' + wide.c.label + ' model spreads more from task to task (spread ' + Math.max(tA, tB).toFixed(1) + ' against ' + Math.min(tA, tB).toFixed(1) + ' difficulty units): a heavier tail of tasks it keeps failing pulls its average failure rate up and its average-rate crossing down, while its typical task is the safer one.'
                    : ' The model with the wider spread from task to task has a heavier tail of tasks it keeps failing, which pulls its average failure rate up and its average-rate crossing down while its typical task stays safer.';
  var cens = (A.ridge.p_censored > 0.05 || B.ridge.p_censored > 0.05)
    ? ' Part of the 1% crossing draws are censored here (' + Math.round(100 * A.ridge.p_censored) + '% and ' + Math.round(100 * B.ridge.p_censored) + '%); read the ridges with that share in mind.'
    : ' This is not a censoring effect: no draw of either model’s 1% crossing is censored; the open triangles on the plane concern the 50% crossings.';
  var cov = '';
  [A, B].forEach(function (a) { var cv = coverageOf(a.c); if (cv && cv.tasks < cv.of) cov += ' ' + a.c.label + ' has attempts on ' + Math.round(cv.share * 100) + '% of this set\u2019s tasks; the tasks it did not attempt (its refusals) are out of its fit, which favours it a little under the average-rate reading.'; });
  txt.textContent = 'Ridge here = the posterior of the median-task 1% crossing, the quantity the ridges view used to draw under every definition: the difficulty at which a typical task is failed less than once in a hundred. Scatter = the default point, the average-rate 1% crossing: the difficulty at which the average failure rate over tasks reaches 1%; that is the default reliability. '
    + 'Under the default definition ' + A.c.label + ' reads ' + P(A.avg.z) + ' and ' + B.c.label + ' ' + P(B.avg.z) + ' (80% bands ' + band(A.avg) + ' and ' + band(B.avg) + '), so ' + moreAvg.c.label + ' is the more reliable' + (overlap ? ', and the two bands overlap: the ordering is suggestive, not settled.' : '.')
    + ' On the ridges ' + moreRidge.c.label + ' is the higher (' + P(moreRidge.ridge.median_z) + ' against ' + P(lessRidge.ridge.median_z) + '): on a typical task it is the safer model.'
    + (moreAvg !== moreRidge ? ' Both readings are right about different things.' : '') + spread + cens + cov
    + ' Trust the scatter for reliability, the default definition; read the median-task ridge as the typical-task view. The ridges view itself now follows the definition switch: under the average-rate definition it shows the 80% band of the same crossing the dot marks, so the two views agree; the median-task ridges remain under the Median definition where that chain is served.';
}

function ridgeCentre(r, lev) {
  var t = tableAt(state.def === 'average' ? r.levels_avg : r.levels, logit(lev)); if (t && t.z != null) return t.z;
  var b = state.def === 'average' ? (lev === 0.5 ? r.d50_avg : r.d1_avg) : null; b = b || (lev === 0.5 ? r.d50 : r.d1); return b ? b.median_z : -Infinity;
}
function renderRidges() {
  if (playBtn) { playBtn.disabled = true; playBtn.title = 'the sweep moves the scatter; switch the view back to use it'; }
  var chart = document.getElementById('chart');
  var visible = Array.from(sel).filter(function (i) { return !isHidden(i); }).sort(function (a, b) { return a - b; });
  var skipped = visible.filter(function (i) { return !D.bayById[D.shared.configs[i].id]; }).length;
  var rows = visible.filter(function (i) { return !!D.bayById[D.shared.configs[i].id]; }).map(function (i) {
    return { i: i, r: D.bayById[D.shared.configs[i].id] };
  }).sort(function (a, b) { return capOrder([a.i, b.i])[0] === a.i ? -1 : 1; });
  var g = D.bay.kde_grid, avgDef = state.def === 'average';


  layout();
  var rh = 24, RML = NARROW ? 120 : 195;
  var Hr = MT + (rows.length + 1) * rh + MB;
  chart.setAttribute('viewBox', '0 0 ' + W + ' ' + Hr);
  var rzx = function (z) {
    var L = limT(state.xs === 'raw');
    return RML + (tf(z, state.xs === 'raw') - L[0]) / (L[1] - L[0])
      * (W - RML - MR);
  };
  var out = '';
  var rxt = state.xs === 'raw' ? RAW_TICKS : LOGIT_TICKS;
  rxt.forEach(function (v) {
    var z = logit(Math.min(0.9999, Math.max(0.0001, v / 100)));
    var L = limT(state.xs === 'raw');
    if (tf(z, state.xs === 'raw') <= L[0]
        || tf(z, state.xs === 'raw') >= L[1]) return;
    out += '<line x1="' + rzx(z) + '" y1="' + MT + '" x2="' + rzx(z)
      + '" y2="' + (Hr - MB) + '" stroke="#e0d9c8" '
      + 'stroke-width="0.6"/>'
      + '<text x="' + rzx(z) + '" y="' + (Hr - MB + 17)
      + '" text-anchor="middle" fill="#52514e" font-size="11">'
      + v + '%</text>';
  });
  out += '<text x="' + (RML + (W - RML - MR) / 2) + '" y="'
    + (Hr - 6) + '" text-anchor="middle" fill="#52514e" '
    + 'font-size="12">task difficulty</text>';
  rows.forEach(function (row, k) {
    var y0 = MT + (k + 1) * rh;
    var c = D.shared.configs[row.i];


    var drawnY = null;
    [[state.a / 100, true], [state.c / 100, false]].forEach(function (Q) {
      var lev = Q[0], filled = Q[1], baked = filled ? Math.abs(lev - 0.5) < 1e-9 : Math.abs(lev - 0.01) < 1e-9;
      var blk = baked ? (avgDef ? (filled ? row.r.d50_avg : row.r.d1_avg) : (filled ? row.r.d50 : row.r.d1)) : null;
      if (!filled) drawnY = blk && blk.kde ? blk : null;
      if (blk && blk.kde) {
        var kd = blk.kde, mx = Math.max.apply(null, kd) || 1, d = '', pen = false, z0 = null, zN = null;
        for (var jj = 0; jj < g.length; jj++) {
          if (g[jj] < LIM[0] || g[jj] > LIM[1]) { continue; }
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
      var t = tableAt(avgDef ? row.r.levels_avg : row.r.levels, logit(lev));
      if (!t || t.z == null) return;
      var lo = t.lo != null ? Math.max(LIM[0], Math.min(LIM[1], t.lo)) : t.z, hi = t.hi != null ? Math.max(LIM[0], Math.min(LIM[1], t.hi)) : t.z, zc = Math.max(LIM[0], Math.min(LIM[1], t.z));
      var h = filled ? rh * 0.5 : rh * 0.7, yb = y0 - (filled ? rh * 0.62 : rh * 0.72);
      out += filled
        ? '<rect x="' + rzx(lo).toFixed(1) + '" y="' + yb.toFixed(1) + '" width="' + Math.max(1.5, rzx(hi) - rzx(lo)).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + c.color + '" fill-opacity="0.45" stroke="none" data-mark/>'
        : '<rect x="' + rzx(lo).toFixed(1) + '" y="' + yb.toFixed(1) + '" width="' + Math.max(1.5, rzx(hi) - rzx(lo)).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="none" stroke="' + c.color + '" stroke-width="1.2"' + (c.think ? ' stroke-dasharray="5 3"' : '') + ' data-mark/>';
      out += '<line x1="' + rzx(zc).toFixed(1) + '" y1="' + yb.toFixed(1) + '" x2="' + rzx(zc).toFixed(1) + '" y2="' + (yb + h).toFixed(1) + '" stroke="' + c.color + '" stroke-width="1.6"/>';
    });
    var ltxt = c.label + (drawnY && drawnY.p_censored > 0.05
      ? ' · ' + Math.round(drawnY.p_censored * 100) + '% cens.'
      : '');
    out += '<text x="' + (RML - 6) + '" y="' + (y0 - 3)
      + '" text-anchor="end" font-size="9.5" fill="#52514e"'
      + (ltxt.length > 34
         ? ' textLength="' + (RML - 14)
           + '" lengthAdjust="spacingAndGlyphs"' : '')
      + '>' + ltxt + '</text>';
  });
  document.getElementById('plotg').innerHTML = out;
  document.getElementById('trackg').style.display = 'none';
  document.getElementById('fitline').textContent = '';
  var bakedX = Math.abs(state.a - 50) < 1e-9, bakedY = Math.abs(state.c - 1) < 1e-9;
  var anyShape = rows.some(function (row) { return avgDef ? (row.r.d50_avg && row.r.d1_avg) : (row.r.d50 && row.r.d1); });
  var shapeNote = (bakedX && bakedY && anyShape) ? 'true posterior shapes (crossing draws)'
    : (!anyShape ? 'the 80% band with its median from the fitted tables (this set has no crossing draws)'
       : 'the 80% band with its median at levels other than 50% and 1% (a shape there would need draws the fit does not export); shapes at 50% and 1%');
  document.getElementById('narrate').textContent = 'the spread of the same crossings the dots mark, across the fitted draws (' + (avgDef ? 'average-rate' : 'median-task') + ' definition): filled = the crossing at the x level ' + state.a + '%, outlined = at the y level ' + state.c + '% — ' + shapeNote + ' · ' + visible.length + ' of ' + D.shared.configs.length + ' models · move x or y and the view follows' + (bakedX && bakedY && anyShape ? ' · censored draws are not in a shape (the label notes the fraction)' : '');
  notes();
  stamp();
  paintChips();
}


function vocabNote() {
  var el = document.getElementById('vocabnote'); if (!el) return;
  el.textContent = isCap()
    ? dName('y') + ': the difficulty at which a model\u2019s solve chance is ' + fmtLev(100 - state.c) + '%.'
    : dName('x') + ' and ' + dName('y') + ': the difficulty at which a model\u2019s solve chance is ' + fmtLev(100 - state.a) + '% and ' + fmtLev(100 - state.c) + '%.';
}
function avgWhiskerLabel() {
  var rows = (D.bay && D.bay.rows) || [], nEx = rows.filter(function (r) { return r.avg_source === 'exact'; }).length;
  if (rows.length && nEx === rows.length) return '80% credible band (crossing draws, average-rate)';
  if (!nEx) return D.bay ? D.bay.whisker_label_avg : '';
  return '80% credible band (crossing draws where exported; band-inverted otherwise)';
}
function narrate(visible, nFull) {
  var src = state.src === 'bayes'
    ? 'Bayesian posterior' : houseName().toLowerCase();
  var unfitNote = '';
  var medNote = '';
  if (state.def === 'median' && state.src === 'house'
      && visible.length) {

    var worst = null, worstI = null;
    var gA = Math.round(gidxOf(logit(state.a / 100)));
    var gC = Math.round(gidxOf(logit(state.c / 100)));
    visible.forEach(function (i) {
      var df = D.medById[D.shared.configs[i].id].dfrac;
      var v = Math.min(
        df[Math.max(0, Math.min(df.length - 1, gA))],
        df[Math.max(0, Math.min(df.length - 1, gC))]);
      if (worst === null || v < worst) { worst = v; worstI = i; }
    });
    if (worst !== null)
      medNote = ' · bootstrap support at this pair: down to ' + Math.round(worst * 100) + '% of resamples for some models (per-dot fractions on hover)';
  }
  document.getElementById('narrate').textContent = (bayesNote() ? bayesNote() + ' \u00b7 ' : '')
    + (isCap()
      ? 'x = Capability C (metrics-report definition, difficulty '
        + 'counting chain) · y: ' : '')
    + (state.def === 'median' ? 'median-task chain'
      : 'average-rate chain'
        + (state.src === 'bayes'
           && (D.bay.estimator_version_avg || '')
              .indexOf('band inversion') >= 0
           ? ' (band-inverted interim)' : ''))
    + ' · ' + src + (isCap() ? ' · horizontal: ' + CAP_KEYS[state.xdef].name() + ' (level-free)' : ' · horizontal level ' + state.a + '%') + ' · vertical level '
    + state.c + '% · hold ' + (isCap() ? 'n/a (the Capability view is level-free)' : ({ k: 'K', a: 'horizontal level', c: 'vertical level' })[state.hold]) + unfitNote
    + (undrawn.length ? ' · ' + undrawn.length + ' not drawn: ' + undrawn.join('; ') : '')
    + (beyondArms.length ? ' \u00b7 not drawn, crossing beyond the hardest task at these levels: ' + beyondArms.map(function (i) { return D.shared.configs[i].label; }).join(', ') : '')

    + ' · whiskers ' + state.w
    + (state.w !== 'on' ? ''
       : state.src === 'bayes'
         ? ' · ' + (state.def === 'average'
             ? avgWhiskerLabel() : D.bay.whisker_label)
       : state.def === 'average'
         ? ' (' + (state.wd === 'adj' ? 'correlation-adjusted'
                                      : 'independence') + ' widths)'
         : '')
    + ' · ' + visible.filter(function (i) { return !isRun(i); }).length + ' of ' + mainConfigs().length
    + ' models (' + nFull
    + (state.src === 'bayes'
       ? ' with both crossings in the fitted range)'
       : ' fully measured at this pair)')
    + medNote;
}
var CAPC_CHECKS_RUNNING = false;
function notes() {
  var el = document.getElementById('notes');
  el.textContent = '';
  function warn(html) {
    var w = document.createElement('div');
    w.className = 'warn';
    w.innerHTML = html;
    el.appendChild(w);
  }
  if (state.src === 'bayes') { var uc = D.shared.configs.filter(underCredit); if (uc.length) warn('Under-credited at this cut: passes on wave 2 were counted as failures for ' + uc.map(function (c) { return c.label; }).join(', ') + ' \u2014 their crossings read less capable and less reliable until the re-fit on corrected counts.'); }
  if (state.src === 'bayes') { var cs = D.shared.configs.filter(cleanedScope); if (cs.length) warn('Cleaned fits with a partial scope: ' + cs.map(function (c) { return c.label + ' \u2014 ' + cleanedScope(c); }).join('; ') + '.'); }
  if (state.src === 'bayes') { var ag = D.shared.configs.filter(asGraded); if (ag.length) warn('The fitted curves use the attempts as first graded: ' + ag.map(function (c) { return c.label; }).join(', ') + '. The local-logistic estimator already carries the adopted cleaning.'); }
  var ab = D.bay && D.bay.disclosures && D.bay.disclosures.abandoned_cut;
  if (ab && ab.plain && state.src === 'bayes') warn(ab.plain);
  var noted = D.shared.configs.filter(function (c) { return armNote(c); });
  if (noted.length) warn('Model notes: ' + noted.map(function (c) { return c.label + ' \u2014 ' + armNote(c); }).join('; ') + '.');
  var wa = withheldArms();
  if (wa.length) warn('Not shown: ' + wa.map(function (i) { var c = D.shared.configs[i]; return c.label + ' \u2014 ' + WITHHELD[c.id]; }).join('; ') + '.');
  var pa = partialArms();
  if (pa.length) {
    var pnames = pa.map(function (i) { var c = D.shared.configs[i], cv = coverageOf(c); return c.label + ' (' + Math.round(cv.share * 100) + '%)'; });
    warn((partialShown() ? 'Partial models shown greyed and kept out of the fit' : 'Partial models hidden') + ' \u2014 attempts on fewer than 90% of this set\u2019s tasks: ' + pnames.join(', ') + (partialShown() ? '.' : '. The Partial models switch shows them.'));
  }


  if (state.src === 'bayes' && D.bay) {
    var nEx = D.bay.rows.filter(function (r) { return r.avg_source === 'exact'; }).length, nAll = D.bay.rows.length;
    warn(state.def === 'average'
      ? 'Bayesian reliability shown = the average-rate 1% crossing (the default reliability): ' + (nEx === nAll ? 'exact crossing draws for every model.' : nEx ? 'exact crossing draws for ' + nEx + ' of ' + nAll + ' models; the rest band-inverted from the fit\u2019s average-rate curves (an interim estimator).' : 'band-inverted from the fit\u2019s pointwise average-rate curves (an interim estimator).')
      : 'Median-task definition: exact crossing draws from the fit\u2019s levels tables; the default reliability is the average-rate 1% crossing (the \u201cAverage rate\u201d definition), one to two steps of the difficulty scale easier for most models.');
  }

  if (state.src === 'bayes' && D.bay) {
    warn('Reliability and Bayesian capability come from the served Gaussian-task-effect fit; on models with concentrated failures it places the 1% crossing too early by up to 1.3 steps of the difficulty scale and the 50% crossing about 0.5 too late (the bias note); the count-average reading beside them is the check.');
  }
  var flags = D.shared.artifact_flags;
  if (flags) {
    var names = Object.keys(flags.by_cfg).map(function (id) {
      var c2 = D.shared.configs.find(function (c3) { return c3.id === id; });
      return c2 ? c2.label : id;
    });
    warn('\u2020 Artifact defect: positions for '
      + names.join(', ') + ' are NON-QUOTABLE \u2014 their fits ingest '
      + 'defect-flagged cells; dots drawn faded with a red dashed ring '
      + 'until the defect is corrected. ' + (flags.stamp || ''));
  }
  var SPACING_CHECKS_RUNNING = false;
  if ((state.xs === 'raw' || state.ys === 'raw') && SPACING_CHECKS_RUNNING) {
    warn('New spacing toggle \u2014 checks running. Went live on '
      + 'a provisional basis; the check battery runs against '
      + 'it and fixes land in place. Spacing changes where things sit, '
      + 'never what they are \u2014 every reading is identical in both '
      + 'spacings.');
  }
  if (isCap()) {
    var capw = capBlock() && capBlock().by_cfg[
      D.shared.configs[0].id].ci80_z
      ? ' Whiskers: 80% bootstrap interval (task draw, finite attempts, '
        + 'and level re-estimation captured jointly; the model roster is '
        + 'held fixed by construction \u2014 asymmetric whiskers near the '
        + 'floor/ceiling are real, not an error).'
      : '';
    warn((CAPC_CHECKS_RUNNING
        ? 'New option — checks running. This axis went live on '
          + 'a provisional basis; the full check battery is '
          + 'running against it and fixes land in place. '
        : '')
      + 'The two capability definitions (fitted 50% crossing \u00b7 '
      + 'Capability C) agree closely today \u2014 visible divergence '
      + 'between them is exactly the alarm the '
      + 'metrics report '
      + 'describes; this toggle is that watch.' + capw);
  }
  if (state.view === 'ridges' || state.src === 'bayes') {


    var gaps = D.bay.rows.filter(function (r) {
      return r.gap_range_grade;
    }).map(function (r) { return r.d50.median_z - r.d1.median_z; });
    var nEx = D.bay.rows.length - gaps.length;
    var glo = Math.min.apply(null, gaps).toFixed(1);
    var ghi = Math.max.apply(null, gaps).toFixed(1);
    warn('Bayesian reading: '
      + ''
      + ''
      + ''
      + 'The '
      + 'physical content of this scatter is each model\'s '
      + 'GAP between the two crossings: ' + glo + '–' + ghi
      + ' steps of the difficulty scale over the ' + gaps.length
      + ' models with <5% censored deep-crossing mass (' + nEx
      + ' censoring-heavy models excluded from the range; per-model '
      + 'fractions on hover) — much of the correlation is shared '
      + 'construction.');
  }
  if (state.view === 'scatter')
    warn('Reading the drawn slope: it is instrument-loaded in BOTH '
      + 'directions — measurement error attenuates it toward zero '
      + 'while difficulty-axis edge compression inflates it (a true '
      + 'slope of 1 reads ~1.19 through the same pipeline) — so '
      + 'neither above nor below 1 is physical without the '
      + 'corrections.'
      + ''
      + '');
  if (state.def === 'median' && state.src === 'house')
    warn('Median-task chain at deep levels: crossings below the '
      + 'per-task measurement floor are BOUNDS (open triangles '
      + 'pointing toward the uncertain side), never interpolated '
      + 'through censored bins; the average-rate chain reaches deep '
      + 'levels by pooling where the median chain cannot at 128 '
      + 'attempts per task.');
}

var BENCH_NAME = { humaneval: 'wave 1', mbpp: 'wave 1' };
function sampledNote(f) {
  if (!f.n_arms_sampled || f.n_arms_sampled === f.population_M) return '';
  var wh = f.partial_arms_withheld || [], byb = f.n_arms_by_benchmark || {};
  var pending = Object.keys(byb).filter(function (b) { return byb[b] < f.n_arms_sampled; }).map(function (b) { return BENCH_NAME[b] || 'wave 1'; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
  var reasons = f.withheld_reasons || {};
  var parts = wh.map(function (x) { var r = reasons[x]; return x.replace(/^[^/]+\//, '') + (r ? ' \u2014 ' + String(r).split(' (')[0] : ''); });
  var unexplained = wh.some(function (x) { return !reasons[x]; });
  return ' (' + f.n_arms_sampled + ' sampled \u00b7 ' + wh.length + ' withheld: ' + parts.join(', ')
    + (unexplained ? (pending.length ? ', ' + pending.join(' + ') + ' not in this copy' : ', a benchmark not in this copy') : '') + ')';
}


function asOf(ts) {
  var s = String(ts || ''), t = Date.parse(s), out = plainTs(s);
  if (isFinite(t)) { var ageH = (Date.now() - t) / 36e5; if (ageH > 36) out += ' (inputs unchanged for ' + Math.round(ageH / 24) + ' days)'; }
  return out;
}
function bayesNote() {
  if (!(D.bay && (D.bay.interim && D.bay.interim.n || !bayesDefault()))) return '';
  return 'Bayesian: ' + D.bay.rows.length + ' of ' + D.shared.configs.length + ' models with posteriors' + (D.bay.interim && D.bay.interim.n ? ', ' + D.bay.interim.n + ' interim (from the newer fit)' : '') + (bayesDefault() ? '' : ' \u2014 local-logistic estimator shown by default, Bayesian one click away');
}
function recordCount(dataId) {
  var C = D && D.man && D.man.counts_of_record; if (!C) return null;
  var k = { board: 'wave1', top: 'wave2', board_top: 'wave12', 'new': 'new_total', all: 'all' }[dataId];
  return k && C[k] != null ? +C[k] : null;
}
function tasksText(f, dsId) {
  var t = tasksTextBase(f, dsId), rc = D && D.golden ? null : recordCount(D && D.dataId), shown = f.tasks_kept != null ? f.tasks_kept : f.tasks;
  if (rc == null || shown == null || rc === shown) return t;
  var fmt = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); };
  var clause = rc < shown ? 'the kept count is now ' + fmt(rc) + '; this fit frame predates a withdrawal' : 'the kept count is ' + fmt(rc) + '; the rest is not on this axis';
  return /\)$/.test(t) ? t.replace(/\)$/, '; ' + clause + ')') : t + ' (' + clause + ')';
}
function tasksTextBase(f, dsId) {
  if (f.tasks_kept != null && f.tasks_kept !== f.tasks) return f.tasks + ' tasks on the axis (' + f.tasks_kept + ' kept; ' + (f.tasks_awaiting_axis != null ? f.tasks_awaiting_axis : f.tasks_kept - f.tasks) + ' are not on this axis)';
  if (f.tasks_on_axis != null) return f.tasks + ' tasks on the axis';
  return f.tasks + (dsId === 'board' ? ' kept tasks' : ' tasks');
}


function heldCheck() { }
var HELD = {};
function setHeld(msg, kind) {
  HELD[kind || 'data'] = msg || '';
  msg = Object.keys(HELD).map(function (k) { return HELD[k]; }).filter(Boolean).join(' ');
  var el = document.getElementById('framebar') || document.querySelector('main') || document.body; if (!el) return;
  var h = document.getElementById('heldline');
  if (!h) { h = document.createElement('div'); h.id = 'heldline';  h.style.cssText = 'color:#8a2f0e;font-size:.85rem;margin:.1rem 0 .3rem'; if (el.id === 'framebar') el.parentNode.insertBefore(h, el); else el.insertBefore(h, el.firstChild); }
  h.textContent = msg; h.hidden = !msg;
  if (msg) h.setAttribute('data-critical-text', ''); else h.removeAttribute('data-critical-text');
}
function frameLine() {
  var el = document.getElementById('framebar'); if (!el || !D || !D.shared) return;
  var f = D.shared.frame || {};
  var base = (D.golden ? 'golden set (12) \u00b7 ' : '') + (DATASETS[D.dataId] ? (DATASETS[D.dataId].frameLabel || DATASETS[D.dataId].label) + ': ' : '') + mainConfigs().length + ' models' + RUNS.filter(function (R) { return R.idx.length && runOnPlane(R); }).map(function (R) { return ' \u00b7 ' + R.name + ': ' + R.clause; }).join('') + ' \u00b7 as of ' + asOf(f.build_ts || f.build_date) + ', ' + CADENCE + '.';

  el.textContent = base;
  if (D.golden) { base += ' ' + String(f.golden_note || 'golden set: a data point, not the difficulty definition').replace(/\s*\([^)]*\)/, '') + '.'; el.textContent = base; }
}


function reliabilityDefinition() {
  var el = document.getElementById('reliability-def'); if (!el || !D.shared) return;
  var f = D.shared.frame, ft = D.bay && D.bay.fit_frame ? D.bay.fit_frame.tasks : f.tasks;
  var frameClause = 'an estimate names the keep-set it was fitted on (the current keep-set ' + f.keep_set_hash
    + (ft !== f.tasks ? '; the fitted rows on this page were fitted on the keep-set before its latest label changes' : '') + ')';
  el.textContent = 'Reliability: the difficulty up to which a model fails fewer than one attempt in a hundred. Its adopted name is the average-rate 1% crossing: '
    + 'the difficulty at which the model\u2019s fitted average failure rate first reaches 1%, on the kept tasks; ' + frameClause + '. '
    + 'Two estimators of this one quantity appear on this site and are named wherever a number is shown: the average-rate estimate (a local-logistic fit of failure rate against pooled task difficulty) '
    + 'and the Bayesian estimate (the posterior-median crossing of the fitted model, band-inverted). They differ most in the 1% tail, so a figure is comparable only with its estimator and its task frame named.';
}


function fitCaption(fit, n) {
  var el = document.getElementById('fitcaption'); if (!el) return;
  var logitFit = !inAxes() || (state.xs !== 'raw' && state.ys !== 'raw');
  var fold = document.getElementById('fitfold');
  if (!fit || !n || state.line === 'off' || state.lw === 'bands' || !logitFit || fit.lo == null) { el.textContent = ''; el.hidden = true; if (fold) fold.hidden = true; return; }
  var xn = dName('x'), yn = dName('y'), xl = fmtLev(state.a) + '%', yl = fmtLev(state.c) + '%';
  var a = fit.a, b = fit.b, ea = Math.exp(a);
  var eaTxt = a < 0 ? '1/' + Math.round(1 / ea) : ea.toFixed(2);
  var aRange = (fit.aLo != null && fit.aHi != null) ? ' [' + fit.aLo.toFixed(2) + ', ' + fit.aHi.toFixed(2) + ']' : '';
  var set = String((DATASETS[state.data] && DATASETS[state.data].label) || state.data).replace(/\s*\([^)]*\)\s*$/, '');
  var runDrawn = anyRunOnPlane() && Array.from(sel).some(function (i) { return isRun(i) && !isHidden(i); });
  var outs = [state.partial === 'show' ? 'the faded partial models' : null, null].filter(Boolean);
  var drawnTxt = outs.length ? 'across the fitted models (' + outs.join(' and ') + ' drawn are not in the fit)' : 'across the drawn models';
  el.hidden = false; if (fold) fold.hidden = false;
  el.textContent = 'Both axes are positions on the difficulty scale. A task’s position is its failure rate averaged over the models that shape the scale (one vote per model), smoothed toward one half by the Jeffreys step on the total attempts, placed on the scale by its odds: one step on the scale multiplies the odds of failure by about 2.7, and positions print as shares (a difficulty of 70% is a task those models fail on 70% of their attempts on average). '
    + xn + ' is the difficulty at which a model’s fitted failure curve crosses ' + xl + ', ' + yn + ' the difficulty at which the same curve crosses ' + yl + '. The line ' + yn + ' = a + b·' + xn + ' is fitted in scale steps ' + drawnTxt + ' (ordinary least squares, every dot equal; equal axes). The slope b is how many steps ' + yn + ' moves for each step of ' + xn + ' across models; with b near one the intercept a is a constant gap: every model’s ' + yn + ' sits |a| steps below its ' + xn + ', the same gap for every model, and the odds of failure at the ' + yn + ' position are e^a times those at the ' + xn + ' position. With b away from one the gap changes by (b − 1) steps per step of ' + xn + ', so the intercept alone is the gap at the scale’s 50% mark. '
    + 'Today: slope ' + b.toFixed(2) + ' [' + fit.lo.toFixed(2) + ', ' + fit.hi.toFixed(2) + '], intercept ' + a.toFixed(2) + aRange + ' steps (e^' + a.toFixed(2) + ' ≈ ' + eaTxt + '), R ' + fit.r.toFixed(2) + ', ' + n + ' models on ' + set + '.';
}
function headline(nFit, fit, nFull, sweeping) {
  var el = document.getElementById('headline'); if (!el) return;
  if (sweeping && !fit) return;
  var capC = isCap();
  var q = capC ? 'Does a model that solves more of the pool also stay reliable further up the difficulty scale?'
               : 'Does a more capable model also stay reliable further up the difficulty scale?';
  var est = state.src === 'bayes' ? 'estimates from the fitted failure curves' : 'estimates from the smoothed failure trend';
  var xw = capC ? CAP_KEYS[state.xdef].name() : dName('x');
  var ans;
  if (fit) {


    ans = 'The fitted line across the models, ' + dName('y') + ' against ' + xw + ': slope ' + fit.b.toFixed(2) + ' [' + fit.lo.toFixed(2) + ', ' + fit.hi.toFixed(2) + '], R ' + fit.r.toFixed(2) + (inAxes() ? ', in the axes as set' : '') + (state.lw === 'bands' ? ', each dot weighted by its bands' : '') + '.';
  } else ans = 'Too few fully measured models at these levels to fit a line (' + nFull + ' measured; the fit needs three).';
  el.textContent = q + ' ' + ans;
}
var frameLineDone = false;
function disclosureLine() {
  var dz = D.bay && D.bay.disclosures; if (!dz) return '';
  var out = '', bt = dz.basis_truncation;
  if (bt && bt.disclosure) out += ' \u00b7 basis: ' + bt.disclosure;
  if (dz.cut_flag && Object.keys(dz.cut_flag).length) out += ' \u00b7 cut flag: ' + Object.keys(dz.cut_flag).map(function (k) { return k.split('/').pop(); }).join(', ') + ' \u2014 answers cut at the 768-token cap on a small share of cells; a flag beside the model, never failures to claim';
  if (dz.pool_cells_undercredit && dz.pool_cells_undercredit.disclosure) out += ' \u00b7 under-credit at this cut: ' + dz.pool_cells_undercredit.disclosure + (dz.pool_cells_undercredit.affected_arms && dz.pool_cells_undercredit.affected_arms.length ? ' (models: ' + dz.pool_cells_undercredit.affected_arms.map(function (k) { return String(k).split('/').pop(); }).join(', ') + ')' : '');
  if (dz.pool_cells_undercredit && dz.pool_cells_undercredit.pending_plain) out += ' \u2014 pending: ' + dz.pool_cells_undercredit.pending_plain;
  if (dz.provisional_classes && dz.provisional_classes.length) out += ' \u00b7 provisional: ' + dz.provisional_classes.map(function (c) { return c['class'] || c; }).join(', ');
  return out;
}
function fitSetCount() {
  var nInt = (D.bay.interim && D.bay.interim.n) || mainRows().filter(function (r) { return r.source === 'interim'; }).length, served = mainRows().length - nInt, n = D.bay.fit_set.n_arms;
  return (served === n ? served + ' models' : served + ' of ' + n + ' models served') + (nInt ? ' · ' + nInt + ' interim' : '');
}
function stamp() {
  if (!frameLineDone) { frameLineDone = true; frameLine(); reliabilityDefinition(); }
  var f = D.shared.frame;


  document.getElementById('stamp').innerHTML =
    '<span data-chain-inv>' + mainConfigs().length + ' models · keep-set ' + f.keep_set_hash + ' · data fingerprint ' + f.runs_fingerprint + (f.runs_window ? ' · runs window ' + plainTs(f.runs_window) : '')
    + ' · axis ' + D.shared.axis.axis_id + (D.golden ? ' · ' + String(f.golden_note || 'golden set: a data point, not the difficulty definition').replace(/\s*\([^)]*\)/, '') : '') + '</span>'
    + (D.bay && D.bay.fit_set && D.bay.fit_set.sha12 ? ' · Bayesian fit set <span data-fit-set>' + D.bay.fit_set.sha12 + '</span> (' + fitSetCount() + ')' : '')
    + ' · <a href="' + MOUNT + 'data/manifest.json">data manifest</a>';
  var more = document.getElementById('stampmore');
  if (!more) { more = document.createElement('div'); more.id = 'stampmore'; more.className = 'sub'; more.style.cssText = 'font-size:.8rem;color:#8b8477;margin:.2rem 0'; var st = document.getElementById('stamp'); st.parentNode.insertBefore(more, st.nextSibling); }
  more.innerHTML = (D.bay ? 'estimators: <span data-chain-val="def src">median-task ' + D.bay.estimator_version + ' · average-rate ' + D.bay.estimator_version_avg + '</span>' : 'estimator: local-logistic average-rate chain (crossing rows from the curves)')
    + (D.shared.capC ? ' · ' + CAP_KEYS.capC.name() + ' <span data-chain-val="xdef">' + D.shared.capC.method_version + '</span>' + (D.shared.capC.frame && D.shared.capC.frame.population_M ? ' (population ' + D.shared.capC.frame.population_M + ')' : '') : '')
    + (D.shared.capC_z ? ' · ' + CAP_KEYS.capC_z.name() + ' <span data-chain-val="xdef">' + D.shared.capC_z.method_version + '</span>' : '')
    + (D.shared.capC_j ? ' · ' + CAP_KEYS.capC_j.name() + ' <span data-chain-val="xdef">' + D.shared.capC_j.method_version + '</span>' : '')
    + (D.shared.artifact_flags ? ' · <span data-chain-val>\u2020 artifact flags active</span>' : '')
    + (D.bay && D.bay.gates && D.bay.gates.line ? ' · ' + D.bay.gates.line : '')
    + disclosureLine();
}


var tipPinned = false;
function hoverWire() {
  var box = document.getElementById('chartbox');
  function showFor(ev) {
    var g = ev.target.closest ? ev.target.closest('[data-i]') : null;
    if (!g || state.view !== 'scatter') { if (ev.type === 'pointerdown' || !tipPinned) { tipPinned = false; Kit.tooltip.hide(); } return; }
    if (ev.type === 'pointerdown' && ev.pointerType === 'touch') tipPinned = true;
    var i = +g.dataset.i;
    var c = D.shared.configs[i];
    var la = logit(state.a / 100), lc = logit(state.c / 100);
    var rx = reading(i, la, 'x'), ry = reading(i, lc, 'y');
    function fmt(r) {
      if (r.z == null) return 'undefined';
      var v = fmtPct(r.z);
      if (r.kind === 'lo-bound') return '≤ ' + v;
      if (r.kind === 'hi-bound') return '≥ ' + v;
      var w = (r.lo != null && r.hi != null)
        ? ' [' + fmtPct(r.lo) + ', ' + fmtPct(r.hi) + ']' : '';
      return v + w;
    }
    var fl = armFlag(i), fe = D.shared.fit_excluded && D.shared.fit_excluded[c.id];
    var cf = D.bay && D.bay.disclosures && D.bay.disclosures.cut_flag && D.bay.disclosures.cut_flag[c.id];
    Kit.tooltip.show(ev.clientX, ev.clientY, [
      { key: c.gates_failed ? '#b3261e' : c.color, value: fmt(rx), label: axisName('x') + (c.gates_failed ? ' \u00b7 flagged fit: ' + (c.gate_flag || 'the fit failed a sampler gate') : '') },
      { key: c.color, value: fmt(ry), label: axisName('y') },
      { key: null, value: '', label: rx.extra },
      { key: null, value: '', label: ry.extra === rx.extra ? '' : ry.extra },
    ].concat(D.moves && D.moves[c.id] ? [{ key: '#8b8477', value: 'moved', label: 'from ' + prevFitName() + ': x ' + D.moves[c.id].dx + ', y ' + D.moves[c.id].dy + ' (percent of the scale)' }] : []).concat(coverageText(c) ? [{ key: null, value: isPartial(i) ? 'partial' : '', label: coverageText(c) }] : []).concat(armNote(c) ? [{ key: '#8b8477', value: 'note', label: armNote(c) }] : []).concat(cf ? [{ key: '#8b8477', value: 'cut flag', label: cf }] : []).concat(fl ? [{ key: '#b3261e', value: '\u2020 non-quotable',
      label: fl.reason + ' \u2014 until ' + fl.until
        + '' }] : []).concat(fe ? [{ key: '#8b8477', value: 'out of the fit population',
      label: (fe.short || 'protocol defect under correction') + (fe.reversible_when ? ' \u2014 reversible when ' + fe.reversible_when : '') + ' (drawn greyed, out of the drawn fit and the difficulty axis)' }] : []), c.label);
  }
  box.addEventListener('pointermove', showFor);
  box.addEventListener('pointerdown', showFor);
  box.addEventListener('pointerleave', function () { if (!tipPinned) Kit.tooltip.hide(); });
  document.addEventListener('pointerdown', function (ev) { if (tipPinned && !box.contains(ev.target)) { tipPinned = false; Kit.tooltip.hide(); } });
}
})();

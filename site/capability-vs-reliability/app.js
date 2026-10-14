/* app.js — the capability-against-reliability page: loads the bundle, mounts the controls, the levels and the chips,
 * and renders. The controls' values live in the address (kit.js), so a link reproduces a view. */
'use strict';

if (window.Kit && Kit.setExportLegendFont) Kit.setExportLegendFont(17);

fetch(MOUNT + 'data/manifest.json')
  .then(function (r) { if (!r.ok) throw new Error('manifest: HTTP ' + r.status); return r.json(); })
  .then(function (man) {
    D.man = man;
    var files = man.files || {};
    return Promise.all(['shared', 'crossings'].map(function (k) {
      return fetch(MOUNT + 'data/' + (files[k] || (k + '.json'))).then(function (r) { if (!r.ok) throw new Error(k + ': HTTP ' + r.status); return r.json(); });
    }));
  })
  .then(function (all) {
    D.shared = all[0]; D.cross = all[1];
    prepare();
    boot();
  })
  .catch(function (e) {
    var el = document.getElementById('headline');
    if (el) { el.textContent = 'The chart did not draw: ' + String(e && e.message || e); el.setAttribute('role', 'alert'); el.id = 'failline'; }
  });

/* The joins: the crossing rows by model id, the levels as logits, the scale's reach. */
function prepare() {
  D.crossById = {};
  (D.cross.rows || []).forEach(function (r) { D.crossById[r.id] = r; });
  D.cross.lev_logit = (D.cross.levels_fail_rate || []).map(function (p) { return Math.log(p / (1 - p)); });
  if (!D.shared.families) D.shared.families = [];
  if (!D.shared.runs) D.shared.runs = [];
  D.shared.arms.forEach(function (c) { if (c.family == null) c.family = ''; });
}

function boot() {
  LIM = [D.shared.reachable.floor_z - 0.35, D.shared.reachable.top_z + 0.35];
  var zFloor = logit(AXIS_FLOOR_PCT / 100) - 0.15;
  if (LIM[0] > zFloor) LIM[0] = zFloor;

  /* the selection: from the address when it names models, else every released model (a run's positions open off) */
  sel = new Set();
  var selParam = Kit.state.get('sel', null), selRewrite = false;
  if (selParam !== null && selParam !== '') {
    slugIndex();
    var byKey = {}; D.shared.arms.forEach(function (c, i) { byKey[c.id] = i; byKey[SLUG_OF[i]] = i; byKey[slugify(c.label)] = i; });
    var bad = [];
    selParam.split(',').forEach(function (k) { if (byKey[k] !== undefined) { sel.add(byKey[k]); if (SLUG_OF[byKey[k]] !== k) selRewrite = true; } else if (k) bad.push(k); });
    if (bad.length) selRewrite = true;
    if (!sel.size) { D.shared.arms.forEach(function (_, i) { if (!isRun(i)) sel.add(i); }); selRewrite = true; }
    if (Kit.state.get('partial', 'hide') !== 'show' && sel.size && Array.from(sel).every(isPartial)) {
      dataNote = 'the link named only partial models, which are hidden; every shown model is drawn';
      D.shared.arms.forEach(function (_, i) { if (!isPartial(i) && !isRun(i)) sel.add(i); }); selRewrite = true;
    }
    if (selRewrite) writeSel();
  } else {
    D.shared.arms.forEach(function (_, i) { if (!isRun(i)) sel.add(i); });
  }
  state.a = +Kit.state.get('a', 50);
  state.c = +Kit.state.get('c', 1);
  var row = Kit.filterRow('#controls');
  row.classList.add('kit-static');
  var setLineEl = document.getElementById('setline');
  if (setLineEl) setLineEl.textContent = D.shared.set.label + ' · ' + D.shared.set.models + ' models · ' + Number(D.shared.set.tasks).toLocaleString('en-US') + ' tasks';

  var partialSw = Kit.switchControl({ mount: document.getElementById('armsbar') || row, key: 'partial', label: CONTROL_WORDS.partial.label,
    options: CONTROL_WORDS.partial.options, dflt: 'hide',
    onchange: function (v) { state.partial = v === 'show' ? 'show' : 'hide'; Kit.state.set('partial', state.partial, 'hide'); refreshPartialChips(); if (sel) render(); } });
  if (!partialArms().length) { var psw = document.querySelector('.kit-switch[data-key="partial"]'); if (psw) psw.style.display = 'none'; }
  showDataNote();
  Kit.switchControl({ mount: row, key: 'view', label: CONTROL_WORDS.view.label, options: CONTROL_WORDS.view.options, dflt: 'scatter',
    onchange: function (v) { state.view = v; Kit.state.set('view', state.view, 'scatter'); if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'def', label: CONTROL_WORDS.def.label, options: CONTROL_WORDS.def.options, dflt: 'average',
    onchange: function (v) { state.def = v; Kit.state.set('def', state.def, 'average'); if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'kp', label: CONTROL_WORDS.kp.label, options: CONTROL_WORDS.onoff, dflt: 'off',
    onchange: function (v) { state.kp = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'lad', label: CONTROL_WORDS.lad.label, options: CONTROL_WORDS.onoff, dflt: 'off',
    onchange: function (v) { state.lad = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'w', label: CONTROL_WORDS.w.label, options: CONTROL_WORDS.onoff, dflt: 'on',
    onchange: function (v) { state.w = v; if (sel) render(); } });
  Kit.switchControl({ mount: row, key: 'fitci', label: CONTROL_WORDS.fitci.label, options: CONTROL_WORDS.fitci.options, dflt: 'honest',
    onchange: function (v) { state.fitci = v; if (sel) render(); } });

  ['xs', 'ys'].forEach(function (k) { var v0 = Kit.state.get(k, null); if (v0 !== null && v0 !== 'raw' && v0 !== 'logit') Kit.state.set(k, null, null); });
  var lv0 = Kit.state.get('line', null); if (lv0 !== null && lv0 !== 'off' && lv0 !== 'steps' && lv0 !== 'axes') Kit.state.set('line', null, null);
  var lw0 = Kit.state.get('lw', null); if (lw0 !== null && lw0 !== 'equal' && lw0 !== 'bands') Kit.state.set('lw', null, null);
  var rs0 = Kit.state.get('resid', null); if (rs0 !== null && rs0 !== 'off' && rs0 !== 'on') Kit.state.set('resid', null, null);
  var sb = document.getElementById('spacebar'), moreDet = document.getElementById('morecontrols');
  if (!moreDet && sb) {
    moreDet = document.createElement('details'); moreDet.id = 'morecontrols'; moreDet.className = 'about';
    moreDet.innerHTML = '<summary>' + CONTROL_WORDS.more + '</summary><div class="kit-filter-row kit-static" id="moreswitches"></div><div class="kit-filter-row kit-static" id="morelevels"></div>';
    sb.parentNode.insertBefore(moreDet, sb); moreDet.appendChild(sb);
  }
  [['xs', CONTROL_WORDS.xs.label], ['ys', CONTROL_WORDS.ys.label]].forEach(function (ax) {
    Kit.switchControl({ mount: sb, key: ax[0], label: ax[1], options: CONTROL_WORDS.scale, dflt: 'logit',
      onchange: function (v) { state[ax[0]] = v === 'raw' ? 'raw' : 'logit'; if (sel) render(); } });
  });
  state.xs = Kit.state.get('xs', 'logit') === 'raw' ? 'raw' : 'logit'; state.ys = Kit.state.get('ys', 'logit') === 'raw' ? 'raw' : 'logit';
  Kit.switchControl({ mount: sb, key: 'line', label: CONTROL_WORDS.line.label, options: CONTROL_WORDS.line.options, dflt: 'steps',
    onchange: function (v) { state.line = (v === 'off' || v === 'axes') ? v : 'steps'; if (sel) render(); } });
  var lv = Kit.state.get('line', 'steps'); state.line = (lv === 'off' || lv === 'axes') ? lv : 'steps';
  Kit.switchControl({ mount: sb, key: 'lw', label: CONTROL_WORDS.lw.label, options: CONTROL_WORDS.lw.options, dflt: 'equal',
    onchange: function (v) { state.lw = v === 'bands' ? 'bands' : 'equal'; if (sel) render(); } });
  state.lw = Kit.state.get('lw', 'equal') === 'bands' ? 'bands' : 'equal';
  Kit.switchControl({ mount: sb, key: 'resid', label: CONTROL_WORDS.resid.label, options: CONTROL_WORDS.onoff, dflt: 'off',
    onchange: function (v) { state.resid = v === 'on' ? 'on' : 'off'; if (sel) render(); } });
  state.resid = Kit.state.get('resid', 'off') === 'on' ? 'on' : 'off';

  buildLevels();
  state.view = Kit.state.get('view', 'scatter') === 'ridges' ? 'ridges' : 'scatter';
  state.def = Kit.state.get('def', 'average') === 'median' ? 'median' : 'average';
  state.partial = Kit.state.get('partial', 'hide') === 'show' ? 'show' : 'hide';
  buildChips(); refreshPartialChips();
  hoverWire();
  wireDrag();
  render();
}

function render() {
  syncPresets();
  if (!elA || !sel) return;
  mountExport();
  if (state.view === 'ridges') { renderRidges(); return; }
  if (EXPORTING) { renderScatter(); return; }
  var sweeping = dragActive || !!playTimer;
  if (!sweeping || !CROP) { LIMX = null; LIMY = null; renderScatter(); CROP = cropRange(EXT, LIM); }
  if (CROP) { LIMX = CROP.slice(); LIMY = CROP.slice(); try { renderScatter(); } finally { LIMX = null; LIMY = null; } }
}

/* The question the page answers and the fitted line's readout under it. */
function headline(nFit, fit, nFull, sweeping) {
  var el = document.getElementById('headline'); if (!el) return;
  if (sweeping && !fit) return;
  var q = 'Does a more capable model also stay reliable further up the difficulty scale?';
  var ans = fit
    ? 'The fitted line across the models, ' + dName('y') + ' against ' + dName('x') + ': slope ' + fit.b.toFixed(2) + ' [' + fit.lo.toFixed(2) + ', ' + fit.hi.toFixed(2) + '], R ' + fit.r.toFixed(2) + (inAxes() ? ', in the axes as set' : ', in logit space') + (state.lw === 'bands' ? ', each dot weighted by its bands' : '') + '.'
    : 'Too few point crossings at these levels to fit a line (' + nFull + ' measured; the fit needs three).';
  var fb = document.getElementById('fitbox');
  if (!fb) { fb = document.createElement('div'); fb.id = 'fitbox'; fb.className = 'kit-readout-box'; el.insertAdjacentElement('afterend', fb); }
  var escH = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  el.textContent = q;
  var fm = fit ? /^(.*?: )(slope [-\d.]+ \[[^\]]+\], R [-\d.]+)(.*)$/.exec(ans) : null;
  if (fm) fb.innerHTML = '<span class="fitlead">' + escH(fm[1]) + '</span><b>' + escH(fm[2]) + '</b><span class="fittail">' + escH(fm[3]).replace(/\.\s*$/, '') + ', along a difficulty scale built from the models’ own outcomes, its unit set by the model mix and compressed at the hard end.</span>';
  else fb.textContent = ans;
}

/* The fold under the chart: what the axes and the fitted line mean, in plain words, with the numbers of the view. */
function fitCaption(fit, n) {
  var el = document.getElementById('fitcaption'); if (!el) return;
  var logitFit = !inAxes() || (state.xs !== 'raw' && state.ys !== 'raw');
  var fold = document.getElementById('fitfold');
  if (!fit || !n || state.line === 'off' || state.lw === 'bands' || !logitFit || fit.lo == null) { el.textContent = ''; el.hidden = true; if (fold) fold.hidden = true; return; }
  var xn = dName('x'), yn = dName('y'), xl = fmtLev(state.a) + '%', yl = fmtLev(state.c) + '%';
  var a = fit.a, b = fit.b, ea = Math.exp(a);
  var eaTxt = a < 0 ? '1/' + Math.round(1 / ea) : ea.toFixed(2);
  var aRange = (fit.aLo != null && fit.aHi != null) ? ' [' + fit.aLo.toFixed(2) + ', ' + fit.aHi.toFixed(2) + ']' : '';
  var runDrawn = Array.from(sel).some(function (i) { return isRun(i) && !isHidden(i); });
  var outs = [state.partial === 'show' ? 'the faded partial models' : null, runDrawn ? 'the training runs’ positions' : null].filter(Boolean);
  var drawnTxt = outs.length ? 'across the fitted models (' + outs.join(' and ') + ' drawn are not in the fit)' : 'across the drawn models';
  el.hidden = false; if (fold) fold.hidden = false;
  el.textContent = 'Both axes are positions on the difficulty scale. A task’s position is its failure rate averaged over the models (one vote per model), kept away from 0 and 1 by a small prior on the total attempts, placed on the scale by its odds: one step on the scale multiplies the odds of failure by about 2.7, and positions print as shares (a difficulty of 70% is a task those models fail on 70% of their attempts on average). '
    + xn + ' is the difficulty at which a model’s fitted failure curve crosses ' + xl + ', ' + yn + ' the difficulty at which the same curve crosses ' + yl + '. A straight line is fitted through the models in scale steps ' + drawnTxt + ' (ordinary least squares, every dot equal; equal axes): it gives ' + yn + ' as an intercept a plus a slope b times ' + xn + '. The slope b is how many steps ' + yn + ' moves for each step of ' + xn + ' across models; with b near one the intercept a is a constant gap: every model’s ' + yn + ' sits a steps below its ' + xn + ', the same gap for every model, and the odds of failure at the ' + yn + ' position are e to the power a times those at the ' + xn + ' position. With b away from one the gap changes by (b − 1) steps per step of ' + xn + ', so the intercept alone is the gap at the scale’s 50% mark. '
    + 'A crossing that lies beyond the scale’s end is drawn as an open chevron at the end, pointing to the side it lies beyond, with its band, and is kept out of the fitted line. '
    + 'This view: slope ' + b.toFixed(2) + ' [' + fit.lo.toFixed(2) + ', ' + fit.hi.toFixed(2) + '], intercept ' + a.toFixed(2) + aRange + ' steps (e to the power ' + a.toFixed(2) + ', about ' + eaTxt + '), R ' + fit.r.toFixed(2) + ', ' + n + ' models on ' + D.shared.set.label + '.';
}

/* The line under the chart: the fit's words and the marks' meaning. */
function setLine() {
  var fitEl = document.getElementById('fitline'); if (!fitEl) return;
  fitEl.innerHTML = '<span>' + String(lastFitText || '').replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }) + '</span>'
    + (state.view === 'scatter' ? ' <span style="color:#8b8477">· an open chevron: a crossing at the scale’s end (a bound), pointing to the side it lies beyond, drawn with its band and out of the fit · an open whisker end marks a band that runs past the scale</span>' : '');
}

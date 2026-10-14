/* levels.js — the level controls of the capability-against-reliability page: the two typed levels (x, the failure
 * rate whose crossing is the horizontal position; y, the vertical one), the presets, the fold K = x / y with its slider
 * and chips, the sweep that moves x while y stays, and the drag of either level on the track above the plot. The two
 * levels are independent: moving one never moves the other; K is derived and never capped. Every change is written to
 * the address once it settles. */
'use strict';

var rafId = 0;
function scheduleRender() {
  if (rafId) return;
  rafId = requestAnimationFrame(function () { rafId = 0; render(); });
}

var elA, elC, playBtn;
function buildLevels() {
  var box = document.getElementById('levels');
  function num(label, key, val, onset) {
    var lab = document.createElement('label');
    lab.innerHTML = '<b>' + label + '</b> ';
    var inp = document.createElement('input');
    inp.type = 'number'; inp.min = '0.1'; inp.max = '99.5'; inp.step = 'any'; inp.value = val;
    inp.addEventListener('change', function () {
      var raw = inp.value, n = parseFloat(raw), prev = state[key], name = key === 'a' ? 'x' : 'y';
      if (raw === '' || !isFinite(n)) {
        inputNote = (raw === '' ? 'typed ' + name + ' is empty or not a number' : 'typed ' + name + ' “' + raw + '” is not a level') + '; ' + name + ' kept at ' + prev + '%';
        inp.value = prev; render(); return;
      }
      var v = Math.max(0.1, Math.min(99.5, n));
      inputNote = v !== n ? 'typed ' + name + ' ' + n + '% is outside the 0.1–99.5% range; set to ' + v + '%' : null;
      onset(v);
      var got = state[key];
      if (got !== r2(v)) inputNote = (inputNote ? inputNote + ' · ' : '') + 'typed ' + name + ' ' + v + '% became ' + got + '%';
      render();
    });
    lab.appendChild(inp);
    lab.appendChild(document.createTextNode(' %'));
    box.appendChild(lab);
    return inp;
  }
  elA = num('Horizontal level (failure rate)', 'a', state.a, function (v) { applyLevel('a', v); Kit.state.set('a', String(state.a), '50'); Kit.state.set('c', String(state.c), '1'); render(); });
  elC = num('Vertical level (failure rate)', 'c', state.c, function (v) { applyLevel('c', v); Kit.state.set('a', String(state.a), '50'); Kit.state.set('c', String(state.c), '1'); render(); });
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
  var kOut = document.createElement('span'); kOut.id = 'kOut'; box.appendChild(kOut);
  var kBound = document.createElement('span'); kBound.id = 'kBound'; box.appendChild(kBound);
  var kl = document.createElement('label');
  kl.innerHTML = '<b>fold K</b> ';
  var ks = document.createElement('input');
  ks.type = 'range'; ks.id = 'kSlider'; ks.min = String(-Math.ceil(Math.log2(K_MAX) * 100) / 100);
  ks.max = String(Math.ceil(Math.log2(K_MAX) * 100) / 100); ks.step = '0.01';
  ks.value = String(Math.log2(state.a / state.c));
  ks.setAttribute('aria-label', 'fold K, log2 scale');
  ks.style.width = '9rem';
  ks.addEventListener('input', function () { setK(Math.pow(2, +ks.value)); scheduleRender(); });
  ks.addEventListener('change', function () { Kit.state.set('a', String(state.a), '50'); Kit.state.set('c', String(state.c), '1'); render(); });
  kl.appendChild(ks);
  box.appendChild(kl);
  K_CHIPS.forEach(function (kk) {
    var b = document.createElement('button');
    b.className = 'preset kchip';
    b.textContent = kk + '×';
    b.title = 'set the fold K = ' + kk;
    b.onclick = function () { setK(kk); Kit.state.set('a', String(state.a), '50'); Kit.state.set('c', String(state.c), '1'); render(); };
    box.appendChild(b);
  });
}
function clampLev(v) { return Math.max(0.2, Math.min(99.5, v)); }
function r2(v) { return Math.round(v * 100) / 100; }
function playLabel() { return '▶ sweep x (y stays)'; }
/* A moved level moves alone; the other never follows. */
function applyLevel(key, v) {
  lastMoved = key; if (key === 'a') lockNote = null;
  if (dragActive) inputNote = null;
  v = clampLev(v);
  if (key === 'a') state.a = v; else state.c = v;
  state.a = r2(state.a); state.c = r2(state.c);
  elA.value = state.a; elC.value = state.c;
}
/* The K slider and chips set x = K times y; y never moves. */
function setK(K) {
  K = Math.max(1 / K_MAX, Math.min(K_MAX, K));
  state.a = r2(clampLev(K * state.c));
  elA.value = state.a; elC.value = state.c;
  var ks = document.getElementById('kSlider');
  if (ks) ks.value = Math.log2(state.a / state.c);
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
  var dir = 1, aLo = logit(0.2 / 100), aHi = logit(99.5 / 100);
  playBtn.textContent = 'stop the sweep';
  playTimer = setInterval(function () {
    var cur = logit(state.a / 100), next = cur + dir * 0.12;
    if (next >= aHi) { dir = -1; next = cur; }
    if (next <= aLo) { dir = 1; next = cur; }
    state.a = r2(pct(next)); elA.value = state.a;
    scheduleRender();
  }, 140);
}

/* The sweep tools (the sweep button, the K chips, the note slot) behind one closed fold; the K slider stays in view. */
function foldSweepTools() {
  var lv = document.getElementById('levels'); if (!lv || !playBtn || !playBtn.parentNode) return;
  var det = document.getElementById('sweeptools');
  if (!det) {
    det = document.createElement('details'); det.id = 'sweeptools'; det.className = 'about';
    det.innerHTML = '<summary id="sweepsum">Sweep and fold</summary>';
    var rowEl = document.createElement('div'); rowEl.className = 'kit-filter-row kit-static'; rowEl.id = 'sweeprow'; det.appendChild(rowEl);
    lv.querySelectorAll('.preset.kchip').forEach(function (b) { rowEl.appendChild(b); });
    rowEl.appendChild(playBtn);
    var kb = document.getElementById('kBound'); if (kb) rowEl.appendChild(kb);
    lv.appendChild(det);
  }
  var rowEl2 = document.getElementById('sweeprow');
  var ksl2 = document.getElementById('kSlider'), kll = ksl2 && ksl2.closest('label');
  if (kll) { if (det.parentNode === lv) { if (kll.nextSibling !== det) lv.insertBefore(kll, det); } else if (kll.parentNode !== lv) lv.appendChild(kll); }
  lv.querySelectorAll(':scope > .preset.kchip').forEach(function (b) { rowEl2.appendChild(b); });
  if (playBtn.parentNode !== rowEl2) rowEl2.appendChild(playBtn);
  var kb2 = document.getElementById('kBound'); if (kb2 && kb2.parentNode !== rowEl2) rowEl2.appendChild(kb2);
}

/* On a phone (600 px and under): short labels on the switches, and the rarely touched controls behind one fold. */
var phoneFolded = false;
function phoneFold() {
  if (!(window.matchMedia && window.matchMedia('(max-width:600px)').matches)) return;
  var cc = document.getElementById('chartcontrols'); if (!cc) return;
  var more = document.getElementById('morecontrols');
  if (!more) {
    var SHORT = { xs: { logit: 'logit', raw: 'normal' }, ys: { logit: 'logit', raw: 'normal' }, line: { off: 'Off', steps: 'logit', axes: 'axes as set' }, lw: { equal: 'each dot equal', bands: 'by the 80% uncertainty bands' }, resid: { off: 'Off', on: 'On' }, def: { average: 'average', median: 'median task' } };
    Object.keys(SHORT).forEach(function (k) { document.querySelectorAll('.kit-switch[data-key="' + k + '"] button').forEach(function (b) { if (SHORT[k][b.dataset.value]) b.textContent = SHORT[k][b.dataset.value]; }); });
    more = document.createElement('details'); more.id = 'morecontrols'; more.className = 'about'; more.innerHTML = '<summary>More controls</summary>';
    var moreRow = document.createElement('div'); moreRow.className = 'kit-filter-row kit-static'; moreRow.id = 'moreswitches'; more.appendChild(moreRow);
    var lvRow = document.createElement('div'); lvRow.className = 'kit-filter-row kit-static'; lvRow.id = 'morelevels'; more.appendChild(lvRow);
    cc.appendChild(more);
  }
  var msw = document.getElementById('moreswitches'), mlv = document.getElementById('morelevels');
  ['view', 'kp', 'lad', 'w', 'fitci'].forEach(function (k) { var sw = document.querySelector('#chartcontrols .kit-switch[data-key="' + k + '"]'); if (sw && sw.parentNode !== msw) msw.appendChild(sw); });
  var lv = document.getElementById('levels');
  if (lv) {
    lv.querySelectorAll('.preset:not(.kchip)').forEach(function (b) { if (b.parentNode !== mlv) mlv.appendChild(b); });
    var st = document.getElementById('sweeptools'); if (st && st.parentNode !== more) more.appendChild(st);
  }
  phoneFolded = true;
}

/* The preset matching the current pair reads pressed. */
function syncPresets() {
  document.querySelectorAll('#levels .preset:not(.kchip), #morelevels .preset:not(.kchip)').forEach(function (b) {
    var on = b.dataset.a !== undefined && +b.dataset.a === +state.a && +b.dataset.c === +state.c;
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

/* Dragging a knob on the track moves that level alone; the address is written once on release. */
var dragKey = null;
var dragActive = false;
function wireDrag() {
  var svg = document.getElementById('chart');
  svg.addEventListener('touchstart', function (ev) {
    var h = ev.target.closest ? ev.target.closest('[data-handle]') : null;
    if (h) ev.preventDefault();
  }, { passive: false });
  svg.addEventListener('pointerdown', function (ev) {
    var h = ev.target.closest ? ev.target.closest('[data-handle]') : null;
    if (!h) return;
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
    applyLevel(dragKey, v);
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

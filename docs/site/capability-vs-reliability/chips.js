/* chips.js — the model chips of the capability-against-reliability page: one chip per model, grouped by family in the
 * palette's order and inside a family from the smallest model to the largest, a thinking model right after its plain
 * one; a row per training run with the base model (checkpoint 0) and the run's positions in step order; the all and
 * none buttons per family; the partial-models state. A chip toggles its model in the selection, which the page writes
 * to its address (the sel parameter) as the slugs of the names of record. Reads the plane module's data and state. */
'use strict';

function famLabel(f) { return f; }
/* The families in the palette's order; a model whose family the palette does not list comes last. */
function famRank(f) { var i = (D.shared.families || []).indexOf(f); return i < 0 ? 1e6 : i; }
function famOrder(indices) {
  return indices.slice().sort(function (a, b) {
    var ca = D.shared.arms[a], cb = D.shared.arms[b];
    var fa = famRank(ca.family), fb = famRank(cb.family);
    return fa !== fb ? fa - fb : a - b;
  });
}

function refreshPartialChips() {
  chips.forEach(function (b) { var i = +b.dataset.idx, c = D.shared.arms[i]; if (!c) return;
    var words = [];
    if (c.think) words.push('thinking form — an open marker on the chart');
    if (c.run) words.push(c.run_name + ' · ' + c.step + ' steps');
    if (c.gates_failed) words.push('the fit failed a sampler check; the point is drawn faded');
    var base = words.join(' · ');
    if (isPartial(i)) {
      if (partialShown()) { b.disabled = false; b.removeAttribute('aria-disabled'); b.classList.remove('partial'); b.classList.add('partialshown'); b.title = capTitle((base ? base + ' · ' : '') + 'partial model (' + coverageText(c) + '), shown greyed'); }
      else { b.disabled = true; b.setAttribute('aria-disabled', 'true'); b.classList.add('partial'); b.classList.remove('partialshown'); b.title = capTitle('partial model (' + coverageText(c) + '), hidden; the Partial models switch shows it'); }
    } else { b.title = base ? capTitle(base) : ''; }
  });
}

function refreshBeyondChips() {
  var B = {}; beyondArms.forEach(function (i) { B[i] = true; });
  chips.forEach(function (b) { var i = +b.dataset.idx; if (B[i]) { b.dataset.beyondTitle = '1'; b.title = 'at the edge: its crossing lies beyond the hardest task at these levels'; } else if (b.dataset.beyondTitle) { b.classList.remove('beyond'); delete b.dataset.beyondTitle; b.title = ''; refreshPartialChips(); } });
}

function writeSel() {
  if (!Object.keys(SLUG_OF).length) slugIndex();
  var all = sel.size === D.shared.arms.length;
  Kit.state.set('sel', all ? null : Array.from(sel).sort(function (p, q) { return p - q; }).map(function (i) { return SLUG_OF[i] || D.shared.arms[i].id; }).join(','), null);
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
  var psw = document.querySelector('#armsbar .kit-switch[data-key="partial"]'); if (psw) box.appendChild(psw);

  var mainIdx = [];
  D.shared.arms.forEach(function (c, i) { if (!c.run) mainIdx.push(i); });
  var ordered = famOrder(mainIdx);
  var fams = [];
  ordered.forEach(function (i) {
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
    nm.className = 'fam'; nm.style.color = D.shared.arms[f.members[0]].color; nm.textContent = famLabel(f.name); nm.title = 'select or clear every ' + famLabel(f.name) + ' model';
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
        bc.title = D.shared.arms[bi].label + ' — the model the run started from, the same point as its chip in the list above';
        line.appendChild(bc);
      }
      idx.forEach(function (i) { var ch = makeChip(i); ch.textContent = (D.shared.arms[i].step != null ? D.shared.arms[i].step + ' steps' : D.shared.arms[i].label); ch.title = D.shared.arms[i].label; line.appendChild(ch); });
      rbox.appendChild(line);
    });
  }

  var oldKey = document.getElementById('runkey'); if (oldKey) oldKey.remove();
  var key = document.createElement('div'); key.className = 'kit-run-key'; key.id = 'runkey'; key.hidden = true; key.innerHTML = runKeyHtml();
  var host = document.getElementById('keyhost');
  if (host) host.appendChild(key); else if (rbox) rbox.appendChild(key); else box.insertAdjacentElement('afterend', key);
}

/* The key to the marks: the bound chevron and, when a training run is drawn, the runs' marks (the shape names the
 * failure count the run trains on, darker is later in training, the dot a minor departure from the plain recipe, the
 * open mark the thinking form). */
function runKeyHtml() {
  if (!window.Kit || typeof Kit.runMarkSvg !== 'function') return '';
  var ink = '#52514e', bg = '#fcfaf3', R = 3.6;
  var svg = function (inner) { return '<svg viewBox="0 0 14 14" aria-hidden="true">' + inner + '</svg>'; };
  var glyph = function (mark) {
    if (mark === 'darker') return svg(Kit.runMarkSvg(3, 7, 2.2, { shape: 'circle', color: '#c9c3b6', bg: bg }) + Kit.runMarkSvg(7.5, 7, 2.2, { shape: 'circle', color: '#8b8477', bg: bg }) + Kit.runMarkSvg(12, 7, 2.2, { shape: 'circle', color: ink, bg: bg }));
    if (mark === 'dot') return svg(Kit.runMarkSvg(7, 7, R, { shape: 'circle', dot: true, color: ink, bg: bg }));
    if (mark === 'open') return svg(Kit.runMarkSvg(7, 7, R, { shape: 'circle', open: true, color: ink, bg: bg }));
    return svg(Kit.runMarkSvg(7, 7, R, { shape: mark, color: ink, bg: bg }));
  };
  var out = '<span data-row="bound" hidden title="a crossing that lies beyond the scale’s end is drawn as an open chevron at the end, pointing to the side it lies beyond, with its band, and is kept out of the fitted line">' + svg('<path d="M2 10.5l5 -8l5 8" fill="none" stroke="' + ink + '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>') + '<span>a crossing beyond the scale, on the side it points</span></span>';
  if (typeof Kit.runMarksKey === 'function') out += Kit.runMarksKey().map(function (r) { return '<span data-row="' + r.mark + '" hidden' + (r.title ? ' title="' + capTitle(String(r.title)).replace(/"/g, '&quot;') + '"' : '') + '>' + glyph(r.mark) + '<span>' + r.text + '</span></span>'; }).join('');
  return out;
}
function refreshRunKey() {
  var keyEl = document.getElementById('runkey'); if (!keyEl) return;
  var anyBound = !!document.querySelector('path[data-mark][data-shape="bound"]');
  var runsOn = Array.from(sel).some(function (i) { return isRun(i) && !!runMarkOf(i); });
  keyEl.querySelectorAll(':scope > span').forEach(function (sp) { sp.hidden = sp.dataset.row === 'bound' ? !anyBound : !runsOn; });
  keyEl.hidden = !(anyBound || runsOn);
}

function paintChips() {
  refreshRunKey();
  chips.forEach(function (b) {
    b.classList.toggle('off', !sel.has(+b.dataset.idx));
    b.setAttribute('aria-pressed', sel.has(+b.dataset.idx) ? 'true' : 'false');
    var c = D.shared.arms[+b.dataset.idx] || {}, nofit = !D.crossById[c.id];
    b.classList.toggle('nofit', nofit);
    if (nofit) { b.title = 'no fit for this model: not drawn'; b.dataset.nofit = '1'; }
    else if (b.dataset.nofit) { b.title = ''; delete b.dataset.nofit; refreshPartialChips(); }
  });
}

/* kit.js — the pages' shared runtime: the state in the address (Kit.state), the switch and select controls, the filter row, and the training runs' mark grammar. Copied beside each page by the site build. */
(function (global) {
  'use strict';
  var KITJS = '2026-10-14';
  if (global.Kit && global.Kit.state && typeof global.Kit.state.onChange === 'function') { if (global.console && global.Kit.kitjs !== KITJS) console.warn('kit.js loaded twice: ' + global.Kit.kitjs + ' kept, ' + KITJS + ' skipped'); return; }
  var Kit = global.Kit || {};

  Kit.kitjs = KITJS;
  var listeners = [];
  function params() { return new URLSearchParams(location.search); }
  function notify(key, value) { listeners.forEach(function (fn) { try { fn(key, value); } catch (e) { if (global.console) console.error(e); } }); }
  Kit.state = {
    get: function (key, dflt) {
      var v = params().get(key);
      return v === null ? dflt : v;
    },
    among: function (key, dflt, values) {
      var v = Kit.state.get(key, dflt);
      if (values && values.indexOf(v) < 0) { v = dflt; Kit.state.set(key, dflt, dflt); }
      return v;
    },
    set: function (key, value, dflt) {
      var p = params();
      var before = p.toString();
      if (value === null || value === undefined || value === dflt) p.delete(key);
      else p.set(key, value);
      var qs = p.toString();
      if (qs === before) return;
      history.replaceState(null, '',
        location.pathname + (qs ? '?' + qs : '') + location.hash);
      notify(key, value);
    },
    onChange: function (fn) { listeners.push(fn); },
  };
  global.addEventListener('popstate', function () { notify(null, null); });
  Kit.render = function (fn) {
    var pending = false;
    function run() { pending = false; fn(); }
    function schedule() { if (pending) return; pending = true; (global.requestAnimationFrame || function (f) { setTimeout(f, 0); })(run); }
    Kit.state.onChange(schedule);
    run();
    return schedule;
  };
  Kit.switchControl = function (cfg) {
    var el = typeof cfg.mount === 'string'
      ? document.querySelector(cfg.mount) : cfg.mount;
    var valid = function (v) { return cfg.options.some(function (o) { return o.value === v; }); };
    var current = Kit.state.get(cfg.key, cfg.dflt);
    if (!valid(current)) { current = cfg.dflt; Kit.state.set(cfg.key, cfg.dflt, cfg.dflt); }

    var wrap = document.createElement('div');
    wrap.className = 'kit-switch';
    wrap.dataset.key = cfg.key;
    wrap.setAttribute('role', 'group');
    var lab = document.createElement('span');
    lab.className = 'kit-switch-label';
    lab.textContent = cfg.label;
    wrap.appendChild(lab);
    var seg = document.createElement('div');
    seg.className = 'kit-switch-seg';
    wrap.appendChild(seg);

    var buttons = cfg.options.map(function (o) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = o.label;
      b.dataset.value = o.value;
      b.setAttribute('aria-pressed', String(o.value === current));
      b.addEventListener('click', function () { set(o.value); });
      seg.appendChild(b);
      return b;
    });

    seg.addEventListener('keydown', function (ev) {
      var idx = cfg.options.findIndex(function (o) { return o.value === current; });
      var to = null;
      if (ev.key === 'ArrowRight') to = Math.min(idx + 1, cfg.options.length - 1);
      else if (ev.key === 'ArrowLeft') to = Math.max(idx - 1, 0);
      else if (ev.key === 'Home') to = 0;
      else if (ev.key === 'End') to = cfg.options.length - 1;
      if (to !== null && to !== idx) {
        ev.preventDefault();
        set(cfg.options[to].value);
        buttons[to].focus();
      }
    });

    function paint() {
      buttons.forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.dataset.value === current));
      });
    }
    function set(value) {
      if (value === current || !valid(value)) return;
      current = value;
      paint();
      Kit.state.set(cfg.key, value, cfg.dflt);
      if (cfg.onchange) cfg.onchange(value);
    }
    Kit.state.onChange(function (key) {
      if (key !== null && key !== cfg.key) return;
      var v = Kit.state.get(cfg.key, cfg.dflt);
      if (!valid(v)) v = cfg.dflt;
      if (v === current) return;
      current = v; paint();
      if (cfg.onchange) cfg.onchange(v);
    });

    el.appendChild(wrap);
    paint();
    if (cfg.onchange) cfg.onchange(current);
    return { value: function () { return current; },
             set: set, element: wrap };
  };
  Kit.selectControl = function (cfg) {
    var el = typeof cfg.mount === 'string' ? document.querySelector(cfg.mount) : cfg.mount;
    var all = (cfg.options || []).concat((cfg.groups || []).reduce(function (a, g) { return a.concat(g.options || []); }, []));
    var okay = function (v) { var o = all.filter(function (x) { return x.value === v; })[0]; return !!o && !o.disabled; };
    var current = Kit.state.get(cfg.key, cfg.dflt);
    if (!okay(current)) { current = cfg.dflt; Kit.state.set(cfg.key, cfg.dflt, cfg.dflt); }
    var wrap = document.createElement('div');
    wrap.className = 'kit-select'; wrap.dataset.key = cfg.key; wrap.setAttribute('role', 'group');
    var lab = document.createElement('label'); lab.className = 'kit-switch-label'; lab.textContent = cfg.label;
    var id = 'kit-select-' + cfg.key; lab.setAttribute('for', id); wrap.appendChild(lab);
    var sel = document.createElement('select'); sel.id = id; sel.dataset.key = cfg.key;
    function addOpt(parent, o) { var op = document.createElement('option'); op.value = o.value; op.textContent = o.label; if (o.disabled) op.disabled = true; parent.appendChild(op); }
    (cfg.options || []).forEach(function (o) { addOpt(sel, o); });
    (cfg.groups || []).forEach(function (g) { var og = document.createElement('optgroup'); og.label = g.label; (g.options || []).forEach(function (o) { addOpt(og, o); }); sel.appendChild(og); });
    sel.value = current;
    function set(value) {
      var o = all.filter(function (x) { return x.value === value; })[0];
      if (!o || o.disabled || value === current) { sel.value = current; return; }
      current = value; sel.value = value;
      Kit.state.set(cfg.key, value, cfg.dflt);
      if (cfg.onchange) cfg.onchange(value);
    }
    sel.addEventListener('change', function () { set(sel.value); });
    Kit.state.onChange(function (key) {
      if (key !== null && key !== cfg.key) return;
      var v = Kit.state.get(cfg.key, cfg.dflt); if (!okay(v)) v = cfg.dflt;
      if (v === current) return;
      current = v; sel.value = v;
      if (cfg.onchange) cfg.onchange(v);
    });
    wrap.appendChild(sel); el.appendChild(wrap);
    if (cfg.onchange) cfg.onchange(current);
    return { value: function () { return current; }, set: set, element: wrap };
  };
  Kit.filterRow = function (mount) {
    var el = typeof mount === 'string' ? document.querySelector(mount) : mount;
    var row = document.createElement('div');
    row.className = 'kit-filter-row';
    el.appendChild(row);
    return row;
  };
  var SEP = ' · ';
  function fitChip(dst) {
    var src = dst.parentNode && dst.parentNode.querySelector('[data-fit-src]');
    if (!src) return;
    var max = +dst.getAttribute('data-fit-max');
    var maxLines = +dst.getAttribute('data-fit-lines');
    var lh = +dst.getAttribute('data-fit-lh');
    var cx = +dst.getAttribute('x');
    var full = src.textContent.replace(/\s+/g, ' ').trim();
    while (dst.firstChild) dst.removeChild(dst.firstChild);
    var probe = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    dst.appendChild(probe);
    function width(s) { probe.textContent = s; return probe.getComputedTextLength(); }
    var raw = full.split(SEP);
    var boundUnits = raw.filter(function (u) { return !/…\s*$/.test(u); });
    if (boundUnits.length && boundUnits.length < raw.length) raw = boundUnits;
    var units = raw.map(function (u, i) { return u + (i < raw.length - 1 ? ' ·' : ''); });
    var lines = [], cur = '';
    function pushWordWrapped(u) {
      u.split(' ').forEach(function (word) {
        var cand = cur ? cur + ' ' + word : word;
        if (width(cand) <= max || !cur) cur = cand;
        else { lines.push(cur); cur = word; }
      });
    }
    units.forEach(function (u) {
      if (width(u) > max) { pushWordWrapped(u); return; }
      var cand = cur ? cur + ' ' + u : u;
      if (width(cand) <= max || !cur) cur = cand;
      else { lines.push(cur); cur = u; }
    });
    if (cur) lines.push(cur);
    dst.removeChild(probe);
    if (lines.length > maxLines) dst.setAttribute('data-fit-overflow', '1');
    else dst.removeAttribute('data-fit-overflow');
    lines.forEach(function (s, i) {
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      t.setAttribute('x', cx);
      if (i) t.setAttribute('dy', lh);
      t.textContent = s;
      dst.appendChild(t);
    });
  }
  Kit.flowFit = function (root) {
    var scope = root || document;
    var dsts = scope.querySelectorAll('[data-fit-dst]');
    for (var i = 0; i < dsts.length; i++) fitChip(dsts[i]);
  };
  (function armFlowFit() {
    var mo = new MutationObserver(function (muts) {
      var hit = muts.some(function (m) {
        var n = m.target.nodeType === 3 ? m.target.parentNode : m.target;
        if (!n || !n.closest) return false;
        if (n.closest('[data-fit-src]')) return true;
        return m.type === 'childList' && [].some.call(m.addedNodes, function (a) {
          return a.nodeType === 1 && (a.matches && a.matches('svg') || a.querySelector && a.querySelector('[data-fit-src]'));
        });
      });
      if (!hit) return;
      mo.disconnect();
      Kit.flowFit();
      model();
    });
    function model() { mo.observe(document.documentElement, { subtree: true, childList: true, characterData: true }); }
    if (document.readyState === 'loading')
      document.addEventListener('DOMContentLoaded', function () { Kit.flowFit(); model(); });
    else { Kit.flowFit(); model(); }
  })();
  Kit.scrollTables = function (root) {
    var n = 0, tables = (root || document).querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
      var t = tables[i], p = t.parentElement, has = false;
      if (!p || t.closest('code, pre, .kit-table-scroll, .tblwrap, .bleed') || p.closest('table')) continue;
      for (var a = p; a && a !== document.body && a !== document.documentElement; a = a.parentElement) { var cs = getComputedStyle(a); if (/(auto|scroll)/.test(cs.overflowX)) { has = true; break; } }
      if (has) continue;
      var box = document.createElement('div'); box.className = 'kit-table-scroll'; p.insertBefore(box, t); box.appendChild(t); n++;
    }
    return n;
  };
  Kit.phoneCharts = function (root, minPx) {
    minPx = minPx || 10; var n = 0, svgs = (root || document).querySelectorAll('svg');
    for (var i = 0; i < svgs.length; i++) {
      var sv = svgs[i], p = sv.parentElement; if (!p || p.closest('svg, button, nav, footer, table, .kit-chart-scroll')) continue;
      var vb = (sv.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number); if (vb.length !== 4 || !vb[2]) continue;
      var texts = sv.querySelectorAll('text'); if (texts.length < 5) continue;
      var minFont = Infinity; for (var k = 0; k < texts.length; k++) { var f = parseFloat(getComputedStyle(texts[k]).fontSize); if (f && f < minFont) minFont = f; }
      if (!isFinite(minFont)) continue;
      var need = Math.ceil(vb[2] * minPx / minFont);
      if (need > vb[2]) need = Math.ceil(vb[2]);
      var have = p.getBoundingClientRect().width; if (have >= need) continue;
      var box = document.createElement('div'); box.className = 'kit-chart-scroll'; p.insertBefore(box, sv); box.appendChild(sv);
      sv.style.minWidth = need + 'px'; sv.style.height = 'auto'; n++;
    }
    return n;
  };

  var LADDER_FAMILIES = [['Qwen2.5-Coder', /qwen[-\s]?2\.5[-\s]?coder/i], ['Qwen2.5', /qwen[-\s]?2\.5(?![-\s]?coder)/i], ['Qwen3.5', /qwen[-\s]?3\.5/i], ['Qwen3', /qwen[-\s]?3(?![.\d])/i]    ,
    ['Claude', /claude|\bhaiku\b|\bsonnet\b|\bopus\b|\bfable\b/i], ['GLM', /\bglm\b/i], ['Kimi', /\bkimi\b|moonshot|moonlight/i], ['DeepSeek-Coder-V2', /deepseek[-\s]?coder[-\s]?v2/i], ['DeepSeek-Coder', /deepseek[-\s]?coder/i],
    ['DeepSeek-R1-Distill', /r1[-\s]?distill|\bds[-\s]?r1d\b/i], ['DeepSeek-V3', /deepseek[-\s]?v3|deepseek[-\s]?r1[-\s]?0528/i], ['GPT-5', /\bgpt[-\s]?5/i], ['Gemini', /\bgemini\b/i], ['Gemma-4', /\bgemma\b/i], ['OLMo-2', /\bolmo[-\s]?2\b/i], ['Olmo 3', /\bolmo[-\s]?3(?:\.\d+)?\b/i]];
  var LADDERS = { 'Qwen3': [0.6, 1.7, 4, 8, 14, 32], 'Qwen2.5': [0.5, 1.5, 3, 7, 14, 32], 'Qwen2.5-Coder': [0.5, 1.5, 3, 7, 14, 32] };
  Kit.ladderFamily = function (label) { for (var i = 0; i < LADDER_FAMILIES.length; i++) if (LADDER_FAMILIES[i][1].test(label)) return LADDER_FAMILIES[i][0]; return null; };
  Kit.ladderRank = function (label) {
    var fam = Kit.ladderFamily(label); if (!fam) return { family: null, familyIndex: LADDER_FAMILIES.length, rank: null };
    var fi = -1; for (var i = 0; i < LADDER_FAMILIES.length; i++) if (LADDER_FAMILIES[i][0] === fam) fi = i;
    var s = String(label).toLowerCase(), base = null, m;
    if (/b-a\d/.test(s) || fam === 'DeepSeek-V3' || /\(final/.test(s)) return { family: fam, familyIndex: fi, rank: null };
    if (fam === 'Claude') { var t = { haiku: 1, sonnet: 2, opus: 3, fable: 4 }; for (var k in t) if (s.indexOf(k) >= 0) base = t[k]; }
    else if (fam === 'GPT-5') base = /\bnano\b/.test(s) ? 1 : /\bmini\b/.test(s) ? 2 : 3;
    else if (fam === 'Gemini') { m = s.match(/\b(\d\.\d)\b/); base = (m ? parseFloat(m[1]) * 10 : 0) + (/flash[-\s]?lite/.test(s) ? 1 : /flash/.test(s) ? 2 : /pro/.test(s) ? 3 : 2); }
    else { m = s.match(/(\d+(?:\.\d+)?)\s?b\b/); if (m) { base = parseFloat(m[1]); var lad = LADDERS[fam]; if (lad && lad.indexOf(base) >= 0) base = lad.indexOf(base); else if (lad) base = lad.length + base / 1000; } }
    if (base === null) return { family: fam, familyIndex: fi, rank: null };
    m = s.match(/\((?:checkpoint|step)\s*(\d+)\s*[);]/); if (m) base += parseInt(m[1], 10) / 1e6;
    var variant = !m && /\(|\b(?:thinking|think|chat|fine-?tune[sd]?|arm|rl|re-?run|rerun|raw|coverage|solutions?|code|maths?|math|sft|dpo|grpo|lora|tuned|trained)\b/i.test(s.replace(/\b\d+(?:\.\d+)?\s?b\b/, ''));
    return { family: fam, familyIndex: fi, rank: base, variant: variant };
  };
  Kit.sortByLadder = function (labels, labelOf) {
    labelOf = labelOf || function (x) { return String(x); };
    return labels.map(function (x, i) { var r = Kit.ladderRank(labelOf(x)); return { x: x, i: i, fi: r.familyIndex, rank: r.rank, variant: !!r.variant }; })
      .sort(function (a, b) { if (a.fi !== b.fi) return a.fi - b.fi; if (a.rank === null && b.rank === null) return a.i - b.i; if (a.rank === null) return 1; if (b.rank === null) return -1; if (a.rank !== b.rank) return a.rank - b.rank; if (a.variant !== b.variant) return a.variant ? 1 : -1; return a.i - b.i; })
      .map(function (o) { return o.x; });
  };
  var RUN_BANDS = [
    ['fails 1–2/8', /fails?\s*1\s*[–—-]\s*2\s*(?:\/|of)\s*8\b/i, 'circle'],
    ['fails 3–5/8', /fails?\s*3\s*[–—-]\s*5\s*(?:\/|of)\s*8\b/i, 'square'],
    ['fails 6–7/8', /fails?\s*6\s*[–—-]\s*7\s*(?:\/|of)\s*8\b/i, 'triangle'],
    ['fails 1–3/32', /fails?\s*1\s*[–—-]\s*3\s*(?:\/|of)\s*32\b/i, 'circle'],
    ['fails 1–7/8', /solves sometimes|fails?\s*1\s*[–—-]\s*7\s*(?:\/|of)\s*8\b/i, 'diamond'],
    ['all tasks', /(?:^|\bon\s+|,\s*|·\s*)all tasks\b/i, 'diamond']
  ];
  var RUN_VARIANTS = [
    ['fixed', /\bfixed(?:\s+set)?\b/i], ['0 redraws', /\b(?:0|zero|no)\s+re-?draws?\b/i], ['1 redraw', /\b(?:1|one)\s+re-?draws?\b/i], ['2 redraws', /\b(?:2|two)\s+re-?draws?\b/i],
    ['*', /re-?drawn\s+every\s+(?!25\b)\d+(?:\s+steps?)?/i],
    ['*', /\bdrawn from [^,·(]+/i],
    ['*', /\b(?:[A-Za-z][\w-]*\s+)?penalty(?:\s+×\s?\d+)?\b/i],
    ['32 answers', /(?:\/|of)\s*32\b/i], ['the tasks it solves sometimes', /solves sometimes|fails?\s*1\s*[–—-]\s*7\s*(?:\/|of)\s*8\b/i],
    ["a teacher's answers", /passing answers|teacher/i], ['fine-tune', /fine-?tune|\bsft\b/i], ['colder sampling', /colder\s+sampling|\btemperature\s+0\.[0-5]\b/i]
  ];
  Kit.RUN_SHAPES = { circle: 'o', square: 's', triangle: '^', diamond: 'D' };
  Kit.runMarks = function (name) {
    var s = String(name || '').replace(/[⁠​﻿]/g, '').replace(/\s+/g, ' ');
    var band = null, shape = null, i, j;
    for (i = 0; i < RUN_BANDS.length; i++) if (RUN_BANDS[i][1].test(s)) { band = RUN_BANDS[i][0]; shape = RUN_BANDS[i][2]; break; }
    var variants = [];
    for (j = 0; j < RUN_VARIANTS.length; j++) { var vm = s.match(RUN_VARIANTS[j][1]); if (vm) variants.push(RUN_VARIANTS[j][0] === '*' ? vm[0].replace(/\s+/g, ' ').trim() : RUN_VARIANTS[j][0]); }
    if (!band && !variants.length && !/\bRL\b/.test(s)) return null;
    var m = s.match(/(\d+)\s+steps?\b/);
    var cellParts = s.split('\u00b7'); if (cellParts.length >= 2) { cellParts[1].split(/,\s*/).forEach(function (p) { p = p.trim().replace(/\s*\((?:step|checkpoint)?\s*\d+\s*steps?\)\s*$/i, '').trim(); if (!p || p.length > 40 || /^(?:RL|fine-?tune|sft)$/i.test(p) || /^\d+\s+steps?$/i.test(p) || /^\(?(?:step|checkpoint)\s*\d+\)?$/i.test(p) || /^re-?drawn\s+every\s+25(?:\s+steps?)?$/i.test(p)) return; if (RUN_BANDS.some(function (b) { return b[1].test(p); }) || RUN_VARIANTS.some(function (v) { return v[1].test(p); })) return; if (variants.indexOf(p) < 0) variants.push(p); }); }
    var tm = s.match(/·\s*fine-?tune[^·]*?,\s*([^·,]+?)(?:(?:'|’)s)?\s+passing answers/i) || s.match(/([A-Z][\w.-]*(?:\s+[\w.-]+){0,3}?)(?:(?:'|’)s)?\s+passing answers/);
    var teacherName = tm ? tm[1].trim() : null;
    if (!teacherName && /fine-?tune/i.test(s)) { var fparts = (s.split('\u00b7')[1] || '').split(/,\s*/).map(function (x) { return x.replace(/\s*\((?:step|checkpoint)?\s*\d+\s*steps?\)\s*$/i, '').trim(); });
      for (var fq = 1; fq < fparts.length; fq++) { var fw = fparts[fq]; if (!fw || RUN_BANDS.some(function (b) { return b[1].test(fw); }) || /penalty|re-?draw|re-?drawn|fixed|held|all tasks/i.test(fw)) continue; if (/^[A-Z][\w.-]*(?:\s+[\w.-]+){0,3}$/.test(fw) && /\d/.test(fw)) { teacherName = fw; break; } } }
    return { band: band, shape: shape || 'circle', dot: variants.length > 0, variant: variants.length ? variants.join(', ') : null, variants: variants,
      treatment: /fine-?tune|\bsft\b|passing answers/i.test(s) ? 'fine-tune' : 'RL', open: /\(thinking\)|\bthinking\b/i.test(s), steps: m ? parseInt(m[1], 10) : null,
      teacher: teacherName };
  };
  Kit.drawRunMark = function (parent, x, y, r, o) {
    o = o || {}; var ns = 'http://www.w3.org/2000/svg', color = o.color || '#52514e', bg = o.bg || '#fcfaf3', open = !!o.open, shape = o.shape || 'circle';
    var g = document.createElementNS(ns, 'g'), el, pts, k, a;
    g.setAttribute('class', 'kit-run-mark'); g.setAttribute('data-shape', shape); if (o.dot) g.setAttribute('data-dot', '1');
    if (shape === 'square') { el = document.createElementNS(ns, 'rect'); el.setAttribute('x', x - r * 0.9); el.setAttribute('y', y - r * 0.9); el.setAttribute('width', r * 1.8); el.setAttribute('height', r * 1.8); }
    else if (shape === 'triangle') { el = document.createElementNS(ns, 'path'); el.setAttribute('d', 'M' + x + ',' + (y - r * 1.1) + ' L' + (x + r * 1.05) + ',' + (y + r * 0.85) + ' L' + (x - r * 1.05) + ',' + (y + r * 0.85) + ' Z'); }
    else if (shape === 'diamond') { el = document.createElementNS(ns, 'path'); el.setAttribute('d', 'M' + x + ',' + (y - r * 1.2) + ' L' + (x + r * 1.2) + ',' + y + ' L' + x + ',' + (y + r * 1.2) + ' L' + (x - r * 1.2) + ',' + y + ' Z'); }
    else { el = document.createElementNS(ns, 'circle'); el.setAttribute('cx', x); el.setAttribute('cy', y); el.setAttribute('r', r); }
    if (open) { el.setAttribute('fill', bg); el.setAttribute('stroke', color); el.setAttribute('stroke-width', Math.max(1.2, r * 0.36)); } else { el.setAttribute('fill', color); }
    g.appendChild(el);
    if (o.dot) { var d = document.createElementNS(ns, 'circle'); d.setAttribute('class', 'kit-run-dot'); d.setAttribute('cx', x); d.setAttribute('cy', y); d.setAttribute('r', Math.max(1.5, r * 0.3)); d.setAttribute('fill', o.dotColor || (open ? color : bg)); if (o.dotColor) g.setAttribute('data-dot-color', o.dotColor); g.appendChild(d); }
    if (parent) parent.appendChild(g);
    return g;
  };
  Kit.runMarkSvg = function (x, y, r, o) {
    var tmp = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); var g = Kit.drawRunMark(tmp, x, y, r, o); return g.outerHTML;
  };
  Kit.runMarkSignature = function (name, color) {
    var r = Kit.runMarks(name); if (!r) return null;
    return [String(color || '').toLowerCase(), r.shape, r.open ? 'open' : 'filled', r.dot ? 'dot' : 'plain', r.teacher ? 'teacher:' + r.teacher : '', r.treatment].join('|');
  };
  var runBase = function (name) { return String(name || '').replace(/\s*·\s*\d+\s+steps?\s*$/i, '').replace(/\s*\((?:step|checkpoint)?\s*\d+\s*steps?\)\s*$/i, '').trim(); };
  var cellParts = function (name) {
    var cell = runBase(name).split('·')[1] || ''; return cell.split(/\s*,\s*/).map(function (p) { return p.trim(); }).filter(function (p) { return p && !/^(?:RL|fine-?tune|sft)$/i.test(p); });
  };
  var distinguishingParts = function (name, others) {
    var mine = cellParts(name), base = runBase(name), theirs = (others || []).filter(function (o) { return runBase(o) !== base; }).map(cellParts);
    if (!theirs.length) return mine;
    var unique = mine.filter(function (p) { return theirs.every(function (t) { return t.indexOf(p) < 0; }); });
    if (unique.length) return unique;
    return mine.filter(function (p) { return theirs.some(function (t) { return t.indexOf(p) < 0; }); });
  };
  Kit.sharedMarkGroups = function (rows) {
    var by = {}, out = [];
    (rows || []).forEach(function (row) { var sig = Kit.runMarkSignature(row && row.name, row && row.color); if (!sig) return; (by[sig] = by[sig] || []).push(row); });
    Object.keys(by).forEach(function (k) { var g = by[k], runs = {}; g.forEach(function (row) { runs[runBase(row.name)] = 1; }); if (Object.keys(runs).length < 2) return;
      var names = g.map(function (row) { return row.name; }); g.forEach(function (row) { row.endLabel = distinguishingParts(row.name, names).join(', '); }); out.push(g); });
    return out;
  };
  Kit.runEndLabelWords = function (name, others) {
    if (others && others.length) return distinguishingParts(name, others).join(', ');
    var r = Kit.runMarks(name); if (!r) return ''; if (r.variant) return r.variant;
    var cell = runBase(name).split('·')[1]; return cell ? cell.trim() : '';
  };
  Kit.drawRunEndLabel = function (parent, x, y, text, o) {
    o = o || {}; var ns = 'http://www.w3.org/2000/svg', t = document.createElementNS(ns, 'text');
    t.setAttribute('class', 'kit-run-end-label'); t.setAttribute('data-role', 'run-end-label');
    t.setAttribute('x', x + (o.dx != null ? o.dx : 8)); t.setAttribute('y', y + (o.dy != null ? o.dy : 4));
    t.setAttribute('font-size', String(o.size || 11)); t.setAttribute('fill', o.color || '#52514e'); if (o.anchor) t.setAttribute('text-anchor', o.anchor);
    t.setAttribute('paint-order', 'stroke'); t.setAttribute('stroke', o.bg || '#fcfaf3'); t.setAttribute('stroke-width', '3'); t.setAttribute('stroke-linejoin', 'round');
    t.textContent = String(text || ''); if (parent) parent.appendChild(t); return t;
  };
  Kit.RUN_MARKS_KEY = [
    { mark: 'circle', text: 'trains on the tasks it fails 1–2 of 8' },
    { mark: 'square', text: 'fails 3–5 of 8' },
    { mark: 'triangle', text: 'fails 6–7 of 8' },
    { mark: 'diamond', text: 'all tasks' },
    { mark: 'darker', text: 'later in training' },
    { mark: 'dot', text: 'another cadence, a penalty, a teacher’s answers, or another failure count', title: 'a minor departure from the plain recipe, re-drawn every 25 steps and nothing else: another cadence or a fixed set, a penalty, a teacher’s passing answers, or a failure count outside the four shapes; the row says which; where the answers are a teacher’s, the dot takes the teacher’s colour' },
    { mark: 'open', text: 'thinking' }
  ];
  Kit.runMarksKey = function (opts) {
    opts = opts || {}; var rows = Kit.RUN_MARKS_KEY.filter(function (r) { return !opts.omit || opts.omit.indexOf(r.mark) < 0; });
    if (!opts.sentence) return rows.slice();
    var words = { circle: 'a circle', square: 'a square', triangle: 'a triangle', diamond: 'a diamond', darker: 'darker', dot: 'a dot at the centre', open: 'an open mark' };
    return rows.map(function (r) { return words[r.mark] + ': ' + r.text; }).join('; ') + '.';
  };

  global.Kit = Kit;
})(window);

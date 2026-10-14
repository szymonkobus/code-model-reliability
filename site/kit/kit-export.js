/* kit-export.js — the pages' one export method: the chart as drawn with a legend by model family, as PNG or SVG (Kit.exportButton, Kit.exportPlot). Copied beside each page by the site build. */
(function (global) {
  'use strict';
  var Kit = global.Kit = global.Kit || {};
  var FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  var LEGEND_FONT_PX = 17, LEGEND_ROW_H = 26;
  Kit.setExportLegendFont = function (px) { px = Math.round(+px || 17); LEGEND_FONT_PX = px; LEGEND_ROW_H = Math.round(px * 1.5); return px; };
  var STYLE_PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'stroke-opacity',
    'opacity', 'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'letter-spacing', 'visibility', 'display'];
  var NS = 'http://www.w3.org/2000/svg';
  Kit.EXPORT_TEXT = { plotWidth: 1020, plotBox: 780, axisTitle: 52, axisTitleWeight: 700, tick: 36, axisTitleScale: 4, tickScale: 3, margins: { left: 200, right: 40, top: 50, bottom: 130 } };
  Kit.EXPORT_TEXT_PANEL = { plotWidth: 900, axisTitle: 26, axisTitleWeight: 400, tick: 18, axisTitleScale: 2, tickScale: 1.5, margins: { left: 90, right: 30, top: 40, bottom: 62 } };
  Kit.exportTextSizes = function (pageAxisTitlePx, pageTickPx) { return { axisTitle: Math.round(4 * pageAxisTitlePx), tick: Math.round(3 * pageTickPx) }; };
  var FAMILIES = Kit.FAMILIES = [
    ['Qwen2.5-Coder', /qwen[-\s]?2\.5[-\s]?coder/i],
    ['Qwen2.5', /qwen[-\s]?2\.5(?![-\s]?coder)/i],
    ['Qwen3', /qwen[-\s]?3(?![.\d])/i],
    ['Qwen3.5', /qwen[-\s]?3\.5/i],
    ['Claude', /claude|\bhaiku\b|\bsonnet\b|\bopus\b|\bfable\b/i],
    ['GLM', /\bglm\b/i],
    ['Kimi', /\bkimi\b|moonshot/i],
    ['DeepSeek-Coder', /deepseek[-\s]?coder(?![-\s]?v2)/i],
    ['DeepSeek-Coder-V2', /deepseek[-\s]?coder[-\s]?v2/i],
    ['DeepSeek-V3', /deepseek[-\s]?v3/i],
    ['DeepSeek-R1-Distill', /deepseek[-\s]?r1|\br1[-\s]?distill|\bds[-\s]?r1d?\b/i],
    ['GPT-5', /\bgpt[-\s]?5/i],
    ['Gemini', /\bgemini\b/i],
    ['Gemma-4', /\bgemma\b/i],
    ['OLMo-2', /\bolmo[-\s]?2\b/i],
    ['Olmo 3', /\bolmo[-\s]?3(?:\.\d+)?\b/i]
  ];
  var MATCH_ORDER = [10, 8, 7, 9].concat(FAMILIES.map(function (_, i) { return i; }).filter(function (i) { return [7, 8, 9, 10].indexOf(i) < 0; }));
  Kit.familyOf = function (row) {
    var name = row && row.family != null ? String(row.family) : '', label = row && row.label != null ? String(row.label) : '';
    for (var i = 0; i < FAMILIES.length; i++) { if (name && name.toLowerCase() === FAMILIES[i][0].toLowerCase()) return FAMILIES[i][0]; }
    for (var j = 0; j < MATCH_ORDER.length; j++) { var f = FAMILIES[MATCH_ORDER[j]]; if (f[1].test(name || label)) return f[0]; }
    return '';
  };
  Kit.familyRank = function (row) { var f = Kit.familyOf(row); for (var i = 0; i < FAMILIES.length; i++) { if (FAMILIES[i][0] === f) return i; } return FAMILIES.length; };
  Kit.legendByFamily = function (rows) {
    return (rows || []).map(function (r, i) { return { r: r, i: i, k: Kit.familyRank(r) }; })
      .sort(function (a, b) { return a.k - b.k || a.i - b.i; })
      .map(function (x) { return x.r; });
  };

  function inlineStyles(src, dst) {
    var a = src.querySelectorAll('*'), b = dst.querySelectorAll('*');
    for (var i = 0; i < a.length && i < b.length; i++) {
      var cs = getComputedStyle(a[i]); var s = '';
      for (var j = 0; j < STYLE_PROPS.length; j++) { var v = cs.getPropertyValue(STYLE_PROPS[j]); if (v && v !== 'normal' && v !== 'auto') s += STYLE_PROPS[j] + ':' + v + ';'; }
      if (s) b[i].setAttribute('style', s);
      if (b[i].tagName === 'text' || b[i].tagName === 'tspan') b[i].setAttribute('font-family', FONT);
    }
    var root = getComputedStyle(src); dst.setAttribute('font-family', FONT); dst.setAttribute('font-size', root.fontSize || '12px');
  }

  function viewBoxOf(svg) {
    var vb = (svg.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
    if (vb.length === 4 && vb.every(function (n) { return !isNaN(n); })) return { x: vb[0], y: vb[1], w: vb[2], h: vb[3] };
    var r = svg.getBoundingClientRect(); return { x: 0, y: 0, w: r.width || 800, h: r.height || 500 };
  }

  function dataCrop(src, vb) {
    var layers = src.querySelectorAll('[data-layer="data"]'); if (!layers.length) return null;
    var y1 = Infinity, x2 = -Infinity, w = 0, h = 0, marks = 0, x1 = Infinity, y2 = -Infinity;
    for (var i = 0; i < layers.length; i++) { var bb; try { bb = layers[i].getBBox(); } catch (e) { continue; } if (!bb || !bb.width || !bb.height) continue;
      x1 = Math.min(x1, bb.x); y1 = Math.min(y1, bb.y); x2 = Math.max(x2, bb.x + bb.width); y2 = Math.max(y2, bb.y + bb.height); marks += layers[i].querySelectorAll('circle, rect, path, polygon, use').length; }
    if (!isFinite(y1) || marks < 3) return null;
    w = x2 - x1; h = y2 - y1; if (w < vb.w * 0.25 || h < vb.h * 0.25) return null;
    var top = Math.max(vb.y, y1 - h * 0.04), right = Math.min(vb.x + vb.w, x2 + w * 0.04);
    return { x: vb.x, y: top, w: right - vb.x, h: vb.y + vb.h - top };
  }

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function markerSvg(kind, cx, cy, color, bg) {
    var r = 4.5, ground = bg || '#fcfaf3';
    if (typeof kind === 'function') return kind(cx, cy, color) || '';
    if (kind && typeof kind === 'object' && kind.d) {
      var fill = kind.fill === undefined ? color : kind.fill, stroke = kind.stroke === undefined ? (kind.fill === 'none' ? color : 'none') : kind.stroke;
      return '<path d="' + esc(kind.d) + '" transform="translate(' + cx + ',' + cy + ')' + (kind.scale ? ' scale(' + kind.scale + ')' : '') + '" fill="' + esc(fill === 'none' ? ground : fill) + '" stroke="' + esc(stroke) + '" stroke-width="' + (kind.strokeWidth || 1.8) + '"/>';
    }
    if (kind === 'none') return '';
    if (kind === 'square') return '<rect x="' + (cx - r) + '" y="' + (cy - r) + '" width="' + 2 * r + '" height="' + 2 * r + '" fill="' + color + '"/>';
    if (kind === 'open-square') return '<rect x="' + (cx - r) + '" y="' + (cy - r) + '" width="' + 2 * r + '" height="' + 2 * r + '" fill="' + ground + '" stroke="' + color + '" stroke-width="1.8"/>';
    if (kind === 'triangle') return '<path d="M' + cx + ',' + (cy - r) + ' L' + (cx + r) + ',' + (cy + r) + ' L' + (cx - r) + ',' + (cy + r) + ' Z" fill="' + color + '"/>';
    if (kind === 'open-triangle') return '<path d="M' + cx + ',' + (cy - r) + ' L' + (cx + r) + ',' + (cy + r) + ' L' + (cx - r) + ',' + (cy + r) + ' Z" fill="' + ground + '" stroke="' + color + '" stroke-width="1.8"/>';
    if (kind === 'open-circle') return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + ground + '" stroke="' + color + '" stroke-width="1.8"/>';
    if (kind === 'open-diamond') return '<path d="M' + cx + ',' + (cy - r - 1) + ' L' + (cx + r + 1) + ',' + cy + ' L' + cx + ',' + (cy + r + 1) + ' L' + (cx - r - 1) + ',' + cy + ' Z" fill="' + ground + '" stroke="' + color + '" stroke-width="1.8"/>';
    if (kind === 'triangle-down' || kind === 'v') return '<path d="M' + cx + ',' + (cy + r) + ' L' + (cx + r) + ',' + (cy - r) + ' L' + (cx - r) + ',' + (cy - r) + ' Z" fill="' + color + '"/>';
    if (kind === 'diamond' || kind === 'D') return '<path d="M' + cx + ',' + (cy - r - 1) + ' L' + (cx + r + 1) + ',' + cy + ' L' + cx + ',' + (cy + r + 1) + ' L' + (cx - r - 1) + ',' + cy + ' Z" fill="' + color + '"/>';
    if (kind === 'cross' || kind === 'x') return '<path d="M' + (cx - r) + ',' + (cy - r) + ' L' + (cx + r) + ',' + (cy + r) + ' M' + (cx - r) + ',' + (cy + r) + ' L' + (cx + r) + ',' + (cy - r) + '" stroke="' + color + '" stroke-width="2" fill="none"/>';
    if (kind === 'plus' || kind === 'P') return '<path d="M' + cx + ',' + (cy - r - 1) + ' L' + cx + ',' + (cy + r + 1) + ' M' + (cx - r - 1) + ',' + cy + ' L' + (cx + r + 1) + ',' + cy + '" stroke="' + color + '" stroke-width="2.2" fill="none"/>';
    if (kind === 'star' || kind === '*') { var pts = []; for (var k = 0; k < 10; k++) { var a = -Math.PI / 2 + k * Math.PI / 5, rr = k % 2 ? r * 0.45 : r + 1; pts.push((cx + rr * Math.cos(a)).toFixed(2) + ',' + (cy + rr * Math.sin(a)).toFixed(2)); } return '<polygon points="' + pts.join(' ') + '" fill="' + color + '"/>'; }
    if (kind === 'hexagon' || kind === 'h' || kind === 'pentagon' || kind === 'p') { var n = (kind === 'hexagon' || kind === 'h') ? 6 : 5, q = []; for (var j = 0; j < n; j++) { var b = -Math.PI / 2 + j * 2 * Math.PI / n; q.push((cx + (r + 0.5) * Math.cos(b)).toFixed(2) + ',' + (cy + (r + 0.5) * Math.sin(b)).toFixed(2)); } return '<polygon points="' + q.join(' ') + '" fill="' + color + '"/>'; }
    if (kind === 'triangle-left' || kind === '<') return '<path d="M' + (cx - r - 1) + ',' + cy + ' L' + (cx + r) + ',' + (cy - r) + ' L' + (cx + r) + ',' + (cy + r) + ' Z" fill="' + color + '"/>';
    if (kind === 'triangle-right' || kind === '>') return '<path d="M' + (cx + r + 1) + ',' + cy + ' L' + (cx - r) + ',' + (cy - r) + ' L' + (cx - r) + ',' + (cy + r) + ' Z" fill="' + color + '"/>';
    if (kind === 's') return markerSvg('square', cx, cy, color, bg); if (kind === '^') return markerSvg('triangle', cx, cy, color, bg); if (kind === 'o') return markerSvg('circle', cx, cy, color, bg);
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + color + '"/>';
  }

  function dotSvg(cx, cy, kind, color, bg, open, dotColor) {
    var isOpen = open === true || (typeof kind === 'string' && /^open-/.test(kind)), ground = bg || '#fcfaf3';
    return '<circle class="kit-legend-dot" cx="' + cx + '" cy="' + cy + '" r="1.5" fill="' + esc(dotColor || (isOpen ? color : ground)) + '"/>';
  }

  function legendPanel(legend, x, y, maxH, bg, title, fontPx) {
    var F = Math.round(+fontPx || LEGEND_FONT_PX), rowH = Math.round(F * 1.5), k = Math.round(F / 12 * 100) / 100;
    var probe = document.createElementNS(NS, 'svg'); probe.setAttribute('width', 10); probe.setAttribute('height', 10); probe.style.position = 'absolute'; probe.style.left = '-9999px';
    var t = document.createElementNS(NS, 'text'); t.setAttribute('font-family', FONT); t.setAttribute('font-size', String(F)); probe.appendChild(t); document.body.appendChild(probe);
    legend.forEach(function (m) { if (!m || !m.label) return; var l = String(m.label).trim(); if (/^(?:checkpoint\s?\d+|final(?:\s?(?:model|weights))?|start(?:\s?model)?|step\s?\d+)$/i.test(l) && (m.model || m.name || m.base)) m.label = String(m.model || m.name || m.base) + ' · ' + l; });
    var widths = legend.map(function (m) { t.textContent = m.label || ''; return t.getComputedTextLength(); });
    document.body.removeChild(probe);
    var perCol = Math.max(20, Math.floor((maxH - 24) / rowH)), cols = Math.min(4, Math.ceil(legend.length / perCol)); perCol = Math.ceil(legend.length / cols);
    var colWs = [], colX = [0];
    for (var ci = 0; ci < cols; ci++) { var mx = 60; for (var ii = ci * perCol; ii < Math.min(legend.length, (ci + 1) * perCol); ii++) mx = Math.max(mx, widths[ii] || 0); colWs.push(Math.ceil(mx) + 44); if (ci) colX.push(colX[ci - 1] + colWs[ci - 1]); }
    var mark = function (cx, cy, inner) { return k === 1 ? inner : '<g transform="translate(' + cx + ' ' + cy + ') scale(' + k + ') translate(' + (-cx) + ' ' + (-cy) + ')">' + inner + '</g>'; };
    var ty = Math.round(F / 3);
    var out = '<text class="kit-legend-title" x="' + x + '" y="' + (y + F) + '" font-family="' + FONT + '" font-size="' + F + '" font-weight="600" fill="#1a1a1a">' + esc(title || 'Models') + '</text>';
    legend.forEach(function (m, i) {
      var c = Math.floor(i / perCol), r = i % perCol, lx = x + colX[c], ly = y + F + 18 + r * rowH, color = m.color || '#52514e';
      if (m.ramp && m.ramp.length > 1) {
        var gid = 'kit-ramp-' + i + '-' + Math.random().toString(36).slice(2, 7);
        out += '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="1" y2="0">' + m.ramp.map(function (col, kk) { return '<stop offset="' + (m.ramp.length === 1 ? 0 : kk / (m.ramp.length - 1)) + '" stop-color="' + esc(col) + '"/>'; }).join('') + '</linearGradient></defs>';
        out += '<rect x="' + lx + '" y="' + (ly - 4) + '" width="26" height="8" rx="2" fill="url(#' + gid + ')"' + (m.dash ? ' stroke="' + esc(m.ramp[m.ramp.length - 1]) + '" stroke-dasharray="' + esc(m.dash) + '" stroke-width="1"' : '') + '/>';
        if (m.marker && m.marker !== 'none') out += mark(lx + 13, ly, '<g stroke="' + esc(bg || '#fcfaf3') + '" stroke-width="0.8" paint-order="stroke">' + markerSvg(m.marker, lx + 13, ly, m.ramp[m.ramp.length - 1], bg) + '</g>');
        if (m.dot) out += mark(lx + 13, ly, dotSvg(lx + 13, ly, m.marker, m.ramp[m.ramp.length - 1], bg, m.open, m.dotColor));
        out += '<text class="kit-legend-row" data-family="' + esc(Kit.familyOf(m)) + '" x="' + (lx + 34) + '" y="' + (ly + ty) + '" font-family="' + FONT + '" font-size="' + F + '" fill="#1a1a1a">' + esc(m.label) + '</text>';
        return;
      }
      if (m.line !== false && m.width !== 0) out += '<line x1="' + lx + '" y1="' + ly + '" x2="' + (lx + 26) + '" y2="' + ly + '" stroke="' + color + '" stroke-width="' + (m.width || 2) + '"' + (m.dash ? ' stroke-dasharray="' + esc(m.dash) + '"' : '') + '/>';
      out += mark(lx + 13, ly, markerSvg(m.marker || 'circle', lx + 13, ly, color, bg));
      if (m.dot) out += mark(lx + 13, ly, dotSvg(lx + 13, ly, m.marker || 'circle', color, bg, m.open, m.dotColor));
      out += '<text class="kit-legend-row" data-family="' + esc(Kit.familyOf(m)) + '" x="' + (lx + 34) + '" y="' + (ly + ty) + '" font-family="' + FONT + '" font-size="' + F + '" fill="#1a1a1a">' + esc(m.label) + '</text>';
    });
    return { svg: out, width: colX[cols - 1] + colWs[cols - 1], height: Math.min(legend.length, perCol) * rowH + F + 18 };
  }

  Kit.composePlotExport = function (opts) {
    var src = typeof opts.svg === 'function' ? opts.svg() : opts.svg; if (!src) throw new Error('exportPlot: no svg');
    if (!opts.legend && src.getAttribute('data-legend')) { try { opts.legend = JSON.parse(src.getAttribute('data-legend')); } catch (e) { opts.legend = []; } }
    ['title', 'page', 'view', 'stamp'].forEach(function (k) { if (!opts[k] && src.getAttribute('data-' + k)) opts[k] = src.getAttribute('data-' + k); });
    var vb = viewBoxOf(src), crop = opts.crop === 'data' ? (dataCrop(src, vb) || vb) : vb;
    var clone = src.cloneNode(true); inlineStyles(src, clone);
    Array.prototype.forEach.call(clone.querySelectorAll('[data-export="omit"]'), function (el) { el.parentNode && el.parentNode.removeChild(el); });
    if (opts.boldAxisTitles === true) { var tw = String((Kit.EXPORT_TEXT && Kit.EXPORT_TEXT.axisTitleWeight) || 700);
      Array.prototype.forEach.call(clone.querySelectorAll('text[data-role="axis-title"], [data-role="axis-title"] text, text.axis-title, text.axis-label'), function (t) { t.setAttribute('font-weight', tw); var st = t.getAttribute('style') || ''; if (/font-weight:/.test(st)) t.setAttribute('style', st.replace(/font-weight:[^;]*;?/, 'font-weight:' + tw + ';')); }); }
    clone.removeAttribute('width'); clone.removeAttribute('height'); clone.removeAttribute('style'); clone.removeAttribute('class'); clone.removeAttribute('id');
    clone.setAttribute('viewBox', crop.x + ' ' + crop.y + ' ' + crop.w + ' ' + crop.h);
    var plotW = Math.round(crop.w), plotH = Math.round(crop.h), pad = 16, titleH = 0, stampH = 0;
    var legend = opts.legendOrder === 'given' ? (opts.legend || []) : Kit.legendByFamily(opts.legend || []);
    var lg = legend.length ? legendPanel(legend, plotW + pad * 2, pad + titleH, plotH, opts.background || '#fcfaf3', opts.legendTitle, opts.legendFont) : { svg: '', width: 0, height: 0 };
    var W = plotW + pad * 2 + (lg.width ? lg.width + pad : 0), H = pad + titleH + Math.max(plotH, lg.height) + stampH + pad;
    clone.setAttribute('x', pad); clone.setAttribute('y', pad + titleH); clone.setAttribute('width', plotW); clone.setAttribute('height', plotH);
    var bg = opts.background || '#fcfaf3';
    var head = '<svg xmlns="' + NS + '" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="' + FONT + '" data-kit-export="6.8">' +
      '<rect width="' + W + '" height="' + H + '" fill="' + bg + '"/>' +
      '';
    var foot = '</svg>';
    var svgText = head + new XMLSerializer().serializeToString(clone) + lg.svg + foot;
    return { svgText: svgText, width: W, height: H };
  };

  function download(blob, name) {
    var a = document.createElement('a'), url = URL.createObjectURL(blob); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  var KEY_LIKE = /^(?:plot|figure|export|chart|image|download|checkpoint[-_ ]?\d+|ckpt[-_ ]?\d+|final(?:[-_ ]?(?:model|weights))?|start(?:[-_ ]?model)?|step[-_ ]?\d+|\d+)$/i;
  Kit.exportFileBase = function (opts) {
    var SAFE = function (t) { return String(t).replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '-').replace(/-{2,}/g, '-').replace(/\s*-\s*(?=[ _]|$)/g, '').replace(/(^|[ _])-+/g, '$1').replace(/\s+/g, ' ').trim(); };
    var given = opts && opts.fileBase ? String(opts.fileBase).trim() : '';
    if (given && !(KEY_LIKE.test(given) && !/\s/.test(given))) return SAFE(given);
    var legend = (opts && opts.legend) || []; var labels = legend.map(function (m) { return m && m.label ? String(m.label).replace(/\s+/g, ' ').trim() : ''; }).filter(Boolean);
    var d = new Date(); var day = d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0') + '-' + String(d.getUTCDate()).padStart(2, '0');
    var BUDGET = 150; var title = opts && (opts.title || opts.page) ? String(opts.title || opts.page).replace(/\s+/g, ' ').trim() : '';
    if (title.length > BUDGET) { title = title.slice(0, BUDGET); title = title.replace(/\s+\S*$/, ''); }
    var parts = title ? [title] : []; var used = title.length; var taken = 0;
    for (var i = 0; i < labels.length; i++) { var sep = taken ? ' · ' : (parts.length ? ' — ' : ''); var more = (labels.length - (taken + 1)) > 0 ? ' and ' + (labels.length - (taken + 1)) + ' more' : ''; if (used + sep.length + labels[i].length + more.length > BUDGET) break; used += sep.length + labels[i].length; taken++; }
    if (taken) { var names = labels.slice(0, taken).join(' · ') + (labels.length > taken ? ' and ' + (labels.length - taken) + ' more' : ''); parts.push(names); used += (labels.length > taken ? (' and ' + (labels.length - taken) + ' more').length : 0); }
    else if (labels.length) { var allMore = labels.length + ' series'; if (used + 3 + allMore.length <= BUDGET) { parts.push(allMore); used += 3 + allMore.length; } }
    var view = opts && opts.view ? String(opts.view).replace(/\s+/g, ' ').trim() : ''; if (view && used + 3 + view.length <= BUDGET) parts.push(view);
    var base = (parts.join(' — ') || given || 'plot') + ' ' + day;
    return SAFE(base);
  };
  Kit.exportPlot = function (opts) {
    var out = Kit.composePlotExport(opts), base = Kit.exportFileBase(opts);
    if ((opts.format || 'png') === 'svg') { download(new Blob([out.svgText], { type: 'image/svg+xml' }), base + '.svg'); return Promise.resolve(out); }
    var scale = opts.scale || 2;
    return new Promise(function (resolve, reject) {
      var img = new Image(); var url = URL.createObjectURL(new Blob([out.svgText], { type: 'image/svg+xml' }));
      img.onload = function () {
        var cv = document.createElement('canvas'); cv.width = Math.round(out.width * scale); cv.height = Math.round(out.height * scale);
        var ctx = cv.getContext('2d'); ctx.scale(scale, scale); ctx.drawImage(img, 0, 0); URL.revokeObjectURL(url);
        cv.toBlob(function (blob) { if (!blob) { reject(new Error('exportPlot: no PNG')); return; } download(blob, base + '.png'); resolve(out); }, 'image/png');
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('exportPlot: the SVG did not rasterise')); };
      img.src = url;
    });
  };

  function legendRowsOf(legend) {
    if (!legend) return [];
    if (Array.isArray(legend)) return legend.map(function (r) { return { label: r.label || '', color: r.color || '#52514e', dash: r.dash || null, open: !!r.open }; });
    var rows = [];
    Array.prototype.forEach.call(legend.children, function (item) {
      var sw = null; Array.prototype.some.call(item.querySelectorAll('*'), function (el) { var bg = getComputedStyle(el).backgroundColor; if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && el.getBoundingClientRect().width <= 40) { sw = bg; return true; } return false; });
      var words = (item.textContent || '').replace(/\s+/g, ' ').trim(); if (words) rows.push({ label: words, color: sw || getComputedStyle(item).color || '#52514e' });
    });
    return rows;
  }
  Kit.composeCanvasExport = function (opts) {
    var cvs = (opts.canvases || []).filter(Boolean); if (!cvs.length) throw new Error('composeCanvasExport: no canvases');
    var s = opts.scale || 2, pad = 16 * s, titleH = 0, stampH = 0, rowH = LEGEND_ROW_H * s, font = FONT;
    var rows = legendRowsOf(opts.legend), legendH = rows.length ? rows.length * rowH + pad : 0;
    var drawW = 0, drawH = 0; cvs.forEach(function (c) { drawW = Math.max(drawW, c.width); drawH += c.height; });
    var W = Math.max(drawW + pad * 2, 400 * s), H = pad + titleH + drawH + legendH + stampH + pad;
    var out = document.createElement('canvas'); out.width = W; out.height = H; var ctx = out.getContext('2d');
    ctx.fillStyle = opts.background || '#faf6ec'; ctx.fillRect(0, 0, W, H);
    var y = pad;
    cvs.forEach(function (c) { ctx.drawImage(c, pad, y, c.width, c.height); y += c.height; });
    if (rows.length) { y += pad / 2; ctx.font = (LEGEND_FONT_PX * s) + 'px ' + font; ctx.textBaseline = 'middle';
      rows.forEach(function (r) { if (r.dash) { ctx.save(); ctx.strokeStyle = r.color; ctx.lineWidth = 2.5 * s; ctx.setLineDash(r.dash.map(function (d) { return d * s; })); ctx.beginPath(); ctx.moveTo(pad, y + rowH / 2); ctx.lineTo(pad + 14 * s, y + rowH / 2); ctx.stroke(); ctx.restore(); } else if (r.open) { ctx.save(); ctx.strokeStyle = r.color; ctx.lineWidth = 2 * s; ctx.strokeRect(pad + s, y + rowH / 2 - 4 * s, 12 * s, 8 * s); ctx.restore(); } else { ctx.fillStyle = r.color; ctx.fillRect(pad, y + rowH / 2 - 5 * s, 14 * s, 10 * s); } ctx.fillStyle = '#1a1a1a'; ctx.fillText(r.label, pad + 20 * s, y + rowH / 2); y += rowH; }); y += pad / 2; }
    return out;
  };
  Kit.exportCanvas = function (opts) {
    var out = Kit.composeCanvasExport(opts), base = Kit.exportFileBase(opts);
    return new Promise(function (resolve, reject) { out.toBlob(function (blob) { if (!blob) { reject(new Error('exportCanvas: no PNG')); return; } download(blob, base + '.png'); resolve({ width: out.width, height: out.height }); }, 'image/png'); });
  };
  Kit.exportFigureLink = function (container, opts) {
    var wrap = document.createElement('span'); wrap.className = 'kit-export';
    var a = document.createElement('a'); a.className = 'kit-export-btn'; a.href = opts.href; a.download = opts.download || ''; a.textContent = opts.label || 'Download figure'; a.title = 'The figure as drawn, legend inside'; wrap.appendChild(a);
    if (opts.svgHref) { var b = document.createElement('a'); b.className = 'kit-export-btn kit-export-svg'; b.href = opts.svgHref; b.download = ''; b.textContent = 'SVG'; wrap.appendChild(b); }
    (container || document.body).appendChild(wrap); return wrap;
  };

  Kit.exportButton = function (container, factory, opts) {
    opts = opts || {};
    var noSvg = opts.svg === false || (factory && typeof factory === 'object' && !!factory.canvases) || (typeof factory === 'function' && factory.canvas === true);
    var wrap = document.createElement('span'); wrap.className = 'kit-export';
    var b1 = document.createElement('button'); b1.type = 'button'; b1.className = 'kit-export-btn'; b1.textContent = 'Export plot'; b1.title = noSvg ? 'Download this plot as a PNG with its legend' : 'Download this plot as a PNG with a legend of every model, cropped to the data shown';
    var run = function (fmt) { var o = typeof factory === 'function' ? factory() : factory; if (o.canvases) { if (fmt === 'png') Kit.exportCanvas(o).catch(function (e) { console.error(e); }); return; } o.format = fmt; Kit.exportPlot(o).catch(function (e) { console.error(e); }); };
    b1.addEventListener('click', function () { run('png'); }); wrap.appendChild(b1);
    if (!noSvg) { var b2 = document.createElement('button'); b2.type = 'button'; b2.className = 'kit-export-btn kit-export-svg'; b2.textContent = 'SVG'; b2.title = 'The same export as an SVG file'; b2.addEventListener('click', function () { run('svg'); }); wrap.appendChild(b2); }
    (container || document.body).appendChild(wrap); return wrap;
  };
})(typeof window !== 'undefined' ? window : this);

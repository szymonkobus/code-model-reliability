


(function (global) {
  'use strict';
  var Kit = global.Kit = global.Kit || {};
  var FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  var STYLE_PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'stroke-opacity',
    'opacity', 'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'letter-spacing', 'visibility', 'display'];
  var NS = 'http://www.w3.org/2000/svg';
  Kit.EXPORT_TEXT = { plotWidth: 900, axisTitle: 26, tick: 18, axisTitleScale: 2, tickScale: 1.5, margins: { left: 90, right: 30, top: 40, bottom: 62 } };
  Kit.exportTextSizes = function (pageAxisTitlePx, pageTickPx) { return { axisTitle: Math.round(2 * pageAxisTitlePx), tick: Math.round(1.5 * pageTickPx) }; };


  var FAMILIES = Kit.FAMILIES = [
    ['Qwen2.5-Coder', /qwen[-\s]?2\.5[-\s]?coder/i],
    ['Qwen2.5-Instruct', /qwen[-\s]?2\.5(?![-\s]?coder)/i],
    ['Qwen3', /qwen[-\s]?3(?![.\d])/i],
    ['Qwen3.5', /qwen[-\s]?3\.5/i],
    ['Claude', /claude|\bhaiku\b|\bsonnet\b|\bopus\b/i],
    ['GLM', /\bglm\b/i],
    ['Kimi', /\bkimi\b|moonshot/i],
    ['DeepSeek-Coder', /deepseek[-\s]?coder(?![-\s]?v2)/i],
    ['DeepSeek-Coder-V2', /deepseek[-\s]?coder[-\s]?v2/i],
    ['DeepSeek-V3', /deepseek[-\s]?v3/i],
    ['DeepSeek-R1-Distill', /deepseek[-\s]?r1|\br1[-\s]?distill|\bds[-\s]?r1d?\b/i],
    ['GPT-5', /\bgpt[-\s]?5/i],
    ['Gemini', /\bgemini\b/i],
    ['Gemma-4', /\bgemma\b/i],
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
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + color + '"/>';
  }

  function legendPanel(legend, x, y, maxH, bg, title) {
    var rowH = 18, colW = 0, probe = document.createElementNS(NS, 'svg'); probe.setAttribute('width', 10); probe.setAttribute('height', 10); probe.style.position = 'absolute'; probe.style.left = '-9999px';
    var t = document.createElementNS(NS, 'text'); t.setAttribute('font-family', FONT); t.setAttribute('font-size', '12'); probe.appendChild(t); document.body.appendChild(probe);
    var widths = legend.map(function (m) { t.textContent = m.label || ''; return t.getComputedTextLength(); });
    document.body.removeChild(probe);
    colW = Math.ceil(Math.max.apply(null, widths.concat([60]))) + 44;
    var perCol = Math.max(20, Math.floor((maxH - 24) / rowH)), cols = Math.min(4, Math.ceil(legend.length / perCol)); perCol = Math.ceil(legend.length / cols);
    var out = '<text class="kit-legend-title" x="' + x + '" y="' + (y + 12) + '" font-family="' + FONT + '" font-size="12" font-weight="600" fill="#1a1a1a">' + esc(title || 'Models') + '</text>';
    legend.forEach(function (m, i) {
      var c = Math.floor(i / perCol), r = i % perCol, lx = x + c * colW, ly = y + 30 + r * rowH, color = m.color || '#52514e';
      if (m.ramp && m.ramp.length > 1) {
        var gid = 'kit-ramp-' + i + '-' + Math.random().toString(36).slice(2, 7);
        out += '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="1" y2="0">' + m.ramp.map(function (col, k) { return '<stop offset="' + (m.ramp.length === 1 ? 0 : k / (m.ramp.length - 1)) + '" stop-color="' + esc(col) + '"/>'; }).join('') + '</linearGradient></defs>';
        out += '<rect x="' + lx + '" y="' + (ly - 4) + '" width="26" height="8" rx="2" fill="url(#' + gid + ')"' + (m.dash ? ' stroke="' + esc(m.ramp[m.ramp.length - 1]) + '" stroke-dasharray="' + esc(m.dash) + '" stroke-width="1"' : '') + '/>';
        out += '<text class="kit-legend-row" data-family="' + esc(Kit.familyOf(m)) + '" x="' + (lx + 34) + '" y="' + (ly + 4) + '" font-family="' + FONT + '" font-size="12" fill="#1a1a1a">' + esc(m.label) + '</text>';
        return;
      }
      if (m.line !== false && m.width !== 0) out += '<line x1="' + lx + '" y1="' + ly + '" x2="' + (lx + 26) + '" y2="' + ly + '" stroke="' + color + '" stroke-width="' + (m.width || 2) + '"' + (m.dash ? ' stroke-dasharray="' + esc(m.dash) + '"' : '') + '/>';
      out += markerSvg(m.marker || 'circle', lx + 13, ly, color, bg);
      out += '<text class="kit-legend-row" data-family="' + esc(Kit.familyOf(m)) + '" x="' + (lx + 34) + '" y="' + (ly + 4) + '" font-family="' + FONT + '" font-size="12" fill="#1a1a1a">' + esc(m.label) + '</text>';
    });
    return { svg: out, width: cols * colW, height: Math.min(legend.length, perCol) * rowH + 30 };
  }

  Kit.composePlotExport = function (opts) {
    var src = typeof opts.svg === 'function' ? opts.svg() : opts.svg; if (!src) throw new Error('exportPlot: no svg');


    if (!opts.legend && src.getAttribute('data-legend')) { try { opts.legend = JSON.parse(src.getAttribute('data-legend')); } catch (e) { opts.legend = []; } }
    ['title', 'page', 'view', 'stamp'].forEach(function (k) { if (!opts[k] && src.getAttribute('data-' + k)) opts[k] = src.getAttribute('data-' + k); });
    var vb = viewBoxOf(src), crop = opts.crop === 'data' ? (dataCrop(src, vb) || vb) : vb;
    var clone = src.cloneNode(true); inlineStyles(src, clone);
    Array.prototype.forEach.call(clone.querySelectorAll('[data-export="omit"]'), function (el) { el.parentNode && el.parentNode.removeChild(el); });
    clone.removeAttribute('width'); clone.removeAttribute('height'); clone.removeAttribute('style'); clone.removeAttribute('class'); clone.removeAttribute('id');
    clone.setAttribute('viewBox', crop.x + ' ' + crop.y + ' ' + crop.w + ' ' + crop.h);
    var plotW = Math.round(crop.w), plotH = Math.round(crop.h), pad = 16, titleH = opts.title ? 28 : 0, stampH = 22;
    var legend = opts.legendOrder === 'given' ? (opts.legend || []) : Kit.legendByFamily(opts.legend || []);
    var lg = legend.length ? legendPanel(legend, plotW + pad * 2, pad + titleH, plotH, opts.background || '#fcfaf3', opts.legendTitle) : { svg: '', width: 0, height: 0 };
    var W = plotW + pad * 2 + (lg.width ? lg.width + pad : 0), H = pad + titleH + Math.max(plotH, lg.height) + stampH + pad;
    clone.setAttribute('x', pad); clone.setAttribute('y', pad + titleH); clone.setAttribute('width', plotW); clone.setAttribute('height', plotH);
    var bg = opts.background || '#fcfaf3';
    var head = '<svg xmlns="' + NS + '" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="' + FONT + '">' +
      '<rect width="' + W + '" height="' + H + '" fill="' + bg + '"/>' +
      (opts.title ? '<text x="' + pad + '" y="' + (pad + 16) + '" font-size="15" font-weight="600" fill="#1a1a1a">' + esc(opts.title) + '</text>' : '');
    var stamp = [opts.page, opts.view, opts.stamp].filter(Boolean).join(' · ');
    var foot = (stamp ? '<text x="' + pad + '" y="' + (H - pad) + '" font-size="11" fill="#6b675f">' + esc(stamp) + '</text>' : '') + '</svg>';
    var svgText = head + new XMLSerializer().serializeToString(clone) + lg.svg + foot;
    return { svgText: svgText, width: W, height: H };
  };

  function download(blob, name) {
    var a = document.createElement('a'), url = URL.createObjectURL(blob); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  Kit.exportPlot = function (opts) {
    var out = Kit.composePlotExport(opts), base = (opts.fileBase || 'plot').replace(/[^\w.-]+/g, '-');
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

  Kit.exportFigureLink = function (container, opts) {

    var wrap = document.createElement('span'); wrap.className = 'kit-export';
    var a = document.createElement('a'); a.className = 'kit-export-btn'; a.href = opts.href; a.download = opts.download || ''; a.textContent = opts.label || 'Download figure'; a.title = 'The figure as drawn, legend inside'; wrap.appendChild(a);
    if (opts.svgHref) { var b = document.createElement('a'); b.className = 'kit-export-btn kit-export-svg'; b.href = opts.svgHref; b.download = ''; b.textContent = 'SVG'; wrap.appendChild(b); }
    (container || document.body).appendChild(wrap); return wrap;
  };

  Kit.exportButton = function (container, factory) {
    var wrap = document.createElement('span'); wrap.className = 'kit-export';
    var b1 = document.createElement('button'); b1.type = 'button'; b1.className = 'kit-export-btn'; b1.textContent = 'Export plot'; b1.title = 'Download this plot as a PNG with a legend of every model, cropped to the data shown';
    var b2 = document.createElement('button'); b2.type = 'button'; b2.className = 'kit-export-btn kit-export-svg'; b2.textContent = 'SVG'; b2.title = 'The same export as an SVG file';
    var run = function (fmt) { var o = typeof factory === 'function' ? factory() : factory; o.format = fmt; Kit.exportPlot(o).catch(function (e) { console.error(e); }); };
    b1.addEventListener('click', function () { run('png'); }); b2.addEventListener('click', function () { run('svg'); });
    wrap.appendChild(b1); wrap.appendChild(b2); (container || document.body).appendChild(wrap); return wrap;
  };
})(typeof window !== 'undefined' ? window : this);

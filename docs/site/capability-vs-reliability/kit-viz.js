


(function (global) {
  'use strict';
  var Kit = global.Kit = global.Kit || {};


  var tipEl = null;
  function ensureTip() {
    if (tipEl) return tipEl;
    tipEl = document.createElement('div');
    tipEl.className = 'kit-tip';
    tipEl.setAttribute('role', 'tooltip');
    document.body.appendChild(tipEl);
    return tipEl;
  }
  Kit.tooltip = {

    show: function (clientX, clientY, rows, title) {
      var el = ensureTip();
      el.textContent = '';
      if (title) {
        var t = document.createElement('div');
        t.className = 'kit-tip-title';
        t.textContent = title;
        el.appendChild(t);
      }
      rows.forEach(function (r) {
        var row = document.createElement('div');
        row.className = 'kit-tip-row';
        if (r.key) {
          var k = document.createElement('span');
          k.className = 'kit-tip-key';
          k.style.background = r.key;
          row.appendChild(k);
        }
        var v = document.createElement('b');
        v.textContent = r.value;
        row.appendChild(v);
        var l = document.createElement('span');
        l.className = 'kit-tip-label';
        l.textContent = r.label;
        row.appendChild(l);
        el.appendChild(row);
      });
      el.style.display = 'block';
      var w = el.offsetWidth, h = el.offsetHeight;
      var x = Math.min(Math.max(8, clientX + 14), window.innerWidth - w - 8);
      var y = clientY - h - 12;
      if (y < 8) y = clientY + 16;
      el.style.left = x + 'px';
      el.style.top = y + 'px';
    },
    hide: function () { if (tipEl) tipEl.style.display = 'none'; },
  };


  Kit.crosshair = function (cfg) {
    var box = typeof cfg.container === 'string'
      ? document.querySelector(cfg.container) : cfg.container;
    var line = document.createElement('div');
    line.className = 'kit-crosshair';
    box.appendChild(line);
    if (!box.hasAttribute('tabindex')) box.tabIndex = 0;
    var idx = -1;

    function nearest(px) {
      var best = 0, bd = Infinity;
      for (var i = 0; i < cfg.xs.length; i++) {
        var d = Math.abs(cfg.xs[i] - px);
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    }
    function showAt(i, clientY) {
      idx = i;
      line.style.left = cfg.xs[i] + 'px';
      line.style.display = 'block';
      var r = box.getBoundingClientRect();
      var out = cfg.readout(i);
      Kit.tooltip.show(r.left + cfg.xs[i],
        clientY != null ? clientY : r.top + r.height / 3,
        out.rows, out.title);
      if (cfg.onSnap) cfg.onSnap(i);
    }
    function hide() {
      line.style.display = 'none';
      Kit.tooltip.hide();
      idx = -1;
    }

    function onMove(ev) {
      var r = box.getBoundingClientRect();
      showAt(nearest(ev.clientX - r.left), ev.clientY);
    }
    function onKey(ev) {
      if (ev.key === 'Escape') { hide(); return; }
      if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
      ev.preventDefault();
      var i = idx < 0 ? (ev.key === 'ArrowRight' ? 0 : cfg.xs.length - 1)
        : Math.max(0, Math.min(cfg.xs.length - 1,
            idx + (ev.key === 'ArrowRight' ? 1 : -1)));
      showAt(i, null);
    }
    box.addEventListener('pointermove', onMove);
    box.addEventListener('pointerleave', hide);
    box.addEventListener('keydown', onKey);
    box.addEventListener('focus', function () { if (idx < 0) showAt(0, null); });
    box.addEventListener('blur', hide);
    return { destroy: function () {
      box.removeEventListener('pointermove', onMove);
      box.removeEventListener('pointerleave', hide);
      box.removeEventListener('keydown', onKey);
      line.remove(); Kit.tooltip.hide();
    } };
  };


  Kit.hoverMarks = function (container, selector, fn) {
    var box = typeof container === 'string'
      ? document.querySelector(container) : container;
    box.querySelectorAll(selector).forEach(function (el) {
      function show(ev) {
        var out = fn(el);
        var r = el.getBoundingClientRect();
        Kit.tooltip.show(ev && ev.clientX || r.left + r.width / 2,
          ev && ev.clientY || r.top, out.rows, out.title);
      }
      el.addEventListener('pointermove', show);
      el.addEventListener('pointerleave', Kit.tooltip.hide);
      el.addEventListener('focus', function () { show(null); });
      el.addEventListener('blur', Kit.tooltip.hide);
    });
  };
})(window);

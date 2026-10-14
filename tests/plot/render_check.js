// render_check.js <base url> <shots dir> <page>... — a headless read of the built pages with playwright for node: each page at a
// desktop and a phone width; one JSON line per read with the chart's path count, the drawn curves or marks, the chips, the
// console errors, the same-origin responses of 400 or more, the fail line if any, and at desktop width the file the export
// button produced. Run by tests/plot/test_render.py; needs the playwright module on NODE_PATH and its chromium.
'use strict';
const { chromium } = require('playwright');
const base = process.argv[2], shots = process.argv[3], pages = process.argv.slice(4);
const VIEWS = [['desktop', 1280, 900], ['phone', 390, 844]];

(async () => {
  const browser = await chromium.launch();
  let bad = 0;
  for (const page of pages) {
    for (const [view, w, h] of VIEWS) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const p = await ctx.newPage();
      const consoleErrors = [], failed = [];
      p.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
      p.on('pageerror', e => consoleErrors.push(String(e && e.message || e).slice(0, 200)));
      p.on('response', r => { if (r.status() >= 400 && r.url().startsWith(base)) failed.push(r.status() + ' ' + r.url().slice(base.length)); });
      const url = base + page + '/';
      await p.goto(url, { waitUntil: 'networkidle' });
      try { await p.waitForFunction(() => document.querySelector('#failline, [role=alert]') || document.querySelectorAll('svg#chart path').length > 0, null, { timeout: 15000 }); } catch (e) {}
      await p.waitForTimeout(300);
      const out = await p.evaluate(() => {
        const q = s => document.querySelectorAll(s).length;
        const fail = document.querySelector('#failline, [role=alert]:not(#datanote)');
        return {
          paths: q('svg#chart path'), curves: q('#curveg path'), marks: q('#marks path[data-mark]'), chips: q('.chip'),
          switches: q('.kit-switch'), table_rows: q('#crossings tr'), details: q('details'), flags: q('.chip .flag'),
          fail_line: fail && fail.textContent.trim() ? fail.textContent.trim().slice(0, 200) : null,
          title: document.title,
        };
      });
      let exported = null;
      if (view === 'desktop' && await p.$('.kit-export-btn')) {
        try {
          const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 15000 }), p.click('.kit-export-btn')]);
          exported = dl.suggestedFilename();
        } catch (e) { exported = 'FAILED: ' + String(e && e.message || e).slice(0, 120); }
      }
      const row = Object.assign({ page, view }, out, { drawn: out.curves > 0 || out.marks > 0, exported, console_errors: consoleErrors, failed_requests: failed });
      if (!row.drawn || row.fail_line || failed.length || consoleErrors.length || /^FAILED/.test(exported || '')) bad++;
      await p.screenshot({ path: `${shots}/${page}-${view}.png`, fullPage: true });
      console.log(JSON.stringify(row));
      await ctx.close();
    }
  }
  await browser.close();
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(String(e && e.stack || e)); process.exit(2); });

// Renders a .dc.html canvas through the design-viewer dev server and either lists its
// screens or checks them. The runtime drops data-screen-label, so screens are found by id.
//
//   node canvas.cjs list  [file]                 → "ID · name · note" per screen
//   node canvas.cjs check [file] [codes] [outDir] → errors/unresolved/overflow + section PNGs
//
// file defaults to "Pema App.dc.html"; codes is a comma list of group codes to screenshot
// (e.g. "I,J,K"); CANVAS_URL overrides http://localhost:4180 (`npm run dev` in design-viewer/).
const path = require('path');
const { loadPlaywright } = require('./lib/pw.cjs');

const [mode = 'list', file = 'Pema App.dc.html', codes = '', outDir = '.'] = process.argv.slice(2);
const BASE = (process.env.CANVAS_URL || 'http://localhost:4180').replace(/\/$/, '');
const SCREEN_ID = '^[A-Z]\\d+$';

(async () => {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  await page.goto(`${BASE}/${encodeURIComponent(file)}`);
  await page.waitForTimeout(6000);

  const screens = await page.evaluate((pattern) => {
    const re = new RegExp(pattern);
    return [...document.querySelectorAll('div[id]')]
      .filter((el) => re.test(el.id))
      .map((el) => {
        // screen → bezel wrapper → column holding the id badge, name and note.
        const column = el.parentElement.parentElement;
        // The runtime wraps interpolated text in nested spans; leaf spans are [id badge, name].
        const spans = [...column.children[0].querySelectorAll('span')].filter((s) => !s.querySelector('span'));
        const R = el.getBoundingClientRect();
        const overflow = [...el.querySelectorAll('*')].some((c) => {
          const r = c.getBoundingClientRect();
          return r.width > 0 && r.right > R.right + 1;
        });
        return {
          id: el.id,
          name: spans[1]?.innerText ?? '',
          note: column.children[0]?.children[1]?.innerText ?? '',
          unresolved: /\{\{/.test(el.innerText),
          overflow,
        };
      });
  }, SCREEN_ID);

  if (mode === 'list') {
    for (const s of screens) console.log(`${s.id} · ${s.name} · ${s.note.replace(/\s+/g, ' ')}`);
    console.log(`\n${screens.length} screens`);
  } else {
    const bad = screens.filter((s) => s.unresolved || s.overflow);
    console.log(JSON.stringify({ total: screens.length, errors, unresolved: bad.filter((s) => s.unresolved).map((s) => s.id), overflow: bad.filter((s) => s.overflow).map((s) => s.id) }, null, 2));
    for (const code of codes.split(',').filter(Boolean)) {
      const el = await page.$(`section#${code}`);
      if (!el) continue;
      const png = path.join(outDir, `canvas-${code}.png`);
      await el.screenshot({ path: png });
      console.log(`screenshot ${png}`);
    }
    process.exitCode = errors.length || bad.length ? 1 : 0;
  }
  await browser.close();
})();

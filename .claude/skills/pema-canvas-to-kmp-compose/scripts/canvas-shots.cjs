// Renders every screen of the design canvas (`Pema App redesign canvas/Pema App.dc.html`) to
// `<outDir>/<ID>.png` (390×844 dp frame at 2×) – the reference images that KMP jvmTest compares
// against (`shotVsCanvas("F4") { … }` → `build/shots/F4-vs.png`, canvas left | Compose right).
//
//   node canvas-shots.cjs                  → pema-kmp/design-ref/, only if the canvas changed
//   node canvas-shots.cjs --force          → re-render everything
//   node canvas-shots.cjs --only=I1,J3     → re-render only these screens
//   node canvas-shots.cjs --out=<dir>      → another output folder
//
// Skips the browser entirely when the canvas file (and this script) are unchanged since the last
// run (hash in `<outDir>/manifest.json`). Starts the design-viewer (vite, port 4180) itself if it
// is not running and stops it afterwards; CANVAS_URL points at another running viewer.
// Needs Playwright + Chromium once: `npx -y playwright@latest install chromium`.
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { loadPlaywright } = require('../../pema-web-to-canvas/scripts/lib/pw.cjs');

const ROOT = path.resolve(__dirname, '../../../..');
const CANVAS_FILE = 'Pema App.dc.html';
const CANVAS_PATH = path.join(ROOT, 'Pema App redesign canvas', CANVAS_FILE);
const VIEWER_DIR = path.join(ROOT, 'design-viewer');
const SCREEN_ID = /^[A-Z]\d+$/;

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, '').split('=');
    return [k, v ?? true];
  }),
);
const OUT = path.resolve(args.out || path.join(ROOT, 'pema-kmp', 'design-ref'));
const ONLY = typeof args.only === 'string' ? args.only.split(',').map((s) => s.trim()).filter(Boolean) : null;
const BASE = (process.env.CANVAS_URL || 'http://localhost:4180').replace(/\/$/, '');

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const version = sha(Buffer.concat([fs.readFileSync(CANVAS_PATH), fs.readFileSync(__filename)]));
const manifestPath = path.join(OUT, 'manifest.json');

function readManifest() {
  try {
    return JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch {
    return null;
  }
}

function reachable(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureViewer() {
  if (await reachable(BASE)) return null;
  if (process.env.CANVAS_URL) throw new Error(`CANVAS_URL ${BASE} is not reachable.`);
  const vite = path.join(VIEWER_DIR, 'node_modules', 'vite', 'bin', 'vite.js');
  if (!fs.existsSync(vite)) throw new Error('design-viewer dependencies missing: run `npm install` in design-viewer/ once.');
  console.log('starting design-viewer on :4180 …');
  const child = spawn(process.execPath, [vite, '--port', '4180', '--strictPort'], { cwd: VIEWER_DIR, stdio: 'ignore' });
  for (let i = 0; i < 60; i++) {
    if (await reachable(BASE)) return child;
    if (child.exitCode !== null) throw new Error('design-viewer exited (port 4180 busy?).');
    await new Promise((r) => setTimeout(r, 1000));
  }
  child.kill();
  throw new Error('design-viewer did not start within 60 s.');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const previous = readManifest();
  if (!args.force && !ONLY && previous?.version === version &&
      previous.screens.every((id) => fs.existsSync(path.join(OUT, `${id}.png`)))) {
    console.log(`design-ref up to date (${previous.screens.length} screens) → ${OUT}`);
    return;
  }

  const viewer = await ensureViewer();
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(`${BASE}/${encodeURIComponent(CANVAS_FILE)}`);
    await page.waitForFunction(
      (pattern) => [...document.querySelectorAll('div[id]')].some((e) => new RegExp(pattern).test(e.id)),
      SCREEN_ID.source,
      { timeout: 60_000 },
    );
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(1500);
    if (errors.length) throw new Error('canvas errors: ' + errors.join(' | '));

    const all = await page.evaluate(
      (pattern) => [...document.querySelectorAll('div[id]')].map((e) => e.id).filter((id) => new RegExp(pattern).test(id)),
      SCREEN_ID.source,
    );
    const missing = (ONLY || []).filter((id) => !all.includes(id));
    if (missing.length) throw new Error('not in canvas: ' + missing.join(', '));
    const ids = ONLY || all;

    for (const id of ids) {
      const el = await page.$(`div#${id}`);
      await el.scrollIntoViewIfNeeded();
      // Screen + its phone frame (status bar, home indicator) = parent element, as in shotVsCanvas.
      const frame = (await el.evaluateHandle((e) => e.parentElement)).asElement() || el;
      await frame.screenshot({ path: path.join(OUT, `${id}.png`) });
    }

    // Drop images of screens removed from the canvas.
    for (const f of fs.readdirSync(OUT)) {
      const id = f.replace(/\.png$/, '');
      if (f.endsWith('.png') && SCREEN_ID.test(id) && !all.includes(id)) fs.unlinkSync(path.join(OUT, f));
    }
    if (!ONLY) fs.writeFileSync(manifestPath, JSON.stringify({ version, canvas: CANVAS_FILE, screens: all }, null, 2));
    console.log(`${ids.length} screen(s) rendered → ${OUT}`);
  } finally {
    await browser.close();
    viewer?.kill();
  }
})().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});

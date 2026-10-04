#!/usr/bin/env node
// W3a: lists and checks the web canvas ("Pema Web redesign canvas/Pema Web.dc.html"), like canvas.cjs does for the app canvas.
//
//   node web-canvas.cjs list  [file]                       "ID · name · note" per screen (no browser needed)
//   node web-canvas.cjs check [file] [groups] [outDir] [--viewport=1440x900|1920x1020|390x844|all] [--canvas-dir <dir>]
//                             [--viewer-url <url>] [--theme=light|dark] [--frames] [--complete]
//
// check renders the canvas through design-viewer (see below) and reports, as JSON:
//   total / expected / missing   screens rendered vs inventory.json ids of the requested groups (--complete fails on `missing`)
//   frames                       frames rendered at this viewport; frameMismatch = ids whose frame sizes differ from the inventory (D4)
//   errors, unresolved, overflow console errors, `{{ }}` left in a frame, frames with a child wider than the frame
//   badIcons, iconFont           icon names that render as text (wrong Material Symbols name, or the font did not load)
//   tokens, hexInBlocks          CSS variables that differ from tokens.json, colours written as hex outside the token block
// and writes one PNG per group and viewport (web-<group>-<viewport>.png) into outDir; --frames also writes one PNG per frame.
// Exit 0 only when errors, unresolved, overflow, badIcons, tokens, hexInBlocks, frameMismatch and unknown ids are all empty.
//
// Each agent starts its OWN design-viewer (deps are installed in the main checkout):
//   cd <main checkout>/design-viewer && DC_CANVAS_DIR=<worktree>/"Pema Web redesign canvas" npm run dev -- --port <your port>
// and passes --viewer-url http://localhost:<your port>. Without it, CANVAS_URL or http://localhost:4181 is used.
const fs = require('fs');
const path = require('path');
const { loadPlaywright } = require('./lib/pw.cjs');
const lib = require('./lib/web-canvas-lib.cjs');

const argv = process.argv.slice(2);
function take(name) {
  const i = argv.findIndex((a) => a === `--${name}` || a.startsWith(`--${name}=`));
  if (i < 0) return null;
  const a = argv[i];
  if (a.includes('=')) {
    argv.splice(i, 1);
    return a.slice(name.length + 3);
  }
  const next = argv[i + 1];
  if (next !== undefined && !next.startsWith('--')) {
    argv.splice(i, 2);
    return next;
  }
  argv.splice(i, 1);
  return true;
}
const VIEWPORT = take('viewport') || '1440x900';
const CANVAS_DIR_ARG = take('canvas-dir');
const VIEWER = String(take('viewer-url') || process.env.CANVAS_URL || 'http://localhost:4181').replace(/\/$/, '');
const THEME = take('theme') || 'light';
const FRAMES = take('frames') === true;
const COMPLETE = take('complete') === true;

const [mode = 'list', fileArg = '', codesArg = '', outDir = '.'] = argv;
const canvasDir = path.resolve(CANVAS_DIR_ARG || lib.CANVAS_DIR);
const fileName = path.basename(fileArg || lib.CANVAS_FILE);
const GALLERY = fileName === lib.BLOCKS_FILE; // the block gallery has scratch ids WA9xx that are not in the inventory
const filePath = path.join(canvasDir, fileName);
const SCREEN_ID = '^W[A-H]\\d+(-\\d+)?$';

/** Evaluate the built canvas script in Node, like specs-lib loadCanvas does for the app canvas. */
function loadGroups(file) {
  const src = lib.read(file);
  const m = /<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/.exec(src);
  if (!m) throw new Error('canvas script not found in ' + file);
  const DCLogic = class {
    constructor() {
      this.props = {};
    }
  };
  return { groups: new Function('DCLogic', `${m[1]}\nreturn new Component().build();`)(DCLogic), src };
}

function staticProblems(src, groups) {
  const out = { tokens: lib.compareTokens(src), hexInBlocks: [], frameMismatch: [], unknown: [] };
  // hex colours anywhere outside the generated token blocks
  const stripped = src.replace(/:root\{[^}]*\}/, '').replace(/\[data-theme=dark\]\{[^}]*\}/, '');
  const hex = stripped.match(/#[0-9a-fA-F]{3,8}\b/g);
  if (hex) out.hexInBlocks = [...new Set(hex)];
  const inv = JSON.parse(lib.read(lib.INVENTORY));
  const byId = Object.fromEntries(inv.screens.map((s) => [s.id, s]));
  for (const g of groups) {
    for (const sc of g.screens) {
      const e = byId[sc.id];
      if (GALLERY) continue;
      if (!e) {
        out.unknown.push(sc.id);
        continue;
      }
      const got = sc.frames.map((f) => f.size).join(',');
      const want = e.frames.join(',');
      if (got !== want) out.frameMismatch.push(`${sc.id}: canvas ${got}, inventory ${want}`);
    }
  }
  return { out, inv };
}

(async () => {
  if (!fs.existsSync(filePath)) {
    console.error(`FAILED ${filePath} does not exist: run web-canvas-build.cjs`);
    process.exit(1);
  }
  const { groups, src } = loadGroups(filePath);

  if (mode === 'list') {
    let n = 0;
    for (const g of groups) {
      for (const s of g.screens) {
        console.log(`${s.id} · ${s.name} · ${String(s.note).replace(/\s+/g, ' ')}`);
        n++;
      }
    }
    console.log(`\n${n} screens`);
    return;
  }

  const { out: st, inv } = staticProblems(src, groups);
  const wanted = codesArg.split(',').map((c) => c.trim()).filter(Boolean);
  const codes = wanted.length ? wanted : lib.GROUP_CODES;
  const expectedIds = GALLERY ? [] : inv.screens.filter((s) => codes.includes(s.group)).map((s) => s.id);

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 2200, height: 1200 } });
  const errors = [];
  const warnings = new Set();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
    else if (m.type() === 'warning' && /never resolved|not an array/.test(m.text())) warnings.add(m.text().slice(0, 160));
  });
  await page.goto(`${VIEWER}/${encodeURIComponent(fileName)}`);
  await page.waitForSelector('section.gs', { timeout: 60000 });
  const vp = VIEWPORT === 'all' ? 'Tất cả' : VIEWPORT;
  if (vp !== '1440x900' || THEME !== 'light') {
    await page.evaluate((v) => window.__dcSetProps(window.__dcRootName(), v), { viewport: vp, theme: THEME });
  }
  await page.waitForTimeout(2500);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1500);

  const frames = await page.evaluate((pattern) => {
    const re = new RegExp(pattern);
    return [...document.querySelectorAll('div[id]')].filter((el) => re.test(el.id)).map((el) => {
      const R = el.getBoundingClientRect();
      const wide = [...el.querySelectorAll('*')].filter((c) => {
        const r = c.getBoundingClientRect();
        return r.width > 0 && r.right > R.right + 1;
      });
      const sc = el.closest('.sc');
      return {
        id: el.id,
        w: Math.round(R.width),
        h: Math.round(R.height),
        name: sc?.querySelector('.sc-nm')?.innerText || '',
        unresolved: /\{\{/.test(el.innerText),
        overflow: wide.length ? wide.slice(0, 3).map((c) => `${c.className || c.tagName}`.toString().slice(0, 40)) : []
      };
    });
  }, SCREEN_ID);
  const icons = await page.evaluate(() => ({
    font: document.fonts.check("20px 'Material Symbols Outlined'"),
    bad: [...new Set([...document.querySelectorAll('.ms')].filter((e) => e.scrollWidth > e.clientWidth + 1 && e.textContent.length > 1).map((e) => e.textContent.trim()))]
  }));

  const baseIds = [...new Set(frames.map((f) => f.id.replace(/-\d+$/, '')))];
  const inScope = (id) => codes.some((c) => id.startsWith(c));
  const rendered = baseIds.filter(inScope);
  const bad = frames.filter((f) => inScope(f.id) && (f.unresolved || f.overflow.length));
  const missing = expectedIds.filter((id) => !rendered.includes(id) && !groups.some((g) => g.screens.some((s) => s.id === id)));
  const report = {
    viewport: vp,
    total: rendered.length,
    expected: expectedIds.length,
    missing: COMPLETE ? missing : missing.length ? `${missing.length} id(s) of the inventory have no frame yet: ${missing.slice(0, 6).join(', ')}${missing.length > 6 ? ' …' : ''}` : [],
    frames: frames.filter((f) => inScope(f.id)).length,
    frameMismatch: st.frameMismatch,
    unknownIds: st.unknown,
    errors,
    unresolved: bad.filter((f) => f.unresolved).map((f) => f.id),
    overflow: bad.filter((f) => f.overflow.length).map((f) => `${f.id} (${f.overflow.join(', ')})`),
    iconFont: icons.font ? 'loaded' : 'missing',
    badIcons: icons.bad,
    tokens: st.tokens,
    hexInBlocks: st.hexInBlocks,
    warnings: [...warnings]
  };
  console.log(JSON.stringify(report, null, 2));

  fs.mkdirSync(outDir, { recursive: true });
  for (const code of codes) {
    const el = await page.$(`section#${code}`);
    if (!el || !rendered.some((id) => id.startsWith(code))) continue;
    const png = path.join(outDir, `web-${code}-${vp === 'Tất cả' ? 'all' : vp}${THEME === 'dark' ? '-dark' : ''}.png`);
    try {
      await el.screenshot({ path: png });
      console.log(`screenshot ${png}`);
    } catch (e) {
      console.log(`screenshot ${png} failed (${e.message.split('\n')[0]}): use --frames`);
    }
  }
  if (FRAMES) {
    for (const f of frames.filter((x) => inScope(x.id))) {
      const el = await page.$(`div[id="${f.id}"]`);
      const png = path.join(outDir, `${f.id.includes('-') ? f.id : f.id + '-' + f.w}${THEME === 'dark' ? '-dark' : ''}.png`);
      await el.screenshot({ path: png });
      console.log(`screenshot ${png}`);
    }
  }
  const failed = errors.length || report.unresolved.length || report.overflow.length || report.badIcons.length || report.tokens.length || report.hexInBlocks.length || report.frameMismatch.length || report.unknownIds.length || (COMPLETE && missing.length) || !icons.font;
  process.exitCode = failed ? 1 : 0;
  await browser.close();
})().catch((e) => {
  console.error('FAILED ' + (e && e.stack ? e.stack : e));
  process.exit(1);
});

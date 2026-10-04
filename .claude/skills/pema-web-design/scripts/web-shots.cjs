#!/usr/bin/env node
// W1: screenshot every inventory id of the old Pema web at the 5 viewports.
//
//   node web-shots.cjs                      capture all ids x all viewports into pema-agent/frontend/visual-ref/old/
//   node web-shots.cjs --only=WB1,WC3       capture only these ids (the manifest keeps the other entries)
//   node web-shots.cjs --check              re-capture into %TEMP% and compare with manifest.json (writes nothing in the repo)
//   node web-shots.cjs --out=DIR            write somewhere else (manifest and gallery go to DIR too)
//
// Output (git-ignored except manifest.json and README.md):
//   <ID>-<W>x<H>.png            viewport capture of the screen (not full page), one per inventory id and viewport
//   <ID>-<W>x<H>-print.png      same screen under print media, only for entries whose notes mention print (WF5, WF6)
//   <W>-<legacy_shot>.png       copy of the 1440-style legacy name used by U0 and U8 (inventory `legacy_shot`)
//   manifest.json               {id, viewport, file, media, sha256, page_width, content_width, overflow, page_errors}
//   index.html                  gallery, grouped by inventory group, the 5 viewports in a row (human review)
//
// Determinism: every capture opens a fresh browser context (fixed clock, zone, locale, empty storage, no animation),
// follows `reach` through lib/old-web.cjs, waits for network idle and document.fonts.ready, then takes the screenshot.
// A failed capture is retried once; a capture that still fails (step error, `expect` not satisfied) is recorded in
// `page_errors` and the run exits 1.
//
// Run ONE browser at a time: python's http.server refuses connections above two parallel clients.
// Needs the old web on http://127.0.0.1:4173 and the finance API on :4174. Env: PLAYWRIGHT_MODULE, PEMA_WEB_BASE.

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { loadPlaywright, REPO } = require('./lib/pw.cjs');
const ow = require('./lib/old-web.cjs');

const argv = process.argv.slice(2);
const CHECK = argv.includes('--check');
const ONLY = (argv.find((a) => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const OUT_ARG = (argv.find((a) => a.startsWith('--out=')) || '').slice(6);
const BASE = (process.env.PEMA_WEB_BASE || 'http://127.0.0.1:4173').replace(/\/$/, '');
const INVENTORY = path.join(REPO, 'design-specs', 'web', 'inventory.json');
const REF_DIR = path.join(REPO, 'pema-agent', 'frontend', 'visual-ref', 'old');
const CHANGED_LIMIT = 0.05;
// the A5 order review is printed from the same page: also capture it under print media
const PRINT_IDS = ['WF5', 'WF6'];

const loadInventory = () => JSON.parse(fs.readFileSync(INVENTORY, 'utf8'));
const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const vpName = ([w, h]) => `${w}x${h}`;

async function http(url) {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(4000) })).status;
  } catch {
    return 0;
  }
}

async function metrics(page) {
  return page.evaluate(() => {
    const content = document.querySelector('.content');
    return {
      page_width: document.documentElement.scrollWidth,
      content_width: content ? content.clientWidth : null,
      inner_width: window.innerWidth,
    };
  });
}

/** One entry at one viewport: returns [{file, media, ...metrics, page_errors}] or throws. */
async function captureOne(browser, inv, entry, viewport, outDir) {
  const [w, h] = viewport;
  const page = await ow.newPage(browser, { viewport: { width: w, height: h }, clock: inv.clock });
  try {
    const shown = await ow.open(page, entry, { base: BASE, role: inv.role });
    await shown.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => {});
    await ow.settle(shown, 300);
    const why = await ow.verify(shown, entry);
    if (why) throw new Error(`expect: ${why}`);
    const base = `${entry.id}-${vpName(viewport)}`;
    const shots = [{ file: `${base}.png`, media: 'screen' }];
    if (PRINT_IDS.includes(entry.id)) shots.push({ file: `${base}-print.png`, media: 'print' });
    const out = [];
    for (const s of shots) {
      if (s.media === 'print') {
        await shown.emulateMedia({ media: 'print' });
        await ow.settle(shown, 300);
      }
      const m = await metrics(shown);
      await shown.screenshot({ path: path.join(outDir, s.file) });
      out.push({ ...s, page_width: m.page_width, content_width: m.content_width, overflow: m.page_width > w });
    }
    // page errors raised while the screen was reached and shot (collected by freeze on every page of the context)
    const errors = [...page.errors];
    return out.map((o) => ({ ...o, page_errors: errors }));
  } finally {
    await page.context().close();
  }
}

async function captureWithRetry(browser, inv, entry, viewport, outDir) {
  let lastError = '';
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await captureOne(browser, inv, entry, viewport, outDir);
    } catch (e) {
      lastError = String(e.message || e).split('\n')[0].slice(0, 200);
      await new Promise((r) => setTimeout(r, 800));
    }
  }
  return [{ file: `${entry.id}-${vpName(viewport)}.png`, media: 'screen', page_width: null, content_width: null, overflow: false, page_errors: [`capture failed: ${lastError}`] }];
}

function entryRows(inv, entry, viewport, results, outDir) {
  const rows = [];
  const [w] = viewport;
  for (const r of results) {
    const full = path.join(outDir, r.file);
    const exists = fs.existsSync(full);
    rows.push({
      id: entry.id,
      viewport: vpName(viewport),
      file: r.file,
      media: r.media,
      sha256: exists ? sha256(full) : null,
      page_width: r.page_width,
      content_width: r.content_width,
      overflow: r.overflow,
      page_errors: r.page_errors,
    });
    if (exists && r.media === 'screen' && entry.legacy_shot) {
      const legacy = `${w}-${entry.legacy_shot}.png`;
      fs.copyFileSync(full, path.join(outDir, legacy));
      rows.push({
        id: entry.id,
        viewport: vpName(viewport),
        file: legacy,
        media: 'legacy-copy',
        sha256: sha256(full),
        page_width: r.page_width,
        content_width: r.content_width,
        overflow: r.overflow,
        page_errors: [],
      });
    }
  }
  return rows;
}

async function captureAll(inv, ids, outDir) {
  const { chromium } = loadPlaywright();
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const rows = [];
  try {
    for (const entry of inv.screens.filter((s) => !ids.length || ids.includes(s.id))) {
      for (const viewport of inv.viewports) {
        const results = await captureWithRetry(browser, inv, entry, viewport, outDir);
        rows.push(...entryRows(inv, entry, viewport, results, outDir));
      }
      const mine = rows.filter((r) => r.id === entry.id && r.media === 'screen');
      const bad = mine.filter((r) => r.page_errors.length).length;
      process.stdout.write(`${bad ? 'FAILED ' : 'ok     '}${entry.id} ${mine.length} shots${bad ? `, ${bad} with errors` : ''}\n`);
    }
  } finally {
    await browser.close();
  }
  return rows;
}

function buildManifest(inv, rows) {
  const order = new Map(inv.screens.map((s, i) => [s.id, i]));
  const mediaOrder = { screen: 0, print: 1, 'legacy-copy': 2 };
  rows.sort((a, b) => order.get(a.id) - order.get(b.id) || parseInt(b.viewport, 10) - parseInt(a.viewport, 10) || mediaOrder[a.media] - mediaOrder[b.media]);
  return {
    generated_from: inv.generated_from,
    clock: inv.clock,
    role: inv.role,
    base_url: inv.base_url,
    viewports: inv.viewports.map(vpName),
    counts: {
      ids: inv.screens.length,
      screens: rows.filter((r) => r.media === 'screen').length,
      print: rows.filter((r) => r.media === 'print').length,
      legacy_copies: rows.filter((r) => r.media === 'legacy-copy').length,
      overflow: rows.filter((r) => r.overflow && r.media !== 'legacy-copy').length,
    },
    images: rows,
  };
}

function writeGallery(inv, manifest, outDir) {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const byKey = new Map(manifest.images.filter((r) => r.media === 'screen').map((r) => [`${r.id}|${r.viewport}`, r]));
  const parts = [
    '<!doctype html><meta charset="utf-8"><title>Old web shots</title>',
    '<style>body{font:14px system-ui;margin:16px;background:#f4f4f4}h2{margin:28px 0 8px}h3{margin:14px 0 4px;font-size:14px}',
    '.row{display:flex;gap:8px;align-items:flex-start;overflow-x:auto}figure{margin:0}figcaption{font-size:11px;color:#444}',
    'img{display:block;height:200px;border:1px solid #bbb;background:#fff}.ov{color:#b00020}</style>',
    `<h1>Old web shots (${manifest.counts.screens} screens, clock ${esc(manifest.clock)}, role ${esc(manifest.role)})</h1>`,
  ];
  for (const g of inv.groups) {
    parts.push(`<h2>${esc(g.code)} ${esc(g.name || '')}</h2>`);
    for (const s of inv.screens.filter((x) => x.group === g.code)) {
      parts.push(`<h3>${esc(s.id)} ${esc(s.name)} <small>(${esc(s.kind)})</small></h3><div class="row">`);
      for (const vp of manifest.viewports) {
        const r = byKey.get(`${s.id}|${vp}`);
        if (!r) continue;
        parts.push(
          `<figure><a href="${esc(r.file)}"><img loading="lazy" src="${esc(r.file)}"></a><figcaption class="${r.overflow ? 'ov' : ''}">${vp}${r.overflow ? ` overflow ${r.page_width}px` : ''}</figcaption></figure>`,
        );
      }
      parts.push('</div>');
    }
  }
  fs.writeFileSync(path.join(outDir, 'index.html'), parts.join('\n') + '\n');
}

function summary(manifest) {
  const c = manifest.counts;
  return `${c.ids} ids, ${c.screens} screen shots, ${c.print} print shots, ${c.legacy_copies} legacy copies, ${c.overflow} overflowing`;
}

async function preflight() {
  const bad = [];
  if ((await http(`${BASE}/clinic-web/`)) !== 200) bad.push(`old web not answering on ${BASE}`);
  if (!(await http('http://127.0.0.1:4174/'))) bad.push('finance API not answering on http://127.0.0.1:4174');
  if (bad.length) {
    bad.forEach((b) => console.error('FAILED ' + b));
    process.exit(1);
  }
}

async function runCapture(inv) {
  await preflight();
  const outDir = OUT_ARG ? path.resolve(OUT_ARG) : REF_DIR;
  const started = Date.now();
  const rows = await captureAll(inv, ONLY, outDir);
  const manifestPath = path.join(outDir, 'manifest.json');
  let all = rows;
  if (ONLY.length && fs.existsSync(manifestPath)) {
    const old = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    all = old.images.filter((r) => !ONLY.includes(r.id)).concat(rows);
  }
  const manifest = buildManifest(inv, all);
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  writeGallery(inv, manifest, outDir);
  const failed = rows.filter((r) => r.page_errors.length);
  failed.forEach((r) => console.error(`FAILED ${r.file}: ${r.page_errors.join(' | ')}`));
  console.log(`wrote ${path.relative(REPO, manifestPath)}: ${summary(manifest)} in ${Math.round((Date.now() - started) / 1000)}s`);
  process.exit(failed.length ? 1 : 0);
}

async function runCheck(inv) {
  await preflight();
  const manifestPath = path.join(REF_DIR, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    console.error('FAILED manifest.json missing; run without --check first');
    process.exit(1);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pema-shots-'));
  const problems = [];
  const expectedIds = inv.screens.map((s) => s.id);
  const have = new Set(manifest.images.map((r) => r.id));
  for (const id of expectedIds) if (!have.has(id)) problems.push(`manifest has no entry for ${id}`);
  for (const r of manifest.images) {
    if (!fs.existsSync(path.join(REF_DIR, r.file))) problems.push(`missing image ${r.file}`);
    if (r.page_errors.length) problems.push(`manifest ${r.file} has page errors: ${r.page_errors.join(' | ')}`);
  }
  const rows = await captureAll(inv, ONLY, tmp);
  const now = new Map(rows.map((r) => [r.file, r]));
  const was = new Map(manifest.images.filter((r) => !ONLY.length || ONLY.includes(r.id)).map((r) => [r.file, r]));
  for (const f of was.keys()) if (!now.has(f)) problems.push(`file set: ${f} is in the manifest but was not captured now`);
  for (const f of now.keys()) if (!was.has(f)) problems.push(`file set: ${f} was captured now but is not in the manifest`);
  for (const r of rows) if (r.page_errors.length) problems.push(`recapture ${r.file}: ${r.page_errors.join(' | ')}`);
  const changed = [];
  for (const [f, r] of now) {
    const before = was.get(f);
    if (before && before.sha256 !== r.sha256) changed.push(f);
  }
  const share = was.size ? changed.length / was.size : 0;
  if (changed.length) console.log(`changed images (${changed.length} of ${was.size}, ${(share * 100).toFixed(1)}%):\n  ${changed.join('\n  ')}`);
  if (share > CHANGED_LIMIT) problems.push(`${changed.length} of ${was.size} images changed (limit ${CHANGED_LIMIT * 100}%)`);
  fs.rmSync(tmp, { recursive: true, force: true });
  if (problems.length) {
    problems.forEach((p) => console.error('FAILED ' + p));
    process.exit(1);
  }
  console.log(`web-shots check ok: ${summary(manifest)}; ${changed.length} changed (limit ${CHANGED_LIMIT * 100}%)`);
}

(async () => {
  const inv = loadInventory();
  const unknown = ONLY.filter((id) => !inv.screens.some((s) => s.id === id));
  if (unknown.length) {
    console.error('FAILED unknown id(s): ' + unknown.join(', '));
    process.exit(1);
  }
  if (CHECK) await runCheck(inv);
  else await runCapture(inv);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

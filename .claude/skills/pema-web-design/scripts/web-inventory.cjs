#!/usr/bin/env node
// W0: walk the old Pema web and write design-specs/web/inventory.json, the frozen list of every screen.
//
//   node web-inventory.cjs             verify the catalog against the live web and rewrite inventory.json
//   node web-inventory.cjs --check     same walk, but fail (exit 1) when inventory.json would change
//   node web-inventory.cjs --verbose   also print every screen and every unused `covers` token
//   node web-inventory.cjs --tokens    print every UI entry point found in the live web (to extend the catalog)
//   node web-inventory.cjs --only=WB6,WF6   debug: walk only these ids (never writes, never checks)
//
// What the walk proves
//   1. every catalog entry reaches its screen from a fresh page with 0 page errors (and shows its `expect`);
//   2. every entry point the live web offers (data-nav, data-tab, data-modal, data-finance-tab, data-ops, data-crm,
//      data-action, ... and the CLINIC_DIALOGS buttons of dump-web.cjs) is claimed by some entry's `covers`,
//      so a new button or tab in the web fails this script until it gets an id.
//
// Needs the old web on http://127.0.0.1:4173 (serve root = prototype/) and the finance API on :4174.
// Env: PLAYWRIGHT_MODULE (see lib/pw.cjs), PEMA_WEB_BASE to override the base url.
// Output is deterministic: it is generated from lib/catalog.cjs, the walk only verifies it.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { loadPlaywright, REPO } = require('./lib/pw.cjs');
const ow = require('./lib/old-web.cjs');
const catalog = require('./lib/catalog.cjs');

const argv = process.argv.slice(2);
const CHECK = argv.includes('--check');
const VERBOSE = argv.includes('--verbose');
const TOKENS = argv.includes('--tokens');
const ONLY = (argv.find((a) => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const BASE = (process.env.PEMA_WEB_BASE || 'http://127.0.0.1:4173').replace(/\/$/, '');
const FINANCE_API = 'http://127.0.0.1:4174';
const OUT = path.join(REPO, 'design-specs', 'web', 'inventory.json');
const DUMP_WEB = path.join(REPO, '.claude', 'skills', 'pema-web-to-canvas', 'scripts', 'dump-web.cjs');
// python's http.server has a tiny accept queue; more than two browsers at once make it refuse connections
const POOL = 2;

const VIEWPORTS = [[1920, 1020], [1440, 900], [1280, 720], [1024, 768], [390, 844]];
// plan D4: pages and tabs get the wide and the phone frame too, dialogs, modals and states only the default one
const FRAMES = {
  page: ['1440x900', '1920x1020', '390x844'],
  tab: ['1440x900', '1920x1020', '390x844'],
  modal: ['1440x900'],
  dialog: ['1440x900'],
  state: ['1440x900'],
};

function sourceHash() {
  try {
    return execFileSync('git', ['log', '-1', '--format=%h', '--', 'prototype'], { cwd: REPO, encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

function clinicDialogs() {
  const src = fs.readFileSync(DUMP_WEB, 'utf8');
  const m = src.match(/const CLINIC_DIALOGS = (\[[\s\S]*?\n\]);/);
  if (!m) throw new Error('CLINIC_DIALOGS not found in dump-web.cjs');
  return new Function(`return ${m[1]}`)();
}

function build() {
  const role = catalog.OWNER;
  const screens = catalog.screens.map((s) => ({
    id: s.id,
    group: s.group,
    name: s.name,
    kind: s.kind,
    role: s.role || role,
    reach: s.reach,
    expect: s.expect,
    sources: s.sources,
    next_route: s.next_route,
    next_status: s.next_status,
    app_canvas: s.app_canvas,
    legacy_shot: s.legacy_shot || null,
    frames: FRAMES[s.kind],
    covers: s.covers || [],
    notes: s.notes || '',
  }));
  const count = (key) => screens.reduce((a, s) => ((a[s[key]] = (a[s[key]] || 0) + 1), a), {});
  const sorted = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b, 'en', { numeric: true })));
  return {
    generated_from: sourceHash(),
    base_url: 'http://127.0.0.1:4173',
    finance_api: FINANCE_API,
    clock: ow.DEFAULT_CLOCK,
    timezone: ow.TIMEZONE,
    role,
    viewports: VIEWPORTS,
    groups: catalog.groups,
    counts: { total: screens.length, by_kind: sorted(count('kind')), by_group: sorted(count('group')) },
    screens,
    non_screens: catalog.non_screens,
  };
}

function validateCatalog() {
  const problems = [];
  const ids = new Set();
  const groups = new Set(catalog.groups.map((g) => g.code));
  for (const s of catalog.screens) {
    if (!/^W[A-H]\d+$/.test(s.id)) problems.push(`${s.id}: id must match ^W[A-H]\\d+$`);
    if (ids.has(s.id)) problems.push(`${s.id}: duplicate id`);
    ids.add(s.id);
    if (!s.id.startsWith(s.group) || !groups.has(s.group)) problems.push(`${s.id}: group ${s.group} does not match`);
    if (!FRAMES[s.kind]) problems.push(`${s.id}: unknown kind ${s.kind}`);
    if (!Array.isArray(s.reach) || !s.reach.length) problems.push(`${s.id}: empty reach`);
  }
  for (const g of catalog.groups) {
    const nums = catalog.screens.filter((s) => s.group === g.code).map((s) => Number(s.id.slice(2)));
    nums.forEach((n, i) => {
      if (n !== i + 1) problems.push(`${g.code}: ids must run 1..n in order (found ${n} at position ${i + 1})`);
    });
  }
  return problems;
}

async function http(url) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(4000) });
    return r.status;
  } catch (e) {
    return 0;
  }
}

/** Entry points (as `<attribute>:<value>`) visible in the whole document. */
async function collectTokens(page) {
  return page.evaluate(() => {
    const out = new Set();
    const MAP = { orderPreview: 'order', orderEdit: 'order', orderPatient: null };
    for (const el of document.querySelectorAll('*')) {
      const d = el.dataset;
      if (!d) continue;
      for (const key of ['nav', 'tab', 'modal', 'financeTab', 'ops', 'crm', 'action', 'careAction', 'careNav', 'guide', 'patientFilter', 'followupFilter', 'todayFilter', 'print']) {
        if (d[key] !== undefined && d[key] !== '') out.add(`${key}:${d[key]}`);
      }
      if (d.question !== undefined) out.add('question:chip');
      if (d.orderPreview !== undefined) out.add('order:preview');
      if (d.orderEdit !== undefined) out.add('order:edit');
      if (d.patient !== undefined && el.tagName === 'TR') out.add('patient:row');
      if (d.patient !== undefined && el.tagName === 'A') out.add('patient:link');
      if (d.quickAdd !== undefined || d.quickRemove !== undefined) out.add('order:cart');
    }
    document.querySelectorAll('#staff-account option').forEach((o) => out.add(`staff:${o.value}`));
    if (document.querySelector('[data-print]')) out.add('order:print');
    if (document.querySelector('#approve')) out.add('order:approve');
    if (document.querySelector('body[data-approved]')) out.add('order:review-page');
    void MAP;
    return [...out];
  });
}

async function walkOne(browser, entry, role) {
  let r = await walkAttempt(browser, entry, role);
  // one fresh try: the static server can drop a connection under load, a real bug fails twice
  if (!r.ok) r = await walkAttempt(browser, entry, role);
  return r;
}

async function walkAttempt(browser, entry, role) {
  const page = await ow.newPage(browser, { viewport: { width: 1440, height: 900 } });
  const result = { id: entry.id, ok: true, problem: '', tokens: [] };
  try {
    const shown = await ow.open(page, entry, { base: BASE, role });
    await ow.settle(shown, 400);
    const bad = await ow.verify(shown, entry);
    if (bad) throw new Error(bad);
    result.tokens = await collectTokens(shown);
    if (page.errors.length) throw new Error('page errors: ' + page.errors.slice(0, 2).join(' | '));
  } catch (e) {
    result.ok = false;
    result.problem = String(e.message || e).split('\n')[0].slice(0, 220);
  } finally {
    await page.context().close();
  }
  return result;
}

/** Visit every allowed page and Patient 360 tab for one account to collect entry points. */
async function sweepRole(browser, account, role) {
  const page = await ow.newPage(browser);
  const tokens = new Set();
  try {
    await ow.clearStorage(page, BASE);
    await page.goto(`${BASE}/clinic-web/?staff=${account}`);
    await ow.settle(page, 500);
    const navs = await page.$$eval('.sidebar [data-nav]', (els) => els.map((e) => e.dataset.nav));
    for (const n of navs) {
      await page.locator(`.sidebar [data-nav="${n}"]`).first().click();
      await ow.settle(page, 250);
      (await collectTokens(page)).forEach((t) => tokens.add(t));
    }
    if (navs.includes('patients')) {
      await page.locator('.sidebar [data-nav="patients"]').first().click();
      await page.locator('tr[data-patient]').first().click();
      await ow.settle(page, 250);
      const tabs = await page.$$eval('[data-tab]', (els) => [...new Set(els.map((e) => e.dataset.tab))]);
      for (const t of tabs) {
        await page.locator(`[data-tab="${t}"]`).first().click();
        await ow.settle(page, 250);
        (await collectTokens(page)).forEach((x) => tokens.add(x));
      }
    }
    void role;
  } finally {
    await page.context().close();
  }
  return [...tokens];
}

async function checkDialogButtons(browser) {
  const problems = [];
  const covered = new Set(catalog.screens.flatMap((s) => s.covers || []));
  const page = await ow.newPage(browser);
  try {
    await ow.clearStorage(page, BASE);
    await page.goto(`${BASE}/clinic-web/?staff=${catalog.OWNER}`);
    await ow.settle(page, 500);
    for (const [navName, button] of clinicDialogs()) {
      await ow.closeAll(page);
      await page.locator(`.sidebar [data-nav="${navName}"]`).first().click();
      await ow.settle(page, 250);
      const n = await page.getByRole('button', { name: button }).count();
      if (!n) problems.push(`dialog ${navName} → ${button}: button not found on the live page (dump-web.cjs list is stale?)`);
      if (!covered.has(`dialog:${navName}→${button}`)) problems.push(`UNCOVERED dialog:${navName}→${button} (no entry lists it in covers)`);
    }
  } finally {
    await page.context().close();
  }
  return problems;
}

async function pool(items, n, fn) {
  const results = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: n }, async () => {
      while (next < items.length) {
        const i = next++;
        results[i] = await fn(items[i], i);
      }
    }),
  );
  return results;
}

function stable(obj) {
  return JSON.stringify(obj, null, 2) + '\n';
}

(async () => {
  const problems = validateCatalog();
  const baseStatus = await http(`${BASE}/clinic-web/`);
  if (baseStatus !== 200) problems.push(`old web not answering on ${BASE} (status ${baseStatus})`);
  const financeStatus = await http(`${FINANCE_API}/`);
  if (!financeStatus) problems.push(`finance API not answering on ${FINANCE_API}`);
  if (problems.length) {
    problems.forEach((p) => console.error('FAILED ' + p));
    process.exit(1);
  }

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const inventory = build();
  const failures = [];
  const seen = new Set();
  let todoCount = 0;
  try {
    const todo = ONLY.length ? catalog.screens.filter((s) => ONLY.includes(s.id)) : catalog.screens;
    todoCount = todo.length;
    const results = await pool(todo, POOL, (entry) => walkOne(browser, entry, inventory.role));
    for (const r of results) {
      if (VERBOSE) console.log(`${r.ok ? 'ok    ' : 'FAILED'} ${r.id}${r.problem ? ' ' + r.problem : ''}`);
      if (!r.ok) failures.push(`FAILED ${r.id} ${r.problem}`);
      r.tokens.forEach((t) => seen.add(t));
    }
    if (!ONLY.length) {
      const accounts = ['owner-tam', 'doctor-mai', 'care-maianh', 'accountant'];
      for (const acc of accounts) (await sweepRole(browser, acc, acc)).forEach((t) => seen.add(t));
      failures.push(...(await checkDialogButtons(browser)));
    }
  } finally {
    await browser.close();
  }

  if (TOKENS) console.log([...seen].sort().join('\n'));
  if (ONLY.length) {
    failures.forEach((f) => console.error(f));
    console.log(`walked ${todoCount} id(s), ${failures.length} problem(s)`);
    process.exit(failures.length ? 1 : 0);
  }

  const covered = new Set(catalog.screens.flatMap((s) => s.covers || []));
  const known = new Set([...covered, ...Object.keys(catalog.actions)]);
  const dynamic = (t) => /^(order:cart)$/.test(t);
  for (const t of [...seen].sort()) {
    if (!known.has(t) && !dynamic(t)) failures.push(`UNCOVERED ${t} (offered by the live web, claimed by no entry)`);
  }
  if (VERBOSE) {
    for (const t of [...covered].sort()) {
      if (!seen.has(t) && !t.startsWith('dialog:') && !t.startsWith('role:') && !t.startsWith('modal:appointment')) console.log(`note   covers token not seen live: ${t}`);
    }
  }

  const text = stable(inventory);
  if (failures.length) {
    failures.forEach((f) => console.error(f));
    console.error(`inventory NOT written: ${failures.length} problem(s)`);
    process.exit(1);
  }
  const kinds = Object.entries(inventory.counts.by_kind).map(([k, v]) => `${k}=${v}`).join(' ');
  const groups = Object.entries(inventory.counts.by_group).map(([k, v]) => `${k}=${v}`).join(' ');
  if (CHECK) {
    // git may check the file out with CRLF on Windows; the content is what counts
    const current = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8').replaceAll('\r\n', '\n') : '';
    if (current !== text) {
      const a = current ? JSON.parse(current) : { screens: [] };
      const diff = inventory.screens.filter((s, i) => JSON.stringify(s) !== JSON.stringify(a.screens[i])).map((s) => s.id);
      console.error(`inventory.json differs from the walk (${diff.slice(0, 12).join(', ') || 'header'}); run without --check`);
      process.exit(1);
    }
    console.log(`inventory ok: ${inventory.counts.total} screens (${kinds}) | ${groups} | ${seen.size} entry points covered`);
    return;
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, text);
  console.log(`wrote ${path.relative(REPO, OUT)}: ${inventory.counts.total} screens (${kinds}) | ${groups} | ${seen.size} entry points covered`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

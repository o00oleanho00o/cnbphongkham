#!/usr/bin/env node
// W2: structured, text-only snapshot of every screen of the old Pema web -> design-specs/web/snapshot.json.
//
//   node web-snapshot.cjs                 walk all inventory ids, rewrite snapshot.json
//   node web-snapshot.cjs --only=WB1,WC4  re-walk these ids and merge them into the existing snapshot.json
//   node web-snapshot.cjs --check         walk everything, fail (exit 1) when snapshot.json differs
//   node web-snapshot.cjs --no-probe      skip the viewport probes (faster, for debugging)
//   node web-snapshot.cjs --show=WB1      print one snapshot entry
//
// Per id (1440x900; pages and tabs are probed again at 1920, 1280, 1024 and 390 wide): shell, regions, the ordered
// layout `tree` (every visible text, field, action, status), the categorised lists (headings, actions, fields, tables,
// chips_tabs, badges_status, kpis, notices, empty_states), `tokens_used` (mapped to tokens.json, `unmatched` listed),
// `responsive` and `stats.uncovered_text` (visible text the tree misses; must stay empty).
//
// Needs the old web on http://127.0.0.1:4173 and the finance API on :4174 (never started or stopped here).
// One browser, one page at a time: the static server drops connections under parallel load.
// Env: PLAYWRIGHT_MODULE (lib/pw.cjs), PEMA_WEB_BASE.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { loadPlaywright, REPO } = require('./lib/pw.cjs');
const ow = require('./lib/old-web.cjs');
const { extractInPage, probeInPage } = require('./lib/web-extract.cjs');
const tm = require('./lib/token-map.cjs');

const argv = process.argv.slice(2);
const CHECK = argv.includes('--check');
const NO_PROBE = argv.includes('--no-probe');
const ONLY = (argv.find((a) => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const SHOW = (argv.find((a) => a.startsWith('--show=')) || '').slice(7);
const BASE = (process.env.PEMA_WEB_BASE || 'http://127.0.0.1:4173').replace(/\/$/, '');
const WEB_DIR = path.join(REPO, 'design-specs', 'web');
const INVENTORY = path.join(WEB_DIR, 'inventory.json');
const OUT = path.join(WEB_DIR, 'snapshot.json');
const PROBE_VIEWPORTS = [[1920, 1020], [1280, 720], [1024, 768], [390, 844]];

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));
const lf = (s) => s.replaceAll('\r\n', '\n');
const sha = (s) => crypto.createHash('sha256').update(lf(s)).digest('hex').slice(0, 16);

function sourceHash() {
  try {
    return execFileSync('git', ['log', '-1', '--format=%h', '--', 'prototype'], { cwd: REPO, encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

// ---------- scope of one screen ----------
/** What part of the page the snapshot describes. Decided on the open page. */
async function scopeOf(page, entry) {
  const hasModal = await page.locator('.modal-backdrop .modal').locator('visible=true').count();
  if (hasModal) return { scope: 'dialog', roots: ['.modal-backdrop .modal'] };
  if (entry.id === 'WA4') return { scope: 'toast', roots: ['.toast'], mode: 'toast' };
  if (['WA1', 'WA2', 'WA3'].includes(entry.id)) return { scope: 'shell', roots: ['.skip-link', '.sidebar', '.topbar'] };
  const hasMain = await page.locator('#main-content').count();
  return hasMain ? { scope: 'content', roots: ['#main-content'] } : { scope: 'body', roots: ['body'] };
}

// ---------- post-processing ----------
function strings(node, into) {
  if (typeof node === 'string') into.push(node);
  else if (Array.isArray(node)) node.forEach((x) => strings(x, into));
  else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) {
      if (['c', 'bg', 'color', 'w2', 'box', 'lay', 'n', 'id', 'hook', 'href', 'tt', 'cols_px', 'px', 'group', 'type', 'mark', 'role', 'tag', 'variant', 'of'].includes(k)) continue;
      strings(v, into);
    }
  }
}

function walkTree(nodes, fn, depth = 0) {
  for (const n of nodes || []) {
    fn(n, depth);
    for (const key of ['children', 'item']) if (Array.isArray(n[key])) walkTree(n[key], fn, depth + 1);
    if (n.first) n.first.forEach((cell) => walkTree(cell, fn, depth + 1));
    if (n.actions) walkTree(n.actions, fn, depth + 1);
  }
}

function dedupe(list, keyFn) {
  const map = new Map();
  for (const it of list) {
    const k = keyFn(it);
    if (map.has(k)) map.get(k).count++;
    else map.set(k, { ...it, count: 1 });
  }
  return [...map.values()];
}

function mergeVariants(tree, lists) {
  walkTree(tree, (n) => {
    const v = n.variants;
    if (!v) return;
    for (const a of v.actions || []) lists.actions.push({ n: 'action', label: a.label, variant: a.variant, hook: a.hook, in_rows: true });
    for (const b of v.badges || []) lists.badges_status.push({ n: 'badge', t: b.t, c: b.c, in_rows: true });
  });
}

function trimAction(a) {
  const o = { label: a.label, variant: a.variant };
  for (const k of ['disabled', 'link', 'href', 'icon_only', 'hook', 'title', 'aria', 'in_rows']) if (a[k]) o[k] = a[k];
  o.count = a.count || 1;
  return o;
}

function columnsOf(tree) {
  // content columns: the first-level groups/cards that carry a CSS layout
  const out = [];
  const visit = (nodes, depth) => {
    for (const n of nodes || []) {
      if (depth <= 2 && n.lay && n.box) out.push({ c: n.c || n.tag || '', box: n.box, lay: n.lay });
      if (depth < 2 && n.children) visit(n.children, depth + 1);
    }
  };
  visit(tree, 0);
  return out;
}

function describeIds(tree) {
  const map = {};
  walkTree(tree, (n) => {
    if (n.w2) map[n.w2] = (n.n === 'group' ? '' : n.n + ' ') + (n.c ? '.' + n.c.split(' ')[0] : n.tag || n.n);
  });
  return map;
}

function responsiveOf(base, probes, desc) {
  const out = {};
  for (const [vp, p] of Object.entries(probes)) {
    const changes = [];
    for (const [id, now] of Object.entries(p.els)) {
      const was = base.els[id];
      if (!was) continue;
      const name = id.startsWith('sel:') ? id.slice(4) : desc[id] || id;
      if (was.v && !now.v) changes.push(`${name}: hidden`);
      else if (!was.v && now.v) changes.push(`${name}: shown`);
      else if (now.v) {
        if (was.cols !== undefined && now.cols !== undefined && was.cols !== now.cols) changes.push(`${name}: grid ${was.cols} → ${now.cols} columns`);
        if (was.dir && now.dir && was.dir !== now.dir) changes.push(`${name}: flex ${was.dir} → ${now.dir}`);
        if (was.wrap !== undefined && now.wrap !== undefined && was.wrap !== now.wrap) changes.push(`${name}: flex-wrap ${was.wrap ? 'on' : 'off'} → ${now.wrap ? 'on' : 'off'}`);
        if (was.thead !== undefined && was.thead !== now.thead) changes.push(`${name}: table header row ${now.thead ? 'shown' : 'hidden'}`);
        if (was.d !== now.d && !(was.d.includes('grid') && now.d.includes('grid')) && !(was.d.includes('flex') && now.d.includes('flex'))) changes.push(`${name}: display ${was.d} → ${now.d}`);
        if (was.pos !== undefined && was.pos !== now.pos) changes.push(`${name}: position ${was.pos} → ${now.pos}`);
        if (id.startsWith('sel:') && ['.sidebar', '.modal-backdrop .modal'].includes(id.slice(4)) && was.w !== now.w) changes.push(`${name}: width ${was.w} → ${now.w}px`);
      }
    }
    const baseSet = new Set(base.texts);
    const nowSet = new Set(p.texts);
    const hidden = base.texts.filter((t) => !nowSet.has(t));
    const shown = p.texts.filter((t) => !baseSet.has(t));
    const o = { overflow_x: p.overflow_x, changes: [...new Set(changes)] };
    if (hidden.length) {
      o.hidden_text_n = hidden.length;
      o.hidden_text = hidden.slice(0, 8);
    }
    if (shown.length) {
      o.new_text_n = shown.length;
      o.new_text = shown.slice(0, 8);
    }
    out[vp] = o;
  }
  return out;
}

function buildEntry(entry, data, scope, probes, tokens, index) {
  const { tree, lists, texts, raw, regions, shell } = data;
  mergeVariants(tree, lists);
  const flat = [];
  strings(tree, flat);
  const universe = flat.join('\n');
  const tokensUsed = tm.mapRaw(raw, tokens, index);
  const uncovered = [...new Set(texts)].filter((t) => !universe.includes(t));
  const e = {
    id: entry.id,
    name: entry.name,
    kind: entry.kind,
    role: entry.role,
    viewport: '1440x900',
    scope: scope.scope,
    url: data.url,
    shell,
    regions,
    columns: columnsOf(tree),
    headings: lists.headings,
    actions: dedupe(lists.actions.map(trimAction), (a) => `${a.label}|${a.variant}|${a.hook || ''}|${a.in_rows ? 1 : 0}`),
    fields: lists.fields.map(({ n, ...f }) => f),
    tables: lists.tables.map(({ id, ...t }) => t),
    chips_tabs: lists.chips_tabs.map((c) => ({ kind: c.n, label: c.label, selected: !!c.selected, ...(c.disabled ? { disabled: true } : {}), ...(c.hook ? { hook: c.hook } : {}) })),
    badges_status: dedupe(lists.badges_status.map((b) => ({ text: b.t, cls: b.c || '', ...(b.in_rows ? { in_rows: true } : {}) })), (b) => `${b.text}|${b.cls}`),
    kpis: lists.kpis.map((k) => ({ label: k.label, value: k.value, ...(k.hint ? { hint: k.hint } : {}) })),
    notices: lists.notices.map((n) => ({ text: n.t, cls: n.c || '', ...(n.role ? { role: n.role } : {}) })),
    empty_states: lists.empty_states.map((x) => x.t),
    tree,
    tokens_used: tokensUsed,
    responsive: probes ? responsiveOf(probes.base, probes.list, describeIds(tree)) : {},
    stats: { text_runs: new Set(texts).size, uncovered_text: uncovered },
  };
  return e;
}

async function snapshotOne(browser, entry, tokens, index) {
  const page = await ow.newPage(browser, { viewport: { width: 1440, height: 900 } });
  try {
    const shown = await ow.open(page, entry, { base: BASE, role: ow_role(entry) });
    await ow.settle(shown, 500);
    const bad = await ow.verify(shown, entry);
    if (bad) throw new Error(bad);
    const scope = await scopeOf(shown, entry);
    const data = await shown.evaluate(extractInPage, { roots: scope.roots, mode: scope.mode || '' });
    let probes = null;
    if (!NO_PROBE && entry.frames.includes('390x844')) {
      const base = await shown.evaluate(probeInPage);
      const list = {};
      for (const [w, h] of PROBE_VIEWPORTS) {
        await shown.setViewportSize({ width: w, height: h });
        await ow.settle(shown, 350);
        list[`${w}x${h}`] = await shown.evaluate(probeInPage);
      }
      probes = { base, list };
    }
    if (page.errors.length) throw new Error('page errors: ' + page.errors.slice(0, 2).join(' | '));
    return buildEntry(entry, data, scope, probes, tokens, index);
  } finally {
    await page.context().close();
  }
}

let INV_ROLE = '';
function ow_role(entry) {
  return entry.role || INV_ROLE;
}

// ---------- output ----------
function renderJson(meta, screens) {
  const lines = ['{', ` "meta": ${JSON.stringify(meta)},`, ' "screens": {'];
  const ids = Object.keys(screens);
  ids.forEach((id, i) => {
    const s = screens[id];
    lines.push(`  ${JSON.stringify(id)}: {`);
    const keys = Object.keys(s);
    keys.forEach((k, j) => lines.push(`   ${JSON.stringify(k)}: ${JSON.stringify(s[k])}${j < keys.length - 1 ? ',' : ''}`));
    lines.push(`  }${i < ids.length - 1 ? ',' : ''}`);
  });
  lines.push(' }', '}');
  return lines.join('\n') + '\n';
}

function tokensSummary(screens) {
  const unmatched = new Map();
  const radius = new Map();
  const text = new Map();
  for (const s of Object.values(screens)) {
    for (const u of s.tokens_used.unmatched.color) {
      const k = u.hex;
      const cur = unmatched.get(k) || { hex: u.hex, nearest: u.nearest, dE: u.dE, n: 0, roles: new Set(), screens: [], ex: u.ex };
      cur.n += u.n;
      cur.roles.add(u.role);
      cur.screens.push(s.id);
      unmatched.set(k, cur);
    }
    for (const u of s.tokens_used.unmatched.radius) radius.set(u.px, { px: u.px, nearest: u.nearest, n: (radius.get(u.px) || { n: 0 }).n + u.n });
    for (const u of s.tokens_used.unmatched.text) text.set(u.px, { px: u.px, nearest: u.nearest, n: (text.get(u.px) || { n: 0 }).n + u.n });
  }
  const colors = [...unmatched.values()].map((u) => ({ hex: u.hex, nearest: u.nearest, dE: u.dE, n: u.n, roles: [...u.roles].sort(), screens: u.screens.length, example: u.ex })).sort((a, b) => b.n - a.n || a.hex.localeCompare(b.hex));
  return { unmatched_colors: colors, unmatched_radius: [...radius.values()].sort((a, b) => a.px - b.px), unmatched_font_px: [...text.values()].sort((a, b) => a.px - b.px) };
}

(async () => {
  const inventory = readJson(INVENTORY);
  INV_ROLE = inventory.role;
  if (SHOW) {
    const all = readJson(OUT);
    console.log(JSON.stringify(all.screens[SHOW], null, 1));
    return;
  }
  const status = await fetch(`${BASE}/clinic-web/`, { signal: AbortSignal.timeout(4000) }).then((r) => r.status, () => 0);
  if (status !== 200) {
    console.error(`FAILED old web not answering on ${BASE} (status ${status})`);
    process.exit(1);
  }
  const tokens = tm.loadTokens();
  const index = tm.colorIndex(tokens);
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const existing = fs.existsSync(OUT) && ONLY.length ? readJson(OUT) : { screens: {} };
  const screens = {};
  const failures = [];
  try {
    for (const entry of inventory.screens) {
      if (ONLY.length && !ONLY.includes(entry.id)) {
        if (existing.screens[entry.id]) screens[entry.id] = existing.screens[entry.id];
        continue;
      }
      let r = null;
      let problem = '';
      for (let attempt = 0; attempt < 2 && !r; attempt++) {
        try {
          r = await snapshotOne(browser, entry, tokens, index);
        } catch (e) {
          problem = String(e.message || e).split('\n')[0].slice(0, 200);
        }
      }
      if (!r) {
        failures.push(`FAILED ${entry.id} ${problem}`);
        continue;
      }
      screens[entry.id] = r;
      console.log(`ok ${entry.id} ${r.scope} text_runs=${r.stats.text_runs} uncovered=${r.stats.uncovered_text.length}`);
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    failures.forEach((f) => console.error(f));
    console.error('snapshot NOT written');
    process.exit(1);
  }
  const ordered = Object.fromEntries(inventory.screens.filter((s) => screens[s.id]).map((s) => [s.id, screens[s.id]]));
  const meta = {
    generator: '.claude/skills/pema-web-design/scripts/web-snapshot.cjs',
    inventory_sha: sha(fs.readFileSync(INVENTORY, 'utf8')),
    web_source: sourceHash(),
    base_url: inventory.base_url,
    clock: inventory.clock,
    count: Object.keys(ordered).length,
    note: 'Text only. The old web is synthetic; no pixels. Edit nothing here: regenerate with web-snapshot.cjs.',
    tokens_summary: tokensSummary(ordered),
  };
  const text = renderJson(meta, ordered);
  if (CHECK) {
    const cur = fs.existsSync(OUT) ? lf(fs.readFileSync(OUT, 'utf8')) : '';
    if (cur !== text) {
      const a = cur ? readJson(OUT).screens : {};
      const diff = Object.keys(ordered).filter((id) => JSON.stringify(a[id]) !== JSON.stringify(ordered[id]));
      console.error(`snapshot.json differs from the live web (${diff.slice(0, 12).join(', ') || 'meta'}); run without --check`);
      process.exit(1);
    }
    console.log(`snapshot ok: ${meta.count} screens`);
    return;
  }
  fs.mkdirSync(WEB_DIR, { recursive: true });
  fs.writeFileSync(OUT, text);
  const bytes = Buffer.byteLength(text);
  console.log(`wrote ${path.relative(REPO, OUT)}: ${meta.count} screens, ${(bytes / 1024).toFixed(0)} KB, unmatched colours ${meta.tokens_summary.unmatched_colors.length}`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

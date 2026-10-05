#!/usr/bin/env node
// W4: generates .claude/skills/pema-web-design/references/coverage-web.md, one row per inventory id:
//     old web reach -> web canvas frames -> app canvas codes -> Next.js route and status -> shots and spec present.
// Everything is read from inventory.json, the built web canvas, the spec files and manifest.json, so the table cannot drift.
//
//   node web-coverage.cjs               regenerate coverage-web.md and print the counts table
//   node web-coverage.cjs --check       exit 1 when coverage-web.md is stale or any id lacks a canvas frame, a spec, its
//                                       5 shots (+ print/legacy copies), or when a Next.js status disagrees with src/app
//   node web-coverage.cjs --images=DIR  also check that every file of manifest.json exists in DIR (default: this checkout's
//                                       pema-agent/frontend/visual-ref/old; images are git-ignored, so a fresh worktree has none)
//   node web-coverage.cjs --counts      print only the counts table
//
// Pure file work: no browser, no running web. It never reads prototype/.
const fs = require('fs');
const path = require('path');
const lib = require('./lib/web-canvas-lib.cjs');
const canvasLayout = require('./lib/canvas-layout.cjs');

const argv = process.argv.slice(2);
const CHECK = argv.includes('--check');
const COUNTS = argv.includes('--counts');
const IMAGES = (argv.find((a) => a.startsWith('--images=')) || '').slice(9);

const ROOT = lib.ROOT;
const OUT = path.join(ROOT, '.claude', 'skills', 'pema-web-design', 'references', 'coverage-web.md');
const MANIFEST = path.join(ROOT, 'pema-agent', 'frontend', 'visual-ref', 'old', 'manifest.json');
const SPEC_DIR = path.join(ROOT, 'design-specs', 'web', 'screens');
const APP_DIR = path.join(ROOT, 'pema-agent', 'frontend', 'src', 'app');

const inv = JSON.parse(lib.read(lib.INVENTORY));
const manifest = fs.existsSync(MANIFEST) ? JSON.parse(lib.read(MANIFEST)) : { images: [] };
const canvas = canvasLayout.loadCanvasScreens();
const problems = [];

// ---- old web reach, in words ----
function reachText(steps) {
  const parts = [];
  for (const st of steps) {
    const sel = st.click || st.clickPopup || (st.press && `press ${st.press}`) || null;
    if (st.goto) {
      const m = /staff=\{role\}|screen=(\w+)|\?(\w+)=/.exec(st.goto);
      if (/screen=/.test(st.goto) || !/staff=\{role\}$/.test(st.goto)) parts.push(`open ${st.goto.replace('{role}', '<role>')}`);
      else if (m) continue;
    } else if (sel) {
      const data = /\[(data-[\w-]+)(?:="([^"]*)")?\]/.exec(sel);
      const id = /#([\w-]+)/.exec(sel);
      if (data) parts.push(data[2] ? `${data[1].replace('data-', '')}=${data[2]}` : data[1]);
      else if (id) parts.push(`#${id[1]}`);
      else parts.push(`\`${sel.length > 40 ? `${sel.slice(0, 37)}…` : sel}\``);
    } else if (st.fill) parts.push(`fill ${st.fill[0]}`);
  }
  return parts.length ? parts.join(' › ') : 'home page';
}

// ---- Next.js route on disk ----
function routeOnDisk(route) {
  if (!route || route.startsWith('(')) return null;
  const segs = route.split('/').filter(Boolean);
  const walk = (dir, i) => {
    if (i === segs.length) return fs.existsSync(path.join(dir, 'page.tsx'));
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return false;
    }
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      if (/^\(.*\)$/.test(e.name) && walk(path.join(dir, e.name), i)) return true; // route group: transparent
      if (e.name === segs[i] && walk(path.join(dir, e.name), i + 1)) return true;
    }
    return false;
  };
  return walk(APP_DIR, 0);
}

// ---- manifest ----
const shots = {};
for (const im of manifest.images) {
  const s = (shots[im.id] = shots[im.id] || { screen: 0, print: 0, legacy: 0, files: [] });
  if (!im.file) continue; // a state the mock cannot give (state_unreachable): a fact in the manifest, no image
  if (im.media === 'legacy-copy') s.legacy++;
  else if (im.media === 'print') s.print++;
  else s.screen++;
  s.files.push(im.file);
}

const wantShots = (s) => (s.source === 'nextjs' ? (s.frames || []).length : inv.viewports.length);
const rows = [];
const countsFrames = { ids: 0 };
for (const s of inv.screens) {
  const cs = canvas && canvas.screens[s.id];
  const frames = cs ? cs.frames.map((f) => f.size) : [];
  const wantFrames = s.frames || [];
  const sh = shots[s.id] || { screen: 0, print: 0, legacy: 0, files: [] };
  const specOk = fs.existsSync(path.join(SPEC_DIR, `${s.id}.md`));
  const disk = routeOnDisk(s.next_route);
  const status = s.next_status || 'none';

  if (!cs) problems.push(`${s.id}: no frame in Pema Web redesign canvas/${s.source === 'nextjs' ? lib.NEXT_FILE : lib.CANVAS_FILE}`);
  else if (cs.canvasFile !== (s.source === 'nextjs' ? lib.NEXT_FILE : lib.CANVAS_FILE)) problems.push(`${s.id}: frame is in ${cs.canvasFile}, expected ${s.source === 'nextjs' ? lib.NEXT_FILE : lib.CANVAS_FILE}`);
  else if (frames.join(',') !== wantFrames.join(',')) problems.push(`${s.id}: canvas frames ${frames.join(', ')} != inventory frames ${wantFrames.join(', ')}`);
  if (!specOk) problems.push(`${s.id}: no spec design-specs/web/screens/${s.id}.md`);
  // old-web ids are shot at the five inventory viewports; Next.js ids (W8) at their own frames
  if (sh.screen !== wantShots(s)) problems.push(`${s.id}: ${sh.screen} screen shots in manifest.json, expected ${wantShots(s)}`);
  if (s.legacy_shot && !sh.legacy) problems.push(`${s.id}: inventory has legacy_shot "${s.legacy_shot}" but manifest.json has no legacy copy`);
  if (disk === true && /^planned/.test(status)) problems.push(`${s.id}: status "${status}" but route ${s.next_route} exists in src/app; update the status in the catalog (lib/catalog.cjs)`);
  if (disk === false && /^built/.test(status)) problems.push(`${s.id}: status "${status}" but route ${s.next_route} has no page.tsx in src/app`);

  rows.push({
    id: s.id,
    name: s.name,
    kind: s.kind,
    reach: `${s.role && s.role !== inv.role ? `as ${s.role}: ` : ''}${reachText(s.reach)}`,
    frames: frames.join(' · ') || '—',
    app: s.app_canvas.length ? s.app_canvas.join(', ') : '—',
    route: s.next_route ? `\`${s.next_route}\`` : '—',
    status,
    onDisk: disk === null ? '—' : disk ? 'yes' : 'no',
    shots: `${sh.screen}${sh.print ? `+${sh.print}p` : ''}${sh.legacy ? `+${sh.legacy}L` : ''}`,
  });
  countsFrames.ids++;
}

// canvas ids that are not inventory ids (the gallery WA9xx lives in its own file, not here)
if (canvas) for (const id of Object.keys(canvas.screens)) if (!inv.screens.some((s) => s.id === id)) problems.push(`${id}: canvas frame without an inventory id`);

const md = `<!-- Generated by .claude/skills/pema-web-design/scripts/web-coverage.cjs. Do not edit; run the script. -->
# Old web ↔ web canvas ↔ app canvas ↔ Next.js (${inv.screens.length} ids)

One row per \`design-specs/web/inventory.json\` id. Owner rule: the web canvas, specs and shots hold every piece of UI of the old web;
nothing is filtered out. "App canvas" is a cross-reference for blocks and wording, never a filter (\`—\` means the app has no
counterpart; the id is still complete). Differences from the app are in \`design-specs/web/notes.json\` (\`differences\`).

- **Old web reach**: how the id is reached from \`/clinic-web/?staff=<role>\` (nav, tab, modal, button selectors; see \`reach\` in the inventory).
- **Web canvas frames**: frame sizes of the id in \`Pema Web redesign canvas/Pema Web.dc.html\` (WA-WI) or \`Pema Web (Next.js).dc.html\` (WJ-WL) (pages, tabs and finance: 1440 · 1920 · 390; states, dialogs, modals: 1440).
- **Shots**: images in \`pema-agent/frontend/visual-ref/old/\` (git-ignored): 5 viewports, \`+Np\` print copies, \`+1L\` legacy-name copy.
- **On disk**: whether the route has a \`page.tsx\` in \`pema-agent/frontend/src/app\` (\`—\` for the app shell and ids with no route). Checked against the status.

| ID | Screen | Kind | Old web reach | Web canvas frames | App canvas | Next.js route | Next.js status | On disk | Shots |
|---|---|---|---|---|---|---|---|---|---|
${rows.map((r) => `| [${r.id}](../../../../design-specs/web/screens/${r.id}.md) | ${r.name} | ${r.kind} | ${r.reach.replace(/\|/g, '\\|')} | ${r.frames} | ${r.app} | ${r.route} | ${r.status} | ${r.onDisk} | ${r.shots} |`).join('\n')}
`;

// ---- counts table ----
const mc = manifest.counts || {};
const specFiles = fs.existsSync(SPEC_DIR) ? fs.readdirSync(SPEC_DIR).filter((f) => /^W[A-L]\d+\.md$/.test(f)).length : 0;
const canvasCount = canvas ? Object.keys(canvas.screens).length : 0;
const screenShots = manifest.images.filter((i) => i.media === 'screen' && i.file).length;
const legacyShots = manifest.images.filter((i) => i.media === 'legacy-copy').length;
let missingItems = '?';
try {
  const wl = require('./web-specs-lib.cjs');
  const m = wl.loadModel();
  const miss = wl.coverageAll(m);
  missingItems = Object.values(miss).reduce((n, a) => n + a.length, 0);
} catch (e) {
  problems.push(`coverage of snapshot items could not be computed: ${e.message}`);
}
const n = inv.screens.length;
const table = [
  ['Item', 'Expected', 'Found'],
  ['inventory ids', n, n],
  ['screenshots (id x viewport; Next.js ids x frames)', `${inv.screens.filter((s) => s.source !== 'nextjs').length} x ${inv.viewports.length} + ${inv.screens.filter((s) => s.source === 'nextjs').reduce((a, s) => a + (s.frames || []).length, 0)} = ${inv.screens.reduce((a, s) => a + wantShots(s), 0)}`, screenShots],
  ['legacy-name copies (ids with legacy_shot x viewports)', `${inv.screens.filter((s) => s.legacy_shot).length} x ${inv.viewports.length} = ${inv.screens.filter((s) => s.legacy_shot).length * inv.viewports.length}`, legacyShots],
  ['specs', n, specFiles],
  ['canvas screens', n, canvasCount],
  ['coverage rows', n, rows.length],
  ['snapshot items missing from specs or frames', 0, missingItems],
];
const widths = table[0].map((_, i) => Math.max(...table.map((r) => String(r[i]).length)));
const countsText = table.map((r) => `| ${r.map((c, i) => String(c).padEnd(widths[i])).join(' | ')} |`).join('\n');
for (const [label, expected, found] of table.slice(1)) {
  const exp = typeof expected === 'string' && expected.includes('=') ? Number(expected.split('=')[1]) : Number(expected);
  if (exp !== Number(found)) problems.push(`count mismatch: ${label}: expected ${expected}, found ${found}`);
}
if (mc.screens != null && mc.screens !== screenShots) problems.push(`manifest.json counts.screens ${mc.screens} != ${screenShots} screen entries`);

// ---- images on disk (optional) ----
if (IMAGES || CHECK) {
  const dir = IMAGES ? path.resolve(IMAGES) : path.dirname(MANIFEST);
  const have = fs.existsSync(dir) ? new Set(fs.readdirSync(dir)) : new Set();
  const missing = manifest.images.filter((i) => !have.has(i.file));
  if (IMAGES && missing.length) problems.push(`${missing.length} image(s) of manifest.json missing in ${dir}: ${missing.slice(0, 5).map((i) => i.file).join(', ')}${missing.length > 5 ? ' …' : ''}`);
  else if (!IMAGES && missing.length) console.log(`note: ${missing.length} of ${manifest.images.length} images are not in ${path.relative(ROOT, dir)} (git-ignored; pass --images=<folder with the PNGs> to check them)`);
  else console.log(`images: all ${manifest.images.length} files of manifest.json exist in ${dir}`);
}

if (COUNTS) {
  console.log(countsText);
  process.exit(problems.length ? 1 : 0);
}

if (CHECK) {
  const cur = fs.existsSync(OUT) ? lib.lf(fs.readFileSync(OUT, 'utf8')) : '';
  if (cur !== md) problems.push(`${path.relative(ROOT, OUT)} is out of date; run node web-coverage.cjs`);
  if (problems.length) {
    problems.forEach((p) => console.error(`FAILED ${p}`));
    process.exit(1);
  }
  console.log(`coverage-web.md up to date: ${rows.length} rows = ${n} ids, ${canvasCount} canvas screens, ${specFiles} specs, ${screenShots} screen shots, 0 snapshot items missing`);
  process.exit(0);
}

fs.writeFileSync(OUT, md);
console.log(`wrote ${path.relative(ROOT, OUT)} (${rows.length} rows)\n${countsText}`);
if (problems.length) {
  problems.forEach((p) => console.error(`WARN ${p}`));
  process.exit(1);
}

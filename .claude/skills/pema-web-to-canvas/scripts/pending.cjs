// What changed on the web since the last canvas sync, so the skill only redoes those screens.
// Reads "Sync baseline" and "## Pending" from web-changes.md, lists web UI files changed since
// that commit (committed, staged, unstaged, untracked), and flags files no pending entry names.
// The old Vietnamese markers ("Mốc đồng bộ", "## Chờ chuyển") are still accepted.
// Usage: node pending.cjs            (run from the repo root)
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const LOG = path.join(__dirname, '..', 'web-changes.md');
const WATCH = ['prototype/clinic-web/', 'prototype/patient-mobile/', 'prototype/finance/', 'prototype/shared/'];

// file pattern → dump-web.cjs section prefixes (for --only) and canvas codes (see references/coverage.md).
// First match wins, so the sample-data line sits above the operations/crm lines.
const MAP = [
  [/shared\/(data|operations-data|crm-data)\.js$/, '(sample data — only log when adding a status/column)', '—'],
  [/shared\/clinic\.js$/, 'clinic:dashboard,clinic:patients,clinic:followups,clinic:studio,clinic:ask,p360:,modal:,dialog:patients', 'A, F1–F3, F10, F15, I1, I5–I7, I12, J'],
  [/shared\/operations-ui\.js$|operations\.css$/, 'clinic:today,clinic:schedule,clinic:resources,clinic:services,clinic:cashier,dialog:today,dialog:schedule,dialog:resources,dialog:services,dialog:cashier', 'A2, F8, F9, F11–F14, I2–I4, I8–I11'],
  [/shared\/crm-[a-z]+\.js$|crm\.css$/, 'clinic:crm,p360:crm,dialog:crm', 'C, I1, I13, J7'],
  [/shared\/(order-[a-z]+|product-catalog[a-z-]*)\.(js|css|json)$|order\.css$/, 'dialog:cashier,p360:consult', 'F4–F7, G6'],
  [/shared\/patient\.js$|patient-mobile\//, 'mobile:', 'E, G, K'],
  [/shared\/guide\.(js|css)$/, 'clinic:guide', 'F16'],
  [/shared\/staff-context\.js$/, 'clinic:', 'A6, B, C, D, F17'],
  [/shared\/(care-finance|finance-bridge)\.js$|prototype\/finance\//, 'finance:,clinic:finance', 'A7, D, H'],
  [/shared\/(design|styles|workspace-layout)\.css$/, '(tokens/layout — read the CSS diff)', '"Nền tảng" section + every screen'],
  [/shared\/ui\.js$|clinic-web\/index\.html$/, '(shared helper/shell)', 'unknown'],
];

const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trim();
const text = fs.readFileSync(LOG, 'utf8');
const base = text.match(/(?:Sync baseline|Mốc đồng bộ):\s*`([0-9a-f]{7,40})`/)?.[1];
if (!base) {
  console.error(`No "Sync baseline: \`<commit>\`" line in ${LOG}`);
  process.exit(2);
}

const pending = (text.split(/^## (?:Pending|Chờ chuyển)\s*$/m)[1] || '').split(/^## /m)[0];
const entries = pending.split(/^### /m).slice(1).map((e) => e.trim());

const changed = new Set();
const add = (out) => out.split('\n').filter(Boolean).forEach((f) => changed.add(f.trim()));
add(git('diff', '--name-only', `${base}..HEAD`, '--', ...WATCH));
add(git('diff', '--name-only', 'HEAD', '--', ...WATCH));
add(git('ls-files', '--others', '--exclude-standard', '--', ...WATCH));

console.log(`Sync baseline: ${base} (${git('log', '-1', '--format=%h %ad %s', '--date=short', base)})`);
console.log(`HEAD:          ${git('log', '-1', '--format=%h %ad %s', '--date=short')}\n`);

console.log(`Pending entries: ${entries.length}`);
for (const e of entries) console.log(`  - ${e.split('\n')[0]}`);

const files = [...changed].sort();
console.log(`\nWeb files changed since baseline: ${files.length}`);
const only = new Set();
let unlogged = 0;
for (const f of files) {
  const hit = MAP.find(([re]) => re.test(f));
  const logged = entries.some((e) => e.includes(path.basename(f)));
  if (!logged) unlogged++;
  if (hit && !hit[1].startsWith('(')) hit[1].split(',').forEach((p) => only.add(p));
  console.log(`  ${logged ? '✓' : '✗ NOT LOGGED'}  ${f}  →  canvas ${hit ? hit[2] : 'unknown'}  ${hit && hit[1].startsWith('(') ? hit[1] : ''}`);
}

if (!entries.length && !files.length) {
  console.log('\nNothing to convert: the canvas matches the web at this baseline.');
  process.exit(0);
}
if (only.size) console.log(`\nSuggested dump:\n  node dump-web.cjs <out> --only=${[...only].join(',')}`);
if (unlogged) {
  console.log(`\n${unlogged} changed file(s) not named by any entry: read \`git diff ${base} -- <file>\` and add the entries before converting.`);
}

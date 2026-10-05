#!/usr/bin/env node
// D6: what changed in the Next.js front end since the web canvas last matched it, so the pema-web-design skill only redoes those screens.
// Mirrors .claude/skills/pema-web-to-canvas/scripts/pending.cjs, for pema-agent/frontend instead of prototype/.
//
// Reads "Sync baseline" and "## Pending" from web-design-changes.md, lists the visible files changed under pema-agent/frontend/src/{app,ui,components}/
// since that commit (committed, staged, unstaged, untracked), and flags files no pending entry names.
// Not visible, so not watched: tests, snapshots, type declarations, route handlers (route.ts), fonts.
//
//   node pending-web.cjs        (run from the repo root; exit 1 when a file is "✗ NOT LOGGED", exit 2 without a baseline, else 0)
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const LOG = path.join(__dirname, '..', 'web-design-changes.md');
const INVENTORY = path.join(ROOT, 'design-specs', 'web', 'inventory.json');
const WATCH = ['pema-agent/frontend/src/app/', 'pema-agent/frontend/src/ui/', 'pema-agent/frontend/src/components/'];
const IGNORE = [/\.test\.[jt]sx?$/, /\.snap$/, /__snapshots__\//, /\.d\.ts$/, /\/route\.ts$/, /\/fonts\//, /\.(ttf|woff2?|txt)$/, /tokens\.schema\.json$/];
const GENERIC = new Set(['page.tsx', 'layout.tsx', 'loading.tsx', 'error.tsx', 'index.ts', 'index.tsx']);

const git = (...args) => execFileSync('git', args, { encoding: 'utf8', cwd: ROOT }).trim();
const text = fs.readFileSync(LOG, 'utf8').replace(/\r\n/g, '\n');
const base = text.match(/Sync baseline:\s*`([0-9a-f]{7,40})`/)?.[1];
if (!base) {
  console.error(`No "Sync baseline: \`<commit>\`" line in ${LOG}`);
  process.exit(2);
}
try {
  git('cat-file', '-e', `${base}^{commit}`);
} catch {
  console.error(`Sync baseline ${base} is not in git history (rebased or squashed?). Pick the commit the web canvas last matched, write it in ${path.basename(LOG)}, and run again.`);
  process.exit(2);
}

const pending = (text.split(/^## Pending\s*$/m)[1] || '').split(/^## /m)[0];
const entries = pending.split(/^### /m).slice(1).map((e) => e.trim());

const changed = new Set();
const add = (out) => out.split('\n').filter(Boolean).forEach((f) => changed.add(f.trim()));
add(git('diff', '--name-only', `${base}..HEAD`, '--', ...WATCH));
add(git('diff', '--name-only', 'HEAD', '--', ...WATCH));
add(git('ls-files', '--others', '--exclude-standard', '--', ...WATCH));
const files = [...changed].filter((f) => !IGNORE.some((re) => re.test(f))).sort();

// route of a src/app file -> inventory ids whose next_route is that route (route groups "(admin)" do not count).
const inv = JSON.parse(fs.readFileSync(INVENTORY, 'utf8'));
function canvasTarget(f) {
  const m = /^pema-agent\/frontend\/src\/(app|ui|components)\/(.*)$/.exec(f);
  if (!m) return 'unknown';
  if (m[1] === 'ui') {
    if (/tokens\.(json|css)$/.test(f)) return 'token block of both web canvases (web-canvas-build.cjs --check) + every frame';
    return 'block of references/blocks-web.md for this kit component; every frame that uses it (design-specs/web/BLOCKS.md "Used in the canvas")';
  }
  if (m[1] === 'components') return 'unknown: find the screens that render this component (grep its name in src/app)';
  const segs = m[2].split('/').filter((s) => !/^\(.*\)$/.test(s));
  segs.pop(); // page.tsx / layout.tsx / local component file
  if (!segs.length) return 'app shell: WA1–WA4 (+ every page frame if the shell changes)';
  const route = `/${segs.join('/')}`;
  const ids = inv.screens.filter((s) => s.next_route && (s.next_route === route || s.next_route.startsWith(`${route}/`))).map((s) => s.id);
  return ids.length ? `${ids.join(', ')} (route ${route})` : `none: route ${route} has no web canvas screen (D3: Next.js-only screens are not in the web canvas); still log it`;
}

const isLogged = (f) => {
  const rel = f.replace(/^pema-agent\/frontend\//, '');
  const base = path.basename(f);
  return entries.some((e) => e.includes(f) || e.includes(rel) || (!GENERIC.has(base) && e.includes(base)));
};

console.log(`Sync baseline: ${base} (${git('log', '-1', '--format=%h %ad %s', '--date=short', base)})`);
console.log(`HEAD:          ${git('log', '-1', '--format=%h %ad %s', '--date=short')}\n`);

console.log(`Pending entries: ${entries.length}`);
for (const e of entries) console.log(`  - ${e.split('\n')[0]}`);

console.log(`\nVisible front-end files changed since baseline: ${files.length}`);
let unlogged = 0;
for (const f of files) {
  const logged = isLogged(f);
  if (!logged) unlogged++;
  console.log(`  ${logged ? '✓' : '✗ NOT LOGGED'}  ${f}  →  web canvas ${canvasTarget(f)}`);
}

if (!entries.length && !files.length) {
  console.log('\nNothing to do: the web canvas matches the front end at this baseline.');
  process.exit(0);
}
if (unlogged) {
  console.log(`\n${unlogged} changed file(s) not named by any entry: read \`git diff ${base} -- <file>\`, add the entry under "Pending" in web-design-changes.md, then update the canvas.`);
  process.exit(1);
}

#!/usr/bin/env node
// Hub of the design layers: design-specs/INDEX.md (app 82 + web 384 + Design System), built by lib/hub.cjs.
//   node unify-index.cjs           write design-specs/INDEX.md (design-specs.cjs writes the same file)
//   node unify-index.cjs --check   exit 1 unless the hub is current and the acceptance holds:
//                                  1 current   INDEX.md equals a fresh build (line endings ignored)
//                                  2 sections  App, Web and Design System headings with the expected row counts
//                                  3 links     every relative link resolves to an existing file
//                                  4 mapping   every app id and web id is in the hub; the app -> web reverse map and the
//                                              web -> app column agree; every WI row has status "served by KMP/Zalo",
//                                              an app id or "—", a reason, and the "revisit when Zalo OA exists" note
//                                  5 skills    both SKILL.md files carry the canonical-skill decision
const fs = require('fs');
const path = require('path');
const hub = require('./lib/hub.cjs');

const norm = (s) => s.replace(/^﻿/, '').replace(/\r\n/g, '\n');
const INDEX = path.join(hub.SPECS, 'INDEX.md');
const appModel = JSON.parse(norm(fs.readFileSync(path.join(hub.SPECS, 'index.json'), 'utf8')));
const fresh = hub.hubMarkdown(appModel);

if (!process.argv.includes('--check')) {
  if (fs.existsSync(INDEX) && norm(fs.readFileSync(INDEX, 'utf8')) === fresh) console.log('design-specs/INDEX.md already current');
  else {
    fs.writeFileSync(INDEX, fresh);
    console.log('design-specs/INDEX.md written');
  }
  process.exit(0);
}

const errors = [];
const fail = (m) => errors.push(m);
const text = fs.existsSync(INDEX) ? norm(fs.readFileSync(INDEX, 'utf8')) : '';

// 1 current
if (text !== fresh) fail('1 current: INDEX.md differs from a fresh build; run unify-index.cjs');

// 2 sections
const { index } = hub.loadWeb();
const web = index.screens;
const want = [
  `## 1. App (${appModel.screens.length})`,
  `## 2. Web (${web.length})`,
  '## 3. Design System',
  '### 2.2 Patient Mobile web (WI): served by KMP/Zalo',
];
for (const h of want) if (!text.includes(`\n${h}\n`)) fail(`2 sections: missing heading "${h}"`);
const rows = (re) => text.split('\n').filter((l) => re.test(l));
const appRows = rows(/^\| \[[A-K]\d+\]\(screens\//);
if (appRows.length !== appModel.screens.length) fail(`2 sections: ${appRows.length} app rows, expected ${appModel.screens.length}`);
const webRows = rows(/^\| \[W[A-L]\d+\]\(web\/screens\//);
const wiCount = web.filter((w) => w.group === 'WI').length;
if (webRows.length !== web.length) fail(`2 sections: ${webRows.length} web rows, expected ${web.length} (each id once as the first cell of a row)`);

// 3 links
let linkCount = 0;
for (const m of text.matchAll(/\]\(([^)#]+)\)/g)) {
  const target = m[1];
  if (/^[a-z]+:/i.test(target)) continue;
  linkCount++;
  const file = path.join(hub.SPECS, decodeURIComponent(target));
  if (!fs.existsSync(file)) fail(`3 links: ${target} does not exist`);
}

// 4 mapping
const appIds = new Set(appModel.screens.map((s) => s.id));
for (const s of appModel.screens) if (!text.includes(`[${s.id}](screens/${s.id}.md)`)) fail(`4 mapping: app id ${s.id} missing`);
for (const w of web) if (!text.includes(`[${w.id}](web/screens/${w.id}.md)`)) fail(`4 mapping: web id ${w.id} missing`);
const rev = hub.reverseMap(web);
for (const [a, ids] of rev) {
  if (!appIds.has(a)) {
    fail(`4 mapping: web ids ${ids.join(', ')} cite unknown app id ${a}`);
    continue;
  }
  const row = appRows.find((r) => r.startsWith(`| [${a}](`)) || '';
  for (const id of ids) if (!row.includes(`[${id}](web/screens/${id}.md)`)) fail(`4 mapping: app row ${a} lacks reverse link to ${id}`);
}
for (const w of web) {
  const row = webRows.find((r) => r.startsWith(`| [${w.id}](`)) || '';
  for (const a of w.app_canvas || []) if (!row.includes(`[${a}](screens/${a}.md)`)) fail(`4 mapping: web row ${w.id} lacks link to ${a}`);
}
const { servedBy } = hub.loadWeb();
for (const w of web.filter((x) => x.group === 'WI')) {
  if (w.next_status !== 'served by KMP/Zalo') fail(`4 mapping: ${w.id} status is "${w.next_status}", expected "served by KMP/Zalo"`);
  if (!((servedBy.reasons || {})[w.id] || '').trim()) fail(`4 mapping: ${w.id} has no reason in notes.json served_by.reasons`);
  if (!Array.isArray(w.app_canvas)) fail(`4 mapping: ${w.id} has no app_canvas list`);
}
if (!/Revisit when the clinic has a Zalo OA/.test(text)) fail('4 mapping: the "revisit when Zalo OA exists" note is missing');

// 5 skills
for (const [name, marker] of [
  ['pema-web-design', 'Canonical skill'],
  ['pema-web-to-canvas', 'Canonical skill'],
]) {
  const f = path.join(hub.ROOT, '.claude', 'skills', name, 'SKILL.md');
  const t = fs.existsSync(f) ? norm(fs.readFileSync(f, 'utf8')) : '';
  const head = t.split('\n').slice(0, 14).join('\n');
  if (!head.includes(marker)) fail(`5 skills: ${name}/SKILL.md has no "${marker}" note at the top`);
}

if (errors.length) {
  console.error(errors.slice(0, 30).join('\n'));
  console.error(`unify-index: ${errors.length} failure(s)`);
  process.exit(1);
}
console.log(`unify-index: ok (app ${appRows.length}, web ${web.length}, WI ${wiCount} mapped with reason, ${linkCount} links resolve)`);

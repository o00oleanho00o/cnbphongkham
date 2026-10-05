#!/usr/bin/env node
// Test script of design-system/. Plain Node, no dependencies. Exit 1 on any failure.
//
//   node design-system/scripts/check.cjs
//
// Checks
//   1 schema        tokens.json validates against tokens.schema.json; a bad colour is rejected; identity values are the Pema ones
//   2 frontend      tokens.json and tokens.schema.json equal pema-agent/frontend/src/ui/ (the web kit reads that copy)
//   3 generated     build.cjs --check: colours, type, spacing and component pages are what the build writes now
//   4 components    every block of design-specs/web/BLOCKS.md has a page with every section; no page without a block
//   5 mapping       the kit component and the KMP composable named for a block exist (or are classified)
//   6 colours       every --color-* the canvas sources and built canvases use is a token and is listed in colors.md;
//                   no hex colour in template.html, nodes.html or a part
//   7 canvases      the three web canvas files point to design-system/
//   8 contrast      the text pairs of colors.md are at least 4.5:1 in light mode (dark-mode misses are reported, not failed)
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const build = require('./build.cjs');

const DS = path.resolve(__dirname, '..');
const ROOT = path.resolve(DS, '..');
const UI = path.join(ROOT, 'pema-agent', 'frontend', 'src', 'ui');
const CANVAS_DIR = path.join(ROOT, 'Pema Web redesign canvas');
const read = (p) => fs.readFileSync(p, 'utf8').replace(/^﻿/, '').replace(/\r\n/g, '\n');

const failures = [];
const notes = [];
let passed = 0;
const fail = (area, msg) => failures.push(`${area}: ${msg}`);
const ok = (area, msg) => {
  passed += 1;
  console.log(`ok   ${area}: ${msg}`);
};

// ---------------------------------------------------------------------------------------------------------------------
// 1 schema: the small subset of JSON Schema that tokens.schema.json uses
// ---------------------------------------------------------------------------------------------------------------------
function validate(schema, value, root = schema, at = '$') {
  const errors = [];
  if (schema.$ref) {
    const target = schema.$ref.replace(/^#\//, '').split('/').reduce((o, k) => o[k], root);
    return validate(target, value, root, at);
  }
  if ('const' in schema && value !== schema.const) errors.push(`${at}: must be ${JSON.stringify(schema.const)}`);
  if (schema.type === 'object') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return [`${at}: must be an object`];
    for (const k of schema.required || []) if (!(k in value)) errors.push(`${at}: missing "${k}"`);
    const props = schema.properties || {};
    for (const [k, v] of Object.entries(value)) {
      if (schema.propertyNames && schema.propertyNames.pattern && !new RegExp(schema.propertyNames.pattern).test(k)) errors.push(`${at}: bad name "${k}"`);
      if (props[k]) errors.push(...validate(props[k], v, root, `${at}.${k}`));
      else if (schema.additionalProperties === false) errors.push(`${at}: unexpected "${k}"`);
      else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') errors.push(...validate(schema.additionalProperties, v, root, `${at}.${k}`));
    }
  } else if (schema.type === 'string') {
    if (typeof value !== 'string') return [`${at}: must be a string`];
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push(`${at}: "${value}" does not match ${schema.pattern}`);
    if (schema.minLength && value.length < schema.minLength) errors.push(`${at}: too short`);
  }
  return errors;
}

const schema = JSON.parse(read(path.join(DS, 'tokens.schema.json')));
const tokens = build.tokens;
{
  const errors = validate(schema, tokens);
  if (errors.length) fail('schema', errors.slice(0, 5).join('; '));
  const broken = structuredClone(tokens);
  broken.color.light.ink = 'navy';
  if (validate(schema, broken).length === 0) fail('schema', 'a colour written as "navy" is accepted');
  const unknown = structuredClone(tokens);
  unknown.extra = {};
  if (validate(schema, unknown).length === 0) fail('schema', 'an unknown top-level group is accepted');
  const identity = { 'brand-500': '#0b4f94', 'brand-600': '#083a6e', 'brand-400': '#3caae5', ink: '#17324d', canvas: '#f4f8fb', surface: '#ffffff', line: '#d9e5ee' };
  for (const [k, v] of Object.entries(identity)) if (tokens.color.light[k] !== v) fail('schema', `identity colour ${k} is ${tokens.color.light[k]}, expected ${v}`);
  if (tokens.font['family-ui'] !== '"Be Vietnam Pro"') fail('schema', 'font family is not Be Vietnam Pro');
  if (!failures.some((f) => f.startsWith('schema'))) ok('schema', `tokens.json valid (${Object.keys(tokens.color.light).length} colours, ${Object.keys(tokens.text).length} sizes), bad colour and unknown group rejected, identity values match`);
}

// ---------------------------------------------------------------------------------------------------------------------
// 2 frontend copy
// ---------------------------------------------------------------------------------------------------------------------
{
  let bad = 0;
  for (const f of ['tokens.json', 'tokens.schema.json']) {
    const mine = read(path.join(DS, f));
    const theirs = read(path.join(UI, f));
    if (mine !== theirs) {
      bad += 1;
      fail('frontend', `${f} differs from pema-agent/frontend/src/ui/${f}: change tokens.css, run \`pnpm tokens\` and copy the file here (or the other way round, see README "Change rule")`);
    }
  }
  if (!bad) ok('frontend', 'tokens.json and tokens.schema.json equal pema-agent/frontend/src/ui/');
}

// ---------------------------------------------------------------------------------------------------------------------
// 3 generated files
// ---------------------------------------------------------------------------------------------------------------------
{
  try {
    const out = execFileSync(process.execPath, [path.join(__dirname, 'build.cjs'), '--check'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    ok('generated', out.trim());
  } catch (e) {
    fail('generated', String(e.stderr || e.message).trim().split('\n').slice(0, 6).join('; '));
  }
}

// ---------------------------------------------------------------------------------------------------------------------
// 4 components
// ---------------------------------------------------------------------------------------------------------------------
const blocks = build.parseBlocks();
{
  const sections = ['## Anatomy', '## Variants', '## States', '## Tokens', '## Do', "## Don't", '## Web (1440 and 1920)', '## Mobile (390)', '## Rules (design-specs/web/BLOCKS.md)'];
  let bad = 0;
  for (const b of blocks) {
    const p = path.join(DS, 'components', `${b.name}.md`);
    if (!fs.existsSync(p)) {
      bad += 1;
      fail('components', `no page for block ${b.name}`);
      continue;
    }
    const text = read(p);
    for (const s of sections) if (!text.includes(s)) { bad += 1; fail('components', `${b.name}.md lacks "${s}"`); }
    if (!text.includes(b.helper)) { bad += 1; fail('components', `${b.name}.md does not carry the helper of BLOCKS.md`); }
  }
  const have = fs.readdirSync(path.join(DS, 'components')).filter((f) => f.endsWith('.md') && f !== 'INDEX.md');
  for (const f of have) if (!blocks.some((b) => `${b.name}.md` === f)) { bad += 1; fail('components', `${f} is a page without a block`); }
  if (!bad) ok('components', `${blocks.length} blocks in BLOCKS.md, ${have.length} pages, all sections present`);
}

// ---------------------------------------------------------------------------------------------------------------------
// 5 mapping
// ---------------------------------------------------------------------------------------------------------------------
{
  let bad = 0;
  const names = build.kmpNames();
  for (const b of blocks) {
    for (const m of b.kit.matchAll(/`([A-Za-z]+)` \(`([a-z-]+\.tsx?)`/g)) {
      const file = path.join(UI, m[2]);
      if (!fs.existsSync(file)) { bad += 1; fail('mapping', `${b.name}: ${m[2]} does not exist in src/ui`); continue; }
      if (!new RegExp(`\\b${m[1]}\\b`).test(read(file))) { bad += 1; fail('mapping', `${b.name}: ${m[1]} is not in ${m[2]}`); }
    }
    for (const n of build.kmpStatus(b.kmp, names).names) {
      if (!names.has(n) && !build.KMP_OUTSIDE[n]) { bad += 1; fail('mapping', `${b.name}: KMP name ${n} is neither in core:ui nor classified in build.cjs KMP_OUTSIDE`); }
    }
  }
  const indexText = read(path.join(DS, 'components', 'INDEX.md'));
  for (const b of blocks) if (!indexText.includes(`[${b.name}.md]`)) { bad += 1; fail('mapping', `INDEX.md has no row for ${b.name}`); }
  const nameOnly = [...new Set(blocks.flatMap((b) => build.kmpStatus(b.kmp, names).names).filter((n) => !names.has(n)))];
  if (!bad) ok('mapping', `every block has a row; kit files and KMP names resolve (not in core:ui, classified: ${nameOnly.join(', ') || 'none'})`);
}

// ---------------------------------------------------------------------------------------------------------------------
// 6 colours
// ---------------------------------------------------------------------------------------------------------------------
{
  const sources = [path.join(CANVAS_DIR, 'template.html'), path.join(CANVAS_DIR, 'nodes.html')];
  for (const f of fs.readdirSync(path.join(CANVAS_DIR, 'parts'))) if (f.endsWith('.js')) sources.push(path.join(CANVAS_DIR, 'parts', f));
  const built = fs.readdirSync(CANVAS_DIR).filter((f) => f.endsWith('.dc.html')).map((f) => path.join(CANVAS_DIR, f));
  const used = new Map();
  for (const f of [...sources, ...built]) {
    for (const m of read(f).matchAll(/var\(--color-([a-z0-9-]+)/g)) used.set(m[1], (used.get(m[1]) || 0) + 1);
  }
  const colorsMd = read(path.join(DS, 'colors.md'));
  let bad = 0;
  for (const name of used.keys()) {
    if (!(name in tokens.color.light)) { bad += 1; fail('colours', `frames use --color-${name}, which is not a token`); }
    else if (!colorsMd.includes(`\`--color-${name}\``)) { bad += 1; fail('colours', `--color-${name} is used by frames but not listed in colors.md`); }
  }
  for (const f of sources) {
    const text = read(f);
    // a 6-digit hex anywhere (not an HTML entity such as &#123456), a 3-digit one only in a CSS value position
    const hex = [...text.matchAll(/(?<![&\w])#[0-9a-fA-F]{6}\b|[:(,]\s*#[0-9a-fA-F]{3}\b/g)].map((m) => m[0].replace(/^[:(,]\s*/, ''));
    if (hex.length) { bad += 1; fail('colours', `${path.relative(ROOT, f)} writes hex colours: ${[...new Set(hex)].slice(0, 5).join(', ')}`); }
  }
  const unused = Object.keys(tokens.color.light).filter((n) => !used.has(n));
  if (!bad) ok('colours', `${used.size} colours used by ${sources.length} sources and ${built.length} built canvases, all tokens and all in colors.md, no hex outside the token block (tokens no frame uses yet: ${unused.join(', ') || 'none'})`);
}

// ---------------------------------------------------------------------------------------------------------------------
// 7 canvases point to design-system/
// ---------------------------------------------------------------------------------------------------------------------
{
  let bad = 0;
  const files = fs.readdirSync(CANVAS_DIR).filter((f) => f.endsWith('.dc.html'));
  if (files.length < 3) { bad += 1; fail('canvases', `expected 3 web canvas files, found ${files.length}`); }
  for (const f of files) {
    const text = read(path.join(CANVAS_DIR, f));
    if (!text.includes('<meta name="design_system" content="design-system/README.md">')) { bad += 1; fail('canvases', `${f} has no design_system metadata`); }
    if (!text.includes('design-system/')) { bad += 1; fail('canvases', `${f} does not mention design-system/`); }
  }
  if (!bad) ok('canvases', `${files.length} web canvas files carry the design_system metadata and the visible pointer`);
}

// ---------------------------------------------------------------------------------------------------------------------
// 8 contrast
// ---------------------------------------------------------------------------------------------------------------------
{
  const pairs = [
    ['ink', 'surface'], ['ink', 'canvas'], ['ink-soft', 'surface'], ['ink-soft', 'canvas'], ['ink-soft', 'tile'], ['heading', 'surface'], ['link', 'surface'],
    ['surface', 'brand-500'], ['surface', 'brand-600'], ['brand-700', 'brand-50'], ['surface', 'accent-strong'],
    ['success', 'success-soft'], ['info', 'info-soft'], ['warning', 'warning-soft'], ['danger', 'danger-soft'], ['surface', 'danger'],
  ];
  const at = (mode, n) => tokens.color[mode][n] ?? tokens.color.light[n];
  let bad = 0;
  const dark = [];
  for (const [fg, bg] of pairs) {
    if (build.contrast(at('light', fg), at('light', bg)) < 4.5) { bad += 1; fail('contrast', `light ${fg} on ${bg} is ${build.contrast(at('light', fg), at('light', bg)).toFixed(2)}:1`); }
    const d = build.contrast(at('dark', fg), at('dark', bg));
    if (d < 4.5) dark.push(`${fg} on ${bg} ${d.toFixed(2)}:1`);
  }
  if (dark.length) notes.push(`dark mode below 4.5:1 (reported, not a failure of this step): ${dark.join('; ')}`);
  if (!bad) ok('contrast', `${pairs.length} text pairs are at least 4.5:1 in light mode`);
}

// ---------------------------------------------------------------------------------------------------------------------
notes.forEach((n) => console.log(`note ${n}`));
if (failures.length) {
  failures.forEach((f) => console.error(`FAILED ${f}`));
  console.error(`${failures.length} failure(s), ${passed} check(s) passed`);
  process.exit(1);
}
console.log(`all ${passed} check groups passed`);

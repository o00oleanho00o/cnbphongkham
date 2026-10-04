// Shared by web-canvas-build.cjs, web-canvas.cjs and web-specs-lib.cjs (W3a).
// The web canvas is GENERATED: template.html (frame, shell, CSS) + nodes.html (block markup, expanded at every nesting
// level) + parts/base.js + parts/WA.js ... WH.js + parts/tail.js + tokens.json  ->  "Pema Web.dc.html".
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '../../../../..');
const CANVAS_DIR = path.join(ROOT, 'Pema Web redesign canvas');
const CANVAS_FILE = 'Pema Web.dc.html';
const BLOCKS_FILE = 'Pema Web blocks.dc.html';
const TOKENS = path.join(ROOT, 'pema-agent', 'frontend', 'src', 'ui', 'tokens.json');
const INVENTORY = path.join(ROOT, 'design-specs', 'web', 'inventory.json');
const GROUP_CODES = ['WA', 'WB', 'WC', 'WD', 'WE', 'WF', 'WG', 'WH'];
const GROUP_SUB = {
  WA: 'Sidebar, thanh trên, tài khoản demo, thông báo nổi · AppShell',
  WB: 'Tổng quan, hôm nay, điều phối lịch, đặt lịch, chi tiết lịch hẹn',
  WC: 'Tìm bệnh nhân, Patient 360 (8 tab), hộp thoại và modal của hồ sơ',
  WD: 'CSKH hôm nay, Xử lý, protocol, nhóm khách, Theo dõi, duyệt phản hồi',
  WE: 'Ảnh trước / sau, Bác sĩ & phòng, khóa phòng, Dịch vụ',
  WF: 'Thu ngân, thu tiền, lên đơn nhanh, tách đơn và bản in A5',
  WG: 'Tài chính & tiền thủ thuật theo vai trò: chủ phòng khám, kế toán, bác sĩ',
  WH: 'Ask Pema và Hướng dẫn sử dụng'
};

const lf = (s) => s.replace(/\r\n/g, '\n');
const read = (p) => lf(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));
const sha = (s) => crypto.createHash('sha256').update(lf(s)).digest('hex').slice(0, 16);

// ---------- tokens ----------
const GROUP_PREFIX = { color: 'color', radius: 'radius', shadow: 'shadow', text: 'text', space: 'space', layout: 'layout', breakpoint: 'breakpoint', z: 'z', font: 'font' };

/** Expected CSS variables of tokens.json: { light: { '--color-ink': '#17324d', ... }, dark: {...overrides} }. */
function tokenVars(tokens) {
  const light = {};
  const dark = {};
  for (const [group, entries] of Object.entries(tokens)) {
    if (group === 'color') {
      for (const [k, v] of Object.entries(entries.light)) light[`--color-${k}`] = v;
      for (const [k, v] of Object.entries(entries.dark)) dark[`--color-${k}`] = v;
    } else if (GROUP_PREFIX[group]) {
      for (const [k, v] of Object.entries(entries)) light[`--${GROUP_PREFIX[group]}-${k}`] = v;
    }
  }
  return { light, dark };
}

function tokenCss(tokens) {
  const { light, dark } = tokenVars(tokens);
  const body = (o) => Object.entries(o).map(([k, v]) => `${k}:${v}`).join(';');
  return { light: `:root{${body(light)}}`, dark: `[data-theme=dark]{${body(dark)}}` };
}

/** Variables written into a built canvas, to compare with tokens.json. */
function tokenVarsOfCanvas(html) {
  const grab = (re) => {
    const m = re.exec(html);
    const o = {};
    if (!m) return null;
    for (const decl of m[1].split(';')) {
      const i = decl.indexOf(':');
      if (i > 0) o[decl.slice(0, i).trim()] = decl.slice(i + 1).trim();
    }
    return o;
  };
  return { light: grab(/:root\{([^}]*)\}/), dark: grab(/\[data-theme=dark\]\{([^}]*)\}/) };
}

function compareTokens(html) {
  const want = tokenVars(JSON.parse(read(TOKENS)));
  const got = tokenVarsOfCanvas(html);
  const problems = [];
  for (const mode of ['light', 'dark']) {
    if (!got[mode]) {
      problems.push(`no ${mode} token block in the canvas`);
      continue;
    }
    for (const [k, v] of Object.entries(want[mode])) if (got[mode][k] !== v) problems.push(`${mode} ${k}: canvas ${got[mode][k] === undefined ? 'missing' : got[mode][k]}, tokens.json ${v}`);
    for (const k of Object.keys(got[mode])) if (!(k in want[mode])) problems.push(`${mode} ${k}: in the canvas but not in tokens.json`);
  }
  return problems;
}

// ---------- node markup ----------
function parseNodes(src) {
  const sec = (name) => {
    const m = new RegExp(`<!--@${name}-->([\\s\\S]*?)<!--@end-->`).exec(src);
    if (!m) throw new Error(`nodes.html: section ${name} not found`);
    return m[1];
  };
  return { inline: sec('inline'), leaf: sec('leaf'), cont: sec('cont') };
}

const MAX_LEVEL = 4; // containers at levels 0-3, leaves up to level 4

function inlineBody(S, v) {
  return S.inline.replace(/\$V/g, v);
}

function expandInline(S, text, L) {
  return text
    .replace(/<!--@inl ([^>]+?)-->/g, (_, e) => `<sc-for list="{{ ${e.trim()} }}" as="x${L}">${inlineBody(S, `x${L}`)}</sc-for>`)
    .replace(/<!--@in ([A-Za-z0-9_]+)-->/g, (_, v) => inlineBody(S, v));
}

/** Markup of one list item at nesting level L (variable b<L>), including the levels below it. */
function nodeMarkup(S, L) {
  const V = `b${L}`;
  let text = S.inline + S.leaf + (L < MAX_LEVEL ? S.cont : '');
  text = text.replace(/\$V/g, V).replace(/\$L/g, String(L));
  text = text.replace(/<!--@kids-->/g, () => `<sc-for list="{{ ${V}.kids }}" as="b${L + 1}">${nodeMarkup(S, L + 1)}</sc-for>`);
  return expandInline(S, text, L);
}

const squeeze = (s) => s.replace(/<!--[\s\S]*?-->/g, '').replace(/>\s+</g, '><').replace(/\n\s*/g, ' ').replace(/\s{2,}/g, ' ');

function groupDefs() {
  const inv = JSON.parse(read(INVENTORY));
  return GROUP_CODES.map((code) => {
    const g = inv.groups.find((x) => x.code === code);
    return { code, title: g ? g.name : code, sub: GROUP_SUB[code] };
  });
}

function propsJson(defs) {
  const meta = {
    showNotes: { editor: 'boolean', default: true, tsType: 'boolean', section: 'Canvas' },
    theme: { editor: 'enum', default: 'light', options: ['light', 'dark'], tsType: 'string', section: 'Canvas' },
    viewport: { editor: 'enum', default: '1440x900', options: ['1440x900', '1920x1020', '390x844', 'Tất cả'], tsType: 'string', section: 'Canvas' },
    group: { editor: 'enum', default: 'Tất cả', options: ['Tất cả', ...defs.map((g) => `${g.code} · ${g.title}`)], tsType: 'string', section: 'Canvas' }
  };
  return JSON.stringify(meta).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

const RENDER_VALS = `
  renderVals() {
    const showNotes = this.props.showNotes ?? true;
    const theme = this.props.theme ?? 'light';
    const viewport = this.props.viewport ?? '1440x900';
    const only = this.props.group ?? 'Tất cả';
    const groups = this.build().filter(g => only === 'Tất cả' || only.startsWith(g.code + ' ')).map(g => ({
      ...g,
      screens: g.screens.map(sc => ({
        ...sc,
        frames: sc.frames.filter(f => viewport === 'Tất cả' || f.size === viewport).map((f, i) => ({ ...f, id: i === 0 ? sc.id : sc.id + '-' + f.w, label: sc.id + ' · ' + sc.name + ' · ' + f.size }))
      })).filter(sc => sc.frames.length)
    }));
    return { groups, showNotes, theme };
  }`;

function buildScript(defs, blocks) {
  // the block gallery replaces WA with parts/blocks.js and leaves the other groups empty
  const names = ['base', ...GROUP_CODES.map((c) => (blocks ? (c === 'WA' ? 'blocks' : null) : c)), 'tail'];
  const parts = names.map((n, i) => (n === null ? `const ${GROUP_CODES[i - 1]} = [];` : read(path.join(CANVAS_DIR, 'parts', `${n}.js`)).replace(/\s+$/, '')));
  const [base, ...rest] = parts;
  const tail = rest.pop();
  const indent = (s) => s.split('\n').map((l) => (l ? '    ' + l : l)).join('\n');
  const body = [base, `const GROUP_DEFS = ${JSON.stringify(defs)};`, ...rest, tail].map(indent).join('\n\n');
  return `class Component extends DCLogic {\n  build() {\n${body}\n  }\n${RENDER_VALS}\n}`;
}

/** The text of "Pema Web.dc.html". */
function buildCanvas(opts = {}) {
  const defs = groupDefs();
  const S = parseNodes(read(path.join(CANVAS_DIR, 'nodes.html')));
  const tpl = read(path.join(CANVAS_DIR, 'template.html'));
  const tok = tokenCss(JSON.parse(read(TOKENS)));
  let out = tpl
    .replace('/*@tokens*/', () => tok.light)
    .replace('/*@dark*/', () => tok.dark)
    .replace(/<!--@nodes list="([^"]+)"-->/g, (_, e) => `<sc-for list="{{ ${e} }}" as="b0">${nodeMarkup(S, 0)}</sc-for>`)
    .replace(/<!--@inl ([^>]+?)-->/g, (_, e) => `<sc-for list="{{ ${e.trim()} }}" as="xf">${inlineBody(S, 'xf')}</sc-for>`);
  out = out
    .replace('/*@props*/', () => propsJson(defs))
    .replace('/*@script*/', () => buildScript(defs, !!opts.blocks));
  const marker = '<meta name="viewport" content="width=device-width, initial-scale=1">';
  out = out.replace(marker, () => `${marker}\n<!-- Generated by .claude/skills/pema-web-design/scripts/web-canvas-build.cjs from template.html, nodes.html, parts/*.js and tokens.json. Edit those, not this file. -->`);
  // squeeze only the markup between <x-dc> and </x-dc>: the helmet CSS and the script keep their line breaks
  out = out.replace(/(<x-dc>)([\s\S]*?)(<\/x-dc>)/, (_, a, b, c) => {
    const helm = /<helmet>[\s\S]*?<\/helmet>/.exec(b)[0];
    const rest = b.replace(helm, '@@HELMET@@');
    return a + '\n' + squeeze(rest).replace('@@HELMET@@', () => '\n' + helm + '\n') + '\n' + c;
  });
  if (!out.endsWith('\n')) out += '\n';
  return out;
}

module.exports = { ROOT, CANVAS_DIR, CANVAS_FILE, BLOCKS_FILE, TOKENS, INVENTORY, GROUP_CODES, lf, read, sha, tokenVars, tokenCss, tokenVarsOfCanvas, compareTokens, buildCanvas, buildScript, groupDefs };

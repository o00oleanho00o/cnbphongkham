// Builds the per-screen specs of the OLD Pema web (design-specs/web/screens/<ID>.md) from
//  - design-specs/web/inventory.json  (W0: ids, how to reach, sources, Next.js target, app cross-reference),
//  - design-specs/web/snapshot.json   (W2: structured text-only snapshot of every screen, see web-snapshot.cjs),
//  - design-specs/web/notes.json      (hand-written: logic, rules, differences, gotchas, todo),
// plus read-only context: the app specs index (design-specs/index.json), FEATURE-INVENTORY.md of the Next.js app,
// staff-context.js (who may see what) and src/ui/tokens.json.
// Used by web-specs.cjs (writes design-specs/web/) and the pema-design MCP server (live).
//
// Owner rule: a web spec lists EVERY field, action, status, filter and text of the old screen. Nothing is filtered.
// coverage() proves it: every item of the categorised snapshot lists must appear in the rendered Layout section.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '../../../..');
const WEB = path.join(ROOT, 'design-specs', 'web');
const INVENTORY = path.join(WEB, 'inventory.json');
const SNAPSHOT = path.join(WEB, 'snapshot.json');
const NOTES = path.join(WEB, 'notes.json');
const SCREENS = path.join(WEB, 'screens');
const APP_INDEX = path.join(ROOT, 'design-specs', 'index.json');
const FEATURE = path.join(ROOT, 'pema-agent', 'frontend', 'FEATURE-INVENTORY.md');
const STAFF = path.join(ROOT, 'prototype', 'shared', 'staff-context.js');
const FRONTEND = path.join(ROOT, 'pema-agent', 'frontend');
const IMG_REL = 'pema-agent/frontend/visual-ref/old';
const NOTE_KEYS = ['logic', 'rules', 'differences', 'gotchas', 'todo'];
const GENERATOR = '.claude/skills/pema-web-design/scripts/web-specs.cjs';
const canvasLayout = require('./lib/canvas-layout.cjs');
const BLOCKS_DOC = path.join(ROOT, '.claude', 'skills', 'pema-web-design', 'references', 'blocks-web.md');

const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
const lf = (s) => s.replace(/\r\n/g, '\n');
const read = (p) => lf(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));
const readJson = (p) => JSON.parse(read(p));
const sha = (s) => crypto.createHash('sha256').update(lf(s)).digest('hex').slice(0, 16);
const q = (s) => JSON.stringify(String(s));

// W9: ids that exist only in the Next.js front end (groups WJ, WK, WL; inventory `source: "nextjs"`)
const NEXT_STATUS = 'exists (design W2)';
const isNextjs = (entry) => entry.source === 'nextjs';
const statusOf = (entry) => (entry.planned ? entry.next_status : isNextjs(entry) ? NEXT_STATUS : entry.next_status);
const NAV = path.join(ROOT, 'pema-agent', 'frontend', 'src', 'lib', 'nav.tsx');

// ---------- the kit (target vocabulary) ----------
const KIT = new Set(['AppShell', 'Sidebar', 'TopBar', 'Workspace', 'PageHeading', 'Card', 'Tile', 'TableShell', 'Tabs', 'TabPanel', 'Badge', 'Button', 'Field', 'Dialog', 'Sheet', 'EmptyState', 'GuardedLink']);
const SHARED = new Set(['Notice', 'FilterChip']); // pieces of the app code that sit next to the kit (src/ui/README.md)

// ---------- loading ----------
function loadStaff() {
  const t = read(STAFF);
  const obj = (re) => new Function(`return ${re.exec(t)[1]}`)();
  const pages = obj(/const pages=(\{[\s\S]*?\});/);
  const capabilities = obj(/const capabilities=(\{[\s\S]*?\});/);
  const gated = {};
  for (const m of t.matchAll(/if\(!can\('(\w+)'\)\)document\.querySelectorAll\('([^']+)'\)/g)) {
    const keys = [];
    const other = [];
    for (const sel of m[2].split(',')) {
      const a = /^\[data-([a-z-]+)="([^"]+)"\]$/.exec(sel.trim());
      if (a) keys.push(`${a[1].replace(/-(\w)/g, (_, c) => c.toUpperCase())}=${a[2]}`);
      else other.push(sel.trim());
    }
    gated[m[1]] = { keys, other };
  }
  const tabsRemoved = [];
  const tm = /if\(account\.role==='care'&&\[([^\]]+)\]\.includes\(b\.dataset\.tab\)\|\|account\.role==='accountant'&&\[([^\]]+)\]\.includes/.exec(t);
  if (tm) {
    tabsRemoved.push(['care', tm[1].replace(/'/g, '').split(',')]);
    tabsRemoved.push(['accountant', tm[2].replace(/'/g, '').split(',')]);
  }
  return { pages, capabilities, gated, tabsRemoved };
}

function loadFeatureRows() {
  const rows = {};
  if (!fs.existsSync(FEATURE)) return rows;
  for (const line of read(FEATURE).split('\n')) {
    const m = /^\| `([^`]+)` \| (.*)$/.exec(line);
    if (!m) continue;
    const cells = m[2].split(' | ');
    if (cells.length < 4) continue;
    rows[m[1]] = { screen: cells[0], tests: [...cells[cells.length - 2].matchAll(/`([^`]+)`/g)].map((x) => x[1]), owner: cells[cells.length - 1].replace(/\s*\|\s*$/, '').trim() };
  }
  return rows;
}

/** page.tsx of a route under src/app; route groups such as (admin) are transparent. '' when there is none. */
function routePage(route) {
  if (!route || route.startsWith('(')) return '';
  const segs = route.split('/').filter(Boolean);
  const walk = (dir, i) => {
    if (i === segs.length) {
      const f = path.join(dir, 'page.tsx');
      return fs.existsSync(f) ? f : '';
    }
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return '';
    }
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      if (/^\(.*\)$/.test(e.name)) {
        const hit = walk(path.join(dir, e.name), i);
        if (hit) return hit;
      }
      if (e.name === segs[i]) {
        const hit = walk(path.join(dir, e.name), i + 1);
        if (hit) return hit;
      }
    }
    return '';
  };
  const file = walk(path.join(FRONTEND, 'src', 'app'), 0);
  return file ? rel(file) : '';
}

/** Menu entries of the Next.js shell (src/lib/nav.tsx): route → { label, section, needs[], planned }. */
function loadNav() {
  const out = {};
  if (!fs.existsSync(NAV)) return out;
  let section = '';
  const src = read(NAV);
  const re = /title:\s*"([^"]+)",\s*items:|\{\s*to:\s*"([^"]+)",\s*label:\s*"([^"]+)",[^{}]*?needs:\s*\[([^\]]*)\]([^{}]*?)\}/g;
  for (const m of src.matchAll(re)) {
    if (m[1]) section = m[1];
    else out[m[2]] = { label: m[3], section, needs: [...m[4].matchAll(/"([^"]+)"/g)].map((x) => x[1]), planned: /\bplanned:\s*true\b/.test(m[0]) };
  }
  return out;
}

function loadModel() {
  const inventory = readJson(INVENTORY);
  const snapText = fs.existsSync(SNAPSHOT) ? read(SNAPSHOT) : '';
  const snapshot = snapText ? JSON.parse(snapText) : { meta: {}, screens: {} };
  const notes = fs.existsSync(NOTES) ? readJson(NOTES) : { groups: {}, screens: {} };
  const app = fs.existsSync(APP_INDEX) ? readJson(APP_INDEX) : { screens: [] };
  // W9: Next.js-only ids (source "nextjs") are specified without a snapshot too: their spec is built from the inventory row,
  // notes.json (groups, routes, screens) and a check of the quoted texts against the front-end source; a snapshot of the
  // mock-BE page (W8, `web-snapshot.cjs`) adds the measured layout, tokens and responsive notes when it exists.
  return {
    inventory,
    snapshot,
    snapshotHash: snapText ? sha(snapText) : 'none',
    notes,
    app,
    appById: Object.fromEntries(app.screens.map((s) => [s.id, s])),
    staff: loadStaff(),
    nav: loadNav(),
    feature: loadFeatureRows(),
    groups: Object.fromEntries(inventory.groups.map((g) => [g.code, g])),
    canvas: canvasLayout.loadCanvasScreens(),
  };
}

// ---------- notes ----------
function loadNotes() {
  try {
    return readJson(NOTES);
  } catch {
    return { groups: {}, screens: {} };
  }
}

function saveNotes(notes) {
  fs.mkdirSync(WEB, { recursive: true });
  fs.writeFileSync(NOTES, JSON.stringify(notes, null, 2) + '\n');
}

/** Appends a learned fact to a screen's notes (key: logic | rules | differences | gotchas | todo). */
function addNote(id, kind, text) {
  const notes = loadNotes();
  notes.screens ||= {};
  const s = (notes.screens[id] ||= {});
  const key = NOTE_KEYS.includes(kind) ? kind : 'gotchas';
  (s[key] ||= []).includes(text) || s[key].push(text);
  saveNotes(notes);
  return s;
}

function notesFor(model, entry) {
  const g = (model.notes.groups || {})[entry.group] || {};
  const r = (isNextjs(entry) && (model.notes.routes || {})[entry.next_route]) || {};
  const s = (model.notes.screens || {})[entry.id] || {};
  const out = {};
  for (const k of NOTE_KEYS) out[k] = [...(g[k] || []), ...(r[k] || []), ...(s[k] || [])];
  return out;
}

// ---------- rendering of the layout tree as kit component calls ----------
function attrs(o) {
  return Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== false && v !== '' && v !== null)
    .map(([k, v]) => (v === true ? ` ${k}` : typeof v === 'string' ? ` ${k}=${q(v)}` : ` ${k}={${JSON.stringify(v)}}`))
    .join('');
}

const BADGE_TONE = [
  [/status-green|approved|success|\bdone\b/, 'success'],
  [/status-yellow|warning|urgent|pending|draft/, 'warning'],
  [/status-red|danger|overdue|missing|error/, 'danger'],
  [/status-blue|\binfo\b/, 'info'],
  [/chip-soft/, 'brand'],
];
const badgeTone = (c) => (BADGE_TONE.find(([re]) => re.test(c || '')) || [0, 'neutral'])[1];
const noticeTone = (c) => (/ops-error|crm-error|danger/.test(c || '') ? 'danger' : /alert-strip|warning|print-blocked|draft-mark|urgent/.test(c || '') ? 'warning' : 'info');

function ctxNew() {
  return { used: {} };
}
const use = (ctx, name) => {
  ctx.used[name] = (ctx.used[name] || 0) + 1;
  return name;
};

const variantsLine = (v) => {
  if (!v) return '';
  const parts = [];
  if (v.actions) parts.push('actions ' + v.actions.map((a) => `${q(a.label)} (${a.variant}${a.hook ? ', ' + a.hook : ''}) ×${a.count}${a.distinct ? `, ${a.distinct} different labels` : ''}`).join(', '));
  if (v.badges) parts.push('statuses ' + v.badges.map((b) => `${q(b.t)}${b.c ? ` (${b.c})` : ''} ×${b.count}`).join(', '));
  if (v.links) parts.push(`${v.links} link-style name button(s)`);
  return parts.join(' · ');
};

const hookTail = (n) => (n.hook ? `  // ${n.hook}` : '');

function actionLine(n, ctx) {
  if (/nav-item/.test(n.c || '')) {
    use(ctx, 'Sidebar');
    return `<Sidebar.Item${attrs({ active: n.current, href: n.href, icon: n.icon })}>${q(n.label)}</Sidebar.Item>` + hookTail(n);
  }
  const name = use(ctx, 'Button');
  const a = { variant: n.variant, disabled: n.disabled, href: n.href, 'aria-label': n.aria, title: n.title, draggable: n.draggable, icon: n.icon };
  if (n.icon_only) a['icon-only'] = true;
  if (n.link) a.as = 'link';
  if (n.c) a.old = n.c;
  if (n.icon_only) a['aria-label'] = n.label;
  return `<${name}${attrs(a)}>${n.icon_only ? '' : q(n.label)}</${name}>` + hookTail(n);
}

function fieldLine(n, ctx) {
  const name = use(ctx, 'Field');
  const a = { label: n.label, type: n.type, required: n.required, disabled: n.disabled, readonly: n.readonly, multiple: n.multiple, placeholder: n.placeholder, default: n.default, min: n.min, max: n.max, step: n.step, maxlength: n.maxlength, accept: n.accept, pattern: n.pattern, name: n.group, checked: n.checked === true ? true : undefined, id: n.id };
  let line = `<${name}${attrs(a)}`;
  if (n.options) line += ` options={${JSON.stringify(n.options)}}${n.options_n > n.options.length ? ` /* ${n.options_n} options in the demo, first ${n.options.length} shown */` : ''}`;
  return line + ' />';
}

function textParts(n) {
  if (n.p) return n.p.map(([t, m]) => (m === 'strong' ? `<Strong>${q(t)}</Strong>` : m === 'small' ? `<Small>${q(t)}</Small>` : q(t))).join(' ');
  return q(n.t);
}

function renderTabs(run, pad, out, ctx) {
  const name = use(ctx, 'Tabs');
  const sel = run.find((t) => t.selected);
  out.push(`${pad}<${name} items={${JSON.stringify(run.map((t) => t.label))}} selected=${q(sel ? sel.label : '')}${run.some((t) => t.disabled) ? ' /* some disabled */' : ''} />${run[0].hook ? '  // ' + run[0].hook.replace(/=.*/, '') : ''}`);
}

function renderChips(run, pad, out, ctx) {
  const name = use(ctx, 'FilterChip');
  out.push(`${pad}<${name}Group items={${JSON.stringify(run.map((t) => t.label))}} selected={${JSON.stringify(run.filter((t) => t.selected).map((t) => t.label))}} />${run[0].hook ? '  // ' + run[0].hook.replace(/=.*/, '') : ''}`);
  void name;
}

function isPageHeading(n) {
  return n.n === 'group' && /\bpage-heading\b/.test(n.c || '') && (n.children || []).some((c) => c.n === 'heading' && c.level === 1);
}

function renderPageHeading(n, pad, out, ctx) {
  const eyebrow = (n.children.find((c) => c.n === 'text' && c.eyebrow) || {}).t;
  const h1 = n.children.find((c) => c.n === 'heading' && c.level === 1);
  const sub = n.children.find((c) => c.n === 'text' && /subtitle/.test(c.c || ''));
  const rest = n.children.filter((c) => c !== h1 && c !== sub && !(c.n === 'text' && c.eyebrow));
  out.push(`${pad}<${use(ctx, 'PageHeading')}${attrs({ eyebrow, title: h1.t, subtitle: sub && sub.t })}${rest.length ? '>' : ' />'}`);
  if (rest.length) {
    renderNodes(rest.length === 1 && rest[0].n === 'group' && rest[0].children ? rest[0].children : rest, pad + '  ', out, ctx);
    out.push(`${pad}</PageHeading>`);
  }
}

function cardHead(n) {
  const first = (n.children || [])[0];
  if (first && first.n === 'group' && /\bpanel-head\b/.test(first.c || '') && (first.children || [])[0] && first.children[0].n === 'heading' && !first.children[0].children) {
    return { head: first.children[0], aside: first.children.slice(1), skip: 1 };
  }
  if (first && first.n === 'heading' && first.level >= 2 && !first.children) return { head: first, aside: [], skip: 1 };
  return null;
}

function renderCard(n, pad, out, ctx) {
  const isModal = /\bmodal\b/.test(n.c || '');
  if (isModal) return renderDialog(n, pad, out, ctx);
  const h = cardHead(n);
  const a = { old: n.c, title: h && h.head.t, subtitle: h && h.head.sub, role: n.role, 'aria-label': n.aria };
  if (n.lay) a.layout = n.lay.d === 'grid' ? `grid ${n.lay.cols}` : `flex ${n.lay.dir}`;
  out.push(`${pad}<${use(ctx, 'Card')}${attrs(a)}>`);
  if (h && h.aside.length) {
    out.push(`${pad}  <Card.Aside>`);
    renderNodes(h.aside, pad + '    ', out, ctx);
    out.push(`${pad}  </Card.Aside>`);
  }
  renderNodes((n.children || []).slice(h ? h.skip : 0), pad + '  ', out, ctx);
  out.push(`${pad}</Card>`);
}

function renderDialog(n, pad, out, ctx) {
  const kids = n.children || [];
  let head = kids.find((c) => c.n === 'group' && /modal-head/.test(c.c || ''));
  let eyebrow;
  let title;
  let rest = kids;
  let close = '';
  if (head) {
    eyebrow = (head.children.find((c) => c.n === 'text' && c.eyebrow) || {}).t;
    const h = head.children.find((c) => c.n === 'heading');
    title = h && h.t;
    const x = head.children.find((c) => c.n === 'action' && (c.icon_only || /Đóng/.test(c.aria || '') || /modal-close/.test(c.c || '')));
    close = x ? { label: x.label, ...(x.aria && x.aria !== x.label ? { aria: x.aria } : {}) } : '';
    rest = kids.filter((c) => c !== head);
  } else {
    const h = kids.find((c) => c.n === 'heading');
    title = h && h.t;
    const hi = kids.indexOf(h);
    rest = kids.filter((c, i) => i !== hi && !(c.n === 'text' && c.eyebrow));
    eyebrow = (kids.find((c) => c.n === 'text' && c.eyebrow) || {}).t;
  }
  out.push(`${pad}<${use(ctx, 'Dialog')}${attrs({ old: n.c, eyebrow, title, close, 'aria-label': n.aria })}>`);
  renderNodes(rest, pad + '  ', out, ctx);
  out.push(`${pad}</Dialog>`);
}

function renderTable(n, pad, out, ctx) {
  out.push(`${pad}<${use(ctx, 'TableShell')}${attrs({ old: n.c, caption: n.caption })} columns={${JSON.stringify(n.cols)}} rows={${n.rows}}${n.row_click ? ' rowClickable' : ''}>`);
  if (n.empty) out.push(`${pad}  <EmptyRow>${q(n.empty)}</EmptyRow>`);
  if (n.first) {
    out.push(`${pad}  <Row sample="first of ${n.rows}; demo values, the other rows have the same cells">`);
    n.first.forEach((cell, i) => {
      out.push(`${pad}    <Cell column=${q(n.cols[i] === undefined ? '' : n.cols[i])}>`);
      renderNodes(cell, pad + '      ', out, ctx);
      out.push(`${pad}    </Cell>`);
    });
    out.push(`${pad}  </Row>`);
  }
  if (n.variants) out.push(`${pad}  <RowVariants>${variantsLine(n.variants)}</RowVariants>`);
  if (n.foot) out.push(`${pad}  <Foot>${q(n.foot)}</Foot>`);
  out.push(`${pad}</TableShell>`);
}

function renderNode(n, pad, out, ctx) {
  switch (n.n) {
    case 'group': {
      if (isPageHeading(n)) return renderPageHeading(n, pad, out, ctx);
      let tagName = 'Stack';
      if (/sidebar/.test(n.c || '')) tagName = use(ctx, 'Sidebar');
      else if (/topbar/.test(n.c || '')) tagName = use(ctx, 'TopBar');
      const a = { old: n.c, tag: n.tag };
      if (n.lay) {
        if (n.lay.d === 'grid') {
          tagName = 'Grid';
          a.cols = n.lay.cols;
          a.gap = n.lay.gap;
        } else {
          if (tagName === 'Stack') tagName = 'Row';
          a.gap = n.lay.gap;
          a.justify = n.lay.jc;
          a.wrap = n.lay.wrap;
          if (!n.lay.dir.startsWith('row')) a.direction = n.lay.dir;
        }
      }
      out.push(`${pad}<${tagName}${attrs(a)}>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</${tagName}>`);
      return;
    }
    case 'card':
      return renderCard(n, pad, out, ctx);
    case 'form':
      out.push(`${pad}<form${attrs({ id: n.id, old: n.c })}>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</form>`);
      return;
    case 'nav':
      out.push(`${pad}<nav${attrs({ 'aria-label': n.aria, old: n.c })}>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</nav>`);
      return;
    case 'list_el':
      out.push(`${pad}<${n.ordered ? 'ol' : 'ul'}>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</${n.ordered ? 'ol' : 'ul'}>`);
      return;
    case 'li':
      out.push(`${pad}<li>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</li>`);
      return;
    case 'text': {
      if (n.eyebrow) return void out.push(`${pad}<Eyebrow>${q(n.t)}</Eyebrow>${n.tt ? ` /* ${n.tt} */` : ''}`);
      const a = { old: n.c, strong: n.mark === 'strong', small: n.mark === 'small', transform: n.tt };
      out.push(`${pad}<Text${attrs(a)}>${textParts(n)}</Text>`);
      return;
    }
    case 'heading': {
      const a = { level: n.level, sub: n.sub, transform: n.tt };
      if (n.children) {
        out.push(`${pad}<Heading${attrs(a)} text={${q(n.t)}}>`);
        renderNodes(n.children, pad + '  ', out, ctx);
        out.push(`${pad}</Heading>`);
      } else out.push(`${pad}<Heading${attrs(a)}>${q(n.t)}</Heading>`);
      return;
    }
    case 'details': {
      out.push(`${pad}<Disclosure${attrs({ summary: n.summary, open: n.open })}>`);
      renderNodes(n.children || [], pad + '  ', out, ctx);
      out.push(`${pad}</Disclosure>`);
      return;
    }
    case 'action':
      out.push(pad + actionLine(n, ctx));
      return;
    case 'chip':
      out.push(`${pad}<${use(ctx, 'FilterChip')}${attrs({ selected: n.selected, old: n.c })}>${q(n.label)}</FilterChip>${hookTail(n)}`);
      return;
    case 'tab':
      out.push(`${pad}<Tab${attrs({ selected: n.selected })}>${q(n.label)}</Tab>${hookTail(n)}`);
      return;
    case 'field':
      out.push(pad + fieldLine(n, ctx));
      return;
    case 'badge':
      out.push(`${pad}<${use(ctx, 'Badge')}${attrs({ tone: badgeTone(n.c), old: n.c })}>${q(n.t)}</Badge>`);
      return;
    case 'kpi': {
      const a = { old: n.c, label: n.label, value: n.value, note: n.hint, as: n.is_button ? 'button' : '' };
      if (n.actions && n.actions.length) {
        out.push(`${pad}<${use(ctx, 'Tile')}${attrs(a)}>`);
        n.actions.forEach((x) => out.push(`${pad}  ${actionLine(x, ctx)}`));
        out.push(`${pad}</Tile>`);
      } else out.push(`${pad}<${use(ctx, 'Tile')}${attrs(a)} />${hookTail(n)}`);
      return;
    }
    case 'notice': {
      const a = { tone: noticeTone(n.c), role: n.role, old: n.c, transform: n.tt };
      if (n.children) {
        out.push(`${pad}<${use(ctx, 'Notice')}${attrs(a)} text={${q(n.t)}}>`);
        renderNodes(n.children, pad + '  ', out, ctx);
        out.push(`${pad}</Notice>`);
      } else if (n.actions && n.actions.length) {
        out.push(`${pad}<${use(ctx, 'Notice')}${attrs(a)}>${q(n.t)}`);
        n.actions.forEach((x) => out.push(`${pad}  ${actionLine(x, ctx)}`));
        out.push(`${pad}</Notice>`);
      } else out.push(`${pad}<${use(ctx, 'Notice')}${attrs(a)}>${q(n.t)}</Notice>`);
      return;
    }
    case 'empty':
      if (n.children) {
        out.push(`${pad}<${use(ctx, 'EmptyState')} text={${q(n.t)}}>`);
        renderNodes(n.children, pad + '  ', out, ctx);
        out.push(`${pad}</EmptyState>`);
      } else out.push(`${pad}<${use(ctx, 'EmptyState')}>${q(n.t)}</EmptyState>`);
      return;
    case 'table':
      return renderTable(n, pad, out, ctx);
    case 'facts':
      out.push(`${pad}<Facts items={${JSON.stringify(n.items)}} />`);
      return;
    case 'fact':
      out.push(`${pad}<Fact label=${q(n.label)} value=${q(n.value)} />`);
      return;
    case 'progress':
      out.push(`${pad}<Progress value=${q(n.pct)}${n.aria ? ` aria-label=${q(n.aria)}` : ''}${n.segments ? ` segments={${n.segments}} done={${n.done}}` : ''} />`);
      return;
    case 'avatar':
      out.push(`${pad}<Avatar${attrs({ old: n.c })}>${q(n.t)}</Avatar>`);
      return;
    case 'img':
      out.push(`${pad}<Img${attrs({ alt: n.alt, size: n.box })} />`);
      return;
    case 'rule':
      out.push(`${pad}<hr />`);
      return;
    case 'icon':
      out.push(`${pad}<Icon name=${q(n.name)} />`);
      return;
    case 'list': {
      out.push(`${pad}<Repeat${attrs({ of: '.' + n.of, count: n.count, 'also-classes': (n.classes || []).join(' ') })}>  // first item shown (demo values); the others have the same shape`);
      if (n.sample_aria) out.push(`${pad}  <Item aria-label=${q(n.sample_aria)} />`);
      renderNodes(n.item || [], pad + '  ', out, ctx);
      if (n.variants) out.push(`${pad}  <RowVariants>${variantsLine(n.variants)}</RowVariants>`);
      out.push(`${pad}</Repeat>`);
      return;
    }
    default:
      out.push(`${pad}<!-- unknown node ${n.n} -->`);
  }
}

function renderNodes(nodes, pad, out, ctx) {
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.n === 'tab' || n.n === 'chip') {
      let j = i;
      while (j < nodes.length && nodes[j].n === n.n) j++;
      const run = nodes.slice(i, j);
      if (n.n === 'tab') renderTabs(run, pad, out, ctx);
      else renderChips(run, pad, out, ctx);
      i = j - 1;
      continue;
    }
    renderNode(n, pad, out, ctx);
  }
}

function layoutOf(e) {
  const ctx = ctxNew();
  const out = [];
  const tree = e.tree || [];
  if (e.scope === 'dialog') out.push('// opens over the page; the backdrop and the page behind it are not part of this screen');
  else if (e.scope === 'toast') out.push('// appears over the page; the page behind it is not part of this screen');
  else if (e.scope === 'content') out.push(`<AppShell role=${q(e.role)}>  // sidebar and top bar are the same on every page (WA1-WA3); active menu item ${q((e.shell || {}).active || '')}, page key ${q(((e.shell || {}).body || {}).page || '')}`);
  const base = e.scope === 'content' ? '  ' : '';
  renderNodes(tree, base, out, ctx);
  if (base) out.push('</AppShell>');
  return { lines: out, used: ctx.used };
}

// ---------- coverage ----------
function expectedItems(e) {
  const items = [];
  const add = (kind, text) => text && items.push({ kind, text: String(text) });
  for (const a of e.actions) add('action', a.label);
  for (const f of e.fields) add('field', f.label || f.placeholder);
  for (const c of e.chips_tabs) add('filter/tab', c.label);
  for (const b of e.badges_status) add('status', b.text);
  for (const k of e.kpis) {
    add('kpi label', k.label);
    add('kpi value', k.value);
    add('kpi hint', k.hint);
  }
  for (const n of e.notices) add('notice', n.text);
  for (const t of e.empty_states) add('empty state', t);
  for (const h of e.headings) add('heading', h.t);
  for (const t of e.tables) for (const c of t.cols) add('table column', c);
  const walk = (nodes) => {
    for (const n of nodes || []) {
      if (n.n === 'text') (n.p ? n.p.map((x) => x[0]) : [n.t]).forEach((t) => add('text', t));
      if (n.n === 'facts') n.items.forEach(([a, b]) => (add('text', a), add('text', b)));
      if (n.n === 'fact') (add('text', n.label), add('text', n.value));
      for (const k of ['children', 'item', 'actions']) if (Array.isArray(n[k])) walk(n[k]);
      if (n.first) n.first.forEach(walk);
    }
  };
  walk(e.tree);
  return items;
}

// With a canvas frame the Layout shows sample data (people, numbers, money) instead of the old demo values, so only the labels
// of the old screen are compared, with every run of digits read as one number: "0 Khách mới" is found by "12 Khách mới".
const LABEL_KINDS = new Set(['action', 'field', 'filter/tab', 'status', 'notice', 'empty state', 'heading', 'table column', 'kpi label']);
const normNum = (t) => String(t).replace(/\d+(?:[.,:/′'’·]\d+)*/g, '#').replace(/\s+/g, ' ').trim();

// Person names are sample data (the canvas has its own people), so a name, or a given name that comes after a name was seen, is read as one
// placeholder on both sides: "Hóa đơn của Nguyễn Minh Linh" is found by "Hóa đơn của Nguyễn Thu Hà", and "Hành trình của Linh" by "Hành trình của Hà".
const NAME_RUN = /\p{Lu}\p{Ll}+(?:\s+\p{Lu}\p{Ll}+)+/gu;
const nameTokens = (texts) => {
  const given = new Set();
  for (const t of texts) for (const m of String(t).matchAll(NAME_RUN)) given.add(m[0].trim().split(/\s+/).pop());
  return given;
};
const maskNames = (t, given) => {
  let s = String(t).replace(NAME_RUN, '@');
  for (const g of given) s = s.replace(new RegExp(`(^|[^\\p{L}])${g}(?![\\p{L}])`, 'gu'), '$1@');
  return s;
};

// A notice or an empty state of the old web is one text made of several pieces (title, text, bullets, button label, a leading glyph); the
// canvas draws the pieces as separate lines. Read the layout's text-bearing string literals in order and compare letters and digits only.
const TEXT_ATTRS = new Set(['title', 'text', 'hint', 'label', 'subtitle', 'sub', 'sub2', 'over', 'eyebrow', 'summary', 'caption', 'foot']);
const literalsOf = (lines) => {
  const out = [];
  const src = lines.join('\n').replace(/\w+=\{[^}]*\}/g, ' ');
  for (const m of src.matchAll(/(?:([\w-]+)=)?("(?:[^"\\]|\\.)*")/g)) {
    if (m[1] && !TEXT_ATTRS.has(m[1])) continue;
    try {
      out.push(JSON.parse(m[2]));
    } catch {
      /* not a JSON string */
    }
  }
  return out;
};
const alnum = (t) => normNum(t).replace(/[^\p{L}\p{N}#@]+/gu, '');

/** Labels of the snapshot that a canvas Layout does not contain. `demoData` (notes.json screens.<id>.demo_data) lists old demo values that the canvas replaces on purpose. */
function canvasCoverage(e, layoutLines, demoData = []) {
  const items = expectedItems(e);
  const given = nameTokens([...items.map((i) => i.text), ...layoutLines]);
  const norm = (t) => normNum(maskNames(t, given));
  const text = norm(layoutLines.join('\n').replace(/\\"/g, '"'));
  const joined = alnum(literalsOf(layoutLines).map((l) => maskNames(l, given)).join(' '));
  const exempt = demoData.map(norm);
  const missing = [];
  const seen = new Set();
  // links named after a patient, and the avatar button of the phone web (the patient's initials, "ML"): sample data
  const names = new Set((e.actions || []).filter((a) => /^crm=profile$|^patient=/.test(a.hook || '') || /^\p{Lu}{1,3}$/u.test(a.label || '')).map((a) => a.label));
  for (const it of items) {
    if (!LABEL_KINDS.has(it.kind) || (it.kind === 'action' && names.has(it.text))) continue;
    const n = norm(it.text);
    const key = it.kind + '|' + n;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!n || exempt.some((x) => n.includes(x) || x.includes(n))) continue;
    if (text.includes(n)) continue;
    if (['notice', 'empty state', 'action'].includes(it.kind) && joined.includes(alnum(maskNames(it.text, given)))) continue;
    missing.push(it);
  }
  return missing;
}

/** Items of the snapshot that the rendered Layout does not contain. Empty = the spec shows everything. */
function coverage(e, layoutLines) {
  const text = layoutLines.join('\n');
  const missing = [];
  const seen = new Set();
  for (const it of expectedItems(e)) {
    const key = it.kind + '|' + it.text;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!text.includes(q(it.text).slice(1, -1)) && !text.includes(it.text)) missing.push(it);
  }
  const unc = (e.stats && e.stats.uncovered_text) || [];
  for (const t of unc) missing.push({ kind: 'visible text not in the tree', text: t });
  for (const c of (e.stats && e.stats.unseen_controls) || []) missing.push({ kind: 'visible control not in the tree', text: c });
  return missing;
}

// ---------- spec markdown ----------
const bullet = (list) => (list.length ? list.map((x) => `- ${String(x).replace(/\n/g, '\n  ')}`).join('\n') : '- (none recorded)');

function tokensLines(e) {
  const t = e.tokens_used;
  const top = (o, n = 8) => Object.entries(o).slice(0, n).map(([k, v]) => `${k} ×${v}`).join(', ') || '—';
  const lines = [
    `- Text colour: ${top(t.color)}`,
    `- Background: ${top(t.background)}`,
    `- Border: ${top(t.border)}`,
    `- Radius: ${top(t.radius)}`,
    `- Font size: ${top(t.text, 12)}`,
    `- Font: ${top(t.family, 3)}`,
  ];
  const u = t.unmatched;
  lines.push(`- Unmatched colours (no token within ΔE 3): ${u.color.length ? u.color.map((c) => `\`${c.hex}\` (${c.role}, ×${c.n}, nearest \`${c.nearest}\` ΔE ${c.dE})`).join('; ') : 'none'}`);
  if (u.radius.length) lines.push(`- Unmatched radius: ${u.radius.map((r) => `${r.px}px ×${r.n} (nearest \`${r.nearest}\`)`).join(', ')}`);
  if (u.text.length) lines.push(`- Unmatched font size: ${u.text.map((r) => `${r.px}px ×${r.n} (nearest \`${r.nearest}\`)`).join(', ')}`);
  return lines.join('\n');
}

function frameLines(e, entry) {
  const lines = [entry.group === 'WI'
    ? `- Primary frame 390×844 (phone, inventory D4). Snapshot taken at ${e.viewport.replace('x', '×')}, clock 2026-09-20 09:00 (Asia/Ho_Chi_Minh), scope: ${e.scope}: there the phone column \`.mobile-app\` is centred with max-width 460px (x offset 490); at 390 it fills the width. Boxes below are the 1440 measurements.`
    : `- Viewport ${e.viewport.replace('x', '×')}, clock ${'2026-09-20 09:00 (Asia/Ho_Chi_Minh)'}, account \`${e.role}\`; snapshot scope: ${e.scope}.`];
  for (const r of e.regions) lines.push(`- Region \`${r.sel}\` (${r.name}): x ${r.box[0]}, y ${r.box[1]}, ${r.box[2]}×${r.box[3]} px`);
  for (const c of e.columns.slice(0, 12)) lines.push(`- Layout \`.${(c.c || '').split(' ')[0] || 'region'}\` ${c.box[2]}×${c.box[3]} px: ${c.lay.d === 'grid' ? `grid, columns \`${c.lay.cols}\` (${c.lay.px})${c.lay.gap ? ', gap ' + c.lay.gap : ''}` : `flex ${c.lay.dir}${c.lay.wrap ? ' wrap' : ''}${c.lay.jc ? ', ' + c.lay.jc : ''}${c.lay.gap ? ', gap ' + c.lay.gap : ''}`}`);
  lines.push(`- Frames to build (inventory D4): ${entry.frames.join(', ')}.`);
  return lines.join('\n');
}

function responsiveLines(e, entry) {
  const r = e.responsive || {};
  const keys = Object.keys(r);
  const lines = [];
  if (!keys.length) {
    lines.push(`- Not probed: this ${entry.kind} has a 1440x900 frame only (plan D4). Look at \`${IMG_REL}/${entry.id}-1440x900.png\`; the dialog fits the viewport on a phone through \`.modal\` CSS (see Tokens for sizes).`);
    return lines.join('\n');
  }
  lines.push(entry.group === 'WI' ? '- 390×844 is the primary frame; the snapshot reference is 1440×900, where the phone column is 460px wide (Frame, Layout).' : '- 1440×900 is the reference (Frame, Layout).');
  for (const vp of keys) {
    const c = r[vp];
    const parts = [];
    if (c.changes.length) parts.push(c.changes.slice(0, 14).join('; ') + (c.changes.length > 14 ? `; … ${c.changes.length - 14} more` : ''));
    else parts.push('no layout change');
    if (c.overflow_x) parts.push(`horizontal overflow of ${c.overflow_x}px`);
    if (c.hidden_text_n) parts.push(`hidden: ${c.hidden_text.map(q).join(', ')}${c.hidden_text_n > c.hidden_text.length ? ` (+${c.hidden_text_n - c.hidden_text.length})` : ''}`);
    if (c.new_text_n) parts.push(`new: ${c.new_text.map(q).join(', ')}${c.new_text_n > c.new_text.length ? ` (+${c.new_text_n - c.new_text.length})` : ''}`);
    lines.push(`- ${vp.replace('x', '×')}: ${parts.join(' · ')}`);
  }
  lines.push(`- Overflow per viewport from the screenshots: \`${IMG_REL}/manifest.json\` (W1), when present.`);
  return lines.join('\n');
}

function permissionLines(model, entry, e) {
  // Patient Mobile (WI) has no staff context; the clinic-web steps of some reaches only prepare data
  if (entry.group === 'WI') return '- Patient Mobile has no staff account: it does not load `staff-context.js`, no capability removes a control, and the patient is a synthetic profile (localStorage `pema-patient-identity`). Reaches that start in the clinic web (creating a profile, recording a CSKH task, approving an order) run as `' + entry.role + '` only to prepare the data.';
  const st = model.staff;
  const reachNav = ((entry.reach || []).map((s) => s.click || '').map((c) => /data-nav="([^"]+)"/.exec(c)).find(Boolean) || [])[1];
  const hasP360 = (entry.reach || []).some((s) => /data-patient/.test(s.click || ''));
  const key = hasP360 ? 'patient' : reachNav || ((entry.reach || []).some((s) => (s.goto || '').includes('screen=finance')) ? 'finance' : '');
  const lines = [];
  if (key) {
    const roles = Object.entries(st.pages).filter(([, p]) => p.includes(key)).map(([r]) => r);
    lines.push(`- Page key \`${key}\` is allowed for roles: ${roles.join(', ')} (\`staff-context.js\` › pages). Shown here with account \`${entry.role}\`.`);
  } else lines.push(`- Shown with account \`${entry.role}\`; the screen is part of the shell or an overlay (no page key).`);
  lines.push('- Capabilities (`staff-context.js` › capabilities): ' + Object.entries(st.capabilities).map(([k, v]) => `${k}: ${v.join('/')}`).join('; ') + '.');
  const hooks = new Set();
  const walk = (nodes) => {
    for (const n of nodes || []) {
      if (n.hook) hooks.add(n.hook);
      for (const k of ['children', 'item', 'actions']) if (Array.isArray(n[k])) walk(n[k]);
      if (n.first) n.first.forEach(walk);
      if (n.variants && n.variants.actions) n.variants.actions.forEach((a) => a.hook && hooks.add(a.hook));
    }
  };
  walk(e.tree);
  const gatedHere = [];
  for (const [cap, g] of Object.entries(st.gated)) {
    for (const k of g.keys) {
      const hit = [...hooks].filter((h) => h.split(' ').includes(k));
      if (hit.length) gatedHere.push(`\`${k}\` needs \`${cap}\` (roles ${st.capabilities[cap].join('/')})`);
    }
  }
  lines.push(gatedHere.length ? `- Controls removed for roles without the capability: ${gatedHere.join('; ')}.` : '- No control on this screen is removed by a capability check.');
  if (e.kind === 'tab' || (entry.reach || []).some((s) => /data-tab/.test(s.click || ''))) {
    for (const [role, tabs] of st.tabsRemoved) lines.push(`- Patient 360 tabs removed for role ${role}: ${tabs.join(', ')}.`);
  }
  return lines.join('\n');
}

function targetLines(model, entry) {
  const route = entry.next_route;
  const status = statusOf(entry);
  const step = (/\((U\d)\)/.exec(entry.next_status) || [])[1] || (/U\d/.exec(entry.next_status) || [])[0] || '—';
  const row = route && model.feature[route];
  const page = routePage(route);
  const lines = [`- Route: ${route ? `\`${route}\`` : 'none yet (no page in the Next.js app)'} · status: **${status}** · U step: ${step}`];
  lines.push(row ? `- FEATURE-INVENTORY row: \`${route}\` "${row.screen}" (owner ${row.owner}); test ids: ${row.tests.length ? row.tests.map((t) => `\`${t}\``).join(', ') : 'none'}` : `- FEATURE-INVENTORY row: ${route && !route.startsWith('(') ? 'none yet (the step that builds the page appends it)' : 'not applicable'}`);
  lines.push(`- Existing page file: ${page ? `\`${page}\`` : status.startsWith('planned') ? '— (planned)' : '—'}`);
  return lines.join('\n');
}

function appInfo(model, entry, e) {
  if (!entry.app_canvas.length) return { text: '- (none: this old-web screen has no app counterpart; it is still specified in full, the app only lends the look)', missing: [] };
  const lines = [];
  const appTexts = [];
  for (const code of entry.app_canvas) {
    const s = model.appById[code];
    if (!s) {
      lines.push(`- ${code}: not in design-specs/index.json`);
      continue;
    }
    const blocks = [...new Set((s.layout || []).flatMap((l) => [...l.matchAll(/\b(Pema[A-Za-z]+|[A-Z][A-Za-z]+Row|Week[A-Za-z]+)\(/g)].map((m) => m[1])))];
    lines.push(`- [${code}](../../screens/${code}.md) · ${s.name} (group ${s.group}, ${s.kmp && s.kmp.composable ? s.kmp.composable : 'web-only logic'}): blocks reused: ${blocks.length ? blocks.map((b) => `\`${b}\``).join(', ') : '—'}`);
    appTexts.push(...(s.texts || []), ...(s.constraints || []));
  }
  const web = [...new Set(e.notices.map((n) => n.text))];
  const missing = web.filter((t) => !appTexts.some((a) => a.includes(t) || t.includes(a)));
  return { text: lines.join('\n'), missing };
}

function imageLines(entry) {
  if (entry.planned) return '- (none yet: designed in step O5 and shot only after step O6 builds it; the canvas frame is the reference)';
  const dir = path.join(ROOT, IMG_REL);
  return entry.frames
    .map((f) => {
      const name = `${entry.id}-${f}.png`;
      return `- \`${IMG_REL}/${name}\`${fs.existsSync(path.join(dir, name)) ? '' : ' (not on disk: run `web-shots.cjs`; the images are git-ignored)'}`;
    })
    .join('\n');
}

function promptOf(entry, model) {
  const g = model.groups[entry.group];
  const where = entry.next_route ? `Next.js route ${entry.next_route} (${entry.next_status})` : 'no Next.js route yet';
  return [
    `Build/port web screen ${entry.id} "${entry.name}" (group ${entry.group} · ${g.name}, ${entry.kind}) in pema-agent/frontend using only src/ui (tokens.json and the kit: Card, Tile, Badge, Button, Field, Dialog, Tabs, TableShell, EmptyState; Notice and FilterChip where the layout names them). Target: ${where}.`,
    `Content comes from the old Pema web, completely: every field, action, status, filter and text in "Layout" must exist, nothing may be dropped (owner rule). Keep the Vietnamese text and the "Required text" sentences verbatim.`,
    `Look comes from the app design: tokens and block shapes. Where the old web and the app say it differently (see "Differences from the app design"), keep the old web's UI and leave the choice to the owner.`,
    `Do not read prototype/ again: this spec was generated from it. Verify against ${IMG_REL}/${entry.id}-${entry.frames[0]}.png at the frames listed in "Frame".`,
  ].join('\n');
}

// ---------- Next.js-only ids (groups WJ, WK, WL) ----------
// Their "old web" is the front end itself (pema-agent/frontend, mock BE). Content comes from three layers:
//   1. the inventory row (W7): reach, expect, sources and `notes`, a brief read from the code with every UI text in quotes;
//   2. notes.json: groups.<WJ|WK|WL>, routes.<route> (purpose, gate, roles, actions, context, related, rules, ...) and screens.<ID>;
//   3. snapshot.json (W8, web-snapshot.cjs), when it holds the id: measured layout tree, tokens, responsive notes.
// Without a snapshot the Layout is the brief, and every quoted text of it is checked against the front-end source.

const FE_ROOT = 'pema-agent/frontend';
const feCache = new Map();
function feFiles(p) {
  const abs = path.join(ROOT, p);
  if (!fs.existsSync(abs)) return [];
  if (fs.statSync(abs).isFile()) return [abs];
  return fs.readdirSync(abs).sort().flatMap((f) => feFiles(`${p}/${f}`));
}
const isCode = (f) => /\.(tsx?|json)$/.test(f) && !/\.test\.tsx?$/.test(f);
function feText(files) {
  return files
    .filter(isCode)
    .map((f) => {
      // whitespace is collapsed: JSX wraps long sentences over several lines
      if (!feCache.has(f)) feCache.set(f, lf(fs.readFileSync(f, 'utf8')).replace(/\s+/g, ' '));
      return feCache.get(f);
    })
    .join('\n');
}
let feAllCache = null;
const feAll = () => (feAllCache ??= feText([...feFiles(`${FE_ROOT}/src`), ...feFiles(`${FE_ROOT}/mock`)]));

/** The brief of an id (inventory `notes`) cut into sentences; a full stop inside a quoted text does not end a sentence. */
function briefSentences(entry) {
  const text = String(entry.notes || '').trim();
  const out = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    cur += c;
    if (c === '"') inQ = !inQ;
    if (!inQ && c === '.' && (i === text.length - 1 || text[i + 1] === ' ') && !/\d$/.test(cur.slice(0, -1))) {
      out.push(cur.trim());
      cur = '';
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}
const isTestSentence = (s) => /^(Tests?\b|No (page |UI )?tests?\b)/i.test(s);

function wrapText(text, width) {
  const out = [];
  let cur = '';
  for (const w of text.split(' ')) {
    if (cur && cur.length + 1 + w.length > width) {
      out.push(cur);
      cur = w;
    } else cur = cur ? `${cur} ${w}` : w;
  }
  if (cur) out.push(cur);
  return out;
}

// A quoted text may be a template: {name}, "N phút", a table header "A | B | C". Its literal fragments are what the code must contain.
// (a number in the brief may be a constant the code interpolates, "ít nhất 8 ký tự" = `ít nhất ${MIN} ký tự`)
const PLACEHOLDER = /\{[^}]*\}|…|\.\.\.|\s\|\s|\d+(?:[.,]\d+)*|(?<![\p{L}\p{N}])(?:N|H|M)(?![\p{L}\p{N}])/gu;
const fragmentsOf = (text) =>
  text
    .split(PLACEHOLDER)
    .map((f) => f.replace(/\s+/g, ' ').replace(/^[\s.,:;·%()/-]+|[\s.,:;·%()/-]+$/g, ''))
    .filter((f) => f.length >= 3 && /\p{L}/u.test(f));

/** Texts the brief quotes (verbatim UI text), each checked against the sources of the id, then the whole front end (src and mock, no tests). */
function quotedTexts(entry) {
  const texts = new Set();
  const add = (t) => {
    const s = String(t).trim();
    if (s.length < 3 || s.length > 400 || !/\p{L}/u.test(s) || /^[a-z_]+(\.[a-z_]+)+$/.test(s)) return;
    if (fragmentsOf(s).length) texts.add(s);
  };
  if (entry.expect && entry.expect.text) add(entry.expect.text);
  for (const st of entry.reach || []) {
    if (st.button) add(st.button);
    if (st.text) add(st.text);
  }
  for (const sent of briefSentences(entry)) {
    if (isTestSentence(sent)) continue;
    for (const m of sent.matchAll(/"([^"]+)"/g)) add(m[1]);
  }
  const own = feText(entry.sources.flatMap(feFiles));
  const has = (hay, f) => hay.includes(f) || hay.includes(f.replace(/"/g, '\\"'));
  const res = { in_source: [], elsewhere: [], not_found: [] };
  for (const t of texts) {
    const frags = fragmentsOf(t);
    if (frags.every((f) => has(own, f))) res.in_source.push(t);
    else if (frags.every((f) => has(feAll(), f))) res.elsewhere.push(t);
    else res.not_found.push(t);
  }
  return res;
}

const pageOf = (model, entry) => model.inventory.screens.find((s) => isNextjs(s) && s.next_route === entry.next_route && s.kind === 'page' && s.id !== entry.id);
const sameRoute = (model, entry) => model.inventory.screens.filter((s) => isNextjs(s) && s.next_route === entry.next_route && s.id !== entry.id);
const nameOf = (model, id) => (model.inventory.screens.find((s) => s.id === id) || {}).name || '';
const idLink = (model, id) => `[${id}](${id}.md)${nameOf(model, id) ? ` · ${nameOf(model, id)}` : ''}`;
const kindWord = { page: 'page', tab: 'tab of a page', dialog: 'dialog or drawer', modal: 'dialog', state: 'state' };

function reachWords(steps) {
  return (steps || [])
    .map((st) => {
      if (st.login) return `sign in as the mock account \`${st.login}\``;
      if (st.goto) return `open \`${st.goto}\``;
      if (st.button) return `click the button or link ${q(st.button)}`;
      if (st.text) return `click the text ${q(st.text)}`;
      if (st.fill) return `type ${q(st.fill[1])} into the field ${q(st.fill[0])}`;
      if (st.wait) return `wait for ${q(st.wait)}`;
      if (st.note) return `condition: ${st.note}`;
      return JSON.stringify(st);
    })
    .join(' → ');
}

const asList = (v) => (Array.isArray(v) ? v : v ? [v] : []);
/** A note key at the three levels (group, route, screen), concatenated in that order. */
function extraList(model, entry, key) {
  const g = (model.notes.groups || {})[entry.group] || {};
  const r = (model.notes.routes || {})[entry.next_route] || {};
  const s = (model.notes.screens || {})[entry.id] || {};
  return [...asList(g[key]), ...asList(r[key]), ...asList(s[key])];
}
/** A single-text note key: the most specific level wins (screen, then route, then group). */
function extraStr(model, entry, key) {
  const g = (model.notes.groups || {})[entry.group] || {};
  const r = (model.notes.routes || {})[entry.next_route] || {};
  const s = (model.notes.screens || {})[entry.id] || {};
  return s[key] || r[key] || g[key] || '';
}

function nextLayoutBrief(entry) {
  const out = [];
  if (entry.kind === 'dialog' || entry.kind === 'modal') out.push('// opens over the page (a drawer or a dialog); the page and the backdrop behind it are not part of this screen');
  const shell = entry.next_route === '/login' ? 'public page, no shell' : `inside <AppShell role=${q(entry.role)}>`;
  out.push(`<Screen id=${q(entry.id)} kind=${q(entry.kind)} route=${q(entry.next_route)} account=${q(entry.role)}>  // ${shell}`);
  for (const s of briefSentences(entry)) for (const [i, l] of wrapText(s, 108).entries()) out.push(`  ${i ? '//    ' : '// '}${l}`);
  out.push('</Screen>');
  return out;
}

function nextSpecMarkdown(entry, model) {
  const e = model.snapshot.screens[entry.id];
  const g = model.groups[entry.group];
  const notes = notesFor(model, entry);
  const cs = model.canvas && model.canvas.screens[entry.id];
  const snap = e ? layoutOf(e) : { lines: nextLayoutBrief(entry), used: {} };
  const lay = cs ? canvasLayout.layout(cs) : snap;
  const kitUsed = Object.entries(lay.used).filter(([k]) => KIT.has(k)).sort((a, b) => b[1] - a[1]);
  const page = entry.kind === 'page' ? null : pageOf(model, entry);
  const siblings = sameRoute(model, entry);
  const nav = model.nav[entry.next_route];
  const gate = extraStr(model, entry, 'gate');
  const roles = extraStr(model, entry, 'roles');
  const suffix = entry.name.includes(' · ') ? entry.name.slice(entry.name.indexOf(' · ') + 3) : entry.name;
  const routePurpose = (((model.notes.routes || {})[entry.next_route] || {}).purpose || '').trim();
  const ownPurpose = (((model.notes.screens || {})[entry.id] || {}).purpose || '').trim();
  const kindText = kindWord[entry.kind] || entry.kind;
  const purpose = ownPurpose || (entry.kind === 'page' ? routePurpose : `${kindText[0].toUpperCase()}${kindText.slice(1)} of ${page ? idLink(model, page.id) : 'the shell'}: ${suffix}.${routePurpose ? ` Page: ${routePurpose}` : ''}`);
  const quoted = quotedTexts(entry);
  const tests = briefSentences(entry).filter(isTestSentence);
  const ownActions = asList(((model.notes.screens || {})[entry.id] || {}).actions);
  const actions = entry.kind === 'page' || ownActions.length ? extraList(model, entry, 'actions') : ['(actions of the page; this state or dialog adds the controls its Layout lists)', ...extraList(model, entry, 'actions')];
  const context = extraList(model, entry, 'context');
  const relNotes = Object.fromEntries(extraList(model, entry, 'related').map((r) => [r.split(' ')[0], r.includes(' ') ? r.slice(r.indexOf(' ') + 1) : '']));
  const relText = (id) => `- ${idLink(model, id)}${relNotes[id] ? ` — ${relNotes[id]}` : ''}`;
  const known = (id) => model.inventory.screens.some((s) => s.id === id);
  const sameIds = new Set(siblings.map((s) => s.id));
  const cross = Object.keys(relNotes).filter((id) => known(id) && id !== entry.id && !sameIds.has(id) && !(page && page.id === id));
  const relLines = [
    ...(siblings.length && entry.kind === 'page' ? ['States, dialogs and tabs of this page:', ...siblings.map((s) => `- ${idLink(model, s.id)} (${s.kind})`)] : []),
    ...(page ? ['The page of this route:', relText(page.id), ...(siblings.length > 1 ? ['Other states and dialogs of the same page:', ...siblings.filter((s) => s.id !== page.id).map((s) => `- ${idLink(model, s.id)} (${s.kind})`)] : [])] : []),
    ...(cross.length ? ['Other screens:', ...cross.map(relText)] : []),
  ];
  const noticeTexts = e ? [...new Set(e.notices.map((n) => n.text))] : [];
  const required = [...quoted.in_source, ...quoted.elsewhere];
  const rules = [...noticeTexts.map((t) => `- (notice on the page) ${q(t)}`), ...(notes.rules.length ? [bullet(notes.rules)] : [])].join('\n') || '- (none recorded)';
  const diffs = notes.differences;
  const hash = e ? `, snapshot.json (${model.snapshotHash})` : '';
  const responsive = e
    ? responsiveLines(e, entry)
    : [
        ...briefSentences(entry)
          .filter((s) => !isTestSentence(s) && /\b(md|lg|xl)\b|\d\s?px\b|\bcolumns?\b|cards? below|on a phone|phone:|segmented|max-w-/i.test(s))
          .map((s) => `- ${s}`),
        `- Measured behaviour at 1920, 1280, 1024 and 390 comes with the snapshot of the mock-BE page (W8, \`web-snapshot.cjs\`); frames to build: ${entry.frames.join(', ')}.`,
      ].join('\n');
  const requiredAll = [...required, ...noticeTexts, ...(e ? e.empty_states.map((t) => `${t} (empty state)`) : [])];
  const frame = e
    ? frameLines(e, entry)
    : [
        `- Frames to build: ${entry.frames.join(', ')} (${entry.frames.length > 1 ? '1440×900 primary, 1920×1020 and 390×844 for a page or tab' : 'a state or dialog is drawn at 1440×900 only'}), account \`${entry.role}\`.`,
        `- Shell: ${entry.next_route === '/login' ? 'none (public page, full-height canvas)' : 'the Next.js shell (WL10-WL19): sidebar, top bar from lg, bottom tab bar on a phone'}.`,
      ].join('\n');
  const layoutHead = cs
    ? `## Layout (top to bottom, from the web canvas frame, region → src/ui component)
Generated from the blocks of \`Pema Web redesign canvas/${cs.canvasFile || 'Pema Web (Next.js).dc.html'}\` (frame ${entry.id}); labels, actions, statuses and notices are the front end's, verbatim.`
    : e
      ? `## Layout (top to bottom, region → src/ui component)
Measured from the running page (snapshot of the mock BE): every field, action, status, filter and text is listed; repeating rows show the first one and their count.`
      : `## Layout (brief from the code, region by region)
No structure snapshot yet (W8): this is the inventory brief of W7, read from the page components, with every UI text in quotes. Run \`web-snapshot.cjs\` and \`web-specs.cjs\` to replace it with the measured tree.`;
  return `<!-- Generated by ${GENERATOR} from inventory.json, design-specs/web/notes.json${hash}. Edit notes.json, not this file. -->
# ${entry.id} · ${entry.name}

Group **${entry.group} · ${g.name}** · ${entry.kind} · Next.js: **${statusOf(entry)}**${entry.next_route ? ` (\`${entry.next_route}\`)` : ''} · account \`${entry.role}\`

## Purpose
${purpose || '- (not written yet)'}
${context.length ? `\n## Agent and care context\n${bullet(context)}\n` : ''}
## Who may see it
- Account in this frame: \`${entry.role}\` (a mock account of \`mock/auth.ts\`; the back end decides the real matrix, the menu is a convenience).
- Gate: ${gate || '(none recorded)'}
- Roles that can open the page: ${roles || '(none recorded)'}
- Menu entry: ${nav ? `${q(nav.label)} in the section ${q(nav.section)}, shown when the role holds any of ${nav.needs.map((n) => `\`${n}\``).join(', ')}${nav.planned ? ' (planned: not a link yet)' : ''}` : 'not a menu entry (reached by link, redirect or the shell itself)'}.

## Key actions
${actions.length ? bullet(actions) : '- (the Layout lists every control)'}

## Related screens
${relLines.join('\n') || '- (none)'}

## Logic source
${[...entry.sources.map((s) => `- Source: \`${s}\``), ...tests.map((t) => `- ${t}`), notes.logic.length ? bullet(notes.logic) : ''].filter(Boolean).join('\n')}
- How to reach it (mock BE, \`pnpm dev:mock\`): ${reachWords(entry.reach)}; it must show ${entry.expect && entry.expect.text ? q(entry.expect.text) : 'the screen'}.

## Next.js target
${targetLines(model, entry)}

## App canvas
- (none: this screen exists only in the Next.js front end, \`app_canvas\` is null; the app canvas only lends tokens and blocks, see \`design-specs/web/BLOCKS.md\`)

## Frame
${frame}

${layoutHead}
\`\`\`tsx
${lay.lines.join('\n')}
\`\`\`
${e || cs ? `Kit components used: ${kitUsed.length ? kitUsed.map(([k, v]) => `${k}×${v}`).join(', ') : '—'}.\n` : ''}
## Responsive
${responsive}
${e ? `\n## Tokens\n${tokensLines(e)}\n` : ''}
## Required text (keep verbatim)
${requiredAll.length ? requiredAll.map((t) => `- ${t}`).join('\n') : '- (none quoted)'}
${quoted.not_found.length ? `\n## Texts to re-check against the code\nQuoted in the brief but not found verbatim in the front-end source (built from parts, sent by the back end, or worded differently in the code):\n${quoted.not_found.map((t) => `- ${t}`).join('\n')}\n` : ''}
## Business rules
${rules}

## Differences from the app design
${diffs.length ? bullet(diffs) : '- (none: there is no app counterpart to differ from)'}

## Gotchas
${bullet(notes.gotchas)}
${notes.todo.length ? `\n## Still to do\n${bullet(notes.todo)}\n` : ''}
${cs ? `## Web canvas
- Frames: ${cs.frames.map((f) => f.size).join(', ')} (inventory: ${entry.frames.join(', ')}); screen label \`${cs.id} · ${cs.name}\`.
- Canvas note: ${String(cs.note).replace(/\s+/g, ' ')}

` : ''}## Images
${imageLines(entry)}

## Prompt
\`\`\`text
${nextPromptOf(entry, model)}
\`\`\`
`;
}

function nextPromptOf(entry, model) {
  const g = model.groups[entry.group];
  return [
    `Restyle web screen ${entry.id} "${entry.name}" (group ${entry.group} · ${g.name}, ${entry.kind}) in pema-agent/frontend using only src/ui (tokens.json and the kit: Card, Tile, Badge, Button, Field, Dialog, Sheet, Tabs, TableShell, EmptyState; Notice and FilterChip where the layout names them). Route ${entry.next_route} (${statusOf(entry)}): the page already exists, the step restyles it to the canvas frame and does not change its behaviour.`,
    `Every field, action, status, filter and text in "Layout" and "Required text" must stay; nothing may be dropped (owner rule). The rules under "Agent and care context" and "Business rules" (policy profile, control states, human approval) are product rules, not decoration.`,
    `Look comes from the web canvas frame ${entry.id} and the tokens; the app canvas has no counterpart. Do not re-read the page components for content: this spec was generated from them. Verify against the shots in "Images" at the frames listed in "Frame".`,
  ].join('\n');
}

function specMarkdown(entry, model) {
  if (isNextjs(entry)) return nextSpecMarkdown(entry, model);
  const e = model.snapshot.screens[entry.id];
  if (!e) throw new Error(`no snapshot for ${entry.id}: run web-snapshot.cjs`);
  const g = model.groups[entry.group];
  const notes = notesFor(model, entry);
  const snap = layoutOf(e);
  const cs = model.canvas && model.canvas.screens[entry.id];
  const lay = cs ? canvasLayout.layout(cs) : snap;
  const kitUsed = Object.entries(lay.used).filter(([k]) => KIT.has(k)).sort((a, b) => b[1] - a[1]);
  const sharedUsed = Object.entries(lay.used).filter(([k]) => SHARED.has(k));
  const app = appInfo(model, entry, e);
  const noticeTexts = [...new Set(e.notices.map((n) => n.text))];
  const diffs = [...notes.differences];
  if (entry.app_canvas.length) {
    for (const t of app.missing) diffs.push(`(generated) Notice of the old web not found verbatim in ${entry.app_canvas.join('/')}: ${q(t)}`);
  }
  const logic = [
    ...entry.sources.map((s) => `- Old web: \`${s}\``),
    notes.logic.length ? bullet(notes.logic) : '',
    entry.notes ? `- Inventory note: ${entry.notes}` : '',
    permissionLines(model, entry, e),
  ].filter(Boolean).join('\n');
  const rules = [...noticeTexts.map((t) => `- (old web notice) ${q(t)}`), ...(notes.rules.length ? [bullet(notes.rules)] : [])].join('\n') || '- (none recorded)';
  const reach = (entry.reach || []).map((s) => JSON.stringify(s)).join(' → ');
  return `<!-- Generated by ${GENERATOR} from snapshot.json (${model.snapshotHash}), inventory.json and design-specs/web/notes.json. Edit notes.json, not this file. -->
# ${entry.id} · ${entry.name}

Group **${entry.group} · ${g.name}** · ${entry.kind} · Next.js: **${entry.next_status}**${entry.next_route ? ` (\`${entry.next_route}\`)` : ''}${entry.group === 'WI' ? '' : ` · account \`${entry.role}\``}

## Logic source
${logic}
- How to reach it in the old web: ${reach}; it must show ${entry.expect && entry.expect.text ? q(entry.expect.text) : entry.expect && entry.expect.selector ? '`' + entry.expect.selector + '`' : 'the screen'}.

## Next.js target
${targetLines(model, entry)}

## App canvas
${app.text}

## Frame
${frameLines(e, entry)}

${cs ? `## Layout (top to bottom, from the web canvas frame, region → src/ui component)
Generated from the blocks of \`Pema Web redesign canvas/Pema Web.dc.html\` (frame ${entry.id}): every block is one kit component or web block (see BLOCKS.md). Names, numbers and money are the canvas sample data; labels, actions, statuses, filters and notices are the old web's, verbatim. The old web's own tree is under "Old web snapshot".` : `## Layout (top to bottom, region → src/ui component)
Every field, action, status, filter and text of the old screen is listed; rows and cards that repeat show the first one with demo values and their count. \`old="…"\` is the old CSS class, \`// key=value\` the old \`data-*\` hook that carries the behaviour.`}
\`\`\`tsx
${lay.lines.join('\n')}
\`\`\`
Kit components used: ${kitUsed.length ? kitUsed.map(([k, v]) => `${k}×${v}`).join(', ') : '—'}${sharedUsed.length ? `; shared pieces: ${sharedUsed.map(([k, v]) => `${k}×${v}`).join(', ')}` : ''}. Everything else (Row, Grid, Stack, Text, Heading, Progress, Avatar, Facts, Repeat, Cell…) is a plain element styled with tokens; W3 turns the recurring ones into web blocks.

## Responsive
${responsiveLines(e, entry)}

## Tokens
${tokensLines(e)}

## Required text (keep verbatim)
${noticeTexts.length || e.empty_states.length ? [...noticeTexts, ...e.empty_states.map((t) => `${t} (empty state)`)].map((t) => `- ${t}`).join('\n') : '- (no notice or empty state on this screen)'}

## Business rules
${rules}

## Differences from the app design
${bullet(diffs)}

## Gotchas
${bullet(notes.gotchas)}
${notes.todo.length ? `\n## Still to do\n${bullet(notes.todo)}\n` : ''}
${cs ? `## Web canvas
- Frames: ${cs.frames.map((f) => f.size).join(', ')} (inventory: ${entry.frames.join(', ')}); screen label \`${cs.id} · ${cs.name}\`.
- Canvas note: ${String(cs.note).replace(/\s+/g, ' ')}

## Old web snapshot (for comparison)
The old web's own layout, with its demo values.
\`\`\`tsx
${snap.lines.join('\n')}
\`\`\`

` : ''}## Images
${imageLines(entry)}

## Prompt
\`\`\`text
${promptOf(entry, model)}
\`\`\`
`;
}

// ---------- index ----------
function indexJson(model) {
  return {
    generator: GENERATOR,
    snapshot: model.snapshotHash,
    counts: model.inventory.counts,
    groups: model.inventory.groups,
    screens: model.inventory.screens.map((s) => {
      const e = model.snapshot.screens[s.id] || {};
      return {
        id: s.id,
        name: s.name,
        group: s.group,
        kind: s.kind,
        role: s.role,
        source: isNextjs(s) ? 'nextjs' : 'old-web',
        next_route: s.next_route,
        next_status: statusOf(s),
        app_canvas: s.app_canvas,
        frames: s.frames,
        spec: `screens/${s.id}.md`,
        has_snapshot: Boolean(model.snapshot.screens[s.id]),
        counts: { actions: (e.actions || []).length, fields: (e.fields || []).length, chips_tabs: (e.chips_tabs || []).length, statuses: (e.badges_status || []).length, kpis: (e.kpis || []).length, notices: (e.notices || []).length, tables: (e.tables || []).length },
      };
    }),
  };
}

function indexMarkdown(model) {
  const rows = model.inventory.screens.map((s) => {
    const e = model.snapshot.screens[s.id];
    const counts = e ? `${e.actions.length}/${e.fields.length}/${e.badges_status.length}/${e.notices.length}` : '—';
    return `| [${s.id}](screens/${s.id}.md) | ${s.name} | ${s.kind} | ${model.groups[s.group].name} | ${isNextjs(s) ? 'Next.js' : 'old web'} | ${s.next_route ? `\`${s.next_route}\`` : '—'} | ${statusOf(s)} | ${s.app_canvas.length ? s.app_canvas.join(', ') : '—'} | ${counts} |`;
  });
  const nx = model.inventory.screens.filter(isNextjs).length;
  return `<!-- Generated by ${GENERATOR}. Edit notes.json, not this file. -->
# Web screen index (${model.inventory.screens.length})

Source: \`design-specs/web/inventory.json\` (W0, and W7 for the ${nx} Next.js-only ids), snapshot \`${model.snapshotHash}\`. One spec per screen in \`screens/\`. Old-web ids (groups WA-WI): the old web is the reference, the app canvas only lends the look. Next.js-only ids (groups WJ, WK, WL: agent admin, care agent, sign-in, shell and templates; status "${NEXT_STATUS}"): specified from the inventory brief, \`notes.json\` and the front-end source, with the measured snapshot added when it exists. Group WM (shared inbox, package O step O5) is designed before it is built: its status is "designed (O5)", it has no shots and no snapshot, and the canvas frame is the reference for step O6. Counts are actions/fields/statuses/notices of the snapshot (\`—\` = no snapshot for the id yet).

| Code | Screen | Kind | Group | Source | Next.js route | Next.js status | App canvas | A/F/S/N |
|---|---|---|---|---|---|---|---|---|
${rows.join('\n')}
`;
}

// ---------- design-specs/web/BLOCKS.md: blocks-web.md plus how often the canvas uses each block ----------
function blocksMarkdown(model) {
  const doc = fs.existsSync(BLOCKS_DOC) ? read(BLOCKS_DOC) : '';
  const use = model.canvas ? canvasLayout.usage(model.canvas.screens) : {};
  const total = model.canvas ? Object.keys(model.canvas.screens).length : 0;
  const lines = doc.split('\n');
  const hi = lines.findIndex((l) => /^\| Block /.test(l));
  const head = hi < 0 ? '' : lines[hi];
  const body = [];
  for (let k = hi + 2; hi >= 0 && k < lines.length && /^\|/.test(lines[k]); k++) body.push(lines[k]);
  const rows = body.map((l) => {
    const kinds = [...l.split('|')[1].matchAll(/`([A-Za-z]+)`/g)].map((m) => m[1]);
    const n = kinds.reduce((a, k) => a + ((use[k] || {}).nodes || 0), 0);
    const screens = kinds.reduce((a, k) => Math.max(a, (use[k] || {}).screens || 0), 0);
    return `${l} ${n} blocks · ${screens} screens |`;
  });
  const cols = head ? head.split('|').length - 2 + 1 : 0;
  return `<!-- Generated by ${GENERATOR} from .claude/skills/pema-web-design/references/blocks-web.md and the web canvases (Pema Web.dc.html, Pema Web (Next.js).dc.html). Edit blocks-web.md, not this file. -->
# Web canvas blocks

Every block of \`Pema Web redesign canvas\` with the \`src/ui\` component it renders, its KMP \`core:ui\` analogue and the rules for using it. The last column is how often the ${total} canvas screen(s) built so far use it. Helper arguments and examples: \`.claude/skills/pema-web-design/references/blocks-web.md\`.

${head ? head.replace(/\|\s*$/, '| Used in the canvas |') : ''}
${head ? '|' + '---|'.repeat(cols) : ''}
${rows.join('\n')}
`;
}

/** Everything the generator writes: Map(path → text). */
function buildFiles(model) {
  const files = new Map();
  files.set(path.join(WEB, 'index.json'), JSON.stringify(indexJson(model), null, 2) + '\n');
  files.set(path.join(WEB, 'INDEX.md'), indexMarkdown(model));
  files.set(path.join(WEB, 'BLOCKS.md'), blocksMarkdown(model));
  for (const s of model.inventory.screens) files.set(path.join(SCREENS, `${s.id}.md`), specMarkdown(s, model));
  return files;
}

/** Per id: items of the snapshot missing from the rendered Layout. */
function coverageAll(model) {
  const out = {};
  for (const s of model.inventory.screens) {
    const e = model.snapshot.screens[s.id];
    if (!e) {
      // a Next.js-only id may have no snapshot: its spec is built from the inventory brief and notes.json
      if (!isNextjs(s)) out[s.id] = [{ kind: 'snapshot', text: 'no snapshot entry' }];
      continue;
    }
    const cs = model.canvas && model.canvas.screens[s.id];
    const demo = ((model.notes.screens || {})[s.id] || {}).demo_data || [];
    const miss = cs ? canvasCoverage(e, canvasLayout.layout(cs).lines, demo) : coverage(e, layoutOf(e).lines);
    if (miss.length) out[s.id] = miss;
  }
  return out;
}

/** sha of inventory.json as the snapshot generator wrote it into snapshot.json meta. */
function inventorySha() {
  return sha(fs.readFileSync(INVENTORY, 'utf8'));
}

module.exports = {
  isNextjs,
  statusOf,
  quotedTexts,
  briefSentences, canvasCoverage, blocksMarkdown, inventorySha, ROOT, WEB, SCREENS, NOTES, INVENTORY, SNAPSHOT, IMG_REL, NOTE_KEYS, rel, loadModel, loadNotes, saveNotes, addNote, specMarkdown, promptOf, indexMarkdown, indexJson, buildFiles, coverage, coverageAll, layoutOf, lf };

// Builds the per-screen conversion specs ("prompts") for the Pema app from:
//  - the design canvas `Pema App redesign canvas/Pema App.dc.html` (its build() data = every block of
//    every screen, evaluated in Node, no browser),
//  - the KMP code (shot tests, composables, routes, domain functions used; logic of A–H screens),
//  - hand-written notes `design-specs/notes.json` (web sources, business rules, accepted differences).
// Used by `design-specs.cjs` (writes design-specs/) and the `pema-design` MCP server (live).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '../../../..');
const CANVAS = path.join(ROOT, 'Pema App redesign canvas', 'Pema App.dc.html');
const KMP = path.join(ROOT, 'pema-kmp');
const SPECS = path.join(ROOT, 'design-specs');
const NOTES = path.join(SPECS, 'notes.json');
const REF_DIR = path.join(KMP, 'design-ref');

const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
const read = (p) => fs.readFileSync(p, 'utf8');

function walk(dir, filter, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'build' || e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, filter, out);
    else if (filter(p)) out.push(p);
  }
  return out;
}

// ---------- canvas ----------
function loadCanvas() {
  const src = read(CANVAS);
  const m = /<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/.exec(src);
  if (!m) throw new Error('canvas script not found in ' + rel(CANVAS));
  const DCLogic = class { constructor() { this.props = {}; } };
  const groups = new Function('DCLogic', `${m[1]}\nreturn new Component().build();`)(DCLogic);
  return { groups, hash: crypto.createHash('sha256').update(src).digest('hex').slice(0, 16) };
}

// ---------- KMP ----------
function kmpIndex() {
  const files = walk(KMP, (p) => p.endsWith('.kt'));
  const main = files.filter((f) => !/[\\/](jvmTest|commonTest|androidUnitTest)[\\/]/.test(f));
  const tests = files.filter((f) => /[\\/]jvmTest[\\/]/.test(f));

  const routesFile = main.find((f) => f.endsWith(path.join('core', 'common', 'Routes.kt')));
  const routes = {};
  if (routesFile) {
    const t = read(routesFile);
    for (const [, name, id] of t.matchAll(/const val (\w+) = "([^"]+)"/g)) routes[name] = { name, id, title: '' };
    for (const [, name, title] of t.matchAll(/^\s+(\w+) to "([^"]+)",/gm)) if (routes[name]) routes[name].title ||= title;
    for (const [, name, title] of t.matchAll(/appBarTitles[\s\S]*?(\w+) to "([^"]+)"/g)) if (routes[name]) routes[name].appBar = title;
  }

  const defs = {};
  const fileInfo = {};
  for (const f of main) {
    const t = read(f);
    for (const [, name] of t.matchAll(/^(?:internal |private |public )?fun (?:[\w.]+\.)?([A-Z]\w*)\(/gm)) defs[name] ||= f;
    // Lazy-list builders (`fun LazyListScope.patientSearchItems(`) render a screen's rows.
    for (const [, name] of t.matchAll(/^(?:internal |public )?fun LazyListScope\.([a-z]\w*Items)\(/gm)) defs[name] ||= f;
    const domain = [...t.matchAll(/^import com\.pema\.clinic\.shared\.clinic\.([a-z]\w*)$/gm)].map((x) => x[1]);
    const graphs = [...t.matchAll(/fun NavGraphBuilder\.(\w+)\(/g)].map((x) => x[1]);
    fileInfo[f] = { domain, graphs };
  }

  const shots = {};
  const bodyOf = (text, name) => new RegExp(`fun (?:[\\w.]+\\.)?${name}\\([\\s\\S]*?\\r?\\n(?:    )?}\\r?\\n`, 'm').exec(text)?.[0] || '';
  for (const f of tests) {
    const t = read(f);
    const lines = t.split('\n');
    lines.forEach((line, i) => {
      const m = /shotVsCanvas\("(\w+)"/.exec(line);
      if (!m) return;
      // Only this test's body: stop at the next test / shot.
      const next = lines.slice(i + 1).findIndex((l) => /shotVsCanvas\(|@Test/.test(l));
      const win = lines.slice(i, next < 0 ? i + 14 : i + 1 + next).join('\n');
      const calls = [...win.matchAll(/\b([A-Z]\w*)\(/g)].map((x) => x[1])
        .filter((n) => !/^(DetailScaffold|CompositionLocalProvider|LocalOnBack|Session|PatientState|PatientProfile|Modifier|Routes|CapturedPhoto|ClinicStore|Box|Column|Row|Text|Spacer|FinanceState|WorkspaceUiState|SendUpdateDraft|HomeCareUiState|PemaScaffold|PemaTheme)$/.test(n));
      let composable = calls.find((n) => /(Screen|Content|Overlay|Body)$/.test(n)) || calls[0] || '';
      // Test helpers (`BillingShot(...)`, `PatientSearchWorkspace(...)`) wrap the real screen.
      if (composable && !defs[composable]) {
        const inner = [...bodyOf(t, composable).matchAll(/\b([A-Za-z]\w*)\(/g)].map((x) => x[1]).filter((n) => defs[n]);
        composable = inner.find((n) => /(Screen|Content)$/.test(n)) || inner.find((n) => /^[a-z]\w*Items$/.test(n))
          || inner.find((n) => /^[A-Z]/.test(n) && !/^Pema/.test(n)) || inner.find((n) => /^[A-Z]/.test(n)) || composable;
      }
      const shotRoutes = [...win.matchAll(/Routes\.(\w+)/g)].map((x) => x[1]).filter((r) => routes[r]);
      shots[m[1]] ||= { test: f, line: i + 1, composable, routes: [...new Set(shotRoutes)] };
    });
  }
  // Routes named inside a composable's own body (e.g. its DetailScaffold title).
  const bodyRoutes = (name) => {
    const f = defs[name];
    if (!f) return [];
    return [...bodyOf(read(f), name).matchAll(/Routes\.(\w+)/g)].map((x) => x[1]).filter((r) => routes[r] && r !== 'Workspace');
  };
  return { routes, defs, fileInfo, shots, bodyRoutes, moduleOf: (f) => rel(f).split('/src/')[0] };
}

// ---------- canvas block → Compose ----------
const q = (s) => JSON.stringify(String(s ?? ''));

function blockLines(b) {
  if (b.heading) return [`PemaHeading(${q(b.title)}, ${q(b.sub)})`];
  if (b.h2) return [`PemaH2(${q(b.title)}, ${q(b.sub)})`];
  if (b.section) return [`PemaSection(${q(b.title)})`];
  if (b.hero) return [`PemaHero(${q(b.title)}, ${q(b.sub)}, icon = ${q(b.icon)})  // kicker ${q(b.over)}`];
  if (b.metrics) return [`PemaMetrics(${b.items.map((i) => `${q(i.value)} to ${q(i.label)}`).join(', ')})`];
  if (b.actions) return [`PemaActions(${b.items.map((i) => `PemaAction(${q(i.label)}, ${q(i.icon)}) {…}`).join(', ')})`];
  if (b.tile) return [`PemaTile(${q(b.title)}, ${q(b.sub)}, icon = ${q(b.icon)}, onClick = ${b.chevron ? '{…}' : 'null'})`];
  if (b.notice) return [`PemaNotice(${q(b.text)})`];
  if (b.primary) return [`PemaPrimary(${q(b.text)}, onClick = ${b.on ? '{…}' : 'null /* disabled */'})`];
  if (b.outlined) return [`PemaOutlinedButton(${q(b.text)}, icon = ${q(b.icon)}) {…}`];
  if (b.textBtn) return [`PemaTextButton(${q(b.text)}, icon = ${q(b.icon)}) {…}`];
  if (b.dateBtn) return [`PemaTextButton(${q(b.text)}, icon = "calendar_month", iconFilled = true) {…}  // canvas dateBtn`];
  if (b.input) {
    if (b.hasPrefix && b.prefix === 'search') return [`PemaSearchField(value, hint = ${q(b.inside)})`];
    const lines = Math.max(1, Math.round((b.lh || 24) / 24));
    return [`PemaTextField(value = ${q(b.value)}, label = ${q(b.label || b.inside)}${lines > 1 ? `, minLines = ${lines}` : ''})`];
  }
  if (b.dd) return [`PemaDropdownField(value = ${q(b.value)}, options, label = ${q(b.label)})`];
  if (b.week) return [`WeekStrip()  // ${b.days.map((d) => `${d.d} ${d.n}${d.on ? '*' : ''}`).join(' ')}`];
  if (b.chips) return [`PemaChipWrap { ${b.items.map((i) => `PemaFilterChip(${q(i.label)}${i.sel ? ', selected = true' : ''}${i.dis ? ', enabled = false' : ''})`).join('; ')} }`];
  if (b.check) return [`PemaCheckRow(${q(b.label)}, checked = ${!!b.on})`];
  if (b.photos) return [`2 photo tiles 220dp radius 18 bg PemaColors.Tint, icon "face" 76dp PhotoIcon: ${b.items.map((i) => q(i.label)).join(', ')} + text "Minh họa" (real photo: LocalPhoto)`];
  if (b.order) return [`OrderLineCard(${q(b.name)}, qty ${q(b.qty)}, route ${q(b.route)}${b.hasUsage ? `, usage ${q(b.usage)}` : ''})  // feature:orders`];
  if (b.a5) return [`A5 slip ${q(b.kind)} · ${q(b.name)}: ${b.items.map((i) => q(i.text)).join(', ')} · footer ${q(b.footer)}  // feature:orders`];
  if (b.txt) return [`PemaText(${q(b.text)}${b.s !== 14 ? `, size = ${b.s}f` : ''}${b.c !== '#17324D' ? `, color = ${b.c}` : ''}${b.w !== 400 ? `, weight = W${b.w}` : ''})`];
  if (b.sp) return [`Spacer(${b.h}.dp)`];
  if (b.buckets) return [`CareBuckets(${b.items.map((i) => `${q(i.label)} ${i.count}${i.on ? '*' : ''}`).join(', ')})  // feature:care`];
  if (b.careSearch) return [`CareSearchRow(active = ${!!b.active})  // feature:care`];
  if (b.inputChip) return [`PemaInputChip(${q(b.label)}) {…}`];
  if (b.listHead) return [`List header ${q(b.title)} · ${q(b.count)}  // feature:care`];
  if (b.careRow) return [`PemaCareRow(${q(b.initials)}, ${q(b.name)}, ${q(b.group)}, ${q(b.meta)}) {…}`];
  if (b.empty) return [`PemaEmpty(${q(b.text)})`];
  if (b.period) return [`PeriodRow(${q(b.month)}${b.hasStatus ? `, status = ${q(b.status)}` : ''})  // feature:finance`];
  if (b.finHero) return [`FinanceHero(over = ${q(b.over)}, value = ${q(b.value)})  // sub ${q(b.sub)}`];
  if (b.ftitle) return [`PemaCardTitle(${q(b.text)})`];
  if (b.pill) return [`PemaPillButton(${q(b.text)}${b.hasIcon ? `, icon = ${q(b.icon)}` : ''}) {…}`];
  if (b.mcard) return [`MaterialRateCard(${q(b.title)}, ${q(b.sub)})  // feature:finance`];
  if (b.fcard) {
    const inner = (b.items || []).map((c) => {
      if (c.ftitle) return `  PemaCardTitle(${q(c.text)})`;
      if (c.fline) return `  PemaCardLine(${q(c.label)}, ${q(c.value)})`;
      if (c.txt) return `  PemaText(${q(c.text)}${c.s !== 14 ? `, size = ${c.s}f` : ''}${c.c !== '#17324D' ? `, color = ${c.c}` : ''}${c.w !== 400 ? `, weight = W${c.w}` : ''})`;
      if (c.btns) return `  PemaCardTextButtons(${c.items.map((i) => `${q(i.text)} to {…}`).join(', ')})`;
      if (c.filled) return `  PemaCardFilledButton(${q(c.text)}) {…}`;
      if (c.iconTitle) return `  Row { PemaIcon("payments", tint Blue); Text(${q(c.text)}, W700) }`;
      if (c.sp) return `  Spacer(${c.h}.dp)`;
      return `  // ${Object.keys(c).filter((k) => c[k] === true).join(',')}`;
    });
    return ['PemaInfoCard {', ...inner, '}'];
  }
  const kind = Object.keys(b).find((k) => b[k] === true) || '?';
  return [`// block "${kind}" has no mapping: ${JSON.stringify(b).slice(0, 120)}`];
}

function frameLines(s) {
  const out = [];
  if (s.appMain) {
    out.push(`PemaScaffold + PemaMainTopBar(roleLabel = ${q(s.role)}${s.bell ? `, unread = ${s.bellCount}` : ''})`);
    if (s.hasNav) out.push(`PemaBottomNav: ${s.nav.map((n) => `${n.label}${n.active ? '*' : ''}${n.hasBadge ? `(${n.badge})` : ''}`).join(' | ')}`);
  } else if (s.appDetail) {
    out.push(`DetailScaffold(title = ${q(s.title)})  // back button, padding 20`);
  }
  if (s.hasFab) out.push(`PemaExtendedFab(${q(s.fab.label)})`);
  if (s.hasSnack) out.push(`PemaSnackbar(${q(s.snack.text)}${s.snack.action ? `, action = ${q(s.snack.action)}` : ''})`);
  if (s.hasDialog) out.push(`PemaDialog(title = ${q(s.dialog.title)}, value = ${q(s.dialog.value)})`);
  if (s.hasSheet) {
    const sh = s.sheet;
    out.push(`PemaBottomSheet(title = ${q(sh.title)}, sub = ${q(sh.sub)})`);
    for (const r of sh.rows || []) out.push(`  row: icon ${q(r.icon)} ${q(r.text)}${r.hasTrail ? ` · ${q(r.trail)}` : ''}`);
    if (sh.hasNotice) out.push(`  PemaNotice(${q(sh.notice)})`);
    if (sh.hasPrimary) out.push(`  PemaPrimary(${q(sh.primary)})`);
  }
  return out;
}

const textsOf = (s) => {
  const out = new Set();
  const add = (v) => typeof v === 'string' && v.trim() && !/^#|^\d+px|^[a-z_]+$/.test(v) && out.add(v.trim());
  const visit = (o) => {
    if (Array.isArray(o)) return o.forEach(visit);
    if (o && typeof o === 'object') for (const [k, v] of Object.entries(o)) {
      if (['icon', 'activeIcon', 'ic', 'tc', 'sc', 'c', 'pad', 'rowPad', 'align', 'ws'].includes(k)) continue;
      typeof v === 'object' ? visit(v) : add(v);
    }
  };
  visit(s.blocks);
  if (s.hasSheet) visit(s.sheet);
  return [...out];
};

// ---------- notes ----------
function loadNotes() {
  try {
    return JSON.parse(read(NOTES));
  } catch {
    return { groups: {}, screens: {} };
  }
}

function saveNotes(notes) {
  fs.mkdirSync(SPECS, { recursive: true });
  fs.writeFileSync(NOTES, JSON.stringify(notes, null, 2) + '\n');
}

/** Appends a learned fact to a screen's notes (used after converting it). */
function addNote(id, kind, text) {
  const notes = loadNotes();
  notes.screens ||= {};
  const s = (notes.screens[id] ||= {});
  const key = ['logic', 'rules', 'differences', 'gotchas', 'todo'].includes(kind) ? kind : 'gotchas';
  (s[key] ||= []).includes(text) || s[key].push(text);
  saveNotes(notes);
  return s;
}

// ---------- model ----------
function buildModel() {
  const { groups, hash } = loadCanvas();
  const kmp = kmpIndex();
  const notes = loadNotes();
  const titleToRoute = {};
  for (const r of Object.values(kmp.routes)) {
    titleToRoute[r.appBar || r.title] ||= r.name;
    titleToRoute[r.title] ||= r.name;
  }

  const screens = [];
  for (const g of groups) {
    for (const s of g.screens) {
      const shot = kmp.shots[s.id];
      let composable = shot?.composable || '';
      // Workspace tabs (A–E, K3) all render through WorkspaceScreen, whatever helper the shot uses.
      if (s.appMain && kmp.defs.WorkspaceScreen && !/CareQueue|PatientSearch|patientSearch/.test(composable)) composable = 'WorkspaceScreen';
      const file = kmp.defs[composable];
      const financeRoute = { FinanceScreen: 'Finance', RateScreen: 'FinanceRates', ProcedureFormScreen: 'FinanceProcedure', DeniedScreen: '' }[composable];
      const routeName = s.appMain
        ? 'Workspace'
        : financeRoute !== undefined
          ? financeRoute
          : kmp.bodyRoutes(composable)[0] || shot?.routes.find((r) => r !== 'Workspace') || titleToRoute[s.title] || '';
      const route = composable === 'DeniedScreen'
        ? { name: 'denied', id: 'denied?route={route}', title: `${s.title} (permission blocked: Routes.denied(title))` }
        : kmp.routes[routeName];
      const webOnly = /^Web ›/.test(s.note || '') || ['I', 'J', 'K'].includes(g.code);
      const groupNote = notes.groups?.[g.code] || {};
      const own = notes.screens?.[s.id] || {};
      const merge = (k) => [...(groupNote[k] || []), ...(own[k] || [])];
      const ref = path.join(REF_DIR, `${s.id}.png`);
      screens.push({
        id: s.id,
        name: s.name,
        group: g.code,
        groupTitle: g.title,
        note: s.note || '',
        kind: s.appMain ? 'tab' : 'detail',
        role: s.role || '',
        tab: s.appMain ? (s.nav.find((n) => n.active)?.label || '') : '',
        source: webOnly
          ? { kind: 'web', hint: (s.note || '').replace(/^Web ›\s*/, '') }
          : { kind: 'kmp', class: composable, file: file ? rel(file) : '' },
        kmp: {
          route: route ? { name: route.name, id: route.id, title: route.appBar || route.title } : null,
          composable,
          file: file ? rel(file) : '',
          module: file ? kmp.moduleOf(file) : '',
          graph: file ? kmp.fileInfo[file]?.graphs || [] : [],
          domain: file ? kmp.fileInfo[file]?.domain || [] : [],
          shotTest: shot ? `${rel(shot.test)}:${shot.line}` : '',
          shotImage: file ? `${kmp.moduleOf(file)}/build/shots/${s.id}-vs.png` : '',
        },
        reference: fs.existsSync(ref) ? rel(ref) : '',
        frame: frameLines(s),
        layout: s.blocks.flatMap(blockLines),
        constraints: [...new Set([
          ...s.blocks.filter((b) => b.notice).map((b) => b.text),
          ...(s.hasSheet && s.sheet.hasNotice ? [s.sheet.notice] : []),
        ])],
        texts: textsOf(s),
        logic: merge('logic'),
        rules: merge('rules'),
        differences: merge('differences'),
        gotchas: merge('gotchas'),
        todo: merge('todo'),
        status: shot && file ? 'ported' : 'not-ported',
      });
    }
  }
  return { canvasHash: hash, canvas: rel(CANVAS), groups: groups.map((g) => ({ code: g.code, title: g.title, sub: g.sub, count: g.screens.length })), screens };
}

// ---------- markdown / prompt ----------
function bullet(list) {
  return list.length ? list.map((x) => `- ${String(x).replace(/\n/g, '\n  ')}`).join('\n') : '- (none recorded)';
}

/** Canvas block helper → Compose (core:ui unless noted). Shared by every screen spec. */
const BLOCK_CATALOG = [
  ['h(title, sub)', 'heading', 'PemaHeading(title, sub)'],
  ['h2(title, sub)', 'h2', 'PemaH2(title, sub)'],
  ['s(title)', 'section', 'PemaSection(title)'],
  ['hero(title, sub, icon)', 'hero', 'PemaHero(title, sub, icon) — kicker "PEMA • CHĂM SÓC LIÊN TỤC"'],
  ['m([v, l], …)', 'metrics', 'PemaMetrics(v to l, …) — tiles of equal height'],
  ['a([label, icon], …)', 'actions', 'PemaActions(listOf(PemaAction(label, icon) {…}))'],
  ['t(title, sub, icon, tap)', 'tile', 'PemaTile(title, sub, icon, onClick | null)'],
  ['n(text)', 'notice', 'PemaNotice(text)'],
  ['p(text, on)', 'primary', 'PemaPrimary(text, onClick | null)'],
  ['outlined(text, icon)', 'outlined', 'PemaOutlinedButton(text, icon = …)'],
  ['textBtn(text, icon)', 'textBtn', 'PemaTextButton(text, icon = …)'],
  ['dateBtn(text)', 'dateBtn', 'PemaTextButton(text, icon = "calendar_month", iconFilled = true)'],
  ['input({label, value, lines})', 'input', 'PemaTextField(value, label, minLines)'],
  ['search(hint)', 'input+prefix', 'PemaSearchField(value, hint)'],
  ['dd(value, label)', 'dd', 'PemaDropdownField(value, options, label)'],
  ['week()', 'week', 'WeekStrip() (days/selected/onSelect when a day must be picked)'],
  ['chips([[label, sel|dis]])', 'chips', 'PemaChipWrap { PemaFilterChip(label, selected, enabled) }'],
  ['check(label, on)', 'check', 'PemaCheckRow(label, checked)'],
  ['photos()', 'photos', 'Photo tile 220dp radius 18 bg Tint + icon face 76dp (real photo: LocalPhoto)'],
  ['txt(text, {s, c, w})', 'txt', 'PemaText(text, size, color, weight)'],
  ['sp(h)', 'sp', 'Spacer(h.dp)'],
  ['fc(…)', 'fcard', 'PemaInfoCard { … }'],
  ['ftitle(text)', 'ftitle', 'PemaCardTitle(text)'],
  ['fl(label, value)', 'fline', 'PemaCardLine(label, value)'],
  ['fb(text, …)', 'btns', 'PemaCardTextButtons(text to {…}, …)'],
  ['ff(text)', 'filled', 'PemaCardFilledButton(text) {…}'],
  ['careRow(p)', 'careRow', 'PemaCareRow(initials, name, group, meta) {…}'],
  ['chip(label)', 'inputChip', 'PemaInputChip(label) {…}'],
  ['empty(text)', 'empty', 'PemaEmpty(text)'],
  ['pill(text, icon)', 'pill', 'PemaPillButton(text, icon)'],
  ['buckets / careSearch / listHead', '…', 'feature:care CareQueue (bucket, search row, list header)'],
  ['order / a5', '…', 'feature:orders OrderLineCard / A5 slip'],
  ['period / finHero / mcard', '…', 'feature:finance PeriodRow / FinanceHero / MaterialRateCard'],
  ['home(…)', 'appMain', 'PemaScaffold + PemaMainTopBar(role, bell) + PemaBottomNav (tabs per role)'],
  ['det(…)', 'appDetail', 'DetailScaffold(title = Routes.appBarTitleOf(Routes.X))'],
  ['{hasFab}', 'fab', 'DetailScaffold(floatingActionButton = { PemaExtendedFab(label) })'],
  ['{hasSheet}', 'sheet', 'PemaBottomSheet { … } (no nested verticalScroll)'],
  ['{hasSnack}', 'snack', 'rememberPemaMessenger().show(text) / PemaSnackbar'],
  ['{hasDialog}', 'dialog', 'PemaDialog(title) { … }'],
];

function blocksMarkdown() {
  return `<!-- Generated — see README.md -->
# Canvas block → Compose

Helpers in \`build()\` of \`Pema App.dc.html\` and their components (\`pema-kmp/core/ui/.../widgets\`). Colors/type: only \`PemaColors.*\`, \`PemaType.*\`; icons \`PemaIcon("material_name", filled)\`.

| Canvas | Block key | Compose |
|---|---|---|
${BLOCK_CATALOG.map(([c, k, v]) => `| \`${c}\` | ${k} | ${v} |`).join('\n')}
`;
}

function screenPrompt(s) {
  const src = s.source.kind === 'web'
    ? `Logic comes from the Pema web (${s.source.hint}); see "Logic source".`
    : `Logic lives in the KMP code ${s.source.class || '(see "Logic source")'}${s.source.file ? ` (${s.source.file})` : ''}; keep its behavior unless asked to change it.`;
  return [
    `Build screen ${s.id} "${s.name}" (group ${s.group} · ${s.groupTitle}) with Compose Multiplatform in pema-kmp, 1:1 with the canvas \`Pema App.dc.html\` (390×844dp frame).`,
    src,
    s.kmp.route ? `Route: Routes.${s.kmp.route.name} ("${s.kmp.route.id}"), app bar "${s.kmp.route.title}".` : (s.kind === 'tab' ? `It is the "${s.tab}" tab of WorkspaceScreen, role ${s.role}.` : ''),
    `Only use core:ui blocks (PemaHeading, PemaTile, PemaInfoCard…); top-to-bottom layout as in "Layout". Keep the Vietnamese text and the required sentences verbatim.`,
    `Verify: shotVsCanvas("${s.id}") { … } in jvmTest, then open ${s.kmp.shotImage || '<module>/build/shots/' + s.id + '-vs.png'} (canvas left | Compose right).`,
  ].filter(Boolean).join('\n');
}

function screenMarkdown(s, model) {
  return `<!-- Generated by .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs from the canvas (${model.canvasHash}), KMP code and design-specs/notes.json. Edit notes.json, not this file. -->
# ${s.id} · ${s.name}

Group **${s.group} · ${s.groupTitle}** · ${s.kind === 'tab' ? `tab "${s.tab}" (${s.role})` : 'detail screen'} · status: **${s.status === 'ported' ? 'ported' : 'not ported'}**

> ${s.note || '(no canvas note)'}

## Logic source
${s.source.kind === 'web' ? `- Web: ${s.source.hint}` : `- KMP: \`${s.source.class || '?'}\`${s.source.file ? ` — \`${s.source.file}\`` : ''}`}
${bullet(s.logic)}

## KMP
- Route: ${s.kmp.route ? `\`Routes.${s.kmp.route.name}\` ("${s.kmp.route.id}") · app bar "${s.kmp.route.title}"` : s.kind === 'tab' ? '`Routes.Workspace` (tab in WorkspaceScreen)' : '—'}
- Composable: ${s.kmp.composable ? `\`${s.kmp.composable}\`` : '—'}${s.kmp.file ? ` — \`${s.kmp.file}\`` : ''}
- Registered by graph: ${s.kmp.graph.length ? s.kmp.graph.map((g) => `\`${g}\``).join(', ') : '—'}
- \`shared/clinic\` domain functions imported by the file (shared by every screen in it): ${s.kmp.domain.length ? s.kmp.domain.map((d) => `\`${d}\``).join(', ') : '—'}
- Shot test: ${s.kmp.shotTest ? `\`${s.kmp.shotTest}\`` : '—'} → \`${s.kmp.shotImage || '—'}\`
- Canvas image: ${s.reference ? `\`${s.reference}\`` : '(run `gradlew canvasRefs`)'}

## Frame
${s.frame.map((x) => `- ${x}`).join('\n') || '- —'}

## Layout (top to bottom, canvas block → Compose)
\`\`\`kotlin
${s.layout.join('\n')}
\`\`\`

## Required canvas text (keep verbatim)
${bullet(s.constraints)}

## Business rules
${bullet(s.rules)}

## Accepted differences from the canvas
${bullet(s.differences)}

## Gotchas / notes
${bullet(s.gotchas)}
${s.todo.length ? `\n## Still to do\n${bullet(s.todo)}\n` : ''}
## Prompt
\`\`\`text
${screenPrompt(s)}
\`\`\`
`;
}

function indexMarkdown(model) {
  const rows = model.screens.map((s) => `| [${s.id}](screens/${s.id}.md) | ${s.name} | ${s.source.kind === 'web' ? 'web' : 'KMP'} | ${s.kmp.composable ? `\`${s.kmp.composable}\`` : '—'} | ${s.kmp.module || '—'} | ${s.status === 'ported' ? '✓' : '—'} |`);
  return `<!-- Generated — see README.md -->
# Screen index (${model.screens.length})

Canvas: \`${model.canvas}\` (${model.canvasHash})

| Code | Screen | Logic source | KMP composable | Module | Ported |
|---|---|---|---|---|---|
${rows.join('\n')}
`;
}

module.exports = { ROOT, SPECS, NOTES, REF_DIR, KMP, buildModel, screenMarkdown, screenPrompt, indexMarkdown, blocksMarkdown, BLOCK_CATALOG, loadNotes, saveNotes, addNote, rel };

// Reads the web canvas the way specs-lib loadCanvas() reads the app canvas (evaluates build() in Node) and renders a canvas
// screen as kit component calls, so a web spec's Layout section shows what the frame draws, with the real text.
const fs = require('fs');
const path = require('path');
const lib = require('./web-canvas-lib.cjs');

const q = (s) => JSON.stringify(String(s));
const attrs = (o) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== false && v !== '' && v !== null && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => (v === true ? ` ${k}` : typeof v === 'string' ? ` ${k}=${q(v)}` : ` ${k}={${JSON.stringify(v)}}`))
    .join('');

const KIT = new Set(['AppShell', 'Sidebar', 'TopBar', 'Workspace', 'PageHeading', 'Card', 'Tile', 'TableShell', 'Tabs', 'TabPanel', 'Badge', 'Button', 'Field', 'Dialog', 'Sheet', 'EmptyState', 'GuardedLink']);
const SHARED = new Set(['Notice', 'FilterChip']);

/** { screens: { id: screen }, file } or null when the canvas has not been built. */
function loadCanvasScreens(dir) {
  const file = path.join(dir || lib.CANVAS_DIR, lib.CANVAS_FILE);
  if (!fs.existsSync(file)) return null;
  const src = lib.read(file);
  const m = /<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/.exec(src);
  if (!m) return null;
  const DCLogic = class {
    constructor() {
      this.props = {};
    }
  };
  const groups = new Function('DCLogic', `${m[1]}\nreturn new Component().build();`)(DCLogic);
  const screens = {};
  for (const g of groups) for (const s of g.screens) screens[s.id] = { ...s, group: g.code };
  return { screens, file };
}

const partText = (parts) => parts.map((p) => (/\bp-b\b|\bp-x\b/.test(p.c) ? `<Strong>${q(p.t)}</Strong>` : /p-sm|p-soft/.test(p.c) ? `<Small>${q(p.t)}</Small>` : q(p.t))).join(' ');
const variantOf = (cls) => (/bt-(\w+)/.exec(cls) || [0, 'secondary'])[1].replace('dangers', 'danger-solid').replace('link', 'quiet');
const toneOf = (cls, p) => (new RegExp(`${p}-(\\w+)`).exec(cls) || [0, 'neutral'])[1];

function inline(n, ctx, tail = '') {
  const use = (c) => ((ctx.used[c] = (ctx.used[c] || 0) + 1), c);
  switch (n.k) {
    case 'txt':
      return `<${/\beb\b/.test(n.cls) ? 'Eyebrow' : 'Text'}${/t-s\b|t-l\b|t-m\b/.test(n.cls) ? ' small' : ''}${/w-[bx]/.test(n.cls) ? ' strong' : ''}>${partText(n.parts)}</${/\beb\b/.test(n.cls) ? 'Eyebrow' : 'Text'}>`;
    case 'btn':
      return `<${use('Button')}${attrs({ variant: variantOf(n.cls), 'aria-label': n.aria, icon: n.icon, 'icon-after': n.ric, disabled: /bt-dis/.test(n.cls), 'icon-only': /bt-ico/.test(n.cls) })}>${n.text ? q(n.text) : ''}</Button>${tail}`;
    case 'badge':
      return `<${use('Badge')} tone=${q(n.tone)}${n.dot ? '' : ' dot={false}'}>${q(n.text)}</Badge>`;
    case 'avatar':
      return `<Avatar${/av-lg/.test(n.cls) ? ' size="lg"' : /av-sm/.test(n.cls) ? ' size="sm"' : ''}>${q(n.text)}</Avatar>`;
    case 'icon':
      return `<Icon name=${q(n.name)} />`;
    case 'chip':
      return `<${use('FilterChip')}${/ch-sel/.test(n.cls) ? ' selected' : ''}${/ch-dis/.test(n.cls) ? ' disabled' : ''}${n.count ? ` count=${q(n.count)}` : ''}>${q(n.text)}</FilterChip>`;
    case 'prog':
      return `<Progress value="${n.pct}%"${n.label ? ` label=${q(n.label)}` : ''} />`;
    default:
      return `<!-- ${n.k} -->`;
  }
}

function fieldLine(n, ctx) {
  ctx.used.Field = (ctx.used.Field || 0) + 1;
  const type = { check: 'checkbox', radio: 'radio', file: 'file', range: 'range', textarea: 'textarea', select: 'select', search: 'search' }[n.ty] || n.ty;
  const a = { label: n.text || n.label, type, required: n.req, placeholder: n.ph, default: n.vc === 'fc-v' && n.box ? n.shown : n.ty === 'file' || n.ty === 'range' ? n.shown : '', checked: n.ty === 'check' && /ck-on/.test(n.cb) ? true : undefined, hint: n.hint, error: n.err };
  if (n.opts && n.opts.length) a.options = n.opts.map((o) => o.t);
  return `<Field${attrs(a)} />`;
}

function renderNodes(nodes, pad, out, ctx) {
  for (const n of nodes) renderNode(n, pad, out, ctx);
}

function inlines(list, pad, out, ctx) {
  for (const x of list || []) out.push(pad + inline(x, ctx));
}

function renderNode(n, pad, out, ctx) {
  const use = (c) => ((ctx.used[c] = (ctx.used[c] || 0) + 1), c);
  const push = (s) => out.push(pad + s);
  switch (n.k) {
    case 'txt': case 'btn': case 'badge': case 'avatar': case 'icon': case 'chip': case 'prog':
      return push(inline(n, ctx));
    case 'h': {
      const lvl = Number(n.cls.slice(-1));
      return push(`<Heading level={${lvl}}${attrs({ sub: n.sub, eyebrow: n.eyebrow })}>${q(n.text)}</Heading>`);
    }
    case 'pageHead':
      push(`<${use('PageHeading')}${attrs({ eyebrow: n.eyebrow, title: n.title, subtitle: n.sub })}${n.actions.length ? '>' : ' />'}`);
      if (n.actions.length) {
        inlines(n.actions, pad + '  ', out, ctx);
        push('</PageHeading>');
      }
      return;
    case 'hero':
      push(`<Hero${attrs({ over: n.over, icon: n.icon })}>`);
      push(`  <Heading level={2}>${q(n.title)}</Heading>`);
      push(`  <Text>${q(n.sub)}</Text>`);
      if (n.rail && n.rail.length) push(`  <Progress aria-label=${q(n.railLabel)} segments={${n.rail.length}} done={${n.rail.filter(Boolean).length}} />`);
      inlines(n.actions, pad + '  ', out, ctx);
      return push('</Hero>');
    case 'kpis':
      push(`<Grid cols="repeat(${n.n}, 1fr)" cols-390="repeat(2, 1fr)">`);
      for (const it of n.items) {
        push(`  <${use('Tile')}${attrs({ label: it.label, value: it.unit ? `${it.value} ${it.unit}` : it.value, note: it.note, tone: it.tone !== 'neutral' ? it.tone : '', icon: it.icon, chevron: it.chev })}${it.actions.length ? '>' : ' />'}`);
        if (it.actions.length) {
          inlines(it.actions, pad + '    ', out, ctx);
          push('  </Tile>');
        }
      }
      return push('</Grid>');
    case 'stat':
      return push(`<Text><Small>${q(n.label)}</Small> <Strong>${q(n.unit ? `${n.value} ${n.unit}` : n.value)}</Strong>${n.sub ? ` <Small>${q(n.sub)}</Small>` : ''}</Text>`);
    case 'chips': {
      const sel = n.items.filter((i) => /ch-sel/.test(i.cls)).map((i) => i.text);
      use('FilterChip');
      return push(`<FilterChipGroup${n.cls === 'chs-v' ? ' direction="vertical"' : ''} items={${JSON.stringify(n.items.map((i) => (i.count ? `${i.text} ${i.count}` : i.text)))}} selected={${JSON.stringify(sel)}} />`);
    }
    case 'tags':
      push('<Row gap="6px" wrap>');
      n.items.forEach((i) => push(`  <${use('Badge')} tone=${q(/bd-(\w+)/.exec(i.cls)[1])}>${q(i.text)}</Badge>`));
      return push('</Row>');
    case 'tabs': {
      use('Tabs');
      const sel = n.items.find((i) => /tbi-on/.test(i.cls));
      return push(`<Tabs${/tbs-seg/.test(n.cls) ? ' segmented' : ''} items={${JSON.stringify(n.items.map((i) => (i.count ? `${i.text} ${i.count}` : i.text)))}} selected=${q(sel ? sel.text : '')} />`);
    }
    case 'notice': {
      use('Notice');
      const block = n.actions.length || (n.items && n.items.length);
      push(`<Notice tone=${q(n.tone)}${n.title ? ` title=${q(n.title)}` : ''}${block ? '>' : ` text=${q(n.text)} />`}`);
      if (block) {
        if (n.text) push(`  <Text>${q(n.text)}</Text>`);
        if (n.items && n.items.length) {
          if (n.itemsTitle) push(`  <Text><Strong>${q(n.itemsTitle)}</Strong></Text>`);
          push('  <ul>');
          n.items.forEach((t) => push(`    <li>${q(t)}</li>`));
          push('  </ul>');
        }
        inlines(n.actions, pad + '  ', out, ctx);
        push('</Notice>');
      }
      return;
    }
    case 'facts':
      return push(`<Facts items={${JSON.stringify(n.rows.map((r) => (r.sub ? [r.l, r.v, r.sub] : [r.l, r.v])))}} />`);
    case 'field':
      return push(fieldLine(n, ctx));
    case 'table': {
      push(`<${use('TableShell')} columns={${JSON.stringify(n.head.map((h) => h.h))}} rows={${n.rows.length}}${n.foot ? ` foot=${q(n.foot)}` : ''}  /* cards at 390 */>`);
      const seen = new Set();
      const keyOf = (x) => `${x.k}|${x.k === 'btn' ? x.text + x.icon + x.ric : x.text || ''}`.replace(/\d+(?:[.,:/]\d+)*/g, '#');
      n.rows.forEach((r, ri) => {
        const cells = r.cells.map((c) => (ri === 0 ? c.items : c.items.filter((x) => ['btn', 'badge', 'chip'].includes(x.k) && !(x.k === 'btn' && /\bbt-link\b/.test(x.cls)) && !seen.has(keyOf(x)))));
        r.cells.forEach((c) => c.items.forEach((x) => seen.add(keyOf(x))));
        if (ri > 0 && !cells.some((c) => c.length)) return;
        push(ri === 0 ? '  <Row sample="first row; demo values, the other rows have the same cells">' : `  <Row sample="row ${ri + 1} of ${n.rows.length}: only the actions and statuses that the rows above do not show">`);
        cells.forEach((items, i) => {
          if (ri > 0 && !items.length) return;
          push(`    <Cell column=${q(n.head[i] ? n.head[i].h : '')}>`);
          inlines(items, pad + '      ', out, ctx);
          push('    </Cell>');
        });
        push('  </Row>');
      });
      if (n.empty) push(`  <EmptyRow>${q(n.empty)}</EmptyRow>`);
      return push('</TableShell>');
    }
    case 'empty':
      push(`<${use('EmptyState')}${attrs({ icon: n.icon })}>`);
      push(`  <Heading level={3}>${q(n.title)}</Heading>`);
      if (n.hint) push(`  <Text>${q(n.hint)}</Text>`);
      inlines(n.actions, pad + '  ', out, ctx);
      return push('</EmptyState>');
    case 'bars':
      return push(`<StatusBars items={${JSON.stringify(n.items.map((i) => [i.label, i.count]))}} />`);
    case 'timeline':
      push('<Timeline>');
      n.items.forEach((e) => push(`  <TimelineItem date=${q(e.date)} title=${q(e.title)}${e.detail ? ` detail=${q(e.detail)}` : ''}${e.by ? ` by=${q(e.by)}` : ''} />`));
      return push('</Timeline>');
    case 'list':
      push(`<List${/ls-box/.test(n.cls) ? ' boxed' : ''}${n.items[0] && n.items[0].num ? ' ordered' : ''}>`);
      n.items.forEach((i) => {
        push(`  <ListItem${attrs({ avatar: i.avatar, icon: i.icon, over: i.over, title: i.t, sub: i.sub, sub2: i.sub2, chevron: !!i.chev })}${i.actions.length ? '>' : ' />'}`);
        if (i.actions.length) {
          inlines(i.actions, pad + '    ', out, ctx);
          push('  </ListItem>');
        }
      });
      return push('</List>');
    case 'board':
      push(`<ScheduleBoard rooms={${JSON.stringify(n.rooms.map((r) => [r.name, r.sub]))}} corner=${q(n.corner)}>`);
      n.rooms.forEach((r) => r.bk.forEach((b) => push(b.kind === 'buffer' ? `  <Buffer room=${q(r.name)} service={${b.svc}}>${q(b.title)}</Buffer>` : b.kind === 'slot' ? `  <DropSlot room=${q(r.name)} aria-label=${q(b.label)}>${q(b.title)}</DropSlot>` : `  <Booking room=${q(r.name)} label=${q([b.time, b.title, b.sub, b.sub2].filter(Boolean).join(' '))} service={${b.svc}} />`)));
      n.legend.forEach((l) => push(`  <LegendItem service={${l.svc}}>${q(l.t)}</LegendItem>`));
      return push('</ScheduleBoard>');
    case 'weekGrid':
      push('<WeekGrid>');
      n.days.forEach((d) => {
        push(`  <Day title=${q(d.title)}${d.sub ? ` sub=${q(d.sub)}` : ''}${d.add ? ` add=${q(d.add)}` : ''}>`);
        d.items.forEach((b) => push(`    <Booking label=${q([b.time, b.title, b.sub].filter(Boolean).join(' '))} service={${b.svc}} />`));
        push('  </Day>');
      });
      n.legend.forEach((l) => push(`  <LegendItem service={${l.svc}}>${q(l.t)}</LegendItem>`));
      return push('</WeekGrid>');
    case 'photos':
      push('<PhotoGrid>');
      n.items.forEach((p) => push(`  <PhotoPlaceholder label=${q(p.label)}${p.meta ? ` meta=${q(p.meta)}` : ''} tag=${q(p.tag)}${/po-ph-dis/.test(p.cls) ? ' empty' : ''}${p.slider ? ' slider' : ''} />`));
      return push('</PhotoGrid>');
    case 'a5':
      push('<A5Sheet>');
      push(`  <Text><Strong>${q(n.brand)}</Strong> <Small>${q(n.brandSub)}</Small></Text>`);
      push(`  <Heading level={1}>${q(n.title)}</Heading>`);
      if (n.draft) push(`  <Notice tone="warning">${q(n.draft)}</Notice>`);
      n.rows.forEach((r) => push(`  <Text${r.cls ? ' wide' : ''}><Strong>${q(r.l)}</Strong> ${q(r.v)}</Text>`));
      n.items.forEach((i) => push(`  <Text><Strong>${q(i.t)}</Strong> ${q(i.qty)}</Text>${i.use ? ` <Text small>${q(i.use)}</Text>` : ''}`));
      push(`  <Text><Strong>${q(n.noteL)}</Strong> ${q(n.note)}</Text>`);
      push(`  <Text>${q(n.signDate)} <Strong>${q(n.signRole)}</Strong> <Strong>${q(n.signName)}</Strong></Text>`);
      return push('</A5Sheet>');
    case 'appt':
      push(`<Appointment${attrs({ day: n.day, month: n.month, icon: n.icon, title: n.title })}>`);
      n.lines.forEach((l) => push(`  <Text>${q(l)}</Text>`));
      return push('</Appointment>');
    case 'events':
      push('<EventList>');
      n.items.forEach((e) => {
        push(`  <Disclosure summary=${q(e.date + ' ' + e.title)} icon=${q(e.icon)}${e.open ? ' open' : ''}>`);
        push(`    <Text>${q(e.detail)}</Text>`);
        push('  </Disclosure>');
      });
      return push('</EventList>');
    case 'bubbles':
      push('<MessageList>');
      n.items.forEach((m) => push(`  <Message${/bu-me/.test(m.cls) ? ' mine' : ''}${m.who ? ` from=${q(m.who)}` : ''}>${q(m.text)}${m.note ? ` <Small>${q(m.note)}</Small>` : ''}${m.time ? ` <Small>${q(m.time)}</Small>` : ''}</Message>`));
      return push('</MessageList>');
    case 'upload':
      push('<Card old="upload-box">');
      push(`  <Icon name=${q(n.icon)} />`);
      push(`  <Text>${q(n.text)}</Text>`);
      push(`  <Field label=${q(n.btn)} type="file" accept="image/png,image/jpeg,image/webp" />`);
      if (n.file) push(`  <Text>${q(n.file)}</Text>`);
      if (n.status) push(`  <Text small>${q(n.status)}</Text>`);
      if (n.preview) push(`  <Img placeholder alt="Ảnh cập nhật đã chọn — bản demo" tag=${q(n.tag)} />`);
      return push('</Card>');
    case 'stepper':
      push(`<Row><Text strong>${q(n.label)}</Text> <Progress value="${n.pct}%" aria-label="Số buổi điều trị đã hoàn tất" /></Row>`);
      return n.caption ? push(`<Text small>${q(n.caption)}</Text>`) : undefined;
    case 'quick':
      push(`<Grid cols="repeat(${n.n}, minmax(0, 1fr))" gap="8px">`);
      n.items.forEach((i) => push(`  <Button variant="secondary" icon=${q(i.icon)}>${q(i.title + ' ' + i.sub)}</Button>`));
      return push('</Grid>');
    case 'rx':
      push(`<${use('Card')} old="mobile-linked-prescriptions">`);
      push('  <Row justify="space-between">');
      push(`    <Heading level={3}>${q(n.title)}</Heading>`);
      push(`    <${use('Badge')} tone="brand">${q(n.count)}</Badge>`);
      push('  </Row>');
      if (n.empty) push(`  <Text>${q(n.empty)}</Text>`);
      n.sections.forEach((sec) => {
        push(`  <Text strong>${q(sec.title)}</Text>`);
        if (sec.sub) push(`  <Text small>${q(sec.sub)}</Text>`);
        sec.groups.forEach((g) => {
          if (g.heading) push(`  <Heading level={4}>${q(g.heading)}</Heading>`);
          g.lines.forEach((l) => push(`  <Text><Strong>${q(l.name)}</Strong>${l.qty ? ' ' + q(l.qty) : ''} ${q(l.use)}</Text>`));
        });
      });
      return push('</Card>');
    case 'matrix': {
      push(`<${use('TableShell')} columns={${JSON.stringify(n.head.map((h) => h.h))}} rows={${n.rows.length}}${n.foot ? ` foot=${q(n.foot)}` : ''} fields  /* MatrixGrid: cells hold fields; cards at 390 */>`);
      n.rows.forEach((r, ri) => {
        push(ri === 0 ? '  <Row sample="first row; demo values, the other rows have the same cells">' : `  <Row sample="row ${ri + 1} of ${n.rows.length}: same cells">`);
        r.cells.forEach((c, i) => {
          if (ri > 0 && !c.input && !c.check && !c.items.length) return;
          push(`    <Cell column=${q(n.head[i] ? n.head[i].h : '')}>`);
          if (c.text && ri === 0) push(`      <Text>${q(c.text)}</Text>${c.sub ? ` <Text small>${q(c.sub)}</Text>` : ''}`);
          if (c.input || c.check) {
            use('Field');
            push(`      <Field${attrs({ label: c.label, type: c.check ? 'checkbox' : c.ty, default: c.input && c.vc === 'fc-v' ? c.shown : '', placeholder: c.input && c.vc !== 'fc-v' ? c.shown : '', checked: c.check && /ck-on/.test(c.cb) ? true : undefined })} />`);
          }
          inlines(c.items, pad + '      ', out, ctx);
          push('    </Cell>');
        });
        push('  </Row>');
      });
      return push('</TableShell>');
    }
    case 'trace':
      push('<TracePane>');
      n.runs.forEach((r) => {
        push(`  <${use('Button')} variant="secondary"${r.open ? ' expanded' : ''}>${q(r.label + ' ' + r.toggle)}</Button>`);
        r.steps.forEach((st) => {
          push(`  <Row gap="8px" wrap>  // ${st.n}`);
          push(`    <Text>${q(st.n)}</Text>`);
          if (st.finish) push(`    <Text>${q(st.finish)}</Text>`);
          if (st.tokens) push(`    <Text>${q(st.tokens)}</Text>`);
          push('  </Row>');
          st.parts.forEach((p) => {
            push(`  <Text transform="uppercase">${q(p.label)}</Text>`);
            push(p.mono ? `  <Code>${q(p.text)}</Code>` : `  <Text>${q(p.text)}</Text>`);
          });
        });
      });
      return push('</TracePane>');
    case 'errLine':
      return push(`<Notice tone="danger" role="alert" old="error-line">${q(n.text)}</Notice>`);
    case 'img':
      return push(`<Img placeholder label=${q(n.label)} />`);
    case 'legend':
      return push(`<Legend items={${JSON.stringify(n.items.map((l) => l.t))}} />`);
    case 'sp':
      return;
    case 'hr':
      return push('<Divider />');
    case 'code':
      return push(`<Code>${q(n.text)}</Code>`);
    // containers
    case 'stack':
      push('<Stack>');
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Stack>');
    case 'row':
      push(`<Row${attrs({ gap: (/--g:(\d+)px/.exec(n.st) || [])[1] + 'px', justify: (/--jc:([\w-]+)/.exec(n.st) || [])[1] !== 'flex-start' ? (/--jc:([\w-]+)/.exec(n.st) || [])[1] : '' })} wrap>`);
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Row>');
    case 'grid':
      push(`<Grid cols=${q(n.cols)}${n.colsn !== '1fr' ? ` cols-390=${q(n.colsn)}` : ''} gap="${(/--g:(\d+)px/.exec(n.st) || [])[1]}px">`);
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Grid>');
    case 'card':
      push(`<${use('Card')}${attrs({ component: n.comp, variant: (/cd cd-(\w+)/.exec(n.cls) || [0, 'panel'])[1] === 'panel' ? '' : (/cd cd-(\w+)/.exec(n.cls) || [0, ''])[1], tint: n.tint, eyebrow: n.eyebrow, title: n.title, subtitle: n.sub })}>`);
      if (n.aside.length) {
        push('  <Card.Aside>');
        inlines(n.aside, pad + '    ', out, ctx);
        push('  </Card.Aside>');
      }
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Card>');
    case 'box':
      push(`<Box tone=${q(n.tone)}${n.title ? ` title=${q(n.title)}` : ''}>`);
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Box>');
    case 'disc':
      push(`<Disclosure summary=${q(n.title)} open>`);
      renderNodes(n.kids, pad + '  ', out, ctx);
      return push('</Disclosure>');
    default:
      return push(`<!-- ${n.k} -->`);
  }
}

/** The Next.js shell (group WJ, WK, WL): sidebar by permission, top bar with breadcrumb, search and bell, phone header and tab bar. */
function shellLinesNx(sc, ctx) {
  const out = [];
  const s = sc.shell;
  const use = (c) => ((ctx.used[c] = (ctx.used[c] || 0) + 1), c);
  if (s.skip) out.push(`<${use('Button')} variant="secondary" href="#main-content" as="link" old="skip-link">"Đến nội dung chính"</Button>`);
  out.push(`<${use('Sidebar')} old="sidebar">  // menu of role \`${s.accountId}\` (lib/nav.tsx); at 390 a header with the menu button and a bottom tab bar (${s.tabs.map((t) => q(t.label)).join(', ')}) replace it`);
  out.push(`  <${use('Button')} variant="quiet" href="/" title="Về trang chính" as="link">"PHÒNG KHÁM DA LIỄU"</Button>`);
  out.push('  <nav aria-label="Chức năng">');
  for (const sec of s.sections) {
    out.push(`    <Text transform="uppercase">${q(sec.title)}</Text>`);
    for (const it of sec.items) {
      if (it.tag) out.push(`    <Row gap="10px">  // planned entry: not a link, tooltip "Màn này sẽ có ở bản sau"\n      <Text>${q(it.label)}</Text>\n      <Text>${q(it.tag)}</Text>\n    </Row>`);
      else out.push(`    <${use('Button')} variant="quiet" href=${q(it.key)} as="link"${/sb-it-on/.test(it.cls) ? ' aria-current="page"' : ''}>${q(it.label)}</Button>`);
    }
  }
  out.push('  </nav>');
  out.push(`  <Row gap="10px"><Avatar>${q(s.user.init)}</Avatar> <Text>${q(s.user.name)}</Text> <Text>${q(s.user.role)}</Text></Row>`);
  out.push(`  <Row justify="space-between"><Text>${q(s.ver)}</Text> <Button variant="quiet" aria-label="Đổi giao diện sáng/tối" icon-only></Button> <Button variant="quiet" aria-label="Đăng xuất" icon-only></Button></Row>`);
  out.push('</Sidebar>');
  out.push(`<${use('TopBar')} old="topbar">`);
  out.push(`  <nav aria-label="Vị trí"><Text>"Không gian phòng khám"</Text> <Text>"/"</Text> <Text strong>${q(s.crumb)}</Text></nav>`);
  if (s.search) out.push(`  <${use('Field')} label="Tìm bệnh nhân" type="text" placeholder="Tìm bệnh nhân..." />`);
  if (s.bell) out.push(`  <${use('Button')} variant="quiet" href="/inbox" aria-label="Mở thông báo" icon-only as="link"></Button>`);
  out.push('</TopBar>');
  out.push(`<Row gap="12px">  // phone header\n  <Button variant="quiet" aria-label="Mở menu" icon-only></Button>\n  <Button variant="quiet" href="/" title="Về trang chính" as="link">${q(s.clinic)}</Button>\n</Row>`);
  out.push(`<nav aria-label="${s.tabAria}">${s.tabs.map((t) => `\n  <Button variant="quiet"${t.label === 'Menu' ? '' : ' as="link"'}>${q(t.label)}</Button>`).join('')}\n</nav>`);
  return out;
}

function shellLines(sc, ctx) {
  if (sc.shell.nx) return shellLinesNx(sc, ctx);
  const out = [];
  const s = sc.shell;
  const use = (c) => ((ctx.used[c] = (ctx.used[c] || 0) + 1), c);
  if (s.skip) out.push(`<${use('Button')} variant="secondary" href="#main-content" as="link" old="skip-link">"Đến nội dung chính"</Button>`);
  out.push(`<${use('Sidebar')} old="sidebar">  // menu of account \`${s.accountId}\`; at 390 a top bar with menu button and a bottom tab bar (${s.tabs.map((t) => q(t.label)).join(', ')}) replace it`);
  out.push('  <Text old="brand-context">"PHÒNG KHÁM DA LIỄU"</Text>');
  for (const sec of s.sections) {
    out.push(`  <Text old="nav-section">${q(sec.title)}</Text>`);
    for (const it of sec.items) out.push(`  <Sidebar.Item${/sb-it-on/.test(it.cls) ? ' active' : ''} icon=${q(it.icon)}>${q(it.badge ? `${it.label} ${it.badge}` : it.label)}</Sidebar.Item>`);
  }
  out.push(`  <Row old="clinic-user"><Avatar>${q(s.user.init)}</Avatar> <Text><Strong>${q(s.user.name)}</Strong> <Small>${q(s.user.role)}</Small></Text></Row>`);
  out.push('</Sidebar>');
  out.push(`<${use('TopBar')} old="topbar">`);
  out.push(`  <Text old="breadcrumbs">"Không gian phòng khám" <Strong>"/"</Strong> <Strong>${q(s.crumb)}</Strong></Text>`);
  if (s.fin) out.push(`  <Button variant="quiet" href="../finance/" as="link">${q(s.fin)}</Button>`);
  out.push(`  <${use('Field')} label="Tài khoản demo" type="select" default=${q(s.account)} options={${JSON.stringify(s.accounts.map((a) => a.t))}} />${s.pickerTag ? '  // native select popup of the browser, drawn open: ' + s.pickerTag : ''}`);
  out.push(`  <${use('Field')} label="Tìm kiếm bệnh nhân" type="text" placeholder="Tìm bệnh nhân..." />`);
  if (s.bell) out.push(`  <${use('Button')} variant="secondary" aria-label="Thông báo" icon="notifications" icon-only></Button>`);
  out.push(`  <${use('Button')} variant="secondary" aria-label="Đặt lại dữ liệu demo" icon="restart_alt" icon-only></Button>`);
  out.push('</TopBar>');
  return out;
}

/** A native browser dialog drawn over the page (confirm, prompt, alert, print, download); select is the open account list of the top bar. */
function nativeLines(sc, pad = '') {
  if (!sc.hasNative) return [];
  const n = sc.native;
  const type = (/NATIVE · (\w+)\(\)/.exec(n.tag) || [0, 'confirm'])[1];
  const out = [`${pad}// native browser dialog, not a page element: the exact text the browser showed when the shots were taken`];
  out.push(`${pad}<NativeDialog type=${q(type)}${n.print ? '' : n.download ? ` file=${q(n.message)}` : ` message=${q(n.message)}`}${n.prompt ? ` value=${q(n.value)}` : ''}${n.buttons.length ? ` buttons={${JSON.stringify(n.buttons.map((b) => b.t))}}` : ''} />`);
  return out;
}

/** The Patient Mobile page: phone top bar, content, bottom navigation of five tabs, toast, sheet, native dialog. */
function phoneLines(sc, ctx) {
  const out = [];
  const use = (c) => ((ctx.used[c] = (ctx.used[c] || 0) + 1), c);
  const m = sc.mob;
  out.push(`<${use('PhoneFrame')} patient=${q(m.name)} active=${q(m.active)}>  // 390×844, no clinic sidebar or top bar`);
  out.push('  <Row old="mobile-top" justify="space-between">');
  out.push('    <Img alt="Pema clinic & spa" />');
  out.push(`    <${use('Button')} variant="secondary" aria-label=${q('Mở hồ sơ demo của ' + m.name)} old="mobile-icon">${q(m.init)}</Button>  // screen=profile`);
  out.push('  </Row>');
  out.push('  <Stack old="mobile-content" tag="main">');
  renderNodes(sc.blocks, '    ', out, ctx);
  out.push('  </Stack>');
  out.push('  <nav old="mobile-nav">');
  m.tabs.forEach((t) => out.push(`    <Button variant="secondary" icon=${q(t.icon)}${/mnav-on/.test(t.cls) ? ' active' : ''}>${q(t.label)}</Button>`));
  out.push('  </nav>');
  if (sc.hasToast) out.push(`  <Notice tone="info" role="status" old="mobile-toast">${q(sc.toast)}</Notice>`);
  if (sc.hasDialog) {
    out.push(`  <Sheet${attrs({ eyebrow: sc.dialog.eyebrow, title: sc.dialog.title, subtitle: sc.dialog.sub })}>  // bottom sheet over the dimmed page`);
    renderNodes(sc.dialog.blocks, '    ', out, ctx);
    if (sc.dialog.footer.length) {
      out.push('    <Sheet.Footer>');
      inlines(sc.dialog.footer, '      ', out, ctx);
      out.push('    </Sheet.Footer>');
    }
    out.push('  </Sheet>');
  }
  nativeLines(sc, '  ').forEach((l) => out.push(l));
  out.push('</PhoneFrame>');
  return out;
}

/** { lines, used } of a canvas screen, as the Layout section of its spec. */
function layout(sc) {
  const ctx = { used: {} };
  const out = [];
  if (sc.phone) return { lines: phoneLines(sc, ctx), used: ctx.used };
  if (sc.bare) {
    renderNodes(sc.blocks, '', out, ctx);
    if (sc.hasToast) out.push(`<Toast>${q(sc.toast)}</Toast>`);
    return { lines: out, used: ctx.used };
  }
  if (sc.hasDialog) {
    // The Next.js dialogs are measured with the page that stays under them (a Sheet sits inside the content region), so their Layout lists that page first.
    if (/^W[JKL]\d+$/.test(sc.id) && sc.blocks.length) {
      out.push(`<AppShell role=${q(sc.role)} active=${q(sc.shell.crumb)}>  // the page behind the dialog (dimmed)`);
      renderNodes(sc.blocks, '  ', out, ctx);
      out.push('</AppShell>');
    }
    out.push(`// opens over the page "${sc.shell.crumb}" (dimmed); the page behind it is not part of this screen`);
    out.push(`<${(ctx.used.Dialog = 1, 'Dialog')}${attrs({ eyebrow: sc.dialog.eyebrow, title: sc.dialog.title, subtitle: sc.dialog.sub, width: sc.dialog.w + 'px' })}>`);
    out.push('  <Dialog.Close aria-label="Đóng hộp thoại" icon="close">"×"</Dialog.Close>');
    renderNodes(sc.dialog.blocks, '  ', out, ctx);
    if (sc.dialog.footer.length) {
      out.push('  <Dialog.Footer>');
      inlines(sc.dialog.footer, '    ', out, ctx);
      out.push('  </Dialog.Footer>');
    }
    out.push('</Dialog>');
    if (sc.hasToast) out.push(`<Toast>${q(sc.toast)}</Toast>`);
    nativeLines(sc).forEach((l) => out.push(l));
    return { lines: out, used: ctx.used };
  }
  out.push(`<AppShell role=${q(sc.role)} active=${q(sc.shell.crumb)}>`);
  for (const l of shellLines(sc, ctx)) out.push('  ' + l);
  if (sc.hasToast) out.push(`  <Toast>${q(sc.toast)}</Toast>`);
  renderNodes(sc.blocks, '  ', out, ctx);
  nativeLines(sc, '  ').forEach((l) => out.push(l));
  out.push('</AppShell>');
  return { lines: out, used: ctx.used };
}

// ---------- usage counts for design-specs/web/BLOCKS.md ----------
function usage(screens) {
  const nodes = {};
  const where = {};
  const count = (n, id) => {
    nodes[n.k] = (nodes[n.k] || 0) + 1;
    (where[n.k] ||= new Set()).add(id);
    if (n.comp) {
      nodes[n.comp] = (nodes[n.comp] || 0) + 1;
      (where[n.comp] ||= new Set()).add(id);
    }
    for (const k of n.kids || []) count(k, id);
    const inl = [...(n.aside || []), ...(n.actions || [])];
    for (const i of n.items || []) for (const k of [...(i.actions || []), ...(Array.isArray(i.items) ? i.items.filter((x) => x && x.k) : [])]) inl.push(k);
    for (const r of n.rows || []) for (const c of r.cells || []) for (const k of c.items || []) inl.push(k);
    for (const k of inl) count(k, id);
  };
  for (const sc of Object.values(screens)) {
    sc.blocks.forEach((b) => count(b, sc.id));
    sc.dialog.blocks.forEach((b) => count(b, sc.id));
    sc.dialog.footer.forEach((b) => count(b, sc.id));
  }
  return Object.fromEntries(Object.keys(nodes).sort().map((k) => [k, { nodes: nodes[k], screens: where[k].size }]));
}

module.exports = { loadCanvasScreens, layout, usage, KIT, SHARED };

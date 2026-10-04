// base.js: shared sample data and every helper a group part may use (frozen after W3a).
// The generated canvas puts this file first inside `build()`, then parts WA.js ... WH.js, so a part is only a
// `const WX = [ ...screens... ];` that calls the helpers below. Blocks are plain objects `{ k: kind, ... }`;
// the markup for each kind is in nodes.html and the CSS in template.html. See
// .claude/skills/pema-web-design/references/blocks-web.md for every helper with its arguments.

// ---------------------------------------------------------------------------------------------------------
// Sample data (synthetic). Same patients, care groups and money format as the app canvas, so both canvases
// show the same people and numbers. The old web's demo values are not copied; its labels and texts are.
// ---------------------------------------------------------------------------------------------------------
// the space before the currency sign is a no-break space, so a money value never wraps before "₫"
const money = v => Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.') + '\u00a0₫';
const GROUPS = { d1: 'Sau thủ thuật · D+1', d3: 'Ảnh tiến triển · D+3', d7: 'Bác sĩ review · D+7', due: 'Đến hạn tái khám', overdue: 'Quá hạn tái khám', no_show: 'Vắng hẹn', abandoned: 'Tiếp tục liệu trình', dormant90: 'Kết nối lại · 90 ngày', dormant180: 'Kết nối lại · 180 ngày', birthday: 'Sinh nhật trong tuần' };
const people = [
  ['P001', 'Nguyễn Thu Hà', 'BS. Tâm', 'd1'], ['P002', 'Trần Minh Anh', 'BS. Mai', 'd3'],
  ['P003', 'Lê Hoàng Yến', 'BS. Tâm', 'd7'], ['P004', 'Phạm Quốc Bảo', 'BS. An', 'due'],
  ['P005', 'Võ Ngọc Trâm', 'BS. Tâm', 'overdue'], ['P006', 'Đặng Gia Linh', 'BS. Mai', 'no_show'],
  ['P007', 'Bùi Khánh Vy', 'BS. Lan', 'abandoned'], ['P008', 'Hồ Thanh Tùng', 'BS. Tâm', 'dormant90'],
  ['P009', 'Ngô Mỹ Duyên', 'BS. An', 'dormant180'], ['P010', 'Đỗ Phương Thảo', 'BS. Mai', 'birthday'],
  ['P011', 'Lý Tuấn Kiệt', 'BS. Tâm', ''], ['P012', 'Mai Hải Yến', 'BS. Lan', '']
].map(([id, name, doctor, group], i) => ({ id, name, doctor, group, groupLabel: GROUPS[group] || '', phone: '09•• ••• ' + String(100 + i), age: 28 + i, init: name.split(' ').slice(-2).map(v => v[0]).join('') }));
const pt = people[0];
const doctors = [['BS. Tâm', 'Da liễu'], ['BS. Mai', 'Da liễu'], ['BS. An', 'Thẩm mỹ da'], ['BS. Lan', 'Chăm sóc da']].map(([name, spec]) => ({ name, spec }));
const rooms = [['Khám da liễu', 'phòng 1'], ['Tư vấn chuyên sâu', 'phòng 2'], ['Laser & thủ thuật', 'phòng 3'], ['Chăm sóc da', 'phòng 4']].map(([name, sub]) => ({ name, sub }));
const services = [['Tái khám & đánh giá', 300000, 30], ['Tư vấn da liễu', 500000, 45], ['Laser theo chỉ định', 2500000, 45], ['Chăm sóc theo chỉ định', 1200000, 45]].map(([name, price, mins], i) => ({ name, price, mins, svc: i }));
const UPDATE = 'Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa.';
const RESPONSE = 'Đỏ nhẹ sau thủ thuật là bình thường. Tiếp tục dưỡng ẩm, tránh nắng và báo lại nếu rát tăng.';
const WEB = 'Web › ';

// ---------------------------------------------------------------------------------------------------------
// Inline blocks (can sit in a card header, page heading, table cell, dialog footer...)
// ---------------------------------------------------------------------------------------------------------
const FLAG = { b: 'p-b', x: 'p-x', sm: 'p-sm', up: 'p-up', soft: 'p-soft', danger: 'p-danger', success: 'p-success', warning: 'p-warning', link: 'p-link', heading: 'p-heading' };
const flagCls = f => String(f || '').split(' ').filter(Boolean).map(x => FLAG[x] || '').join(' ');
const partsOf = p => (Array.isArray(p) ? p : [p]).map(x => (Array.isArray(x) ? { t: String(x[0]), c: flagCls(x[1]) } : { t: String(x), c: '' }));

// txt(text | [part, ...], { size, tone, w, up, cls }): a part is 'plain' or ['text', 'b sm up soft danger ...'].
const txt = (text, o = {}) => ({ k: 'txt', cls: ['t', 't-' + (o.size || 'b'), 'c-' + (o.tone || 'ink'), o.w ? 'w-' + o.w : '', o.up ? 't-up' : '', 't-ml', o.cls || ''].filter(Boolean).join(' '), parts: partsOf(text) });
const sm = (text, o = {}) => txt(text, { size: 's', tone: 'soft', ...o });
const lbl = (text, o = {}) => txt(text, { size: 'l', tone: 'soft', ...o });
const strong = (text, o = {}) => txt(text, { w: 'b', ...o });
const eyebrow = text => ({ k: 'txt', cls: 't eb', parts: partsOf(text) });
// kv('Họ tên:', 'Nguyễn Thu Hà'): bold label then value on one line.
const kv = (label, value, o = {}) => txt([[label, 'b'], ' ' + value], o);

// btn(text, variant, { icon, ric, dis, sm, full, ico }); variant: primary secondary danger dangers quiet link light.
const btn = (text, v = 'secondary', o = {}) => ({ k: 'btn', v, text: o.ico ? '' : text, icon: o.icon || '', ric: o.ric || '', cls: ['bt', 'bt-' + v, o.sm ? 'bt-sm' : '', o.dis ? 'bt-dis' : '', o.ico ? 'bt-ico' : '', o.full ? 'bt-full' : ''].filter(Boolean).join(' ') });
const primary = (text, o) => btn(text, 'primary', o);
const secondary = (text, o) => btn(text, 'secondary', o);
const quiet = (text, o) => btn(text, 'quiet', o);
const danger = (text, o) => btn(text, 'danger', o);
const lnk = (text, o) => btn(text, 'link', o);
const light = (text, o) => btn(text, 'light', o); // pale button on a dark hero (Patient Mobile "Xem hành trình →")
const back = text => btn(text, 'quiet', { sm: true }); // Patient Mobile back link, the "← Trang chủ" glyph is part of the text
const iconBtn = (icon, o = {}) => btn('', 'secondary', { ...o, icon, ico: true });
// badge(text, tone, { dot }); tone: neutral brand info success warning danger. The text is always the status.
const badge = (text, tone = 'neutral', o = {}) => ({ k: 'badge', text, tone, dot: o.dot !== false, cls: 'bd bd-' + tone });
const avatar = (text, o = {}) => ({ k: 'avatar', text, cls: 'av av-' + (o.size || 'md') });
const ico = (name, o = {}) => ({ k: 'icon', name, cls: ['ms', 'ic-' + (o.size || 20), 'c-' + (o.tone || 'soft')].join(' ') });
// chip(text, state, count): one filter pill; state 'sel' | '' | 'dis'.
const chip = (text, st = '', count = '') => ({ k: 'chip', text, count: count === '' ? '' : String(count), cls: 'ch' + (st === 'sel' ? ' ch-sel' : st === 'dis' ? ' ch-dis' : '') });
const prog = (pct, o = {}) => ({ k: 'prog', pct, label: o.label || '', cls: o.tone ? 'pg-' + o.tone : '' });

// ---------------------------------------------------------------------------------------------------------
// Leaf blocks
// ---------------------------------------------------------------------------------------------------------
const h = (text, sub = '', o = {}) => ({ k: 'h', text, sub, eyebrow: o.eyebrow || '', cls: 'hd-' + (o.lvl || 3) });
const h1 = (text, sub, o) => h(text, sub, { ...o, lvl: 1 });
const h2 = (text, sub, o) => h(text, sub, { ...o, lvl: 2 });
const h3 = (text, sub, o) => h(text, sub, { ...o, lvl: 3 });
const h4 = (text, sub, o) => h(text, sub, { ...o, lvl: 4 });
// pageHead(title, sub, actions[], eyebrow): title row of a page (PageHeading).
const pageHead = (title, sub = '', actions = [], eyebrow = '') => ({ k: 'pageHead', title, sub, actions, eyebrow });
// hero(title, sub, icon, { over, actions, rail: [done, total], small }): `rail` draws the session rail (one segment per session, `done` of them lit) under the sub line;
// `small` makes the icon a 24px mark in the corner (Patient Mobile home) instead of the large watermark.
const hero = (title, sub, icon = 'spa', o = {}) => ({ k: 'hero', over: o.over || 'PEMA • CHĂM SÓC LIÊN TỤC', title, sub, icon, icls: 'ms hr-i' + (o.small ? ' hr-i-s' : ''), actions: o.actions || [], rail: o.rail ? Array.from({ length: o.rail[1] }, (_, i) => (i < o.rail[0] ? 'rl-on' : '')) : [], railLabel: o.rail ? o.rail[0] + ' trên ' + o.rail[1] + ' buổi hoàn tất' : '' });
// kpi(label, value, note, { tone, icon, unit, chev, actions }) and kpis(kpi, kpi, ...): Tile row, any count.
const kpi = (label, value, note = '', o = {}) => ({ label, value, note, tone: o.tone || 'neutral', icon: o.icon || '', unit: o.unit || '', chev: !!o.chev, actions: o.actions || [], cls: o.btn ? 'tl-btn' : '' });
const kpis = (...items) => ({ k: 'kpis', n: items.length, items });
const stat = (label, value, sub = '', o = {}) => ({ k: 'stat', label, value, sub, unit: o.unit || '' });
// chips(['Tất cả', ['Quá hạn', 'sel', 4], ...], { vert }): FilterChipGroup; an item is 'label' or [label, state, count].
const chips = (items, o = {}) => ({ k: 'chips', cls: o.vert ? 'chs-v' : 'chs', items: items.map(x => { const [text, st = '', count = ''] = Array.isArray(x) ? x : [x]; return { text, count: count === '' ? '' : String(count), icon: '', cls: 'ch' + (st === 'sel' ? ' ch-sel' : st === 'dis' ? ' ch-dis' : '') }; }) });
// tags(badge, badge, ...): a wrapping row of badges (hero chips, status lists) as one leaf.
const tags = (...bs) => ({ k: 'tags', items: bs.flat().map(b => ({ text: b.text, dot: b.dot, cls: b.cls })) });
// tabs(['Tổng quan', ['Tư vấn', 3], ...], activeIndex, { seg }): tab bar (underline) or segmented control.
const tabs = (items, on = 0, o = {}) => ({ k: 'tabs', n: items.length, cls: o.seg ? 'tbs tbs-seg' : 'tbs', items: items.map((x, i) => { const [text, count = ''] = Array.isArray(x) ? x : [x]; return { text, count: count === '' ? '' : String(count), cls: 'tbi' + (i === on ? ' tbi-on' : '') }; }) });
const NT_ICON = { info: 'info', warning: 'warning', danger: 'error', success: 'check_circle' };
// notice(text, tone, { title, actions, items, itemsTitle }): info / warning / danger / success box with the old web's text verbatim.
// `title` is a bold first line; `items` (with an optional bold `itemsTitle`, e.g. "Điểm cần nhớ") is a bullet list under the text.
const notice = (text, tone = 'info', o = {}) => ({ k: 'notice', tone, text, title: o.title || '', icon: o.icon || NT_ICON[tone], actions: o.actions || [], items: o.items || [], itemsTitle: o.itemsTitle || '', cls: 'nt nt-' + tone });
// facts(['Mối quan tâm', 'Nám'], ['Bác sĩ', 'BS. Tâm', { sub }], ...): label left, value right, divider rows.
const facts = (...rows) => ({ k: 'facts', rows: rows.map(([l, v, o = {}]) => ({ l, v, sub: o.sub || '', cls: 'fa-vv' })) });
// empty(title, hint, { icon, actions, flat }): `flat` = no card chrome, centred grey text inside a card (Patient Mobile "Chưa có hóa đơn trong demo.")
const empty = (title, hint = '', o = {}) => ({ k: 'empty', title, hint, icon: o.icon || '', actions: o.actions || [], cls: o.flat ? 'em em-flat' : 'em' });
// bars(['Đã xác nhận', 12, 60, 'success'], ...): horizontal status bars (dashboard "Lịch hẹn theo trạng thái").
const bars = (...items) => ({ k: 'bars', items: items.map(([label, count, pct, tone = '']) => ({ label, count: String(count), pct, cls: tone ? 'pg-' + tone : '' })) });
// timeline({ date, title, detail, by, icon, tone }, ...)
const timeline = (...items) => ({ k: 'timeline', items: items.map(e => ({ icon: 'circle', detail: '', by: '', ...e, cls: e.tone ? 'tm-' + e.tone : '' })) });
// list([{ t, sub, sub2, over, icon, avatar, num, chev, actions }], { box, plain, ordered, sq }): `chev` adds a trailing chevron (the old "›"), `sq` draws the icon in a
// rounded-square tile (Patient Mobile doc-row: invoices, appointments, privacy rows) instead of a circle.
const list = (items, o = {}) => ({ k: 'list', cls: 'ls' + (o.box ? ' ls-box' : '') + (o.plain ? ' ls-plain' : '') + (o.sq ? ' ls-sq' : ''), items: items.map((x, i) => { const it = typeof x === 'string' ? { t: x } : x; return { sub: '', sub2: '', over: '', icon: '', avatar: '', actions: [], ...it, chev: it.chev ? 'chevron_right' : '', num: o.ordered ? String(i + 1) : '', cls: 'ls-r' }; }) });
const img = (label, o = {}) => ({ k: 'img', label, icon: o.icon || 'image', h: o.h || 160 });
const sp = (hh = 12) => ({ k: 'sp', h: hh });
const hr = () => ({ k: 'hr' });
const code = text => ({ k: 'code', text });
const SVC_LEGEND = services.map(s => [s.name, s.svc]);
const legend = (items = SVC_LEGEND) => ({ k: 'legend', items: items.map(([t, svc]) => ({ t, svc })) });

// ---- fields ----
const SUFFIX = { select: 'expand_more', date: 'calendar_month', month: 'calendar_month', time: 'schedule' };
// field(label, { ty, val, ph, hint, err, req, lines, opts, open, on, dis, w, text }); the helpers below set `ty`.
const field = (label, o = {}) => {
  const ty = o.ty || 'text';
  const val = o.val === undefined || o.val === null ? '' : String(o.val);
  const box = !['check', 'radio', 'range', 'file'].includes(ty);
  const opts = (o.opts || []).map(x => { const [t, on] = Array.isArray(x) ? x : [x, String(x) === val]; return { t, on, cls: ty === 'radio' ? 'rd-dot' + (on ? ' rd-on' : '') : 'lb-o' + (on ? ' lb-on' : '') }; });
  return {
    k: 'field', ty, label: ty === 'check' ? '' : label, text: label, ph: o.ph || '', fcls: o.w ? 'fd fd-w' : 'fd', req: !!o.req, hint: o.hint || '', err: o.err || '', w: o.w ? o.w + 'px' : '220px',
    box, cls: 'fc' + (ty === 'textarea' ? ' fc-ta' : '') + (o.err ? ' fc-err' : '') + (o.dis ? ' fc-dis' : ''), lh: (o.lines || 3) * 24 + 16,
    pre: ty === 'search' ? 'search' : '', suf: o.suf !== undefined ? o.suf : (SUFFIX[ty] || ''), vc: val ? 'fc-v' : 'fc-ph', shown: ty === 'file' ? (o.text || 'Chọn tệp') : (val || o.ph || ''),
    cb: 'ck-b' + (o.on ? ' ck-on' : ''), opts, open: !!o.open, pct: o.pct === undefined ? 0 : o.pct
  };
};
const input = (label, val = '', o = {}) => field(label, { ...o, val });
const select = (label, val = '', o = {}) => field(label, { ...o, ty: 'select', val });
const date = (label, val = '', o = {}) => field(label, { ...o, ty: 'date', val });
const time = (label, val = '', o = {}) => field(label, { ...o, ty: 'time', val });
const month = (label, val = '', o = {}) => field(label, { ...o, ty: 'month', val });
const number = (label, val = '', o = {}) => field(label, { ...o, ty: 'number', val });
const textarea = (label, val = '', o = {}) => field(label, { ...o, ty: 'textarea', val });
const check = (label, on = false, o = {}) => field(label, { ...o, ty: 'check', on });
const radio = (label, opts, val = '', o = {}) => field(label, { ...o, ty: 'radio', opts, val });
const search = (ph = 'Tìm bệnh nhân...', o = {}) => field(o.label || '', { ...o, ty: 'search', ph });
const file = (label, text = '', o = {}) => field(label, { ...o, ty: 'file', text });
const range = (label, shown = '', pct = 0, o = {}) => field(label, { ...o, ty: 'range', val: shown, pct });
const fieldsOf = (...args) => args; // readability only: grid(2, ...fieldsOf(a, b))

// ---- table ----
// table(cols, rows, { foot, empty }). `empty` = text of the single empty row shown when `rows` is [] (old `<EmptyRow>`, "Không có lịch phù hợp."). cols: 'Label' | ['Label', '1.4fr' | '96px', 'r'] (width, right-aligned). rows: array of cells; a cell is
// 'text' (a "\n" starts small grey lines) | [inline, inline, ...] | { i: [...], row: true } (items side by side).
// At 390 a row becomes a card: first cell as the title, the other cells under their column label.
const cellItems = x => (typeof x === 'string' ? x.split('\n').map((l, i) => (i === 0 ? txt(l) : sm(l))) : x);
const cell = (items, o = {}) => ({ i: items, ...o });
const table = (cols, rows, o = {}) => {
  const C = cols.map(c => (Array.isArray(c) ? c : [c]));
  return {
    k: 'table', cols: C.map(c => c[1] || '1fr').join(' '), foot: o.foot || '', empty: o.empty || '',
    head: C.map(c => ({ h: c[0], cls: 'tw-hc' + (c[2] === 'r' ? ' al-r' : '') })),
    rows: rows.map(r => ({ cls: o.hover ? 'tw-rh' : '', cells: r.map((x, i) => { const c = x && x.i ? x : { i: x }; const items = [].concat(cellItems(c.i)).filter(v => v !== '' && v !== null && v !== undefined).map(v => (typeof v === 'string' ? txt(v) : v)); return { h: i === 0 ? '' : C[i][0], items, cls: 'tw-c' + (c.row ? ' tw-cr' : '') + (C[i][2] === 'r' ? ' al-r' : ''), ncls: '' }; }) }))
  };
};

// ---- schedule boards ----
const pad2 = n => String(n).padStart(2, '0');
const hm = m => pad2(Math.floor(m / 60)) + ':' + pad2(m % 60);
const toMin = s => { const [a, b] = String(s).split(':'); return Number(a) * 60 + Number(b); };
// board({ rooms: [{ name, sub, bk: [{ start: '08:00', mins: 30, title, sub, sub2, svc: 0..3, buf: 15 }], slots: [{ start: '08:30', mins: 30 }] }], from, to, hh, legend }): rooms × time (day view).
// `buf` (minutes) adds "· +15′ đệm" to the time line and a hatched block "15′ chuẩn bị phòng" right after the booking; `slots` are the free
// time ranges, drawn as dashed "Đặt lịch" buttons (the old web has one invisible drop-slot button per 30 minutes, label "Đặt lịch <phòng> <giờ>").
const board = (o = {}) => {
  const from = o.from ?? 8, to = o.to ?? 18, hh = o.hh ?? 80;
  const topOf = m => (m - from * 60) / 60 * hh + 1;
  const rms = (o.rooms || rooms).map(r => {
    const items = [];
    (r.bk || []).forEach(b => {
      const s = toMin(b.start), e = s + b.mins, svc = b.svc || 0, bh = b.mins / 60 * hh;
      items.push({ kind: 'booking', time: hm(s) + '–' + hm(e) + (b.buf ? ' · +' + b.buf + '′ đệm' : ''), top: topOf(s), hgt: Math.max(bh - 2, 28), cls: 'bk bk-' + svc + (bh < 56 ? ' bk-s' : bh < 66 ? ' bk-m' : ''), fcls: 'bk bk-' + svc + ' bk-flat', title: b.title, sub: b.sub || '', sub2: b.sub2 || '', svc, slot: '', label: '' });
      if (b.buf) items.push({ kind: 'buffer', time: '', top: topOf(e), hgt: Math.max(b.buf / 60 * hh - 2, 22), cls: 'bk bk-buf bk-s', fcls: 'bk bk-buf bk-flat', title: b.buf + '′ chuẩn bị phòng', sub: '', sub2: '', svc, slot: '', label: '' });
    });
    (r.slots || []).forEach(sl => { const s = toMin(sl.start); items.push({ kind: 'slot', time: '', top: topOf(s), hgt: Math.max((sl.mins || 30) / 60 * hh - 2, 22), cls: 'bk bk-slot bk-s', fcls: 'bk bk-slot bk-flat', title: o.slotText || 'Đặt lịch', sub: '', sub2: '', svc: 0, slot: 'add', label: 'Đặt lịch ' + r.name + ' ' + hm(s) }); });
    return { name: r.name, sub: r.sub || '', bk: items };
  });
  const hours = []; for (let t = from; t < to; t++) hours.push({ t: t + ':00', top: (t - from) * hh });
  return { k: 'board', rooms: rms, nc: rms.length, hh, h: (to - from) * hh, hours, corner: o.corner || 'GIỜ', legend: (o.legend || SVC_LEGEND).map(([t, svc]) => ({ t, svc })) };
};
const week = board;
// weekGrid({ days: [{ title, sub, add: 'Đặt lịch', items: [{ time, title, sub, svc }] }], legend }): 7-day columns.
const weekGrid = (o = {}) => ({ k: 'weekGrid', nc: (o.days || []).length, days: (o.days || []).map(d => ({ title: d.title, sub: d.sub || '', add: d.add || '', items: (d.items || []).map(b => ({ time: b.time, title: b.title, sub: b.sub || '', svc: b.svc || 0 })) })), legend: (o.legend || SVC_LEGEND).map(([t, svc]) => ({ t, svc })) });

// ---- photos and print ----
// photos([{ label, meta, tag, icon, empty, slider }], { n }): illustrative placeholders only (no real or generated faces).
// `sq` = square tiles with the tag at the bottom (Patient Mobile photo compare).
const photos = (items, o = {}) => ({ k: 'photos', n: o.n || items.length, items: items.map(x => ({ tag: 'MINH HỌA TỔNG HỢP', meta: '', icon: x.empty ? 'no_photography' : 'photo_camera', slider: false, ...x, cls: 'po-ph' + (x.empty ? ' po-ph-dis' : '') + (o.sq ? ' po-sq' : '') })) });
// a5({ logo, brand, brandSub, title, draft, rows: [[label, value, wide?]], items: [{ t, qty, use }], noteL, note, signDate, signRole, signName }): order print preview.
const a5 = o => ({ k: 'a5', logo: 'Pema', brand: 'PEMA DIGITAL CLINIC', brandSub: 'Phòng khám da liễu · dữ liệu demo', title: '', draft: '', noteL: 'Dặn dò:', note: '', signDate: '', signRole: '', signName: '', items: [], ...o, rows: (o.rows || []).map(([l, v, wide]) => ({ l, v, cls: wide ? 'a5-w' : '' })) });

// ---- Patient Mobile blocks (web-only; the Next.js kit has no patient-facing components) ----
// appt({ day, month, title, lines, none }): appointment card body (date tile + title + lines). `none` = no valid date: calendar icon and "Chọn lịch" in the tile.
//   appt({ day: '20', month: 'Tháng 09', lines: ['Chủ Nhật, 20/09 · 08:00', 'BS. Tâm · Nám · tăng sắc tố'] })
const appt = (o = {}) => ({ k: 'appt', day: o.none ? '' : o.day || '', month: o.none ? 'Chọn lịch' : o.month || '', icon: o.none ? 'calendar_month' : '', title: o.title || 'Đánh giá mốc tiếp theo', lines: o.lines || [], dcls: 'ap-d' + (o.none ? ' ap-d-n' : '') });
// events({ date, title, detail, kind, open }, ...): the journey "Cập nhật gần đây" rows (old <details>): icon by kind (followup, photo, done), date, bold title, chevron.
// `open` expands that row and shows `detail` under it; a collapsed row hides its detail, as the old page does.
const EV_ICON = { followup: 'chat_bubble', photo: 'photo_library', done: 'check', aftercare: 'check', appointment: 'event' };
const events = (...items) => ({ k: 'events', items: items.map(e => ({ icon: EV_ICON[e.kind] || e.icon || 'check', date: e.date, title: e.title, detail: e.detail || '', open: !!e.open, chev: e.open ? 'expand_more' : 'chevron_right' })) });
// bubbles({ text, time, mine }, ...): care-team message bubbles; `mine` = the patient's own message, right aligned.
const bubbles = (...items) => ({ k: 'bubbles', items: items.map(m => ({ text: m.text, time: m.time || '', cls: 'bu-b' + (m.mine ? ' bu-me' : '') })) });
// upload({ text, btn, file, status, preview, icon }): the send-update file chooser (dashed box: icon, hint, "Chọn ảnh" button, chosen file name, status line, preview placeholder).
//   `file` also writes the status "Đã chọn: <file> (đã giữ trong phiên demo)" unless `status` is given. `preview` draws the (synthetic) preview placeholder.
const upload = (o = {}) => ({ k: 'upload', icon: o.icon || 'photo_camera', text: o.text || 'Thêm ảnh nếu bạn muốn đội ngũ xem vùng da cụ thể.', btn: o.btn || 'Chọn ảnh', file: o.file || '', status: o.status !== undefined ? o.status : o.file ? 'Đã chọn: ' + o.file + ' (đã giữ trong phiên demo)' : '', preview: !!o.preview, tag: 'MINH HỌA TỔNG HỢP' });
// stepper(label, pct, caption): progress row "2/5 buổi" + bar + caption under it (journey summary). pct 0-100.
const stepper = (label, pct, caption = '') => ({ k: 'stepper', label, pct, caption });
// quick([icon, title, sub], ...): quick-action tiles in one row (home "Việc hôm nay").
const quick = (...items) => ({ k: 'quick', n: items.length, items: items.map(([icon, title, sub]) => ({ icon, title, sub })) });
// rx({ title, count, empty, sections: [{ title, sub, groups: [{ heading, lines: [{ name, qty, use }] }] }] }): the card "Đơn & phiếu đã duyệt" injected on home, profile and docs.
//   no `sections` = empty state (chip "Chưa có", "Đơn và phiếu sẽ xuất hiện sau khi bác sĩ duyệt."); `lines` is a shortcut for one group without heading.
//   count defaults to "<n> đơn". A cashier order adds a section whose groups have headings "Đơn thuốc" and "Phiếu tư vấn".
const rx = (o = {}) => {
  const secs = (o.sections || []).map(s => ({ title: s.title, sub: s.sub || '', groups: (s.groups || [{ lines: s.lines || [] }]).map(g => ({ heading: g.heading || '', lines: (g.lines || []).map(l => ({ name: l.name, qty: l.qty ? '· ' + l.qty : '', use: l.use || '' })) })) }));
  return { k: 'rx', title: o.title || 'Đơn & phiếu đã duyệt', count: o.count !== undefined ? o.count : secs.length ? secs.length + ' đơn' : 'Chưa có', empty: secs.length ? '' : o.empty !== undefined ? o.empty : 'Đơn và phiếu sẽ xuất hiện sau khi bác sĩ duyệt.', sections: secs };
};
// errLine(text): inline error line (old `.ops-error`, `.crm-error`, `#review-error`, `<p role="alert">`): danger-coloured text with an error icon, no box. Goes at the end of a
// dialog body or form, under the field or tabs it belongs to. Use `notice(text, 'danger')` only when the old web draws a boxed notice.
const errLine = text => ({ k: 'errLine', text });
// mobTitle(title, greeting): Patient Mobile page title; the optional greeting ("Chào Linh") sits above it in small grey.
const mobTitle = (title, greeting = '') => (greeting ? stack({ g: 2 }, sm(greeting), h1(title)) : h1(title));

// ---------------------------------------------------------------------------------------------------------
// Containers (nest up to 4 levels: container > container > container > container > leaf)
// ---------------------------------------------------------------------------------------------------------
const isNode = x => !!x && typeof x === 'object' && typeof x.k === 'string';
const lead = a => (a.length && a[0] && typeof a[0] === 'object' && !Array.isArray(a[0]) && !isNode(a[0]) ? [a[0], a.slice(1)] : [{}, a]);
const flat = a => a.flat(Infinity).filter(x => x !== null && x !== undefined && x !== false);
// stack({ g }, ...kids): column. row({ g, ai, jc }, ...kids): wrapping row. grid(cols, ...kids): cols is a CSS template, a number (equal
// columns) or { cols, colsn, g }; `colsn` is the template at 390 (default one column, 2 for 4+ equal columns).
// Every container renders through one markup: outer element (cls, st), optional head (card title, box title, disclosure summary),
// inner element (icls, ist) holding the children; stack, row and grid use `display: contents` for the inner one.
const cont = (kind, o) => ({ k: kind, cont: true, st: '', icls: 'dc', ist: '', hasHead: false, hcls: '', tcls: '', title: '', sub: '', eyebrow: '', icon: '', aside: [], ...o });
const stack = (...a) => { const [o, k] = lead(a); return cont('stack', { cls: 'k-stack', st: '--g:' + (o.g ?? 12) + 'px', kids: flat(k) }); };
const row = (...a) => { const [o, k] = lead(a); return cont('row', { cls: 'k-row', st: '--g:' + (o.g ?? 8) + 'px;--ai:' + (o.ai || 'center') + ';--jc:' + (o.jc || 'flex-start'), kids: flat(k) }); };
const grid = (cols, ...a) => {
  const [o0, k] = lead(a);
  const o = cols && typeof cols === 'object' ? { ...cols, ...o0 } : { ...o0, cols };
  const n = typeof o.cols === 'number' ? o.cols : 0;
  const c = n ? 'repeat(' + n + ',minmax(0,1fr))' : o.cols;
  const cn = o.colsn || (n >= 4 ? 'repeat(2,minmax(0,1fr))' : '1fr');
  return cont('grid', { cls: 'k-grid', st: '--g:' + (o.g ?? 16) + 'px;--cols:' + c + ';--colsn:' + cn, cols: c, colsn: cn, kids: flat(k) });
};
// card({ title, sub, eyebrow, aside: [inline], v, g }, ...kids); v: panel soft ai plain flush hero. panel(title, sub, aside, ...kids) is the short form.
// `tint` colours the card like a service or a tone: a tone name (info brand success warning danger) or a service number 0-3
// (0 = none, 1 = brand, 2 = success, 3 = warning: the old web's service cards S0-S3); title and headings take the tone's text colour.
const TINT = ['', 'brand', 'success', 'warning'];
const card = (o0, ...k) => {
  const o = typeof o0 === 'string' ? { title: o0 } : (o0 || {});
  const aside = o.aside || [];
  const tint = typeof o.tint === 'number' ? TINT[o.tint] || '' : o.tint || '';
  return cont('card', { title: o.title || '', sub: o.sub || '', eyebrow: o.eyebrow || '', aside, tint, hasHead: !!(o.title || o.sub || o.eyebrow || aside.length), hcls: 'cd-h', tcls: 'cd-t', cls: 'cd cd-' + (o.v || 'panel') + (tint ? ' cd-tn-' + tint : ''), icls: 'k-stack', ist: '--g:' + (o.g ?? 12) + 'px', kids: flat(k) });
};
const panel = (title, sub, aside, ...k) => card({ title, sub, aside: aside || [] }, ...k);
// box(tone, ...kids): notice-coloured container for rich callouts (kids may be fields and badges). box({ tone, title }, ...kids).
const box = (o0, ...k) => { const o = typeof o0 === 'string' ? { tone: o0 } : (o0 || {}); return cont('box', { title: o.title || '', hasHead: !!o.title, hcls: 'bx-h', tcls: 'bx-t', cls: 'bx bx-' + (o.tone || 'info'), tone: o.tone || 'info', icls: 'k-stack', ist: '--g:' + (o.g ?? 8) + 'px', kids: flat(k) }); };
// disc('+ Ghi nhận ...', ...kids): the old `<details>` section, drawn open.
const disc = (summary, ...k) => cont('disc', { title: summary, icon: 'expand_more', hasHead: true, hcls: 'ds-s', tcls: 'ds-t', cls: 'ds', icls: 'ds-b k-stack', ist: '--g:12px', kids: flat(k) });
// split(main[], aside[]): two columns 1.65fr : 1fr (stacked at 390); a column with several blocks is wrapped in a stack, a single block is not (saves a nesting level).
const col = (k, g) => { const a = [].concat(k).flat(); return a.length === 1 ? a[0] : stack({ g }, ...a); };
const split = (main, aside, o = {}) => grid(o.cols || 'minmax(0,1.65fr) minmax(300px,1fr)', col(main, o.g ?? 16), col(aside, o.g ?? 16));

// ---------------------------------------------------------------------------------------------------------
// Shell: sidebar, top bar, roles (old web: clinic.js nav, staff-context.js pages)
// ---------------------------------------------------------------------------------------------------------
const NAV = [
  ['Không gian làm việc', [['dashboard', 'Tổng quan', 'space_dashboard'], ['today', 'Hôm nay', 'today'], ['schedule', 'Điều phối lịch', 'calendar_month'], ['patients', 'Tìm bệnh nhân', 'group'], ['crm', 'CSKH hôm nay', 'forum'], ['followups', 'Theo dõi', 'inbox'], ['studio', 'Ảnh trước / sau', 'photo_library']]],
  ['Quản lý', [['resources', 'Bác sĩ & phòng', 'stethoscope'], ['services', 'Dịch vụ', 'spa'], ['cashier', 'Thu ngân', 'receipt_long'], ['finance', 'Tài chính & tiền thủ thuật', 'account_balance_wallet']]],
  ['Phân tích', [['ask', 'Ask Pema', 'auto_awesome'], ['guide', 'Hướng dẫn', 'menu_book']]]
];
const PAGES = {
  owner: ['dashboard', 'today', 'schedule', 'patients', 'crm', 'followups', 'studio', 'resources', 'services', 'cashier', 'finance', 'ask', 'guide'],
  doctor: ['dashboard', 'today', 'schedule', 'patients', 'followups', 'studio', 'finance', 'guide'],
  care: ['crm', 'schedule', 'patients', 'guide'],
  accountant: ['finance', 'cashier', 'patients', 'guide']
};
const ACCOUNTS = [
  { id: 'owner-tam', name: 'BS. Tâm', role: 'owner', label: 'Chủ phòng khám', init: 'BT' },
  { id: 'doctor-tam', name: 'BS. Tâm', role: 'doctor', label: 'Bác sĩ điều trị', init: 'BT' },
  { id: 'doctor-mai', name: 'BS. Mai', role: 'doctor', label: 'Bác sĩ điều trị', init: 'BM' },
  { id: 'doctor-an', name: 'BS. An', role: 'doctor', label: 'Bác sĩ điều trị', init: 'BA' },
  { id: 'doctor-lan', name: 'BS. Lan', role: 'doctor', label: 'Bác sĩ điều trị', init: 'BL' },
  { id: 'care-maianh', name: 'Mai Anh', role: 'care', label: 'CSKH', init: 'MA' },
  { id: 'care-thu', name: 'Thu', role: 'care', label: 'CSKH', init: 'T' },
  { id: 'accountant', name: 'Kế toán', role: 'accountant', label: 'Đối soát & thu ngân', init: 'KT' }
];
const TAB_KEYS = { owner: ['today', 'patients', 'followups'], doctor: ['today', 'patients', 'followups'], care: ['crm', 'schedule', 'patients'], accountant: ['cashier', 'finance', 'patients'] };
const TAB_SHORT = { today: 'Hôm nay', patients: 'Hồ sơ', followups: 'Theo dõi', crm: 'CSKH', schedule: 'Lịch', cashier: 'Thu ngân', finance: 'Tài chính' };
const NAV_FLAT = NAV.flatMap(([, items]) => items);
const accountOf = id => ACCOUNTS.find(a => a.id === id) || ACCOUNTS[0];
// shellOf(account id, nav key, { crumb, fin, pickerOpen, skip, badge }): data the template needs to draw sidebar, top bar and tab bar.
const shellOf = (accId, navKey, o = {}) => {
  const acc = accountOf(accId);
  const pages = PAGES[acc.role];
  const label = (key, def) => (key === 'finance' && acc.role === 'doctor' ? 'Doanh số của tôi' : def);
  const sections = NAV.map(([title, items]) => ({ title, items: items.filter(([key]) => pages.includes(key)).map(([key, def, icon]) => ({ key, icon, label: label(key, def), cls: 'sb-it' + (key === navKey ? ' sb-it-on' : ''), badge: key === 'followups' ? (o.badge ?? '5') : '' })) })).filter(s => s.items.length);
  const tabs = TAB_KEYS[acc.role].filter(k => pages.includes(k)).map(k => ({ label: TAB_SHORT[k], icon: NAV_FLAT.find(n => n[0] === k)[2], cls: 'tabbar-i' + (k === navKey ? ' tabbar-on' : '') }));
  tabs.push({ label: 'Menu', icon: 'menu', cls: 'tabbar-i' });
  const crumbOf = key => label(key, (NAV_FLAT.find(n => n[0] === key) || [0, 'Tổng quan'])[1]);
  return {
    sections, tabs, user: { init: acc.init, name: acc.name, role: acc.label }, account: acc.name + ' · ' + acc.label, accountId: acc.id, crumb: o.crumb || crumbOf(navKey),
    bell: ['owner', 'doctor'].includes(acc.role), // the old web draws the notification bell for the owner and the doctors only
    fin: o.fin === undefined ? (['owner', 'doctor', 'accountant'].includes(acc.role) ? 'Tài chính đã đồng bộ' : '') : o.fin, pickerOpen: !!o.pickerOpen, skip: !!o.skip,
    accounts: ACCOUNTS.map(a => ({ t: a.name + ' · ' + a.label, cls: 'lb-o' + (a.id === acc.id ? ' lb-on' : '') }))
  };
};

// ---------------------------------------------------------------------------------------------------------
// Screens
// ---------------------------------------------------------------------------------------------------------
const SIZES = { '1440x900': { w: 1440, h: 900, cls: 'wf-md' }, '1920x1020': { w: 1920, h: 1020, cls: 'wf-xl' }, '390x844': { w: 390, h: 844, cls: 'wf-sm' } };
const ALL_FRAMES = ['1440x900', '1920x1020', '390x844'];
const ONE_FRAME = ['1440x900'];
const PHONE_FRAME = ['390x844'];
const KIND_LABEL = { page: 'trang', tab: 'tab Patient 360', dlg: 'hộp thoại', fin: 'tài chính', state: 'trạng thái', mob: 'trang điện thoại', mobState: 'trạng thái điện thoại' };
// A Patient Mobile frame (`o.phone`) has no clinic sidebar or top bar: `fr.phone` draws the phone top bar and bottom navigation instead.
const frameOf = (key, o = {}) => { const s = SIZES[key], ph = !!o.phone; return { size: key, w: s.w, h: s.h, cls: s.cls + (ph ? ' wf-ph' : ''), wide: !ph && s.w > 600, narrow: !ph && s.w <= 600, phone: ph, sb: !ph && (s.w > 600 || !!o.drawer), sbCls: s.w > 600 ? 'sb' : 'sb sb-dr', drawer: !ph && s.w <= 600 && !!o.drawer, id: '', label: '' }; };
// native(type, message, { value, options, buttons }): a native browser dialog drawn over the page, with the exact text the shots manifest captured (`native_dialog`).
//   type: confirm (message + OK/Cancel), prompt (message + input showing `value` + OK/Cancel), alert (message + OK), print (print dialog with a sheet preview, no message),
//   download (download bubble with the file name as `message`), select (the open option list of the account picker; `options` = every option, the first is current).
//   Pass it as the screen option `native` of page / tab / fin / dlg: page('WA5', ..., 'dashboard', blocks, { state: true, native: native('confirm', 'Đặt lại dữ liệu demo?') }).
const NATIVE_BTN = { confirm: ['OK', 'Cancel'], prompt: ['OK', 'Cancel'], alert: ['OK'], print: ['Print', 'Cancel'], download: [], select: [] };
const native = (type, message = '', o = {}) => ({ type, message, value: o.value || '', options: o.options || [], buttons: o.buttons || NATIVE_BTN[type] || ['OK'] });
const nativeOf = n => !n ? { has: false, cls: 'nd', tag: '', message: '', value: '', box: false, prompt: false, print: false, download: false, buttons: [] } : {
  has: true, cls: 'nd' + (['confirm', 'prompt', 'alert', 'print'].includes(n.type) ? ' nd-dim' : ''), tag: 'NATIVE · ' + n.type + '()', message: n.message, value: n.value,
  box: ['confirm', 'prompt', 'alert'].includes(n.type), prompt: n.type === 'prompt', print: n.type === 'print', download: n.type === 'download',
  buttons: n.buttons.map((t, i) => ({ t, cls: 'bt bt-' + (i === 0 ? 'primary' : 'secondary') + ' bt-sm' }))
};
const baseScreen = (kind, id, name, note, nav, blocks, o) => {
  const sc = {
    id, name, note, kind, kindLabel: KIND_LABEL[o.state ? 'state' : kind], nav, role: o.role || 'owner-tam', state: !!o.state, phone: !!o.phone,
    frames: (o.frames || (kind === 'dlg' || o.state ? ONE_FRAME : ALL_FRAMES)).map(f => frameOf(f, o)),
    shell: { ...shellOf(o.role || 'owner-tam', nav, o), pickerTag: '' }, blocks: flat(blocks), hasDialog: false, dialog: { blocks: [], footer: [], w: 640, title: '', sub: '', eyebrow: '', ovCls: 'ov', dgCls: 'dg', close: true },
    hasToast: !!o.toast, toast: o.toast || '', toastCls: o.phone ? 'ts mtoast' : 'ts', toastIcon: !o.phone, hasNative: false, native: nativeOf(null), mob: { name: '', init: '', tabs: [] }
  };
  if (o.native) {
    sc.hasNative = true;
    sc.native = nativeOf(o.native);
    if (o.native.type === 'select') { // the native option list of the account picker, drawn open under the picker
      sc.shell.pickerOpen = true;
      sc.shell.pickerTag = sc.native.tag;
      sc.shell.accounts = o.native.options.map((t, i) => ({ t, cls: 'lb-o' + (i === 0 ? ' lb-on' : '') }));
      sc.hasNative = false;
    }
  }
  return sc;
};
// page(id, name, note, navKey, blocks, { role, state, frames, toast, drawer, crumb, fin, pickerOpen, skip, native }): a page inside the app shell.
// Pages and Patient 360 tabs get 1440, 1920 and 390 frames; pass `state: true` for the screens the inventory lists as `state` (1440 only).
const page = (id, name, note, nav, blocks, o = {}) => baseScreen('page', id, name, note, nav, blocks, o);
// Patient 360 header (back link, hero card with avatar, name, chips, actions, tab bar) for tab().
const P360_TABS = ['Tổng quan', 'Tư vấn', 'Kế hoạch', 'Buổi điều trị', 'Ảnh trước / sau', 'Dịch vụ & tài chính', 'CRM & CSKH', 'Lịch sử'];
const patientHead = (p, tabIndex, o = {}) => [
  quiet('← Danh sách bệnh nhân'),
  card({ v: 'hero' },
    row({ g: 20, jc: 'space-between', ai: 'center' },
      row({ g: 16, ai: 'center' }, avatar(p.init, { size: 'lg' }),
        stack({ g: 4 }, eyebrow('Hồ sơ ' + p.id + ' · ' + (o.status || 'Đặt hẹn')), h1(p.name),
          txt(p.age + ' tuổi · Nữ · ' + p.phone + ' · Bác sĩ phụ trách: ' + p.doctor, { size: 's', tone: 'soft' }),
          tags(...(o.chips || [badge('Nám · tăng sắc tố', 'brand', { dot: false }), badge('⚠ Da nhạy cảm', 'warning', { dot: false }), badge('⚠ Theo dõi đỏ da sau điều trị', 'warning', { dot: false })])))),
      row({ g: 8, jc: 'flex-end' }, ...(o.actions || [secondary('AI brief', { icon: 'auto_awesome' }), secondary('Nhắn tin'), primary('Ghi buổi điều trị', { icon: 'add' })])))),
  tabs(P360_TABS, tabIndex)
];
// tab(id, name, note, tabIndex, blocks, { patient, status, chips, actions, role, state }): Patient 360 tab; `blocks` come under the tab bar.
const tab = (id, name, note, tabIndex, blocks, o = {}) => baseScreen('tab', id, name, note, 'patients', [patientHead(o.patient || pt, tabIndex, o), flat(blocks)], o);
// fin(id, name, note, tabIndex, blocks, { role, title, tabs, eyebrow, state }): finance page (own header: eyebrow, title, period + refresh, 4 tabs).
const FIN_TABS = ['Tổng quan', 'Tiền thủ thuật', 'Chính sách tỷ lệ', 'Phiếu thu & thông báo'];
const finHead = (tabIndex, o = {}) => [
  row({ g: 20, jc: 'space-between', ai: 'flex-end' },
    stack({ g: 2 }, txt(o.eyebrow || 'ĐIỀU HÀNH • PEMA CLINIC', { size: 's', tone: 'soft', up: true }), h1(o.title || 'Tài chính & tiền thủ thuật')),
    row({ g: 12, ai: 'flex-end' }, month('Kỳ báo cáo', '2026-09', { w: 160 }), secondary('Làm mới'))),
  tabs(o.tabs || FIN_TABS, tabIndex)
];
const fin = (id, name, note, tabIndex, blocks, o = {}) => baseScreen('fin', id, name, note, 'finance', [finHead(tabIndex, o), flat(blocks)], o);
// dlg(id, title, note, blocks, { eyebrow, sub, w, footer: [inline], nav, behind: [blocks], role }): dialog or modal over the dimmed page (1440 only).
const dlg = (id, title, note, blocks, o = {}) => {
  const sc = baseScreen('dlg', id, title, note, o.nav || 'dashboard', o.behind || [], o);
  sc.hasDialog = true;
  sc.dialog = { ...sc.dialog, blocks: flat(blocks), footer: o.footer || [], w: o.w || 640, title, sub: o.sub || '', eyebrow: o.eyebrow || '' };
  return sc;
};
// mob(id, name, note, active, blocks, { patient, toast, sheet, native, state }): a Patient Mobile page (old `prototype/patient-mobile`) in a 390×844 phone frame: top bar (logo + avatar button
// "ML" that opens Hồ sơ), `blocks` as the content, the bottom navigation of five tabs (Trang chủ, Lịch hẹn, Hành trình, Tin nhắn, Hồ sơ) and optional overlays. There is no clinic sidebar.
//   active: the lit tab, as the old web lights it: 'home', 'appointments', 'journey', 'messages', 'profile'; the sub-screens light their parent ('progress', 'care', 'send' -> journey,
//   'docs' -> profile) or pass 0-4. o.toast: the dark toast above the navigation (the old `mobile-toast`, role status). o.sheet: { title, sub, eyebrow, blocks, footer } draws a bottom sheet over the
//   dimmed page. o.native: native(...) over the page. o.patient: a `people` entry (avatar initials and the aria-label of the avatar button). o.state: true for inventory kind state/dialog/modal.
const MOB_TABS = [['home', 'Trang chủ', 'home'], ['appointments', 'Lịch hẹn', 'calendar_month'], ['journey', 'Hành trình', 'route'], ['messages', 'Tin nhắn', 'chat_bubble'], ['profile', 'Hồ sơ', 'person']];
const MOB_ACTIVE = { home: 0, appointments: 1, journey: 2, progress: 2, care: 2, send: 2, messages: 3, profile: 4, docs: 4 };
const mob = (id, name, note, active, blocks, o = {}) => {
  const p = o.patient || pt, on = typeof active === 'number' ? active : MOB_ACTIVE[active];
  if (on === undefined) throw new Error(`${id}: mob() active tab "${active}" is not one of ${Object.keys(MOB_ACTIVE).join(', ')}`);
  // a toast would hide the last lines of a frame that is taller than the phone screen, so the frame keeps room under the content
  const sc = baseScreen('mob', id, name, note, 'home', [flat(blocks), o.toast ? sp(64) : null], { ...o, phone: true, frames: o.frames || PHONE_FRAME });
  sc.kindLabel = KIND_LABEL[o.state ? 'mobState' : 'mob'];
  sc.mob = { name: p.name, init: p.init, tabs: MOB_TABS.map(([, label, icon], i) => ({ label, icon, cls: 'mnav-i' + (i === on ? ' mnav-on' : '') })), active: MOB_TABS[on][1] };
  if (o.sheet) {
    sc.hasDialog = true;
    sc.dialog = { ...sc.dialog, blocks: flat(o.sheet.blocks || []), footer: o.sheet.footer || [], w: 390, title: o.sheet.title || '', sub: o.sheet.sub || '', eyebrow: o.sheet.eyebrow || '', ovCls: 'ov ov-sh', dgCls: 'dg dg-sh', close: false, sheet: true };
  }
  return sc;
};

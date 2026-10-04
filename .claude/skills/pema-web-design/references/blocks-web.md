# Web canvas blocks and helpers (`Pema Web redesign canvas`)

This file is the whole manual for writing a group part (`parts/WA.js` … `WH.js`, and `parts/WI.js` + `parts/WI2.js` for the Patient Mobile group WI). A fresh agent does not need to read
`template.html`, `nodes.html` or `base.js`. Every block is drawn like the app canvas block of the same purpose (see
`design-specs/BLOCKS.md`) at web size, with tokens only (`tokens.json`), and stands for one `pema-agent/frontend/src/ui`
component. Blocks the app has no counterpart for are marked **web-only**. A block whose kit component does not exist yet is a
**kit gap** (listed for the director; the Next.js kit is not changed in package W).

Owner rule: a canvas screen shows EVERY field, action, status, filter, notice and text of its old-web screen. Labels and
business sentences come from the spec (`design-specs/web/screens/<ID>.md`) and the shot, verbatim. Names, numbers and money are
the canvas sample data (`people`, `doctors`, `rooms`, `services`, `money()`), never the old web's demo values.

## 1. Work loop

```
# once per agent: your own viewer (deps are installed in the main checkout; pick a free port, 4180 is reserved)
cd C:/Users/phanx/Documents/Codex/2026-09-11/create-an-image-of/cnbphongkham/design-viewer
DC_CANVAS_DIR=C:/wt/<your worktree>/"Pema Web redesign canvas" npm run dev -- --port <your port>      # run in the background

# every round, in your worktree
node .claude/skills/pema-web-design/scripts/web-canvas-build.cjs                      # parts -> "Pema Web.dc.html" (do not commit it in W3b)
PLAYWRIGHT_MODULE=C:/Users/phanx/Documents/Codex/2026-09-11/create-an-image-of/cnbphongkham/pema-agent/frontend/node_modules/playwright \
node .claude/skills/pema-web-design/scripts/web-canvas.cjs check "Pema Web redesign canvas/Pema Web.dc.html" <GROUP> "%TEMP%/<dir>" \
     --canvas-dir "C:/wt/<your worktree>/Pema Web redesign canvas" --viewer-url http://localhost:<your port> [--viewport=1920x1020|390x844|all] [--frames] [--theme=dark]
node .claude/skills/pema-web-design/scripts/web-specs.cjs --check --group=<GROUP>      # coverage of your ids against the old-web snapshot
# an agent that owns some ids of a group: judge only those (viewport defaults to 390x844 when the group is WI, else 1440x900)
#   web-canvas.cjs check "Pema Web redesign canvas/Pema Web.dc.html" WI "%TEMP%/<dir>" --canvas-dir ... --viewer-url ... --frames --complete --ids=WI3,WI4
#   web-specs.cjs            # regenerate design-specs/web (specs, INDEX.md, BLOCKS.md, index.json) after the build; commit what it changes
node .claude/skills/pema-web-design/scripts/web-canvas.cjs list                        # ID · name · note of every screen
```

`--ids=WI3,WI4` narrows `expected`, `missing`, `frames` and the PNGs to those ids, so `--complete` can pass while the rest of the group is still empty. `check` prints JSON (`total`, `expected`, `missing`, `frames`, `frameMismatch`, `errors`, `unresolved`, `overflow`, `badIcons`,
`tokens`, `hexInBlocks`) and writes `web-<GROUP>-<viewport>.png` (whole group) and, with `--frames`, one PNG per frame
(`<ID>-<width>.png`). Open the PNGs and look: text overflow, wrapped numbers, icon names shown as text. `--complete` also fails
while ids of the group have no frame yet. `Pema Web blocks.dc.html` (build with `web-canvas-build.cjs --blocks`, check with
`web-canvas.cjs check "Pema Web blocks.dc.html" WA`) is the block gallery: every block below drawn once at 1440, 1920 and 390.

## 2. Rules

- A part is only `const WX = [ page(...), tab(...), dlg(...), fin(...) ];` using the helpers below. Never edit `template.html`,
  `nodes.html`, `base.js`, `tail.js` or another part. Missing block or helper: write it as an open item and skip that screen.
- No colour, font size or radius in a part: only helpers. `check` fails on a hex colour outside the token block.
- Nesting: containers (`stack row grid card box disc`) nest 4 levels deep (container > container > container > container > leaf).
  Build fails with the screen id when a screen is deeper. Flatten with `split`, `grid` or by putting a row of `tags`/`chips`.
- **Inline blocks** (`txt btn badge avatar icon chip prog`) may sit in lists named `aside`, `actions`, `footer` and in table cells.
  Everything else (fields, tiles, notices…) is a leaf that goes in a container's children.
- Frames follow the inventory (decision D4): `page` and `tab` and `fin` get 1440, 1920 and 390; screens the inventory lists as
  `state`, `dialog` or `modal` get 1440 only (pass `{ state: true }` to `page`/`tab`/`fin`; `dlg` is always 1440). Every WI id (Patient Mobile) gets
  one 390×844 frame, made by `mob(...)` (section 9).
  `check` reports `frameMismatch` against `inventory.json`.
- Notes start with `WEB + '<nav/tab/modal> · <difference from the old web, if any>'`; for Next.js targets `planned (U4|U5|U6)` add
  `· chưa có trên Next.js`.
- Photos are placeholders (`photos`) with consent text; no real or generated faces, no before/after scoring.
- `web-specs.cjs` compares labels only: every run of digits is one number ("0 Khách mới" matches "12 Khách mới"), person names are one placeholder
  on both sides ("Hóa đơn của Nguyễn Minh Linh" matches "Hóa đơn của Nguyễn Thu Hà", "Hành trình của Linh" matches "… của Hà"), booking-card labels
  compare the same way, and a notice, an empty state or an action made of several pieces (title + text + bullets + button) matches when the layout
  holds the pieces in order. All 81 ids pass with no exemption. If a label of your screen still needs one, add `"demo_data": ["…"]` under your id in
  `design-specs/web/notes.json` and say why in the report.

## 3. Sample data (parts/base.js)

| Name | Content |
|---|---|
| `people` | 12 synthetic patients `{ id: 'P001', name, doctor, group, groupLabel, phone: '09•• ••• 100', age, init }`, same as the app canvas |
| `pt` | `people[0]` (Nguyễn Thu Hà, P001, BS. Tâm) |
| `doctors`, `rooms`, `services` | `{ name, spec }` ×4, `{ name, sub }` ×4, `{ name, price, mins, svc }` ×4 (`svc` 0-3 = booking colour) |
| `GROUPS` | care group labels (`d1 … birthday`) |
| `money(n)` | `'1.200.000 ₫'` |
| `UPDATE`, `RESPONSE` | sample patient update and clinic reply (app canvas) |
| `WEB` | `'Web › '`, the note prefix |
| `ACCOUNTS`, `NAV`, `PAGES`, `accountOf(id)` | the 8 demo accounts and the menu by role (old `staff-context.js`) |
| `P360_TABS`, `FIN_TABS` | the 8 Patient 360 tabs, the 4 finance tabs |
| `SVC_LEGEND` | the 4 service names with their colours, used by boards |

## 4. Screen helpers

`page(id, name, note, nav, blocks, o?)` is a page inside the app shell. `nav` is the menu key: `dashboard today schedule patients crm
followups studio resources services cashier finance ask guide`. `blocks` is an array (or several arguments nested in arrays; falsy
values are dropped). Options `o`: `role` (account id, default `'owner-tam'`; others `doctor-tam doctor-mai doctor-an doctor-lan
care-maianh care-thu accountant`: the sidebar shows the pages of that role; the bell is drawn for owner and doctors only), `state` (1440 only), `frames` (explicit list),
`toast` (bottom-right toast text), `drawer` (390 frame shows the open drawer), `crumb` (breadcrumb text when not the menu label),
`fin` (top-bar finance link text or `''`), `pickerOpen` (account list open), `skip` (the "Đến nội dung chính" link in focus),
`badge` (count on "Theo dõi"), `native` (a native browser dialog over the page, below).

`tab(id, name, note, tabIndex, blocks, o?)` is a Patient 360 tab: back link, patient card (avatar, name, meta line, chips, three
buttons) and the 8-tab bar are drawn for you, `blocks` go under the bar. `tabIndex` 0-7. `o`: `patient` (a `people` entry), `status`
(card eyebrow, default 'Đặt hẹn'), `chips` (array of `badge`), `actions` (array of `btn`), plus the `page` options.

`fin(id, name, note, tabIndex, blocks, o?)` is the finance page: eyebrow, title, period field with "Làm mới" and the tab bar are
drawn for you. `o`: `title` (default 'Tài chính & tiền thủ thuật'; doctor 'Doanh số của tôi'), `eyebrow`, `tabs` (array of tab labels,
default `FIN_TABS`), `role`, `state`.

`dlg(id, title, note, blocks, o?)` is a dialog or modal over the dimmed page, 1440 only; its × button has the accessible name "Đóng hộp thoại" (title and aria-label). `o`: `eyebrow` (small line over the title),
`sub`, `w` (panel width in px, default 640; 720 for forms, 1040 for the order dialog), `footer` (array of inline blocks, right-aligned
buttons), `nav` (which menu item is active on the page behind, default `dashboard`), `behind` (blocks drawn on the page behind),
`role`, `toast`, `native`.

`native(type, message, { value, options })` is the **native browser dialog** frame: pass it as the screen option `native` of `page`, `tab`, `fin` or `dlg` (with `state: true`
for page/tab/fin) and the dialog is drawn over the dimmed page with the exact text of the shots manifest (`native_dialog`) and the tag "NATIVE · confirm()". Types:
`confirm` (message + the browser's OK / Cancel), `prompt` (message + empty input, `value` shows typed text + OK / Cancel), `alert` (message + OK), `print` (the print dialog with a
sheet preview and Print / Cancel; no message exists), `download` (the download bubble at the top right; `message` = file name), `select` (the open option list of the account picker:
`options` = every option in order, the first is current). Examples: `page('WA5', 'Đặt lại dữ liệu demo (hộp xác nhận)', note, 'dashboard', [...], { state: true, native: native('confirm', 'Đặt lại dữ liệu demo?') })`;
`dlg('WG16', ..., { native: native('prompt', 'Lý do hủy lượt chưa thu tiền') })`. The page behind the dialog is the page the old shot shows. Native dialogs are annotations for the builder, not Next.js UI.
An **inline error line** (`errLine`, section 5) is how an error is drawn: put it last in the dialog body, as a state frame of the id that describes the error.

```js
const WB = [
  page('WB3', 'Hôm nay', WEB + 'today · …', 'today', [
    pageHead('Hôm nay', 'Lịch hẹn và việc cần làm', [primary('Đặt lịch', { icon: 'add' })]),
    kpis(kpi('Lịch hôm nay', '12'), kpi('Đang chờ', '3', 'Chờ bác sĩ')),
    panel('Danh sách', '', [], table(['Giờ', 'Khách hàng', ''], [['09:00', [lnk(people[0].name), sm(people[0].id)], [secondary('Check-in')]]]))
  ]),
  dlg('WB7', 'Đặt lịch hẹn', WEB + 'dialog · …', [grid(2, select('Bệnh nhân', people[0].name), date('Ngày', '2026-09-20'))],
    { eyebrow: 'Pema · vận hành', footer: [secondary('Hủy'), primary('Lưu')] })
];
```

## 5. Block table

Columns: block kind, the helper(s) that make it, the `src/ui` component it renders (file), the KMP `core:ui` analogue
(`design-specs/BLOCKS.md`), and the usage rules. "kit gap" = no component in `src/ui` yet; "shared" = exists outside `src/ui`
(`components/ops/ops-ui.tsx`, `components/admin/shared`) and sits next to the kit (`src/ui/README.md`).

| Block | Helper | Kit component | KMP analogue | Rules |
|---|---|---|---|---|
| `h` | `h h1 h2 h3 h4` | heading element (`PageHeading` for a page title; no component for h2-h4) | `PemaHeading`, `PemaSection` | h1 = page/hero title 25, h2 = 20, h3 = card title 16, h4 = 15. Optional sub line and eyebrow |
| `pageHead` | `pageHead(title, sub, actions, eyebrow)` | `PageHeading` (`workspace.tsx`) | `PemaHeading` | One per page, first block. Actions are inline blocks (buttons) |
| `hero` | `hero(title, sub, icon, { over, actions, rail: [done, total], small })` | kit gap (gradient hero) | `PemaHero` | Identity areas only, never behind tables or notes. Actions (e.g. the period badge) sit on the right, below the text at 390. `rail` draws the session rail (one segment per session, `done` lit) and `small` makes the icon a 24px corner mark: Patient Mobile home. Use `light(...)` for a button on it. **web-only use** (app uses it on home tabs) |
| `kpis` | `kpi(label, value, note, o)`, `kpis(...)` | `Tile` (`tile.tsx`) | `PemaMetrics`, `PemaTile` | Any count 1-6 in one row (390: 2 per row). Tile = label, value 27/700, note; `unit`, `icon`, `chev`, `tone`, `actions: [btn]` |
| `stat` | `stat(label, value, sub, { unit })` | kit gap (plain text label/value cell) | `PemaCardLine` | Small summary cell, e.g. "Liệu trình hiện tại / Buổi đã hoàn tất" in a `grid(3, ...)` |
| `chips` | `chips(items, { vert })` | `FilterChip` (shared, `ops-ui.tsx`) | `PemaChipWrap`, `PemaFilterChip` | Filter pills: `'Tất cả'` or `[label, 'sel'|'dis'|'', count]`. `vert` stacks them (group lists with counts) |
| `tags` | `tags(...badges)` | `Badge` (`badge.tsx`) in a row | `PemaPillButton` | Wrapping row of badges as one leaf (hero chips) |
| `tabs` | `tabs(items, activeIndex, { seg })` | `Tabs` (`tabs.tsx`) | none (app uses bottom nav) | Underline bar; `seg` = segmented control (Ngày / 7 ngày). Item `'label'` or `[label, count]`. 390: equal pills |
| `notice` | `notice(text, tone, { title, actions, items, itemsTitle })` | `Notice` (shared) | `PemaNotice` | tone `info warning danger success`; text verbatim; `title` = bold first line; `items` (+ bold `itemsTitle`, e.g. "Điểm cần nhớ") = bullet list; `actions: [btn]` for notices with buttons. The coverage check reads title, text, bullets and button labels in order as one old notice |
| `facts` | `facts([label, value, { sub }], ...)` | kit gap (`Facts`, label left / value right rows) | `PemaCardLine` | Key facts, dividers between rows |
| `field` | `field(label, o)` and `input select date time month number textarea check radio search file range` | `Field` (`field.tsx`) | `PemaTextField`, `PemaDropdownField`, `PemaSearchField`, `PemaCheckRow` | One field per old field, label verbatim. `o`: `req hint err ph lines opts open dis w`. `select(..., { open: true, opts })` shows the option list |
| `table` | `table(cols, rows, { foot })`, `cell(items, { row })` | `TableShell` (`table-shell.ts`, re-export) | none (cards `PemaCareRow` on mobile) | Up to 7 columns. At 390 every row becomes a card (first cell = title, others under their column label). Use a table for 3+ comparable rows, `list` or cards otherwise. `{ empty: 'Không có lịch phù hợp.' }` with `rows = []` draws the single empty row (old `<EmptyRow>`) |
| `empty` | `empty(title, hint, { icon, actions, flat })` | `EmptyState` (`empty-state.tsx`) | `PemaEmpty` | Say what is missing and the one action that fixes it. `flat` = no card chrome, centred grey text inside a card (Patient Mobile "Chưa có hóa đơn trong demo.") |
| `bars` | `bars([label, count, pct, tone], ...)` | kit gap | none | Dashboard "Lịch hẹn theo trạng thái"; `pct` 0-100, tone `success warning danger info` |
| `timeline` | `timeline({ date, title, detail, by, icon, tone }, ...)` | kit gap | `PemaTile` list (J8) | Patient journey / history. Dot icon + connector line |
| `list` | `list(items, { box, plain, ordered, sq })` | kit gap | `PemaTile`, `PemaCareRow` | Rows `{ t, sub, sub2, over, icon, avatar, chev, actions }`; `ordered` numbers them, `plain` = text lines (guide steps), `box` = bordered rows (wait cards, the journey photo shortcut). `sq` + `chev` = the Patient Mobile doc-row: rounded-square icon tile and a trailing "›"; money or a status goes in `actions` |
| `board` | `board({ rooms, from, to, hh, legend })` (alias `week`) | kit gap | `WeekStrip` (partial) | **web-only.** Rooms × time, bookings positioned by start/mins; `buf` (minutes) adds "· +15′ đệm" to the time line and a hatched "15′ chuẩn bị phòng" block; `slots` draw free time as dashed "Đặt lịch" buttons (label "Đặt lịch <phòng> <giờ>"). 390: one list per room |
| `weekGrid` | `weekGrid({ days, legend })` | kit gap | `WeekStrip` (partial) | **web-only.** 7 day columns of booking cards with "Đặt lịch" per day. 390: one list per day |
| `photos` | `photos(items, { n, sq })` (alias `photoGrid`) | kit gap | photo tile / `LocalPhoto` | Placeholders only, always with the tag "MINH HỌA TỔNG HỢP"; `{ empty: true }` for a missing photo, `{ slider: true }` for the slider compare; `sq` = square tiles with the tag at the bottom (Patient Mobile compare) |
| `a5` | `a5({ title, draft, rows, items, note, signDate, signRole, signName })` | kit gap (print sheet) | `A5PrintPreviewScreen` | **web-only.** Portrait paper (148 × 210), 2 per row in a `grid(2, ...)` |
| `img` | `img(label, { icon, h })` | kit gap | none | Neutral image placeholder |
| `legend` | `legend(items)` | kit gap | none | Service colour legend (boards add it themselves) |
| `sp` | `sp(h)` | none | `Spacer` | Vertical gap in px |
| `hr` | `hr()` | none | none | Divider |
| `code` | `code(text)` | none | none | Monospace block for raw text |
| `stack` | `stack({ g }, ...kids)` | none (plain flex column) | `Column` | Container. `g` gap px, default 12 |
| `row` | `row({ g, ai, jc }, ...kids)` | none (plain flex row, wraps) | `Row` | Container. `ai` align-items, `jc` justify-content (`'space-between'`, `'flex-end'`) |
| `grid` | `grid(cols, ...kids)`, `grid({ cols, colsn, g }, ...)`, `split(main, aside)` | `Workspace` (split / cards layout) or plain grid | none | Container. `cols`: number (equal columns), CSS template (`'minmax(0,1.65fr) minmax(300px,1fr)'`) ; `colsn` = template at 390 (default one column, two for 4+ equal columns) |
| `card` | `card({ title, sub, eyebrow, aside, v, tint, g }, ...kids)`, `panel(title, sub, aside, ...kids)` | `Card` (`card.tsx`) | `PemaInfoCard` | Container. `tint`: a tone (`info brand success warning danger`) or a service number 0-3 (0 none, 1 brand, 2 success, 3 warning, as the old service cards S0-S3); title and headings take the tone colour. `v`: `panel` (default) `soft` `ai` (pale brand, "Pema AI · bản nháp") `plain` `flush` `hero` (patient card). `aside` = inline blocks on the header's right |
| `box` | `box(tone, ...kids)`, `box({ tone, title }, ...kids)` | kit gap (rich notice container) | `PemaNotice` | Container. Callout with children (fields, badges, buttons), e.g. a notice that holds a slider |
| `disc` | `disc(summary, ...kids)` | kit gap (disclosure) | none | Container. The old `<details>` (finance "+ Ghi nhận lượt thủ thuật…"), drawn open |
| `txt` | `txt(text, o)`, `sm lbl strong eyebrow kv` | text element | `PemaText` | Inline. See helper reference |
| `btn` | `btn(text, variant, o)`, `primary secondary quiet danger lnk light back iconBtn` | `Button` (`button.tsx`) | `PemaPrimary`, `PemaOutlinedButton`, `PemaTextButton` | Inline. Variants `primary secondary danger dangers quiet link light`; `light` = pale button on a dark hero, `back('← Trang chủ')` = the Patient Mobile back link |
| `badge` | `badge(text, tone, { dot })` | `Badge` (`badge.tsx`) | `PemaPillButton` | Inline. Tones `neutral brand info success warning danger`; the text is always the status |
| `avatar` | `avatar(text, { size })` | kit gap (initials circle) | avatar in `PemaTile` | Inline. Sizes `sm md lg` |
| `icon` | `ico(name, { size, tone })` | icon (`icons.tsx`) | `PemaIcon` (Material) | Inline. Material Symbols Outlined name; a wrong name shows as text and `check` reports `badIcons` |
| `chip` | `chip(text, state, count)` | `FilterChip` (shared) | `PemaFilterChip` | Inline single pill; use `chips` for a group |
| `prog` | `prog(pct, { label, tone })` | kit gap | none | Inline progress bar |
| `appt` | `appt({ day, month, title, lines, none })` | web-only (kit gap) | `PemaTile` (K1 appointment tile) | Appointment card body: date tile ("20" / "THÁNG 09"), bold title, grey lines. `none: true` = no valid date, calendar icon and "Chọn lịch" in the tile. Put it in a `card` (home "Lịch hẹn tiếp theo", appointments "Sắp tới") |
| `events` | `events({ date, title, detail, kind, open }, ...)` | web-only (kit gap) | `PemaTile` list (J8) | Journey "Cập nhật gần đây" rows (old `<details>`): icon by `kind` (`followup photo done`), date, bold title, chevron. `open: true` expands that row and shows `detail`; a collapsed row hides its detail like the old page |
| `bubbles` | `bubbles({ text, time, mine }, ...)` | web-only (kit gap) | `PemaCardLine` (chat bubble) | Care-team messages, left; `mine: true` = the patient's message, right and tinted. Time line under the text |
| `upload` | `upload({ text, btn, file, status, preview })` | web-only (kit gap; `Field` type file is the nearest) | `PemaCheckRow` / photo tile | Send-update file chooser: dashed box, camera icon, hint, "Chọn ảnh" button, chosen file name, status "Đã chọn: … (đã giữ trong phiên demo)", synthetic preview placeholder with the "MINH HỌA TỔNG HỢP" tag when `preview` |
| `stepper` | `stepper(label, pct, caption)` | web-only (kit gap) | none | Journey progress: "2/5 buổi" + bar + caption "Tiến độ số buổi, không phải mức cải thiện da." Session count only, never a skin-improvement score |
| `quick` | `quick([icon, title, sub], ...)` | web-only (kit gap) | `PemaActions`, `PemaAction` | Quick-action tiles in one row (home "Việc hôm nay": Chăm sóc, Ảnh tiến trình, Gửi cập nhật) |
| `rx` | `rx({ title, count, empty, sections: [{ title, sub, lines | groups: [{ heading, lines }] }] })` | web-only (kit gap) | `PemaCareRow` + `PemaNotice` | The card "Đơn & phiếu đã duyệt" with the chip "<n> đơn" and one section per approved prescription or cashier order (groups "Đơn thuốc" / "Phiếu tư vấn"). No `sections` = pending/empty state: chip "Chưa có" and "Đơn và phiếu sẽ xuất hiện sau khi bác sĩ duyệt." A pending (unapproved) prescription is never listed |
| `errLine` | `errLine(text)` | `Field` error line (`field.tsx`, `err`); no component for the dialog-level line | `PemaTextField` error text | Inline error line (old `.ops-error`, `.crm-error`, `#review-error`, `<p role="alert">`): danger text with an error icon, no box. End of a dialog body or form, or under the tabs it belongs to. Use `notice(text, 'danger')` only when the old web draws a boxed notice |

Recipe names: `form` = `grid(2|3, field...)`; `cardGrid` = `grid(n, card...)`; `statusBars` = `bars`; `photoGrid` = `photos`;
`week` = `board`; `dd` = `select`; `m` = `kpis`; `fc` = `card`; `s` = `h3`; `t` = `list` row. `Sidebar`, `TopBar` and `AppShell` are
drawn by the screen helpers (kit: `sidebar.tsx`, `top-bar.tsx`, `app-shell.tsx`; KMP: `PemaBottomNav` role tabs); `Dialog`/`Sheet` by `dlg`
(kit `dialog.tsx`; KMP bottom sheet / alert dialog).

## 6. Helper reference

### Inline blocks
- `txt(text, { size, tone, w, up, cls })`: `text` is a string (`\n` = line break) or an array of parts, a part being `'plain'` or
  `['text', 'flags']` with flags `b x sm up soft danger success warning link heading`. `size`: `b`(14) `s`(13) `l`(12) `m`(11)
  `lg`(15) `sec`(16) `sub`(20) `ti`(25) `me`(27). `tone`: `ink soft heading link success warning danger info`. `w`: `m b x`.
  Example: `txt([['Họ tên:', 'b'], ' ' + pt.name])`.
- `sm(text)` small grey; `lbl(text)` 12px grey; `strong(text)`; `eyebrow(text)` small uppercase; `kv(label, value)` bold label + value.
- `btn(text, variant, { icon, ric, dis, sm, full, ico })`: `icon` leading and `ric` trailing Material name, `dis` disabled, `sm` 32px,
  `full` full width, `ico` icon-only. Shorthands `primary(text, o) secondary quiet danger lnk iconBtn(icon)`. `lnk` = text link
  (patient name in a table). Old web buttons: `btn` → `secondary`, `btn btn-primary` → `primary`, `btn btn-quiet` → `quiet`,
  `btn btn-danger` → `danger`.
- `badge(text, tone, { dot })`, `avatar('BT', { size })`, `ico('favorite', { size, tone })`, `chip(text, 'sel', 4)`, `prog(40, { label, tone })`.

### Leaf blocks
- `pageHead(title, sub, actions, eyebrow)`; `hero(title, sub, icon, { over, actions })`.
- `kpi(label, value, note, { tone, icon, unit, chev, actions, btn })` and `kpis(kpi, kpi, …)`. Old `metric-card`, `crm-kpi`, `ops-stat`.
- `stat(label, value, sub, { unit })`; `facts(['Mối quan tâm', 'Nám'], ['Bác sĩ', 'BS. Tâm', { sub }])`.
- `chips(['Tất cả', ['Quá hạn', 'sel', 4]], { vert })`; `tags(badge, badge)`; `tabs(['Tổng quan', ['Tư vấn', 2]], 0, { seg })`.
- `notice(text, 'info'|'warning'|'danger'|'success', { title, actions })`. Old `notice`/`alert-strip`/`draft-mark`/`photo-disclaimer`.
- `empty(title, hint, { icon, actions })`; `bars(['Đã xác nhận', 12, 60, 'success'])`; `legend()`.
- `timeline({ date: '13/9/2026 · Cập nhật tại nhà', title, detail, by, icon: 'chat_bubble', tone: 'success' })`.
- `list([{ t, sub, sub2, over, icon, avatar, actions: [btn] }], { box, plain, ordered })`; items may be plain strings.
- `img(label, { icon, h })`; `sp(h)`; `hr()`; `code(text)`.

### Fields
`field(label, { ty, val, ph, hint, err, req, lines, opts, open, on, dis, w, text })` is the base; shorthands (all
`(label, value, o)` unless noted): `input select date time month number textarea`, `check(label, on)`, `radio(label, options, selected)`,
`search(placeholder, { label })`, `file(label, text)`, `range(label, shownValue, pct)`. `val` empty + `ph` shows the placeholder.
`w` px is the width inside a `row` (a field without `w` keeps its content width; at 390 it is full width). `money(n)` writes a no-break space before "₫", so money never wraps there. Date values are ISO (`'2026-09-20'`), as the old inputs show them.
Example: `grid(2, select('Dịch vụ', 'Tái khám & đánh giá', { opts: services.map(s => s.name) }), time('Giờ', '08:00'))`.

### Table
`table(cols, rows, { foot })`: `cols` items are `'Label'` or `['Label', width, 'r']` where width is `'1.4fr'` or `'96px'` and `'r'` right-aligns
(money). A row is an array with one cell per column. A cell is a string (a `\n` starts small grey lines: `'Tái khám\n20/9/2026'`),
an array of inline blocks (stacked), or `cell([badge(...), btn(...)], { row: true })` (side by side). Example row:
`[[lnk(x.name), sm(x.id)], 'Sau thủ thuật D+1\n14/9/2026', 'CSKH Mai Anh', [primary('Xử lý →')]]`.
Draw the old web's columns, one sample row shape, and 3-5 rows (the old count goes in the note or `foot`, e.g. `foot: '48 hóa đơn · Trang 1/4'`).
Pagination buttons: a `row({ jc: 'space-between' }, txt('48 hóa đơn · Trang 1/4'), row(secondary('← Trước', { dis: true }), secondary('Sau →')))`
under the table.

### Schedule, photos, print
- `board({ rooms: [{ name, sub, bk: [{ start: '08:00', mins: 30, title, sub, sub2, svc: 0, buf: 15 }], slots: [{ start: '08:30', mins: 30 }] }], from: 8, to: 18, hh: 80, legend })`: a booking card has up to four lines (time, name `title`, service `sub`, doctor · status `sub2`; a card under 66px hides `sub2`); `rooms`
  default to `rooms` of the sample data; `svc` 0-3 picks the booking colour (service). A booking shorter than 56px shows one line.
- `weekGrid({ days: [{ title: 'CN, 20/09', sub: '31 lịch', add: 'Đặt lịch', items: [{ time, title, sub, svc }] }], legend })`.
- `photos([{ label: 'Trước buổi 1', meta: '23/07', empty, slider, tag }], { n })`: `n` columns.
- `a5({ title: 'ĐƠN THUỐC', draft: 'BẢN NHÁP — CHỜ BÁC SĨ DUYỆT', rows: [['Họ tên:', pt.name], ['Chẩn đoán:', '…', true]], items: [{ t, qty, use }], noteL, note, signDate, signRole, signName })`.

### Containers
- `stack({ g }, ...kids)`; `row({ g, ai, jc }, ...kids)`; `grid(cols, ...kids)`; `split(main[], aside[], { cols })` = 2 columns `1.65fr : 1fr`.
- `card({ title, sub, eyebrow, aside, v, g }, ...kids)`; `panel(title, sub, aside, ...kids)`; `box('warning', ...kids)`; `disc(summary, ...kids)`.
- Layout of the old web: page body `Workspace` split = `split(...)`; card grids `grid(3, card, card, card)`; `two-col-form` = `grid(2, field, field)`;
  `ops-toolbar` = `row({ g: 10, ai: 'flex-end' }, secondary('←', { ico: true }), date('Ngày', '2026-09-20', { w: 160 }), …)`.

## 6b. Patient Mobile frames (group WI)

`mob(id, name, note, active, blocks, o?)` is a Patient Mobile page (old `prototype/patient-mobile`, one script `shared/patient.js`) in one **390×844 phone frame**: no clinic sidebar or top bar,
instead the phone top bar (Pema logo, avatar button with the patient initials, accessible name "Mở hồ sơ demo của <tên>"), `blocks` as the content and the bottom navigation of
five tabs in the old order: Trang chủ (`home`), Lịch hẹn (`calendar_month`), Hành trình (`route`), Tin nhắn (`chat_bubble`), Hồ sơ (`person`). The frame is at least 844 tall and grows with the content
(the old page scrolls; the canvas shows everything), the navigation sits at its end. `active` is the lit tab, as the old web lights it: `'home' 'appointments' 'journey' 'messages' 'profile'`, and the
sub-screens light their parent: `'progress'`, `'care'`, `'send'` light Hành trình; `'docs'` lights Hồ sơ (so WI6, WI7, WI8 and WI9 do not light the tab their back button names). Options: `state: true` (inventory
kind state), `toast: 'Đã xác nhận lịch hẹn'` (the dark `mobile-toast` pill, role status, above the navigation; the frame keeps room under the content), `sheet: { title, sub, eyebrow, blocks, footer }` (bottom sheet over the dimmed
page, handle instead of ×), `native` (as above), `patient` (a `people` entry; default `pt`, initials "TH"). The old phone web has no native dialog (`confirm`, `prompt`, `alert`) and no composer on Tin nhắn (a button "Gửi tin nhắn" opens the send screen), and no privacy
switch (Quyền riêng tư is a row that toggles the consent and toasts), so there is no block for those: draw exactly what the spec lists.

Page skeleton (every WI page): `back('← Trang chủ')` (sub-screens only), `h1('Lịch hẹn')` or `mobTitle('Hôm nay của bạn', 'Chào Hà')`, then `card(...)` blocks, then a `notice` if the spec has one.
Cards are the old `mobile-card`: `card({ title, aside: [badge/quiet] }, ...)` with the chip or link of the card head in `aside`. Next-step card = `card({ title }, txt(...), primary(...))`.

| Old element | Draw it with |
|---|---|
| greeting + "Hôm nay của bạn" | `mobTitle('Hôm nay của bạn', 'Chào <tên cuối>')` |
| next-step card (D+1 … birthday, WI10-WI18) | `card({ title }, txt(sentence), primary('Gửi cập nhật'))` |
| journey hero with session rail | `hero(plan, 'Buổi 2 / 5 · Cập nhật 6/9/2026', 'route', { over: 'Hành trình đang tiếp diễn', small: true, rail: [2, 5], actions: [light('Xem hành trình →')] })` |
| appointment tile (home, Lịch hẹn) | `card({ title: 'Lịch hẹn tiếp theo', aside: [quiet('Xem tất cả')] }, appt({ day, month, lines }))`; no date: `appt({ none: true, lines })` |
| "Việc hôm nay" tiles | `card({ title: 'Việc hôm nay', aside: [badge('Pema đồng hành', 'brand', { dot: false })] }, quick([...], [...], [...]))` |
| doc-rows: invoices, booked and past appointments, guides, privacy rows | `list([...], { sq: true })` with `icon`, `t`, `sub`, `sub2`, `chev: true` or `actions: [strong(money(...))]` |
| journey summary | `stepper('2/5 buổi', 40, 'Tiến độ số buổi, không phải mức cải thiện da.')` under `txt`/`h2` and an eyebrow |
| journey photo shortcut | `list([{ icon: 'photo_library', t: 'Ảnh trước & sau', sub: '…', chev: true }], { box: true })` |
| "Cập nhật gần đây" | `card({ title, aside: [badge('4 mốc', 'neutral', { dot: false })] }, events(...), quiet('Xem thêm lịch sử'))` |
| photo compare | `photos([{ label: 'Trước' }, { label: 'Gần nhất' }], { n: 2, sq: true })` (placeholders with the tag, never faces) + `notice(...)` |
| care routine | `list([{ icon: 'auto_awesome', t, sub }], { sq: true })` under `eyebrow`, `h2`, `txt` |
| messages | `card({ title: 'Pema Care Team', aside: [badge('Đang hỗ trợ', 'success')] }, bubbles(...), primary('Gửi tin nhắn', { icon: 'add', full: true }))` |
| send update | `textarea`, `upload(...)`, `check('Tôi đồng ý …', on)`, `errLine`/toast text, `primary('Gửi cho Pema', { full: true })`, `notice` |
| profile | `row(avatar, stack(h3, txt))`, `notice`, `list` of three doc-rows, `select` ×2, `rx` |
| approved prescriptions | `rx(...)` (home, profile, docs) |
| empty text inside a card | `empty('Chưa có hóa đơn trong demo.', '', { flat: true })`; short lines (`Chưa có lịch đã đặt.`) are `sm(...)` |
| toast (WI23, WI28, WI29, WI31, WI33, WI34, WI38-WI40) | `mob(..., { state: true, toast: '<exact text>' })` |

Look: tokens only, card radius and shadow of the app, the phone top bar and nav drawn like the app's `PemaMainTopBar` / `PemaBottomNav` (pill behind the lit icon). Sample data is the canvas data (`pt`, `people`,
`doctors`, `services`, `money()`); dates and the Vietnamese texts stay as the old web has them.

## 7. 390 rules

Tables become cards, grids collapse to one column (4+ equal columns to two), `kpis` show two per row, the board and week grid become lists,
the sidebar becomes a top bar (menu, logo, bell, reset, account picker, search) plus a bottom tab bar (3 screens of the role and "Menu"),
dialogs stay 1440 only. Do not set pixel widths in a part for content that must fit 390; use `grid`, `row` and `w` only as a
preference.

## 8. Not in the canvas (by design)

Real photos, payments, auto-sent messages (every message is a draft needing approval), AI scoring of results. Business sentences stay
verbatim: "AI chỉ là bản nháp", completed treatment is never inferred from payment, messages are not an emergency channel,
illustrative photos do not score efficacy.

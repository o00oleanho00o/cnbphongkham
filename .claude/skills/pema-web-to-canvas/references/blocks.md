# Canvas blocks in `Pema App.dc.html`

Every screen is declared as data inside `class Component … build()` (the `<script type="text/x-dc">` tag). The HTML template above already knows how to render each block, so **new screens only need data added; do not edit the template**. Each block maps to a widget/helper in `flutter-template/lib/`, so any screen built from these blocks can be implemented in Flutter.

## Creating screens

| Helper | Use when | Notes |
|---|---|---|
| `home(id, name, note, role, navKey, tabIndex, blocks, o?)` | Main tab screen: `pema` logo, role switch button, bottom nav | `role`: `'Clinic' \| 'Bác sĩ' \| 'CSKH' \| 'Kế toán' \| 'Care'`; `navKey`: `owner \| staff \| care \| fin` |
| `det(id, title, note, blocks, o?)` | Child screen (`Detail(route)`): back button + title | Use for most screens moved from the web |
| `fin(id, name, note, tabIndex, blocks, o?)` | Finance screen (`FinanceScreen`) | Automatically adds the role row + reporting period |

`o` (optional) may include: `hasFab` + `fab: { label }` (icon is always `add`), `hasSnack` + `snack: { text, action }`, `hasSheet` + `sheet`, `hasDialog` + `dialog: { title, value }`, `title` (top bar title when different from `name`), `ts`/`tw` (title size/weight).

`note` appears under the screen name on the canvas. For screens sourced from the web, start with `WEB + '<route/tab/modal> · <what differs when moved to mobile>'` (`const WEB = 'Web › '`).

## Content blocks

| Helper | Renders | Flutter |
|---|---|---|
| `h(title, sub)` | 25/700 navy heading + subline | `heading()` |
| `h2(title, sub)` | 26/700 ink heading (CSKH) | `CareQueue` header |
| `s(title)` | 17/700 section title | `section()` |
| `hero(title, sub, icon)` | Navy→blue gradient block, large faded icon; `title` accepts `\n` | `hero()` |
| `m([value, label], …)` | Metric tiles; **maximum 3 tiles, short values** (≤ 5 characters, e.g. `11,3tr`) | `metric()` |
| `a([label, icon], …)` | Icon shortcut row (3 cells) | `action()` |
| `t(title, sub, icon, tap = true)` | Tile with avatar icon; `sub` accepts `\n`; `tap=false` removes chevron | `tile()` |
| `n(text)` | Notice with `#E8F4FB` background, navy text; accepts `\n` | `notice()` |
| `p(text, on = true)` | Primary 52px button; `on=false` is disabled | `primary()` / `FilledButton` |
| `outlined(text, icon)` | 48px outlined button | `OutlinedButton.icon` |
| `textBtn(text, icon)` | Text button | `TextButton.icon` |
| `input({ label, value, hint, prefix, lines })` | Input field; when `value` exists, the label floats to the border | `TextField` |
| `search(hint?)` | Search field with icon | `PatientSearch` |
| `dd(value, label?)` | 56px dropdown | `DropdownButtonFormField` |
| `dateBtn(text)` | Date picker button | `showDatePicker` trigger |
| `week()` | 7-day strip, T3 22 selected | `WeekStrip` |
| `chips([[label, state], …])` | Chip; state `'sel' \| '' \| 'dis'` | `ChoiceChip` |
| `check(label, on)` | Checkbox row | `CheckboxListTile` |
| `{ photos: true, items: [{ label }, …] }` | 2 illustrative photo boxes (`photos()` = Trước / Gần nhất) | placeholder image |
| `order(name, qty, route, usage)` | Order review row | order review row |
| `a5(kind, items, footer)` | A5 form preview | A5 preview |
| `txt(text, { s, c, w, ws })` | Free text block (size, color, weight, white-space) | `Text` |
| `sp(h)` | Vertical spacer of `h` px | `SizedBox` |
| `buckets(active)` / `careSearch(active)` / `chip(label)` / `listHead(title, count)` / `careRow(person)` / `empty(text)` | CSKH queue block set | `features/customer_care/presentation/widgets/care_queue.dart` |
| `finHero(over, value, sub?)` / `pill(text, icon?)` / `mcard(title, sub)` | Finance blocks | `finance.dart` |
| `fc(...items)` | Bordered card; inside use `ftitle(text)`, `fl(label, value)`, `txt(...)`, `fb(...labels)` (text buttons), `ff(label)` (filled button), `fi(text)` (money icon row), `sp(h)` | `Card` + `Row` |

## Sheet (bottom sheet)

`sheet` is a flat object; see the `accountSheet`, `groupSheet`, `paySheet`, `methodSheet` examples:

```js
{ pad: '0 20px 16px', align: 'stretch', title, ts: 22, tc: '#17324D', g1: 4, sub, ss: 14, sc: MUTED, g2: 12,
  rowPad: '0 8px', rs: 16, rows: [{ icon, is: 21, ic, text, tc, hasTrail: false, trail: '' }],
  hasNotice: true, notice: '…', hasPrimary: true, primary: 'Nút chính' }
```

A sheet only supports a row list + notice + one button. Forms with many input fields must become a `det(...)` screen.

## Limits to remember

- The 390×844 frame clips overflow (`overflow:hidden`), like the current scroll viewport. Keep the primary action within the first ~700px when possible.
- A new block type needs both an HTML template and a key in `KEYS` (or `CH` when inside `fc`). Add one only when no existing block can express the UI, and only when there is a corresponding Flutter widget.
- New group: add `{ code, title, sub, screens }` to `groups`, and add `"<code> · <name>"` to the `group` prop options in `data-props` (with `&quot;` escaped).
- Sample data uses `people`, `pt`, `GROUPS`, `money()` in the file (Nguyễn Thu Hà · P001 · BS. Tâm · 10:30 22/9/2026). Do not copy names/data from the web (the web uses a different patient set).
- Icon names are Material Symbols Outlined (e.g. `photo_camera`, `event`, `task_alt`, `edit_calendar`, `no_photography`). Wrong names render as text.
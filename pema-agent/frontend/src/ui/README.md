# src/ui: Pema design foundation

One token source and one small component kit for the staff web, shaped to be ported to the KMP app later.

## Tokens

- `tokens.css` is the source: a Tailwind v4 `@theme static` block (light values) and a `.dark` block (colour
  overrides only). Components use the names (`bg-surface`, `text-ink-soft`, `border-line`, `rounded-card`,
  `text-body`, `wide:grid-cols-4` ...), never hex values; `tokens.test.ts` fails on a hard-coded colour in the kit.
- `tokens.json` is generated from it: `pnpm tokens` (`pnpm tokens --check` fails when it is stale; the unit test
  does the same). `tokens.schema.json` is its JSON Schema.
- Groups: `color.light` / `color.dark` (overrides), `radius`, `shadow`, `text` (px), `space` (px), `layout` (px),
  `breakpoint` (rem), `z`, `font`. A name is the CSS variable without its group prefix:
  `--color-brand-500` is `color.light["brand-500"]`.
- KMP: read `tokens.json`, map `color.light` to the light `ColorScheme` and overlay `color.dark` for dark;
  `radius`/`text`/`space`/`layout` are logical pixels (dp/sp); `shadow` and `breakpoint` are web-only hints.
- Status colours come in triples (`success`, `success-soft`, `success-line`, same for `info`, `warning`, `danger`):
  text/icon, background, border. Always show the status as words too.
- Contrast of the text pairs is asserted in both modes (WCAG AA 4.5:1).

## Kit

`AppShell` (frame), `Sidebar`, `TopBar`, `Workspace` + `PageHeading`, `Card`, `Tile`, `TableShell` (re-export of the
dashboard table), `Tabs` (+ `segmentedOnPhone`: equal pills with `shortLabel` below `lg`, used by Patient 360) + `TabPanel`, `Badge`, `Button` + `buttonClass` (primary, secondary, danger, danger-solid,
quiet), `Field` + `FIELD_CONTROL_CLASS` / `FIELD_BASE_CLASS`, `Dialog`, `Sheet`, `EmptyState`,
`GuardedLink` (asks before leaving unsaved changes). Examples of all of them: `/dev/kit` (development only; a
production build answers 404). The data-bound shell that fills the slots is
`components/admin/layout/app-shell.tsx`.

## Menu

`lib/nav.tsx` holds the menu: the old Pema Clinic Web sections first, then "Zalo & CSKH", "Care agent" and
"Quản trị agent". An item with `planned: true` is an old screen whose page a later step builds; it shows greyed
and unclickable and the step removes the flag. `lib/nav.test.ts` checks every page is reachable.

## Restyle status (U1)

Every existing route sits on the kit through the shared pieces: `PageHeader` is `PageHeading`, `SectionCard` is
`Card`, the dashboard `Badge` maps its tones onto the kit `Badge`, `Notice`, `FilterChip`, `PrimaryButton` and
`SecondaryButton` use the status tokens and `Button`, the care sub-navigation uses the tab look. Colours are tokens
only (the Tailwind palette classes `red-*`, `amber-*`, `emerald-*`, `slate-*` and the `dark:` variants that went
with them are gone; the `.dark` block of tokens.css carries the dark values). Font sizes are the token scale
(`text-eyebrow` 10, `text-micro` 11, `text-label` 12, `text-small` 13, `text-body` 14, `text-body-lg` 15,
`text-section` 16, `text-subtitle` 20, `text-title` 25, `text-metric` 27, `text-page` 30).

`gc-card`, `gc-tile` and `gc-input` (globals.css) are compatibility aliases kept only for the pages ported from the
zalo-agent dashboard
(`components/admin/**`). They are marked for removal: a page rebuilt with the kit drops them, and the
last one to go deletes the block. Screens of this app (`components/ops`, the clinic routes) do not
use them.

# Pema Design System

One design source for the staff web (Next.js), the web canvases and the app (KMP `core:ui`). Status: source in the repo,
checked by `scripts/check.cjs`. Publishing to claude.ai/design is deferred (owner decision, 2026-10-05).

A reviewer should be able to answer colour, type, spacing and component for any frame from this folder alone.

## What is here

| File | What it holds |
|---|---|
| `tokens.json` | The single source of values: colours (light and dark), radius, shadow, type scale, spacing, layout, z, breakpoint, font. Validated by `tokens.schema.json` |
| `colors.md` | Colour roles: every token with light and dark value, role and where it is used; contrast table; web token vs app `PemaColors` |
| `typography.md` | Be Vietnam Pro, the eleven sizes with weight and line height, heading and title rules |
| `spacing-radius-elevation.md` | Spacing scale, radius, shadows, layout sizes, the three frame sizes, touch targets, stacking order |
| `components/<block>.md` | One page per block of `design-specs/web/BLOCKS.md` (64): anatomy, variants, states, tokens, do and don't, web and 390 notes, rules |
| `components/INDEX.md` | Mapping table block, page, `src/ui` component, kit status, KMP `core:ui` composable |
| `colors_and_type.css` | The tokens as CSS variables (same names as `src/ui/tokens.css`), light and `.dark` |
| `preview/*.html`, `_ds_manifest.json` | Swatch, type, spacing and component cards in the layout of the earlier `_ds` export |
| `scripts/` | `build.cjs` (writes everything generated), `check.cjs` (the test), `roles.cjs` and `component-data.cjs` (the curated text) |

All files except `README.md`, `tokens.json`, `tokens.schema.json` and `scripts/` are generated. Do not edit them: change the
source and run `node design-system/scripts/build.cjs`.

## How to answer "what does this frame use"

1. Open the frame's spec, `design-specs/web/screens/<ID>.md`, section "Layout": every block of the frame is listed with its kit component.
2. Open `components/<block>.md` for the block: tokens, variants, states, how it behaves at 1440, 1920 and 390.
3. Look the token up in `colors.md`, `typography.md` or `spacing-radius-elevation.md` (values, roles, light and dark).

Frames contain no colour, size or radius of their own: the canvas CSS uses token variables only (`check.cjs` enforces it).

## Where the sources come from

Order of priority, as used here: `pema-agent/frontend/src/ui/tokens.json` (U0) first, then `design-specs/web/BLOCKS.md`, then
`.agents/skills/design-system/references/*` and `.agents/skills/pema-design/references/visual-system.md`. The old web
(`prototype/shared/design.css`, "Pema identity pass") is the visual reference for every identity value.

## Change rule

Tokens change here first, then everywhere else, in this order:

1. Edit `design-system/tokens.json` (and `scripts/roles.cjs` when a token is added).
2. Mirror it in `pema-agent/frontend/src/ui/tokens.css`, run `pnpm tokens` there, so `src/ui/tokens.json` equals this file. `check.cjs` fails while the two differ. The web build reads the `src/ui` copy (`web-canvas-lib.cjs`, `token-map.cjs`), so the canvases follow it.
3. Rebuild the canvases: `node .claude/skills/pema-web-design/scripts/web-canvas-build.cjs` (and `--blocks`).
4. Port the change to KMP `core:ui` (`PemaColors.kt` and theme); the table at the end of `colors.md` shows where the app already differs.
5. `node design-system/scripts/build.cjs && node design-system/scripts/check.cjs`.

A new block goes to `references/blocks-web.md` of the skill (BLOCKS.md is generated from it); `check.cjs` then asks for its page in
`scripts/component-data.cjs`.

## Commands

```
node design-system/scripts/build.cjs           write the generated files
node design-system/scripts/build.cjs --check   fail when a generated file is stale
node design-system/scripts/check.cjs           the whole test (8 groups, see its header)
```

## Reconciled conflicts

Where the sources disagree, the rule of the recipe is "the old web wins, log the difference". The exception is `tokens.json`: U0 already
fixed it, the canvases, the kit and every shot use it, and the plan makes it the base (PLAN-AI01-W2 section 4, W11), so a difference
from the old web stays as shipped and is listed here for the owner.

| # | Topic | Sources | Decision |
|---|---|---|---|
| 1 | Muted ink | old web `--muted #5d7184` (also KMP `Muted`) vs token `ink-soft #5a6d80` | Token kept: U0 darkened it so it reaches 4.7:1 on a tile (the old value gave 4.4). Owner may revert in `tokens.css` |
| 2 | Danger | old web `--red #b84e55`, `.status-red` text `#a14736` on `#fbece8` vs token `danger #a13f46` on `#fbeceb`; KMP `Error #ba1a1a` (Material) | Token kept (close to the old status-red text, cooler in hue, 5.5:1 on its fill). App differs, see the last table of `colors.md` |
| 3 | Success, info, warning | old `.status-green/-blue/-yellow` (`#28745d`, `#426c8a`, `#8a6727` on `#e6f4ef`, `#eaf3f9`, `#fff5df`) | Equal to the tokens |
| 4 | Warning as brand variable | old `--yellow #ad7d2f` | No token: the status colour for warning is `#8a6727` (equal to `.status-yellow`) |
| 5 | Cream and mint | old `--cream #f2f7fb`; `--mint #e8f4fb` | `--mint` is `brand-50`; `--cream` has no token (nearest `row-hover #f2f8fc`) |
| 6 | Line | old `--line #d9e5ee` vs KMP `Line #e0eaf2` | Web value wins (`line`); the app follows when KMP reads `tokens.json` |
| 7 | Radius | old `--radius 14px`, plus 2, 6, 7, 8, 16 used ad hoc; app card 18 | Tokens 9, 10, 12, 14, 20, 24 and pill; ad hoc values collapse to the nearest token |
| 8 | Font weights | old web used 650, 750, 800 in places | Not adopted: 400, 500, 600, 700 |
| 9 | Icons | `visual-system.md`: web Lucide 20px/1.7; canvas draws Material Symbols Outlined; kit has its own SVG set (`icons.tsx`) | Canvas and app use Material names (`icon` block); the kit draws SVG from `icons.tsx`. Left as is, logged for U-work |
| 10 | Generic references | `.agents/skills/design-system/references/*` use generic values (blue-500, button 32/40/48, 150ms transitions, 2px ring offset) | Used for the list of states only (default, hover, focus, active, disabled, loading); values come from the kit and canvas CSS |
| 11 | Card title size | `BLOCKS.md` text "h3 = card title 16" vs card block 15 (`body-lg`) | Both are as drawn: `h3` 16, card title 15. Written in `typography.md` |
| 12 | Notice tones | kit `Notice`: `info warn error success`; canvas: `info warning danger success` | Kept; written in `components/notice.md` |
| 13 | Chip height at 390 | kit 44 (`min-h-11`), canvas 40 | Canvas value kept in the page, kit is the larger touch target |

## Dark mode findings

Contrast of two label pairs in dark mode is under 4.5:1 (computed, `colors.md`): label on the primary button (`surface` on `brand-500`, 3.81:1)
and on the sidebar count badge (`surface` on `accent-strong`, 3.44:1). Both are U-package decisions (the kit sets `text-surface`
on those fills); the canvases are drawn in light mode.

## The `_ds` export (`Pema App redesign canvas/_ds/novaestate-design-system-...`)

Inspected: it is the "NovaEstate" design system, a real-estate analytics dashboard (teal `#14B8A6`, pink primary button, Inter,
glass cards, WebGL lattice). It has no Pema source, no Pema colour, no Pema component, and nothing in the repo references it
(only `PLAN-AI01-W2.md` and this recipe name it; no canvas, viewer, skill, KMP or doc file does).

Decision: **retired. Deprecated, not reused.** The folder stays untouched (the app canvas folder is read-only for W2; delete it only
when the owner asks). Its **layout** is reused here so a later publish needs no restructuring: `README.md`, `colors_and_type.css`
(global CSS), `_ds_manifest.json` with `cards` grouped Colors, Type, Spacing, Components (`preview/*.html`, 700 px wide), `tokens`,
`fonts`. Not copied: its UI kit, WebGL lattice, logo and icon set.

## Canvas references

`Pema Web.dc.html`, `Pema Web (Next.js).dc.html` and `Pema Web blocks.dc.html` (built from `Pema Web redesign canvas/template.html`)
carry `<meta name="design_system" content="design-system/README.md">` and a line in the header text pointing to this folder.
The app canvas `Pema App.dc.html` is not touched in W2 (rule of the package); the same two lines are to be added on its next
sync (open item).

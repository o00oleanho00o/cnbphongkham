# NovaEstate Design System

**Version:** alpha · **Status:** internal preview

NovaEstate is an analytics dashboard for real-estate operators — portfolio
monitoring, deal pipeline, market intelligence, and team workflows. This
design system codifies the visual and interaction language of the
*NovaEstate Analytics Dashboard* surface so any future screen, slide, or
prototype can be assembled without re-deriving the rules.

The product favors **clear information density, modular panels, and
interface rhythm**. Cards stack on a calm light surface; teal acts as the
single accent that earns its place; glass treatments and a fine line
lattice give the chrome a quiet sense of depth.

---

## Sources

This system was produced from a single design brief (the alpha spec). No
codebase, Figma file, or supplemental brand assets were attached at the
time of authoring. If those exist elsewhere, please re-attach via the
**Import** menu so this system can be cross-checked and refined:

- **Figma:** _(none provided)_
- **GitHub / codebase:** _(none provided)_
- **Slide templates:** _(none provided)_
- **Brand kit / logo files:** _(none provided)_

Because the spec is the only source, the **logo, illustration style, and
photographic tone** are inferred. Treat those as placeholders — flag any
that don't match the real brand.

---

## Index

Files at the root of this project:

| File | What it is |
| --- | --- |
| `README.md` | This document — context, fundamentals, index |
| `SKILL.md` | Cross-compatible Agent Skill entry point |
| `colors_and_type.css` | All design tokens as CSS custom properties |
| `CROSS_PLATFORM.md` | Web ↔ React Native / Skia translation notes (WebGL → Skia, glass surfaces, iconography, motion) |
| `assets/` | Logo, icon library reference, sample imagery |
| `preview/` | Per-card HTML used by the Design System tab |
| `ui_kits/dashboard/` | The NovaEstate Dashboard UI kit (JSX components + demo) |

To get started, **read this file → load `colors_and_type.css` → open
`ui_kits/dashboard/index.html`** for the live component reference.

---

## Content Fundamentals

NovaEstate copy is **operator-direct**. The reader is a portfolio manager,
analyst, or principal who wants the number, not a story about the number.

- **Voice.** Confident, factual, lightly technical. Never hype. Never
  exclamatory. If a sentence could appear in a glossy real-estate ad,
  rewrite it.
- **Person.** Use *you* sparingly — most surfaces are third-person
  description of the data. Buttons can address the user directly
  ("Export report", "Compare assets").
- **Casing.** Sentence case for everything in product chrome — buttons,
  menu items, headers, section titles. Reserve Title Case for the
  product name *NovaEstate* and for proper nouns (city names, asset
  names, partner brands).
- **Numbers.** Always show units. Currency formatted with locale-aware
  separators and no trailing zeros below the dollar (`$2.4M`, `$847K`,
  `$1,284`). Percentages take one decimal when below 10, none above
  (`6.2%`, `42%`).
- **Density of language.** Short. A KPI label is two or three words —
  "Net operating income", "Occupancy rate", "Cap rate". Tooltips can
  extend to a sentence; descriptions to two.
- **Emoji.** Not used. Status is communicated with chips, color, and
  iconography from the Solar/linear set.
- **Tone examples.**
  - ✅ *"Cap rate is up 0.4 pp month over month."*
  - ❌ *"Great news — your cap rate is climbing! 🚀"*
  - ✅ *"4 assets need attention this week."*
  - ❌ *"Don't forget to check on a few things!"*

---

## Visual Foundations

### Material
The page reads as a **calm light surface with glass on top**. The
background is a near-white (`#FFFFFF`) sometimes layered with a fine
WebGL line-lattice that breathes slowly behind the chrome. Cards sit on
that base in three flavors:

1. **Solid card** — white, 1px `#F1F5F9` border, 24px radius, micro
   shadow (`0 1px 2px rgba(0,0,0,.05)`). The default surface.
2. **Glass card** — `rgba(255,255,255,0.8)` with 12px backdrop blur, no
   border, 23px radius. Used for hovering panels and overlays.
3. **Shelled card** — a solid card wrapped in a 1px gradient shell
   (`linear-gradient(to right bottom, rgba(255,255,255,0.4),
   rgba(255,255,255,0.1), transparent)`). Reserved for the hero / primary
   panel on a screen — never more than one per view.

Never mix two different shadow recipes on the same screen. Pick one of:
micro (`shadow-sm`), lifted (`shadow-md`, 20–25px ambient), or dramatic
(`shadow-lg`, 30–60px). The dramatic shadow is for floating dialogs only.

### Color vibe
**Cool, low-saturation, light-mode-only.** Teal (`#14B8A6`) is the
single emphasis color; pale blue (`#DBEAFE`) and pale lime (`#F4FCE3`)
are reserved for supporting accents like chart fills or status pills.
The spec'd primary button is a pink chip (`#FDF2F8`/`#DB2777`) — that
exception is honored for the *primary action*, but no other pink is
allowed in the system. Imagery, when used, should be daylight,
architectural, slightly desaturated; avoid warm sunsets and dramatic
black-and-white treatments.

### Layout
**Grid, full bleed.** Page chrome stretches edge-to-edge; content is
pulled inside via padding tokens. Base rhythm is `4px`. Acceptable
spacing increments: `1, 2, 4, 6, 8, 12, 16, 20`. Section padding steps
to `24 / 32 / 40`. Card padding to `9 / 16 / 20 / 24`. No values
outside these ladders.

### Typography
System font stack. Body copy is small and dense (`12 / 16`); labels
sit one step up (`16 / 24`); display headings are tight
(`-0.025em`, weight 600). Weight palette is restrained — `400`, `500`,
`600`. No 700/800 unless rendering a heavy display in a hero.

### Borders
Three line weights, all 1px: `#F1F5F9` (default chrome), `#E2E8F0`
(inputs), `#CBD5E1` (emphasis / focus). Never use thicker strokes — depth
comes from the gradient shell and shadow, not from line weight.

### Corner radii
Strictly: `6, 16, 24, 32, 9999`. The 9999 (pill) radius is reserved for
**buttons and chips only**. Cards do not use pills. Inputs use `16`.

### Hover & press
- **Hover** — text and color only. Links shift from `text-secondary` to
  `text-primary`. Button surfaces deepen one notch (e.g. pink chip
  `#FDF2F8` → `#FCE7F3`). Cards do not move or scale on hover; an
  optional 1px border-color step is permitted.
- **Press** — no scale animation. Background deepens one more notch.
- **Focus** — 3px primary-tinted halo (`rgba(20,184,166,0.15)`) plus
  border swapped to `--ne-primary`.

### Motion
Moderate. Two timing buckets: `150ms` for control feedback, `700ms`
(extending to `1000ms`) for content reveal and scroll-driven entrance.
Easing is `ease` or `cubic-bezier(0.4, 0, 0.2, 1)`. Fades and small
translates only — no bounces, no springs, no parallax beyond the WebGL
lattice's pointer drift.

### Transparency & blur
Glass surfaces use `rgba(255,255,255,0.8)` with `backdrop-filter:
blur(12px)`. The faint variant is `rgba(255,255,255,0.4)` with `4px`
blur — used inside chart legends and tooltips. Reserve blur for these
roles; do not blur background images for decoration.

### Backgrounds
The default page background is plain `#FFFFFF` or `#F8FAFC`. A
**WebGL line lattice** can be rendered behind the chrome on hero or
empty-state screens — fine gray lines, sparse anchors, slow breathing
pulse, subtle pointer drift. A DOM fallback (a stack of two CSS
gradients) is always included for browsers without WebGL.

### Iconography
Linear stroke, ~1.5px weight, square caps and joins, 24×24 viewbox.
The reference set is **Solar Linear**. See `ICONOGRAPHY.md` for
specifics.

---

## Iconography

NovaEstate uses **Solar Linear** as its icon system. Strokes are
~1.5px on a 24px grid, square joins, no fill, no two-tone variants.

- **Distribution.** Pulled from the Iconify CDN at runtime —
  `https://api.iconify.design/solar/<name>-linear.svg` — so no font or
  sprite needs to be bundled. The `<NeIcon name="..." />` component in
  the dashboard UI kit wraps this.
- **Fallback set.** If Solar Linear is unavailable, the nearest match is
  **Lucide** (`https://unpkg.com/lucide-static/icons/<name>.svg`). The
  two libraries share a stroke language so the swap is safe.
- **Sizing.** Default 20px in chrome (buttons, menu rows), 16px in
  dense table cells, 24px in feature placements (empty states, hero
  cards). Color inherits `currentColor`.
- **Emoji.** Not used.
- **Unicode characters as icons.** Avoid. Use the icon set.
- **Logo mark.** A standalone glyph at `assets/novaestate-logo.svg`
  (placeholder — flag if you have the real mark).

### Substitutions flagged
- **Solar Linear via CDN** is a substitution because no icon assets were
  attached. If the brand actually bundles an in-house set or a font, swap
  by replacing the `<NeIcon>` implementation.
- **Logo mark** is hand-built from the brand letters; swap when the real
  logo arrives.

---

## Cross-platform (web ↔ mobile)

This system is authored for the web but is **shared with React Native /
mobile**. Two rules to remember when porting:

1. **No DOM canvas. No ThreeJS in React Native.** The WebGL line lattice
   defined in the spec is translated to a **Skia-native paint** using
   `@shopify/react-native-skia` + `react-native-reanimated`. Do not ship a
   WebView-hosted lattice or a `react-native-canvas` shim.
2. **Token names are stable across platforms.** `--ne-primary` on web is
   `tokens.primary` in React Native; copy `colors_and_type.css` values
   straight across.

See `CROSS_PLATFORM.md` for the full mapping (WebGL → Skia parameters,
glass surface substitutions per OS, motion library equivalence, icon
sprite, hit-area adjustments).

---

## Font Substitution Notice

The spec specifies **"System Font"** for every type role. No webfont was
attached; the CSS stack falls through to `ui-sans-serif, system-ui,
-apple-system, "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif`.
If NovaEstate actually ships a custom face (Inter Tight, Söhne, etc.),
drop it into `fonts/` and update `--ne-font-sans`.

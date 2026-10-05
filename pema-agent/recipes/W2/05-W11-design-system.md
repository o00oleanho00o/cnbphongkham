# W11 — Design System source (one for web and app)

## Goal
A `design-system/` folder in the repo, the single design source for web and app, that both canvases reference: tokens, color roles, type scale, spacing, radius, shadows, components with variants and states, usage rules.

## Read first
1. `PLAN-AI01-W2.md` §2, §7 (the `_ds/novaestate-design-system-…` folder: inspect, decide reuse or retire, report).
2. Token sources in priority order: `pema-agent/frontend/src/ui/tokens.json` (if U0 exists) → `design-specs/web/BLOCKS.md`
   → `.agents/skills/design-system/references/{primitive,semantic,component}-tokens.md`, `component-specs.md`,
   `states-and-variants.md` → `.agents/skills/pema-design/references/visual-system.md`.
3. The structure of the existing `_ds` export (reuse its layout so a later publish needs no restructuring; say so).

## Ingredients
- `design-system/README.md` (how to use, where tokens come from, change rule: tokens change here first, then
  `src/ui/tokens.css` and KMP `core:ui`).
- `design-system/tokens.json` (single source), `colors.md` (roles: primary #0B4F94, navy #083A6E, sky #3CAAE5, ink,
  ink-soft, canvas, surface, line, tile, status colours), `typography.md` (Be Vietnam Pro scale), `spacing-radius-elevation.md`,
  `components/*.md` (one per block in `BLOCKS.md`: anatomy, variants, states, do/don't, web + mobile notes).
- A mapping table block → `src/ui` component → KMP `core:ui` composable (names only where KMP lacks it).

## Steps
1. Reconcile sources; where they disagree, the old web (`design.css`) wins and the difference is logged.
2. Write tokens.json and the markdown set; validate tokens.json against a small JSON schema (test script in the folder).
3. Add to both canvases a reference note (metadata or a first frame "Design System") pointing to `design-system/`.
4. Decide `_ds/novaestate-…`: reuse (rename, document) or retire (keep file, mark deprecated in README).

## Acceptance
- Every block in `BLOCKS.md` has a component page; every colour used by frames appears in `colors.md`; schema test passes.
- A reviewer can answer colour/type/spacing/component for any frame from this folder alone.

## Out of scope
- Publishing to claude.ai/design (deferred). Code changes.

## Report
Use `_REPORT-TEMPLATE.md`; list reconciled conflicts and the `_ds` decision.

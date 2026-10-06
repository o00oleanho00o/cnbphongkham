# W9 — Specs for the new ids

## Goal
One `design-specs/web/screens/<id>.md` per WJ/WK/WL id, generated like the old ones, with the Next.js route and the
agent/care context explained.

## Read first
1. `recipes/W/03-W2-web-specs.md`; `web-specs.cjs` and `web-specs-lib.cjs`; `notes.json` conventions.
2. For meaning: `pema-agent/docs/ARCH-AI01.md`, `PLAN-AI01-M.md` §5–§7 (control states, handoff, routing), zalo-agent
   admin concepts in `PORT-MAP.md`.

## Steps
1. Add `notes.json` entries for the new ids: purpose, roles allowed, key actions, links to related ids (e.g. WK handoff
   list ↔ WC Patient 360), `app_canvas: null` unless an app screen matches.
2. Run `web-specs.cjs`; review 5 random specs for wrong Vietnamese labels against the FE.
3. Regenerate `INDEX.md`; the `Next.js status` for these ids is `exists (design W2)`.

## Acceptance
- Spec count = inventory count; `web-coverage.cjs` shows inventory = specs.

## Out of scope
- Frames; FE changes.

## Report
Use `_REPORT-TEMPLATE.md`.

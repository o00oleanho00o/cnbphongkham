# W12 — Unify: cross-index app ↔ web, WI rows, canonical skill

## Goal
One place to navigate app and web designs, the Patient Mobile web rows settled, and one canonical sync skill.

## Read first
1. `PLAN-AI01-W2.md` §2 (decisions), §6.
2. `design-specs/INDEX.md` (app), `design-specs/web/INDEX.md`, `notes.json` (`app_canvas` cross-refs),
   `.claude/skills/pema-web-to-canvas/SKILL.md`, `.claude/skills/pema-web-design/SKILL.md`.

## Steps
1. Build `design-specs/INDEX.md` as the hub: sections App (82), Web (211 + W2 ids), Design System; a two-way table
   app id ↔ web id generated from `notes.json` (`app_canvas`) plus a reverse map; link to each spec.
2. WI rows: status `served by KMP/Zalo`, each with its app id or `—` and a one-line reason; add a "revisit when Zalo OA
   exists" note (owner decision 1).
3. Skills: name the canonical skill for "keep canvases in sync with the FE" (recommend `pema-web-design`, since the FE
   is now the product; `pema-web-to-canvas` becomes app-only or is marked legacy). Write the decision at the top of both
   SKILL.md files (additive note), do not delete scripts.

## Acceptance
- Hub index renders all three sections with working relative links; every WI row has a status and mapping.

## Out of scope
- Publishing to claude.ai/design (deferred). Deleting canvases or skills.

## Report
Use `_REPORT-TEMPLATE.md`.

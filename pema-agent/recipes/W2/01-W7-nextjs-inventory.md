# W7 — Inventory of Next.js-only screens (groups WJ, WK, WL)

## Goal
Freeze ids for every screen, state and dialog that exists in the Next.js FE but not in the old web, so W8–W10 can shoot,
spec and frame them.

## Read first
1. `PLAN-AI01-W2.md` §1, §3; `PLAN-AI01-W.md` §2 (id rules, D3), `recipes/W/01-W0-inventory.md` and
   `08-W6a-gap-audit-inventory.md` (how ids and states were found before).
2. `design-specs/web/inventory.json`, `INDEX.md` (which FE routes are already referenced: `/today`, `/patients`,
   `/patients/[id]`, `/inbox`, `/review`, `/dashboard`, `/schedule`, …).
3. FE: `pema-agent/frontend/src/app/**/page.tsx`, `src/components/{admin,care,ops}`, tests (`*.test.tsx`) and
   `FEATURE-INVENTORY.md` if U1 has produced it.

## Ingredients
- Group codes: `WJ` = agent admin (`/admin/*` except care), `WK` = care (`/admin/care/*`, `/care/*`),
  `WL` = CSKH/auth leftovers (`/templates`, `/login`, `/dev/kit` excluded).
- Kinds as in package W: `page`, `tab`, `dialog`, `modal`, `state`.
- `inventory.json` entries with the same fields as existing ones plus `nextjs_route`, `source: "nextjs"`.

## Steps
1. Enumerate routes from the file system; for each, read the page and its components to list states (empty, loading,
   error, permission-denied, per-role variants) and dialogs (create/edit/confirm). Use the tests as the list of
   behaviours; do not invent states that the code does not have.
2. Assign ids sequentially per group; one `page` id per route, then its `tab`/`dialog`/`state` ids.
3. Mark rows of group `WI` (Patient Mobile web) `nextjs_status: "served by KMP/Zalo"` with their `app_canvas` ids
   (owner decision 1) — data change only, no deletion.
4. Run `web-inventory.cjs --check`; fix until 0. Regenerate `INDEX.md` via `web-specs.cjs` if the script needs it.

## Acceptance
- Every FE route (except `/dev/kit`) appears in `inventory.json`; `--check` = 0; counts per group in the report.
- No existing id changed.

## Out of scope
- Shots, specs, frames. Any FE change.

## Report
Use `_REPORT-TEMPLATE.md`; include the per-group counts and the list of routes with zero states found.

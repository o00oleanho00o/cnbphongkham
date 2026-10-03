# U1 — Restyle every existing route with the kit, freeze the feature inventory

## Goal
All current FE routes use the U0 shell and kit and look like the old web, with **zero behaviour change**, proven by a
frozen `FEATURE-INVENTORY.md` and an unchanged-or-larger test count.

## Read first
1. `PLAN-AI01-U.md` §2 (principle 2), §3 last paragraph.
2. U0 report, `src/ui/` kit, `scripts/visual-check.ts`.
3. Every `src/app/**/page.tsx` and its components; existing tests (baseline vitest 407 at `0639903`).

## Ingredients
- `FEATURE-INVENTORY.md`: generated table — route · screen name · capabilities (one line each, e.g. "assign
  conversation", "accept handoff", "edit matrix cell") · test id(s) · owner step.
- `scripts/inventory-check.ts`: fails if a route listed is missing, or a listed test id no longer exists.
- Route smoke tests (Playwright, mock BE): each route renders, main heading present, primary action visible.

## Steps
1. Generate the inventory **before** touching styles (routes from the file system, capabilities from existing tests and
   a manual pass; be exhaustive, include admin routes and dialogs). Commit it; later steps only append.
2. Migrate pages route by route to `AppShell` + kit components; replace ad-hoc classes with kit/tokens; keep component
   props, data hooks and tests unchanged. Mobile (390×844): lists become cards/sheets as the old Patient Mobile did.
3. Keep `gc-*` compatibility classes only where a ported zalo-agent admin page depends on them; mark them for removal.
4. Run `pnpm visual`; fix overflow; compare `/today`, `/patients/[id]`, `/inbox`, `/review`, `/admin/overview` with
   the old counterparts where they exist.
5. Add route smoke tests; wire `pnpm inventory` and `pnpm visual` into `pnpm check`.

## Acceptance
- `FEATURE-INVENTORY.md` committed and `pnpm inventory` green; vitest count ≥ 407 (report the number).
- lint/tsc/build clean; `pnpm visual` 0 overflow across 5 viewports.
- No route path, API call, or permission check changed (diff of `src/lib/**` limited to styling helpers).

## Out of scope
- No new screens (U2–U7). No BE changes.

## Report
Use `_REPORT-TEMPLATE.md`; include the inventory row count and the vitest before/after numbers.

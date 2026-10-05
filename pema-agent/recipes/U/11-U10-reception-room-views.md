# U10 — Reception table on `/today`, room-column grid on `/schedule` (owner-approved 2026-10-05)

## Goal
Add the two old-web views the owner asked back: a reception table (Check-in, Vắng, Mời vào phòng) and a
room-column schedule grid, without removing the current CSKH task queue or doctor-column board.

## Read first
1. `pema-agent/docs/PARITY-AI01-U.md` §4 rows `today` (WB3), `schedule` (WB5) — both logged as "dev" (acceptable
   deviation) precisely because these two views were missing; this recipe removes that deviation.
2. `prototype/shared/operations-ui.js` (`edit()`, booking dialog, status buttons Xác nhận/Check-in), `operations-data.js`
   (`rooms`, `blocks`, `validate()` — room conflicts, room-block reason, 08:00–18:00 window), `docs/19_OPERATIONS_DEMO.md`.
3. Existing code: `pema/clinic/actions/appointments.py`, `pema/clinic/actions/dashboard.py`, `clinic.resource` model
   from U4 (rooms, doctors); FE `src/app/(admin)/today/page.tsx` (current CSKH queue — keep it), `src/app/(admin)/schedule/page.tsx`
   (current doctor-column board — the file's own comment names this exact gap: "columns are doctors … they come with
   the resources step"; U4 is merged, so build it now).

## Ingredients
- `/today`: add a reception section above or beside the CSKH queue (do not replace it) — a table of today's
  appointments with Check-in / Vắng / Mời vào phòng actions, reusing `appointments.set_status` (arrived, missed) from
  U2; a room/doctor column if space allows at 1920, hidden below 1280 (reuse the existing responsive pattern of the
  page).
- `/schedule`: a room-column view (toggle or tab next to the current doctor-column board, do not remove the doctor
  view) backed by `clinic.resource` rooms from U4; room blocks (reason, date, time range) as a thin read + one admin
  action `resources.block_room` (RBAC: owner/manager = `config` capability, matching the old `assert('config')`);
  conflict rule identical to `operations-data.js#validate` (room vs. appointment, room vs. block, 08:00–18:00 window).
- Both views emit the same CRM/appointment events the doctor-column board already emits — do not duplicate event
  emission.

## Steps
1. Confirm with `FEATURE-INVENTORY.md` that no reception table or room grid exists yet (expected: none).
2. BE: `resources.block_room` / `resources.list_blocks` actions if not already present from U4; extend
   `appointments.list_day` to include `room_id` if the schema has it (U4's `clinic.resource`), RBAC and audit.
3. FE: reception table component on `/today`; room-column grid component on `/schedule` behind a view switch
   (persist the choice per browser, not per account); mobile: both collapse to the existing card list.
4. `FEATURE-INVENTORY.md` rows; update `PARITY-AI01-U.md` §4 rows `today`/`schedule` from "dev" to "same".
5. Inventory + smoke + visual at 5 viewports; no horizontal overflow at 1920 with both the new table/grid and the
   existing queue/board visible.

## Acceptance
- `/today` keeps the CSKH queue and gains the reception table; `/schedule` keeps the doctor board and gains the room
  grid; room-conflict and block-window rules match the old web exactly (tests for each rejected case).
- Inventory green; vitest ≥ U9's count; visual 0 overflow.

## Out of scope
- Drag-to-move on the room grid (the old web did not have it either — confirm in `operations-ui.js` before building
  it; if absent, do not add it). Waitlist screen (separate, not asked for in this round).

## Report
Use `_REPORT-TEMPLATE.md`; include a note confirming the doctor board and the CSKH queue were not removed.

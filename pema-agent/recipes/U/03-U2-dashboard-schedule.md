# U2 — Dashboard (KPI) and Schedule (appointments, reception statuses)

## Goal
Port the old `dashboard` and `schedule` screens: clinic KPIs for the owner, and a day/week schedule with the
reception status flow, backed by real actions.

## Read first
1. `PLAN-AI01-U.md` §3 rows dashboard, schedule.
2. `prototype/shared/clinic.js` (dashboard section), `operations-ui.js`, `operations-data.js`,
   `docs/19_OPERATIONS_DEMO.md`, `docs/06_CLINIC_WORKFLOW.md`; `design-specs/screens/` for the schedule/today ids.
3. Existing `pema/clinic/actions/appointments.py`, `crm_tasks.py`, routers `appointments.py`, `crm.py`.

## Ingredients
- Actions: `dashboard.kpis(range)` (read model: visits, new/returning patients, follow-up completion, overdue,
  revenue only if U6 exists — otherwise omit, never fake), `appointments.list_day/week`, `appointments.set_status`
  (booked → confirmed → arrived → in_progress → completed; missed; cancelled with reason), conflict check server-side.
- Routers: extend `appointments.py`; new `dashboard.py`. Regenerate OpenAPI + FE types.
- Pages: `/dashboard`, `/schedule` (day view default, week view, filter by doctor/room), status chips identical to
  the old labels (Đặt hẹn, Đã xác nhận, Đang chờ, Đang điều trị, Hoàn tất).

## Steps
1. Read the prototype behaviour and write it down as a short spec in the PR description of the step (what each
   status transition does to Today/CRM, as `crm-automation.js` consumes `appointments`).
2. Implement actions with RBAC per `ARCH-PB01` matrix (reception edits schedule; doctor limited; care read).
3. Emit CRM events on status changes so B2 rules (no_show, due) keep working; test it.
4. Build pages with the kit; mobile shows a list per day.
5. Append rows to `FEATURE-INVENTORY.md`; add smoke tests.

## Acceptance
- BE tests: status transitions, conflict detection, RBAC denials, audit rows.
- FE: pages render with mock data at 5 viewports, no overflow; inventory green; vitest ≥ baseline.
- Dashboard shows no number it cannot compute from real data.

## Out of scope
- Resource (room/doctor) management (U4). Finance numbers (U6).

## Report
Use `_REPORT-TEMPLATE.md`.

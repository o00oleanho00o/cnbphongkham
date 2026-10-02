# M5 — Supervision and admin screens (Next.js)

## Goal
Staff supervise care agents instead of driving them: timeline per patient, pending handoffs with Accept/Decline, Return-to-agent with optional time-boxed level, "tell the agent", and admin screens for skills, shifts, on-call, thresholds, SLA, alerts.

## Read first
1. `PLAN-AI01-M.md` §12.
2. Package E conventions: app router layout, OpenAPI-generated types (`frontend/src/lib/api/schema.d.ts`), brand tokens (primary #0B4F94, navy #083A6E, sky #3CAAE5, Be Vietnam Pro), mobile-first for CSKH.
3. API endpoints exposed by M2b/M2c/M3/M4 (regenerate types from OpenAPI first).

## Ingredients
- Routes under `frontend/src/app/(ops)/care/`:
  - `patients/[id]/timeline` — agent actions, pending drafts, handoff reasons, paused reminders.
  - `handoffs` — "waiting for me": Accept / Decline (reason, suggest colleague), context summary.
  - `patients/[id]/release` — Return to agent: note + level (keep / lower for N days).
  - `patients/[id]/tell-agent` — free-text instruction saved to `care_memory` source `staff`.
- Admin under `frontend/src/app/(admin)/care/`: staff skills & shifts, on-call contacts, depth/autonomy matrix (shows `pending_doctor_approval` badge), SLA, send window, alerts (level demotions, unresponsive patients, red flags, on-call used).

## Steps
1. Regenerate API types; no hand-written DTOs.
2. Build screens with TanStack Query; forms validated with zod; Vietnamese UI copy.
3. Handoff list must update in near real time (SSE/WebSocket from BE if available, else polling ≤ 10 s).
4. Return-to-agent dialog: level options L0/L1/L2 + duration; preview the consequence text.
5. Admin matrix editor: cells editable, saved as `classifier_config`; approval badge toggled only by doctor/manager roles.
6. No business rule in the FE: every decision comes from BE responses.

## Acceptance
- `pnpm lint` and `pnpm build` pass; runs against a BE mock.
- Check 1920×1020, 1440×900, 1280×720, 1024×768, 390×844; no horizontal overflow; handoff list usable on phone.
- Role gating: CSKH cannot see the matrix editor; doctor can approve.

## Out of scope
- No porting of old Clinic Web screens beyond what is listed.
- No business logic or permission checks implemented client-side only.

## Report
Use `_REPORT-TEMPLATE.md`. Attach screenshot paths under `demo-assets/` if produced.

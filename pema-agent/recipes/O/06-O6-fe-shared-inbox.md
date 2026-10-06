# O6 — Frontend: shared inbox for many operators (agent: `pema-ui-builder`)

## Goal
Operators work every customer thread from Pema: queue, claim, takeover, release, lock indicator, identity filter,
roster, notification settings — matching the WM frames from O5 and keeping every existing Inbox feature.

## Read first
1. `PLAN-AI01-O.md` §3–§4; O5 report (WM ids); `AGENT.md` "Web design canvas" (mandatory steps).
2. Existing `src/app/(admin)/inbox/page.tsx`, `src/components/ops/inbox/*` (conversation list, thread view, presence
   line), `src/app/(admin)/admin/accounts/page.tsx`, `src/lib/live/*`, `src/ui/*` kit, `FEATURE-INVENTORY.md`
   (Inbox and accounts rows — none may disappear), `mock/handlers/*`.

## Ingredients
- Types from OpenAPI (`pnpm gen:types` first); no business rules in the FE (the BE decides lock, RBAC, limits).
- Inbox: identity filter, tabs "Chờ nhận / Của tôi / Tất cả", row shows identity, urgency, age, holder; thread view:
  Nhận / Tiếp quản (confirm + reason) / Trả lại (queue or agent); composer disabled with the lock text when someone
  else holds it; 409 `thread_locked` shown as the same banner; "đang xem" vs "đang trả lời" from presence.
- Live: `assignment.changed` and `inbox.changed`; a takeover shows a toast to the previous holder and refreshes.
- `/admin/accounts`: purpose, per-identity limits (fallback shown), internal notifier status; no credential field.
- `/admin/roster`: week view per identity, add/edit/delete slot (owner/manager), read-only for operators.
- `/me/notifications`: push token status (from the app later), Zalo bell link with the one-time code, quiet hours,
  test notification button.
- Mock BE handlers for every new endpoint (synthetic data); nav entries with role guards (accountant and reception
  do not see the shared inbox controls).

## Steps
1. For each WM id: spec + canvas image first; build; `pnpm visual`; compare with the frame; log every visible change
   in `web-design-changes.md`.
2. Tests: claim/takeover/release flows with the mock BE; lock rendering; 409 path; filter persistence; role guards.
3. `FEATURE-INVENTORY.md` rows for new routes and capabilities; `pnpm inventory`.

## Acceptance
- vitest ≥ the count at branch start; lint, check:types, build, smoke; `pnpm visual` 0 failures at 5 viewports;
  `pnpm inventory` green; `pending-web.cjs` no `✗ NOT LOGGED`; WM ids compared and named in the report.
- A two-browser run against the real stack (two operators) shows the takeover toast; record it in the report.

## Out of scope
- KMP UI; Facebook-specific UI (24-hour timer comes with package F).

## Report
Use `_REPORT-TEMPLATE.md`.

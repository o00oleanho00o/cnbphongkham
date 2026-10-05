# O5 — Frontend: shared inbox for many operators

## Goal
Operators work every customer thread from Pema: queue "Chờ nhận", claim, takeover, release, lock indicator, shift
board, channel-account filter, notification settings — in the package-U look.

## Read first
1. `PLAN-AI01-O.md` §3, §4, §8; O1–O4 APIs (regenerate OpenAPI types first).
2. Existing `/inbox`, `/review`, care screens; `pema/live` SSE client (`src/lib/live`); U0 kit if merged.

## Ingredients
- Inbox: filter by channel account ("Long", "Pema Q1", "Page"), tabs "Chờ nhận" / "Của tôi" / "Tất cả"; row shows
  channel, urgency, 24h-window timer (FB) or last message age, lock indicator with operator name.
- Thread view: Nhận / Tiếp quản (confirm + reason) / Trả lại cho agent (note + level); composer disabled with the
  lock message when someone else is active; agent suggestions pane (from M) read-only.
- Shift board (`/admin/ops/shifts`): who covers which account, now and next; channel accounts page
  (`/admin/ops/accounts`): status only, no credentials; notification settings (`/me/notifications`): push token
  status, quiet hours, Zalo fallback linked yes/no.
- Live: subscribe to `assignment.changed`, `inbox.changed`; takeover shows a toast to the previous operator.

## Steps
1. Types from OpenAPI; data hooks; no business rules in FE.
2. Screens with the kit; mobile-first for the queue and thread view (390×844).
3. Tests: claim/takeover/release flows with the mock BE; lock state rendering; filter persistence.
4. Append to `FEATURE-INVENTORY.md` (if U1 is merged) and run `pnpm inventory`, `pnpm visual`.

## Acceptance
- vitest ≥ baseline; lint/tsc/build; 5 viewports no overflow; inventory green; takeover toast verified in a two-browser
  run with the real stack (record it).

## Out of scope
- Facebook-specific UI beyond the timer placeholder (package F).

## Report
Use `_REPORT-TEMPLATE.md`.

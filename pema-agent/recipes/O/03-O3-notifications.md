# O3 — Notifications: KMP push primary, personal Zalo fallback, team-group broadcast

## Goal
Ring the right operator fast and PII-free: app push first, personal Zalo if not acknowledged, and a team-group post so
everyone sees who holds what; escalate through package M's chain when nobody acks.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 4), §3, §5 (`zalo_internal`), §8.
2. O2 `notification_outbox` / `Protocol Notifier`; package M `routing.advance` and SLA; C2 bridge send API
   (for `zalo_internal` account); `pema-kmp/` README for where a push token can be registered.

## Ingredients
- `ops/notify/service.py`: consumes outbox; per-event policy: `push` → wait `ack_timeout` (default 3 min, config) →
  `zalo_personal_fallback` → `team_group` broadcast always for claim/takeover/shift_end (short text).
- `kmp_push.py`: FCM (Android) / APNs (iOS) via a provider adapter; token registration endpoint
  `POST /api/v1/me/push-tokens` (operator's own device only); tokens stored hashed-at-rest where possible.
- `zalo_fallback.py`: sends through the `zalo_internal` channel account (bridge or Bot API) to the operator's personal
  Zalo id stored on `staff_profiles` (operator consents by messaging the internal bot once).
- `team_group.py`: posts "Hoàng nhận ca #1234 (Zalo Long, khẩn)" to the configured group id via `zalo_internal`.
- Ack: opening the deep link (authenticated) or `POST /notifications/{id}/ack` marks acknowledged and stops escalation.
- PII guard: a serializer that only allows customer code, channel, urgency, masked summary, deep link; unit-tested.

## Steps
1. Outbox consumer with retries and idempotency; delivery log per channel with status.
2. Push provider adapter with a fake in tests; KMP: minimal token-registration touchpoint (documented, no UI redesign).
3. Zalo fallback and team group via `zalo_internal`; refuse if the configured account is customer-facing.
4. Wire escalation: no ack within SLA → `routing.advance` (package M) to the next candidate; on-call stays last.
5. Admin settings: ack timeout, group id, enable/disable per channel; operator settings: quiet hours (fallback still
   rings for `critical`).

## Acceptance
- pytest: push then fallback after timeout; ack stops the chain; team-group always posted for claim/takeover/shift_end;
  PII guard blocks a payload containing a phone number; escalation reaches on-call when nobody acks.
- Manual: one real device receives a push with a deep link that opens the thread after login (record device/OS).

## Out of scope
- Rich push UI in KMP; SMS fallback.

## Report
Use `_REPORT-TEMPLATE.md`; include measured push latency.

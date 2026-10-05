# O3 — Notifications: in-app, personal Zalo bell, team group, push-ready; M's StaffNotify and SlaScheduler

## Goal
Ring the right operator fast and PII-free, escalate when nobody acknowledges, and give package M its first real
`StaffNotify` and `SlaScheduler` adapters.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 4), §2 rows M and pema-kmp, §4, §7 (defaults).
2. O2 outbox and `NotificationDelivery` seam; `pema/care/ports.py` (`StaffNotify`, `SlaScheduler`, `RoutingAdvance`,
   `HandoffNotice`, `OnCallInfo`); `pema/scheduler/*` (durable jobs, "never sent ⇒ never ran" rule);
   `pema/channels/zalo_personal/services.py`, `zalo_bot/*` (how to send one text through an account).

## Ingredients
- New package `pema/notify/`: `providers.py` (`InAppProvider` via `emit_live`; `ZaloBellProvider` sends through the
  `purpose = internal` account to `staff_profiles.notify_zalo_user_id`; `TeamGroupProvider` posts to the configured
  group id through the same internal account; `PushProvider` Protocol with `FakePushProvider` and a disabled
  `FcmApnsPushProvider` skeleton that refuses to start without credentials).
- Delivery chain per recipient (settings in `clinic.channel_setting.config` or a small settings row): in-app now →
  push if a token exists and the provider is enabled → bell after `ack_timeout` (default 180 s) → stop on ack.
  Team-group rows are posted once, no ack.
- `clinic.notification_log` (outbox id, provider, attempt, status, latency_ms, error code) and
  `clinic.push_token` (user, platform, token hash + encrypted token, last_seen); `POST/DELETE /api/v1/me/push-tokens`
  (own user only).
- Bell linking: `POST /api/v1/me/notify-zalo/link` starts a one-time code; the operator sends it to the internal
  account; the inbound handler of that account (purpose internal) stores `notify_zalo_user_id` + consent time. The
  internal account never answers customers and never creates a `clinic.conversation`.
- Ack: opening the deep link (authenticated) or `POST /api/v1/notifications/{id}/ack`.
- Escalation: no ack within the SLA → `RoutingAdvance` port (M) → next candidate; on-call last. `SlaScheduler`
  adapter schedules the check on `pema/scheduler`; `StaffNotify` adapter maps `notify_staff` / `notify_on_call` onto
  the outbox (on-call keeps M's own rule; the bell to the on-call number uses the internal account).
- Wiring in `pema/composition`; add `pema.notify` to the import-linter agent-side contract.

## Steps
1. Outbox consumer (worker) with idempotency and retries; log every attempt.
2. Providers with fakes; the internal account guard (refuse to send if `purpose` is not `internal`).
3. Link flow and push-token endpoints; settings (ack timeout, group id, per-provider on/off; operator quiet hours —
   `critical` still rings).
4. `StaffNotify` and `SlaScheduler` adapters + tests with M's fakes.
5. OpenAPI and FE types.

## Acceptance
- pytest: in-app immediately; bell after timeout only if not acked; ack stops the chain; group posted once for
  claim/takeover/shift_end; PII guard rejects a payload with a phone number or full name; internal account refuses a
  customer recipient; link code single-use and expiring; escalation reaches on-call when nobody acks (fakes);
  push path works with the fake provider; real push provider stays disabled without credentials.
- Report measured latency (fake providers) per step of the chain.

## Out of scope
- KMP client code (`pema-kmp` untouched; later step once FCM/APNs credentials exist). SMS. Wiring the care loop (M7).

## Report
Use `_REPORT-TEMPLATE.md`.

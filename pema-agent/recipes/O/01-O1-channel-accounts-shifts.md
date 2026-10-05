# O1 — Channel accounts and shift roster

## Goal
Model the clinic identities customers talk to (Zalo personal "Long", Zalo Bot/OA, Facebook Page, Instagram, plus an
internal notification account) and who covers each identity per shift.

## Read first
1. `PLAN-AI01-O.md` §1–§2, §4, §5.
2. `agent.accounts`, `agent.threads`, `agent.channel_policy` models and the zalo-agent multi-account runner
   (`pema/channels/*`, `PORT-MAP.md`); `clinic.staff_profiles` and shifts from package M.

## Ingredients
- Migration `o1_0010_channel_accounts.py`: extend `agent.accounts` (or a 1-1 table) with `kind`
  (`zalo_personal|zalo_bot|zalo_oa|fb_page|ig|zalo_internal`), `display_name`, `session_status`, `send_gap_ms`,
  `daily_proactive_cap`, `is_customer_facing` (false for `zalo_internal`); `clinic.shift_roster`
  (channel_account_id, operator_id, weekday/time range or explicit date, role).
- Actions (manager only): `channel_accounts.list/update_settings/set_status`, `shifts.*`;
  `channel_accounts.who_is_on(channel_account_id, now)` used by routing.
- Credential boundary: a test asserting no API response, log line or FE DTO contains tokens/cookies/QR payloads.

## Steps
1. Migration + models; seed one `zalo_personal` "Long", one `fb_page` placeholder, one `zalo_internal` (fixture).
2. Actions with RBAC (owner/manager write; others read status and roster only) and audit.
3. Routing hook: `routing.build_candidates` prefers operators on shift for the thread's channel account (additive to
   package M logic; keep on-call as last element unchanged).
4. Regenerate OpenAPI and FE types.

## Acceptance
- pytest: roster lookup by time; routing prefers on-shift operator; credential-boundary test; audit rows.
- `zalo_internal` can never be selected as a customer-facing sender (test).

## Out of scope
- Assignment/lock (O2), notifications (O3), sending (O4).

## Report
Use `_REPORT-TEMPLATE.md`.

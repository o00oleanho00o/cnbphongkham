# O1 — Identities, per-identity limits, thread ↔ identity link, roster

## Goal
Make the existing channel accounts usable as shared clinic identities: mark which ones face customers and which one
is the internal notifier, give each identity its own send limits, tie every conversation to the identity that
received it, and record who covers each identity when.

## Read first
1. `PLAN-AI01-O.md` §1–§3 (§2 is the inventory of what exists — extend, do not re-create).
2. `alembic/versions/0002_agent_schema.py` (`agent.accounts`, `agent.threads`), `0001_clinic_schema.py`
   (`clinic.channel_setting`, `clinic.channel_identity`, `clinic.conversation`), `pema/clinic/models/inbox.py`,
   `pema/care/models.py` (`StaffProfile`), `pema/api/routers/admin_accounts.py`, `admin_channels.py`.
3. `pema/channels/record_incoming_message.py` and the Zalo bot/personal inbound routers (where a conversation is
   found or created — that is where `account_id` gets set).
4. Package M routing: `pema/care/routing.py`, `ports.py` (`RoutingDirectory`). Call through the port; do not edit care.

## Ingredients
- Migration `o1_0010_identities_roster.py` (on the current single head):
  - `agent.accounts.purpose text NOT NULL DEFAULT 'customer' CHECK (purpose IN ('customer','internal'))`;
    `send_gap_min_s`, `send_gap_max_s`, `daily_cap` nullable overrides (NULL = use `clinic.channel_setting`).
  - `clinic.conversation.account_id text NULL` + FK `(clinic_id, account_id) → agent.accounts`; index; backfill
    only where `agent.threads` proves the pair (same `clinic_id`, `thread_id` = the conversation's external thread);
    leave the rest NULL and count them in the report.
  - `clinic.account_roster` (id, clinic_id, account_id, user_id, weekday set or explicit date, start/end time,
    note, created_by, timestamps); a user must hold an assignable role (validated in the action).
  - `clinic.staff_profiles.notify_zalo_user_id text NULL`, `notify_zalo_consented_at timestamptz NULL` (set only
    when the operator links the bell themselves in O3; this step only adds the columns).
- Actions (`pema/clinic/actions/identities.py`, `roster.py`): list identities with status (no credentials),
  `update_identity_settings` (purpose, label, overrides; owner/manager), `effective_limits(account_id)` (override or
  channel row), `roster.list/create/update/delete` (owner/manager write, operators read), `who_is_on(account_id, at)`.
- Inbound: every new conversation gets `account_id`; a conversation can never point to a `purpose = internal` account.
- Routing preference: an adapter for M's `RoutingDirectory` (in `pema/composition`) ranks rostered operators of the
  thread's identity first; on-call stays the last link, unchanged.
- Credential boundary: one test that serialises every admin/identity DTO and the OpenAPI examples and asserts no
  `*_enc`, cookie, token or QR field appears; one test on log capture during an identity update.

## Steps
1. Migration, models, backfill with a dry-run count first; downgrade tested to the named previous head.
2. Actions with RBAC (new permission codes `identity.manage`, `roster.manage`, `roster.read`) and audit rows.
3. Inbound hook sets `account_id`; test with the bot and personal pipelines' testing helpers.
4. Routing adapter + test with M's fakes: rostered operator first, others next, on-call last.
5. Routers, OpenAPI, `pnpm gen:types` (no UI in this step).

## Acceptance
- pytest: purpose CHECK; effective limits fall back to the channel row; roster lookup across midnight and by date;
  `who_is_on`; inbound sets `account_id`; internal account refused as a conversation's account; routing order;
  credential-boundary tests; audit rows; migration up/down/up.
- `alembic heads` = 1; lint-imports green.

## Out of scope
- Assignment and lock (O2), notifications (O3), sending (O4), any UI (O5/O6), Facebook kinds (package F).

## Report
Use `_REPORT-TEMPLATE.md`; give the backfill counts (set / left NULL).

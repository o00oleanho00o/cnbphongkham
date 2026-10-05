# O2 — Assignment history, claim, soft lock, takeover with dual notice, release, shift end

## Goal
Exactly one operator actively replies in a thread at a time; others can read; takeover is allowed and both operators
are told; release hands the thread back. Built on the existing `clinic.conversation.assigned_user_id`.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 3), §2 rows assignment/live/M, §4.
2. `pema/clinic/actions/conversations.py` (`update_conversation`, `send_message`), `assignees.py`,
   `CONTRACTS-AI01.md` "Assignable roles"; `pema/live/{presence,publisher,hub}.py`.
3. Package M: `pema/care/control.py` class `CareControl` (`accept(ctx, patient_id)`, `release_to_auto(...)` — keyed by
   **patient**, not by conversation), `pema/care/supervision.py`, `ports.py` (`ControlStore`, `HandoffRequester`).

## Ingredients
- Migration `o2_0010_assignment.py`: `clinic.conversation_assignment` (id, clinic_id, conversation_id, user_id,
  kind `claim|takeover|release|shift_end|assign`, previous_user_id, reason, at, by) — history only; the current holder
  stays `conversation.assigned_user_id`. Add `conversation.assignment_version int` for optimistic locking.
- Actions (`pema/clinic/actions/assignment.py`): `claim` (only if unassigned or holder released), `takeover`
  (reason required), `release` (back to queue, or to the agent when the conversation is in M's STAFF state: call
  `release_to_auto` through M's port), `assign` (owner/manager put someone on it), `end_shift(user)` (bulk: re-route
  each active thread via O1 `who_is_on`, else back to queue). Every change writes history, audit and an outbox row.
- Lock: `send_message` refuses (409, code `thread_locked`, message "<Tên> đang trả lời — Tiếp quản?") when the caller
  is not the holder; the existing "Phụ trách" update keeps working but goes through `assign`.
- Outbox: `clinic.notification_outbox` (id, clinic_id, kind, recipient_user_id or `team_group`, conversation_id,
  payload jsonb **PII-free**, created_at, state) and a `NotificationDelivery` Protocol seam (like `OutboundDelivery`);
  takeover and shift_end write two recipient rows (previous and new) plus one `team_group` row.
- Live: event `assignment.changed` (conversation, from, to, kind); presence returns the holder separately so the FE can
  show "đang trả lời" vs "đang xem".
- M bridge: a function that maps `CareControl.accept(ctx, patient_id)` to `claim` on that patient's open
  conversation(s) and M's release to `release`; when a patient has several open conversations, claim the one with the
  latest inbound message and say so in the report; tested with M's fakes; registering it in the live care loop is M7's job.

## Steps
1. Migration and models; downgrade to the named previous head.
2. Actions with RBAC (`thread.claim` for assignable roles; `thread.assign` and `thread.end_shift` for owner/manager)
   and audit; optimistic lock on `assignment_version`.
3. Lock check in `send_message`; regenerate OpenAPI and FE types.
4. Outbox seam (no delivery yet; O3 delivers).
5. Race tests: two claims at once → one wins, the other gets 409; takeover during a send → the in-flight send finishes,
   the next send of the old holder is refused; end_shift while a draft is open.

## Acceptance
- pytest: one holder per thread; history rows for every kind; takeover writes 3 outbox rows (old, new, group);
  payload serializer rejects a phone number or a name; 409 on send by a non-holder; release from STAFF calls M's port
  (fake); RBAC denials for accountant and reception; audit rows; migration up/down/up.

## Out of scope
- Delivering notifications (O3), per-identity queue (O4), UI (O5/O6).

## Report
Use `_REPORT-TEMPLATE.md`.

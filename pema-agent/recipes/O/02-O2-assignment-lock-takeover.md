# O2 — Thread assignment, soft lock, takeover with dual notice, release

## Goal
Exactly one operator actively handles a thread at a time; others can read; takeover is allowed and both operators are
informed; release returns the thread to the agent.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 3), §3, §4, §8.
2. Package M `care/control.py` (AUTO/HANDOFF_ROUTING/STAFF, `accept`, `release_to_auto`), `care/routing.py`;
   `pema/live/presence.py` (viewers TTL 30 s) and `hub.py`/`publisher.py` (SSE events).

## Ingredients
- Migration `o2_0010_thread_assignment.py`: `agent.thread_assignment` (thread_id, operator_id, state
  `assigned|active|released`, since, until, taken_over_from, reason), unique active per thread.
- Actions: `assignment.claim(thread)` (from queue or on `accept`), `assignment.takeover(thread, reason)`,
  `assignment.release(thread, note, override_level?)` → delegates to M `release_to_auto`,
  `assignment.handover_on_shift_end(operator)` (bulk reassign via routing when a shift ends).
- Soft lock: sending requires an active assignment by the sender; otherwise 409 with "Hà đang trả lời — Tiếp quản?".
- SSE events `assignment.changed` (thread, from, to, kind `claim|takeover|release|shift_end`).
- Dual notice: on takeover emit a notification job for BOTH operators (O3 consumes it); until O3 exists, write to a
  `notification_outbox` table via a `Protocol Notifier`.

## Steps
1. Models, migration, actions with audit; integrate `accept` from M so accepting a handoff creates the assignment.
2. Lock enforcement in the outbound path hook (O4 will own sending; expose `assignment.assert_can_send`).
3. Presence: show the active assignee as lock indicator; viewers remain informational.
4. Shift end: operators on a finished shift are released; their active threads re-routed; previous and new operators
   both get a notice; team-group broadcast entry queued.
5. Tests for races: two claims at once → one wins; takeover during send → the in-flight send completes, the next is
   blocked for the old operator.

## Acceptance
- pytest: unique active assignment; takeover notifies both (outbox has two rows); release → AUTO; shift-end
  re-route; 409 on send without assignment; audit rows.

## Out of scope
- Delivery of notifications (O3); actual sending (O4); FE (O5).

## Report
Use `_REPORT-TEMPLATE.md`.

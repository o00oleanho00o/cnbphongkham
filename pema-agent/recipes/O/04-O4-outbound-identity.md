# O4 — Outbound as the clinic identity: per-identity queue and limits, lock, no signature

## Goal
Every message to a customer leaves through the thread's identity, from the agent or any operator, with one queue,
one gap and one cap per identity, and a full record of who sent it.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 2), §2 rows outbound/limits.
2. `pema/clinic/actions/outbound.py` (`OutboundDelivery`, `deliver_queued_message`), `conversations.py`
   (`send_message`), `review_items.py` (approved review sends), `pema/api/dashboard_auth.py` (`get_delivery`), the
   channel send path (`pema/channels/deliver_chat_reply.py`, `send_reply_in_parts.py`,
   `zalo_personal/proactive_gate.py`), O1 `effective_limits`, O2 lock.

## Ingredients
- The delivery used by `send_message` and review approval resolves the conversation's `account_id` and sends through
  that account only; a conversation without `account_id` uses the channel's single customer account if there is
  exactly one, otherwise stays `queued` with error code `no_identity` (visible in the Inbox).
- Per-identity queue: a Redis lock + last-send timestamp per `account_id` so agent and all operators share one gap;
  daily cap counts proactive sends only (replies inside a customer-started exchange respect the gap, not the cap),
  using O1 `effective_limits`; kill switch of the channel still wins.
- `sender_type`/`sender_user_id` always set (`staff` + user, or `agent`); a test asserts no operator name or signature
  is appended to the text.
- Lock: the delivery re-checks the O2 holder at send time (a takeover between queue and send blocks the old holder's
  queued message with `thread_locked`).
- Internal account guard: a send to a customer through a `purpose = internal` account is impossible (test).
- Delivery status: store the adapter's `external_message_id` and set `status = sent`. Do not invent a `delivered`
  state: `zalo_personal/message_receipts.py` sends *our* read receipts to the customer, it does not report delivery
  of our messages, and no Zalo adapter reports delivery today.

## Steps
1. Implement inside the existing seam; keep `FakeOutboundDelivery` working for old tests.
2. Queue and limits with injected clock; tests without sleeping.
3. Wire in `pema/composition`; OpenAPI unchanged unless an error code is added (then regenerate types).

## Acceptance
- pytest: two operators and the agent on one identity respect one gap; separate identities do not block each other;
  cap counts proactive only; kill switch blocks all; non-holder refused at send time; `no_identity` path; no
  signature; internal account never used; `external_message_id` stored.

## Out of scope
- Facebook Send API (package F gets an adapter interface only if it fits naturally; do not build F).

## Report
Use `_REPORT-TEMPLATE.md`.

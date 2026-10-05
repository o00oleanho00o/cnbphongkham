# O4 — Outbound as the clinic identity: shared send queue, `sent_by`, caps per account

## Goal
Every message to a customer leaves through the thread's channel account ("Long", the Page), from the agent or any
operator, with one queue, one gap, one cap per identity, no signature, and a full audit of who sent it.

## Read first
1. `PLAN-AI01-O.md` §1 (decision 2), §4, §5, §6, §8.
2. C1/C2 adapters and the zalo-agent send queue (`proactive-send-queue` port, `send-reply-in-parts` port), package M
   caps, `clinic/actions/outbound.py`.

## Ingredients
- `ops/outbound.py`: `send(thread, text, sent_by: OperatorId|AgentId)` → `assignment.assert_can_send` (operators) →
  per-channel-account queue (gap, daily cap for proactive; replies to a customer's message counted separately) →
  adapter send → store `outbound_message` with `sent_by`, external message id, status.
- Signature policy: none (decision 2); a test asserts no operator name is appended.
- Message splitting and sanitising reuse the ported zalo-agent modules; Facebook adapter stub interface for package F.
- Echo reconciliation: inbound echo events (own messages seen by the channel) matched to `outbound_message` to confirm
  delivery.

## Steps
1. Implement the queue per account with Redis locks; agent and operators share it.
2. Route existing operator sends (`outbound.py`) and agent sends through `ops/outbound.send`.
3. Caps: proactive agent sends count against the daily cap; operator replies within an active customer conversation
   do not, but still respect the gap.
4. Audit: who, when, which account, which thread; the customer-visible sender is the account display name only.

## Acceptance
- pytest: two operators + agent sending to different threads on one account respect one gap; operator without active
  assignment is refused; `sent_by` recorded; no signature; echo reconciliation marks delivered.

## Out of scope
- Facebook sending itself (package F) — only the adapter interface.

## Report
Use `_REPORT-TEMPLATE.md`.

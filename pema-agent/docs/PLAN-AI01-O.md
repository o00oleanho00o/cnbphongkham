# PLAN-AI01-O — Package O: one identity, many operators (shared inbox over Zalo and Facebook)

Status: planned 2026-10-05, nothing built. Branch: `feat/ui-parity` (docs); code lands where the orchestrator merges
(single-tenant line). Recipes: `pema-agent/recipes/O/`. Depends on package M (routing, SLA, on-call, control state),
C1/C2 (Zalo adapters), live updates (`pema/live/*`). Package F (Facebook) will build on O.

## 1. Owner decisions (2026-10-05)

1. Customers talk to **clinic identities** ("Long" on Zalo, the Facebook Page). Staff **never** message customers from
   personal Zalo. Staff reply only inside the Pema app/web. Personal Zalo is a **notification bell**, nothing else.
2. Outgoing messages show **only the identity** ("Long"); no operator name or signature.
3. **Takeover is allowed**: another operator may take a thread that is being handled; both the previous and the new
   operator are notified (e.g. Vũ ends his shift, Hoàng takes over "Long"; both get the change notice).
4. Notifications: **KMP app push is primary**, personal Zalo is **fallback**, and a **Zalo team group** receives a
   broadcast so everyone knows who has what.
5. The 24/7 on-call Zalo number from package M **stays as it is** (end of every routing chain).

## 2. Concepts

| Term | Meaning | Owned by |
|---|---|---|
| **Channel account** | The identity customers see: Zalo personal "Long" (bridge zca-js), Zalo Bot/OA, Facebook Page, Instagram. Several per clinic allowed | Clinic (credentials in BE/bridge only) |
| **Operator** | A Pema user with role, skills, shift; replies through Pema only | Package M `staff_profiles` |
| **Thread** | One customer ↔ one channel account; independent of every other thread | `agent.threads` + `clinic.conversations` |
| **Assignment** | Which operator currently holds a thread (soft lock), with history | new |
| **Internal notification account** | A Zalo account/bot used only to ring operators and post to the team group; never talks to customers | new, type `zalo_internal` |

Hard rule: operators have **no access** to channel-account credentials (QR login done by a manager on the bridge host;
Page tokens encrypted in BE). Enforced technically, written into `AGENT.md`.

## 3. Flow

```
Customer → "Long" / Page → BE single pipeline (HarnessProcessor)
   AUTO ........ agent replies under its policy profile
   needs human . routing (M2c) picks an operator by skill/shift/load → ASSIGNED (soft lock)
                 notify: KMP push → (no ack in N min) personal Zalo → team group broadcast "Hoàng nhận ca #1234"
   operator opens deep link (login required) → thread in Pema → "Nhận" → replies → BE sends as "Long"/Page
   takeover ..... another operator "Tiếp quản": previous and new operator notified, team group updated, logged
   done ......... "Trả lại cho agent" (optional time-boxed lower level) → AUTO
```

Notification payloads carry **no PII**: customer code, channel, urgency, one-line masked summary, deep link.

## 4. What exists and what is added

| Exists | Added by O |
|---|---|
| `agent.accounts`, `agent.threads`, `agent.channel_policy` (zalo-agent port) | `channel_account` view/extension: kind (`zalo_personal`, `zalo_bot`, `zalo_oa`, `fb_page`, `ig`, `zalo_internal`), display name, session status, per-account send gap and daily caps, shift roster |
| `conversation_control` AUTO/HANDOFF_ROUTING/STAFF, routing, SLA, on-call | `thread_assignment` (thread, operator, state `assigned|active|released`, since, taken_over_from), soft lock, takeover with dual notification |
| `pema/live` presence (viewers, TTL 30 s, warning only) | presence upgraded to **lock indicator** ("Hà đang trả lời"); still non-blocking for reading |
| `staff_profiles`, shifts | shift roster **per channel account** (who covers "Long" this morning, who covers the Page) |
| audit on mutations | `outbound_message.sent_by` = operator_id or agent_id; identity shown to customer = channel account only |
| SSE `inbox.changed` | notification service: KMP push (FCM/APNs) → Zalo personal fallback via `zalo_internal` → team group broadcast; delivery/ack log; escalation on no-ack |
| C2 bridge send queue | send queue **per channel account** shared by all operators and the agent (gap + caps apply to the identity, not the person) |

## 5. Zalo specifics

- One bridge session per channel account; every operator's reply goes through it. Replies to inbound messages carry
  less risk than proactive sends; caps stay mainly for agent-initiated messages.
- Scale by adding channel accounts ("Pema Hà Nội", "Pema Q1") — still clinic identities. zalo-agent's multi-account
  runner already supports this.
- "Long" should be registered on a clinic SIM, not a person's; history lives in Pema, so the account can be replaced.
- `zalo_internal` must be a separate account/bot so customer-facing identities never post internal notices.

## 6. Facebook specifics (for package F)

Page = one pipeline, PSID = one thread. Operators reply via Send API inside Pema (model A); Handover Protocol only
if someone insists on Business Suite. 24-hour window and `HUMAN_AGENT` (after App Review) apply to operator replies.

## 7. Steps (one recipe each, `recipes/O/`)

| Step | Scope | Needs |
|---|---|---|
| **O1** Channel accounts & shifts | channel_account model over `agent.accounts`, kinds, roster per account, `zalo_internal` kind, admin actions | M1 |
| **O2** Assignment, lock, takeover | `thread_assignment`, claim, soft lock, takeover with dual notice, release; presence → lock indicator | M2b, O1 |
| **O3** Notifications | KMP push (FCM/APNs) primary, Zalo personal fallback, team group broadcast, ack + escalation, PII-free payloads | O2, C2 |
| **O4** Outbound as identity | per-account send queue shared by agent and operators, `sent_by`, no signature, caps/gap, audit | O1, C1/C2 |
| **O5** FE shared inbox | Inbox by channel account, queue "Chờ nhận", Nhận / Tiếp quản / Trả lại, lock indicator, shift board, notification settings | O2–O4, E/U1 |
| **O6** Eval & docs | load test (many threads, few operators), takeover race tests, notification latency, docs + AGENT.md rule | all |

Order: O1 → O2 → (O3 ‖ O4) → O5 → O6.

## 8. Acceptance

- No operator can send to a customer except through Pema; credentials absent from any staff-reachable place.
- Two operators acting on one thread never produce interleaved sends without a logged takeover; both get the notice.
- Notification chain KMP → Zalo → group works with acks; payloads contain no PII (test).
- Every outbound message has `sent_by`; the customer-visible sender is only the channel account.
- Caps and gaps apply per channel account regardless of how many operators are active.

## 9. Open items for the owner

Shift roster source (manual in Pema vs import); whether managers may silently monitor threads (read-only presence);
Zalo team group id and the `zalo_internal` account (clinic SIM); FCM/APNs project credentials for the KMP app.

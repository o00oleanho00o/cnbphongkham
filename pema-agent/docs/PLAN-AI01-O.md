# PLAN-AI01-O — Package O: one identity, many operators (shared inbox over Zalo; Facebook later)

Status: v2, rewritten 2026-10-06 against the code on `feat/ui-parity` `0d7bfda7` (packages M, U0–U12, W, W2 merged).
v1 (2026-10-05, branch `plan/package-o` `b2fecd6`) was parked before U9–U12 and assumed tables and wiring that do not
exist. Nothing of O is built. Branch: **`feat/shared-inbox`** (from `feat/ui-parity` `0d7bfda7`); merge back only when
the owner accepts the package. Recipes: `pema-agent/recipes/O/`.

## 1. Owner decisions (2026-10-05, unchanged)

1. Customers talk only to **clinic identities** ("Long" on Zalo; a Facebook Page later). Staff **never** message
   customers from personal Zalo; they reply only inside Pema. Personal Zalo is a **notification bell**, nothing else.
2. Outgoing messages show **only the identity**; no operator name or signature.
3. **Takeover is allowed**; the previous and the new operator are both notified.
4. Notifications: **KMP app push primary, personal Zalo fallback, Zalo team group broadcast** so everyone sees who
   holds what.
5. The 24/7 on-call Zalo number of package M **stays as it is** (last link of every routing chain).

## 2. What the code has today (checked 2026-10-06) and what that changes

| Fact in the code | Consequence for O |
|---|---|
| `agent.accounts` (PK `clinic_id,id` text; `channel` ∈ `zalo_bot, zalo_personal, zalo_oa`; `label`; `policy_profile`; credentials only as `bot_token_enc`, `credential_enc`, `webhook_secret_enc`); admin screen `/admin/accounts` with the channel switchboard | Channel accounts **exist**. O1 extends them; it does not create a new account model. No `fb_page`/`ig` kind until package F. |
| Send limits live in `clinic.channel_setting`, **one row per channel** (`daily_cap`, `min/max_gap_seconds`, window, kill switch) | Limits are per channel, not per identity. O1 adds per-account overrides that fall back to the channel row. |
| `clinic.conversation` has `channel`, `external_ref`, `assigned_user_id`, `status`, `unread_count` but **no account id**; `agent.threads` is keyed `(clinic_id, account_id, thread_id)` | A thread is not yet tied to the identity that received it. O1 adds `conversation.account_id` (nullable, backfilled where `agent.threads` proves it). |
| `assigned_user_id` + "Phụ trách" picker + `GET /staff/assignable` (`ASSIGNABLE_ROLES` = owner, manager, doctor, cs_staff; accountant and reception excluded) | Assignment **exists**. O2 adds history, claim/takeover/release and a send lock on top of it. Operators are exactly the assignable roles. |
| `clinic.message.sender_user_id` / `sender_type` on every message; outbound goes through the `OutboundDelivery` seam (`pema/clinic/actions/outbound.py`), wired in the API app | "Sent by" is **already recorded**. O4 makes the seam per account and enforces the lock and limits there. |
| `pema/live`: SSE `GET /api/v1/events`, `inbox.changed`, presence (viewers, TTL 30 s, warning only) | O2 adds `assignment.changed`; presence becomes the lock indicator. |
| Package M is **built but not wired** (HANDOFF "What is NOT wired"): `StaffNotify`, `SlaScheduler`, `ChannelSend`, `RoutingAdvance` … have no production adapter in `pema/composition` | O builds two of M's real adapters (`StaffNotify`, `SlaScheduler`) and the claim↔`accept` bridge, tested with M's fakes. Registering the whole care loop (LLM harness, depth, care event scheduling) stays **M7 wiring**, a separate package. Until M7, O works on the human inbox path that is live today. |
| `clinic.staff_profiles` (`skills`, `shift` jsonb, `capacity`); `clinic.on_call_contacts` (`zalo_number`) | Roster per identity is new (O1); the operator's personal Zalo id for the bell is a new consented field. On-call untouched. |
| `pema-kmp` has **no push code** (no FCM/APNs); it is read-only outside a recipe-named touchpoint | KMP push cannot be live in O. O3 builds the BE provider, token endpoint and a fake; the real chain today is **in-app → personal Zalo → team group**. The KMP client is a later step once the owner gives FCM/APNs credentials. |
| Import-linter: `pema.clinic.actions` never imports `pema.channels`/`pema.api`/`pema.agent`; agent-side packages reach the clinic only through actions; only `pema.composition` wires | Pattern of `OutboundDelivery`: state and rules in `pema/clinic/{models,actions}`, a `Protocol` seam there, channel/push senders outside, wiring in `pema/composition`. A new package `pema/notify` is added to the agent-side contract list. |
| FE rule (AGENT.md "Web design canvas", mandatory): UI work needs a screen id, spec and canvas frame first; `pema-ui-builder` does UI; every visible change is logged in `web-design-changes.md` | O gets a design step (screen ids, specs, frames in `Pema Web (Next.js).dc.html`) before the FE step. |
| Alembic: one head (`u9_0010_patient_parity` at `0d7bfda7`); migration tests downgrade to a named revision | O migrations `o<step>_<nnnn>_*.py` stack on the current single head. |
| 3 clock-dependent failures in `tests/care/test_care_routing_store.py` (owner declined the fix) | Expected baseline in every O gate; nobody "fixes" them inside O. |

## 3. Concepts

| Term | Meaning | Lives in |
|---|---|---|
| **Identity** (channel account) | What the customer sees: "Long" (`zalo_personal` via the bridge), a Zalo Bot, a Zalo OA. `purpose = customer` | `agent.accounts` + O1 columns |
| **Internal notifier** | A separate Zalo account/bot that rings operators and posts to the team group; `purpose = internal`; can never send to a customer | `agent.accounts` row with `purpose = internal` |
| **Operator** | A Pema user with an assignable role (owner, manager, doctor, cs_staff) | `clinic.user_account`, `clinic.staff_profiles` |
| **Thread** | One customer × one identity | `clinic.conversation` (+ `account_id`) |
| **Assignment** | Who holds a thread now (`assigned_user_id`) plus its history and lock | `clinic.conversation` + O2 history table |

Hard rule: operators have **no access** to identity credentials (QR login by a manager on the bridge host; tokens stay
encrypted). Enforced by tests (no DTO, response or log line carries `*_enc` fields, cookies or QR payloads) and written
into `AGENT.md` by O7.

## 4. Flow

```
Customer → identity ("Long") → existing inbound pipeline → clinic.conversation (account_id set)
  unassigned ...... queue "Chờ nhận" (account filter); roster says who covers "Long" now
  claim ........... operator presses "Nhận" (or M's accept, once M7 wires it) → assignment active (lock)
                    notify: in-app (SSE) → KMP push (when it exists) → personal Zalo via internal notifier (no ack in N min)
                    → team group "Hoàng nhận #1234 (Long)"
  reply ........... composer → send_message → lock check → per-identity queue (gap/cap) → OutboundDelivery → "Long"
  takeover ........ another operator "Tiếp quản" (reason) → both notified, group updated, history row
  shift end ....... active threads of a finished roster slot re-assigned (or back to queue); both sides notified
  release ......... "Trả lại cho agent" / back to queue; history row
  no ack .......... escalation: M's RoutingAdvance → next candidate → on-call number last (package M rule)
```

Notification payloads carry **no PII**: conversation short code, identity label, urgency, a masked one-line summary,
a deep link that needs login.

## 5. Steps (one recipe each)

| Step | Scope | Needs |
|---|---|---|
| **O1** Identities, limits, roster | `agent.accounts.purpose` (+ CHECK), per-account gap/cap overrides, `clinic.conversation.account_id` + backfill, `clinic.account_roster`, consented `notify_zalo_user_id` on staff profiles, `who_is_on`, routing preference hook, credential-boundary tests | — |
| **O2** Assignment, lock, takeover | history table, `claim/takeover/release/shift_end`, send lock in `send_message`, `assignment.changed` SSE, presence lock indicator, notification outbox + `NotificationDelivery` seam, bridge to M `accept`/`release_to_auto` | O1 |
| **O3** Notifications | outbox consumer, in-app + personal Zalo (internal notifier) + team group live; push provider adapter + token endpoint + fake (KMP client later); ack, escalation via M ports; real `StaffNotify` and `SlaScheduler` adapters | O2 |
| **O4** Outbound as identity | per-identity queue and limits in the delivery path, lock enforced, internal notifier never customer-facing, no signature, `sender_user_id`/`sender_type` always set, receipt reconciliation where the adapter reports it | O1, O2 |
| **O5** Design | screen ids (group WM), specs, frames in `Pema Web (Next.js).dc.html` for the changed Inbox and the new screens | O2 (API shapes) |
| **O6** FE shared inbox | Inbox filters/tabs/actions/lock, `/admin/accounts` extensions, roster screen, `/me/notifications`; inventory, visual, design log | O3, O4, O5 |
| **O7** Eval and docs | load and race suites, security scans, docs, `AGENT.md` rule | all |

Order: `O1 → O2 → (O3 ‖ O4 ‖ O5) → O6 → O7`.

## 6. Acceptance

- No operator can send to a customer except through Pema; no staff-reachable response, log or screen holds a credential.
- Two operators on one thread never interleave sends without a logged takeover; both get the notice.
- The live chain in-app → personal Zalo → team group works with acks; payloads are PII-free (test); push works against
  the fake provider and is ready for real credentials.
- Every outbound message has `sender_user_id` or `sender_type = agent`; the customer only ever sees the identity.
- Gap and cap apply per identity, whatever the number of operators.
- M's `StaffNotify`/`SlaScheduler` have production adapters with tests; the care loop itself is still M7.

## 7. Open items for the owner (defaults used until answered)

| Item | Default in the recipes |
|---|---|
| Roster source | Entered in Pema by owner/manager |
| Managers silently reading threads | Allowed read-only; presence shows "đang xem", not a lock |
| Zalo team group id; internal notifier account (clinic SIM) | Config fields; fixture in tests; the chain skips the step when unset and logs it |
| FCM/APNs credentials; KMP push client | Fake provider; real provider disabled; KMP step planned later |
| Ack timeout | 3 minutes (setting) |
| Facebook Page / Instagram | Out of O; package F adds the kinds and the Send API adapter |

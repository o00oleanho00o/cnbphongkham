# Shared inbox evaluation: package O, step O7

Generated 2026-10-06 04:32 UTC by `evals.ops.run_eval`. Python 3.12.0 on Windows; model: none; Postgres: throwaway database.

Command used:

```bash
cd pema-agent/backend
PYTHONPATH=.. PEMA_EVAL_OPS_DATABASE_URL=<throwaway postgres> uv run python -m evals.ops.run_eval
```

## 0. Read this first

Everything here runs without a model, without Zalo and without a push service. The queue and the chain are the real code with fake clock, channel and senders, so a number tells how the RULES behave under load, not how fast Zalo or FCM is. The numbers in sections 1-4 are printed by the run above; a part that could not run says "not run" and why. The scenario parameters (limits, arrivals, counts) are choices of this eval, not clinic settings.

## 1. One identity under load (the send queue of O4, virtual time)

Scenario: 200 threads on identity `long` arrive over 120 minutes; 5 operators reply 20-120 s after a thread arrives; the care agent sends 40 automatic replies and the scheduler 20 proactive reminders on the same identity; identity `long` has gap 15-45 s and a daily cap of 12 proactive messages; a second identity `hoa` (gap 5-15 s, no cap) carries 30 replies. Seed 20261006. The real `IdentitySendQueue`, a virtual clock: the seconds are what a customer would wait on a clinic with these limits, not wall time. These limits are the scenario's parameters, not clinic values.

### 1a. Requests in time order

| identity | gap s (min-max) | requested | left | refused: daily cap | refused: other | gaps under the minimum | queue wait s p50 / p95 / max | drain h |
|---|---|---:|---:|---:|---:|---:|---|---:|
| `long` | 15-45 | 260 | 252 | 8 | 0 | 0 of 251 | 369.3 / 688.0 / 741.5 (n=252) | 2.05 |
| `hoa` | 5-15 | 30 | 30 | 0 | 0 | 0 of 29 | 0.0 / 0.0 / 1.0 (n=30) | 1.95 |

Queue wait by sender on `long` (seconds, p50 / p95 / max):

| sender | wait s |
|---|---|
| agent | 338.7 / 688.2 / 704.7 (n=40) |
| operator-1 | 393.0 / 672.3 / 708.9 (n=40) |
| operator-2 | 382.6 / 685.7 / 704.2 (n=40) |
| operator-3 | 372.0 / 689.4 / 700.8 (n=40) |
| operator-4 | 373.5 / 670.7 / 706.3 (n=40) |
| operator-5 | 387.0 / 692.2 / 741.5 (n=40) |
| scheduler | 346.1 / 562.5 / 627.9 (n=12) |

### 1b. Burst: every request of `long` at the same instant, concurrently

| identity | gap s (min-max) | requested | left | refused: daily cap | refused: other | gaps under the minimum | queue wait s p50 / p95 / max | drain h |
|---|---|---:|---:|---:|---:|---:|---|---:|
| `long` | 15-45 | 260 | 252 | 8 | 0 | 0 of 251 | 3635.6 / 7032.5 / 7396.0 (n=252) | 2.05 |

Gap violations over all runs: **0**.

## 2. The notification chain (the consumer of O3, fake providers, timed)

Scenario: 5 operators with 40 notices each, 200 team-group notices, 20 on-call notices (420 outbox rows); push switched on (fake provider); ack timeout 180 s; 50% of the user notices acknowledged before the bell. Providers are fakes: **no real Zalo, push service or bridge was involved**, so the time a real provider adds on the network is NOT measured.

| provider | calls | code around the fake, real microseconds p50 / p95 / max | chain delay from due to call, virtual s (min - max) |
|---|---:|---|---|
| in_app | 200 | 0.9 / 1.2 / 21.2 (n=200) | 0 - 0 |
| push | 200 | 2.1 / 2.9 / 8.3 (n=200) | 0 - 0 |
| zalo_bell | 87 | 33.3 / 36.3 / 43.4 (n=87) | 180 - 180 |
| team_group | 200 | 33.2 / 36.7 / 66.2 (n=200) | 0 - 0 |

Outcome of the 420 rows: sent 420, skipped 0, failed 0, still pending 0.
Acknowledged before the bell: 113; the bell rang for **0** of them (must be 0). Not acknowledged: 87; the bell rang for 87 of them.
Texts that reached the internal sender: 307; carrying personal data by the PII mask: **0** (must be 0).

## 3. Escalation (package M's routing with the durable checks of O3)

Package M's own rig of fakes (the real `RoutingService` and `CareControl`) plus the real `DurableSlaScheduler` and `SlaCheckRunner` of O3 over an in-memory store; a virtual clock fires each check at its due time.

- Cases in which nobody accepts: 12; the 24/7 contact was notified in **12**; resolved by any means in 12.
- Cases in which the first candidate accepts: 9; accepted 9; the contact was notified in 0 of them (must be 0).
- Virtual minutes until the contact was notified (nobody accepts): 0.0 - 90.0.
- Model calls during all of it: 0 (must be 0).

| depth | urgency | staff | first accepts | outcome | staff told | on-call told | minutes to on-call |
|---|---|---:|---|---|---:|---:|---:|
| D2 | normal | 0 | no | exhausted_to_oncall | 0 | 1 | 0.0 |
| D2 | normal | 1 | no | exhausted_to_oncall | 1 | 1 | 30.0 |
| D2 | normal | 1 | yes | accepted | 1 | 0 | - |
| D2 | normal | 2 | no | exhausted_to_oncall | 2 | 1 | 60.0 |
| D2 | normal | 2 | yes | accepted | 1 | 0 | - |
| D2 | normal | 3 | no | exhausted_to_oncall | 3 | 1 | 90.0 |
| D2 | normal | 3 | yes | accepted | 1 | 0 | - |
| D4 | urgent | 0 | no | exhausted_to_oncall | 0 | 1 | 0.0 |
| D4 | urgent | 1 | no | exhausted_to_oncall | 1 | 1 | 5.0 |
| D4 | urgent | 1 | yes | accepted | 1 | 0 | - |
| D4 | urgent | 2 | no | exhausted_to_oncall | 2 | 1 | 10.0 |
| D4 | urgent | 2 | yes | accepted | 1 | 0 | - |
| D4 | urgent | 3 | no | exhausted_to_oncall | 3 | 1 | 15.1 |
| D4 | urgent | 3 | yes | accepted | 1 | 0 | - |
| D5 | critical | 0 | no | exhausted_to_oncall | 0 | 1 | 0.0 |
| D5 | critical | 1 | no | exhausted_to_oncall | 1 | 1 | 5.0 |
| D5 | critical | 1 | yes | accepted | 1 | 0 | - |
| D5 | critical | 2 | no | exhausted_to_oncall | 2 | 1 | 10.0 |
| D5 | critical | 2 | yes | accepted | 1 | 0 | - |
| D5 | critical | 3 | no | exhausted_to_oncall | 3 | 1 | 15.1 |
| D5 | critical | 3 | yes | accepted | 1 | 0 | - |

## 4. Claims and replies over a real Postgres (O2 and O4 actions)

200 threads, 5 operators racing on the same list in the same order, every 10th thread taken over after the first reply. Wall time on this machine; real database, no network, fake delivery.

- Claim attempts 1000: won 200, refused `thread_locked` 800, other errors 0.
- Takeovers 11; replies stored and sent 211; reached the fake channel 211.
- Wall time of the whole run: 4.2 s.
- Threads with exactly one holder at the end: 200 of 200.
- Outbox rows written: team group 211, user 22.

| step | milliseconds p50 / p95 / max |
|---|---|
| claim won | 17.3 / 23.5 / 75.6 (n=200) |
| claim refused (`thread_locked`) | 12.9 / 20.8 / 82.5 (n=800) |
| takeover | 19.4 / 23.4 / 23.6 (n=11) |
| reply (`send_message` through the fake delivery) | 29.4 / 37.2 / 46.6 (n=211) |

Invariants checked in SQL over every thread of the run (`evals/ops/invariants.py`): **0 violations**.

## 5. Test suites of this step

One run of `evals/ops` against a throwaway Postgres (`pgvector/pgvector:pg17 -c fsync=off`, started for this run and removed afterwards), after the last edit of the suites:

```bash
cd pema-agent/backend
PEMA_TEST_DATABASE_URL=<throwaway postgres> uv run pytest -c pyproject.toml --rootdir . ../evals/ops -v
```

Result: **92 passed, 1 xfailed, 0 failed, 0 skipped** in 19.6 s.

| file | passed | xfailed | what it holds |
|---|---:|---:|---|
| `test_ops_eval.py` | 11 | 0 | the load, chain and escalation invariants and the report (no database) |
| `test_ops_races.py` | 12 | 1 | the race suite over the real actions (database) |
| `test_ops_security.py` | 69 | 0 | credential boundary, PII guard over every notification kind, internal account, accountant and reception (65 without a database, 4 with one) |

The xfail is a **real defect found by the suite and left unfixed** (O7 may not edit the actions): the same send repeated with one `Idempotency-Key` while the first call is still in flight stores one message and hands it to the channel twice (run with `--runxfail`: `assert 2 == 1` on the deliveries). It is `strict`, so a fix makes the test XPASS and fail until the marker is removed. See SEC-64 in `docs/SECURITY-REVIEW-AI01.md`.

The suites were run more than once while they were written: the first runs with a database showed three failures that were mistakes of the suite (a doctor cannot see the thread of an unlinked customer, which is a 404, so the five operators were changed to owner, manager and three CS users; see SEC-63 a), fixed before the run above. The full backend suite was NOT run (owner instruction), and neither were the existing `tests/ops` suites.

Environment of this run: `docker ps` answered at once, so a throwaway `pgvector/pgvector:pg17` (`-c fsync=off`, port 32831) and a `redis:7` (port 32832) were started for it and removed afterwards; no suite of `evals/ops` uses Redis (the live events are fire-and-forget and the race suite does not read them). Section 5 is filled by hand from the real pytest output of that run; sections 1 to 4 are written by `evals.ops.run_eval` (run once against the same database, no failure).

## 6. Handoff: what still needs M7 and the KMP push client

What package O built and what it left open, in the words of the owner's questions. Nothing here was measured; it is the state of the code at the end of O7.

**Live today (the human inbox path):** identities with purpose and per-identity limits; roster; claim, takeover, release, assign, end of shift with history, lock and `thread_locked`; send through the identity queue (shared gap, proactive-only daily cap, kill switch, `no_identity`); the notification chain in-app, then the personal Zalo bell after the ack timeout, plus the team group and the on-call step; the front end of O6 (tabs, dialogs, roster, accounts, my notifications).

**Needs M7 (care loop wiring):**

- `StaffNotify` (`OutboxStaffNotify`) and `SlaScheduler` (`DurableSlaScheduler`, `SlaCheckRunner`) exist in `pema.notify` and are exposed on `NotifyStack`, but nothing registers them in the care loop. The runner starts only when M7 hands it `RoutingService.on_sla_expired`; until then the checks wait in `clinic.sla_check` and M's own `sweep_overdue` is the backstop.
- `RosterRoutingDirectory` (roster first in M's chain) and `CareAssignmentBridge` (M's `accept` as a claim, `release_to_auto` behind `to_agent`) are not registered either.
- The SLA checks live in `clinic.sla_check`, not on `pema.scheduler` (package S has no callback job kind). Decide whether they move onto package S later.
- Section 3 above shows the escalation chain reaching the 24/7 contact on M's fakes with the real durable checks; it is not a measurement of the wired system.

**Needs the KMP push client (and owner credentials):**

- Push is behind a fake provider. `FcmApnsPushProvider` is a disabled skeleton; there is no FCM/APNs credential and no push code in `pema-kmp`. The token endpoints exist (`POST` and `DELETE /me/push-tokens`) but there is no `GET`, so the push card of the notifications page cannot list devices.
- The live chain is in-app, personal Zalo bell, team group.

**Unverified or open:**

- Whether the Zalo bridge can `send_text` to a phone number is not verified. The on-call contact of package M is a phone number and goes through the internal account; the bell and the group go to Zalo ids and group ids. Try the on-call step once with the real bridge before relying on it (SEC-75).
- The per-identity daily cap of O4 is not merged with package S's own cap (SEC-76).
- Front end: the "Chờ nhận" tab and the identity filter work on the first 100 loaded rows, because `ConversationSummary` has no `account_id` and the list has no account or unassigned filter.
- A send repeated with one `Idempotency-Key` while the first call is in flight can reach the channel twice (SEC-64; strict xfail in `test_ops_races.py`).
- A doctor cannot see or claim the thread of an unlinked customer (SEC-77): decide whether doctors belong on the roster of an identity.

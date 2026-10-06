"""Render ``report.md`` of the ops eval. New module, no zalo-agent original.

Every number comes from a measurement object; a part that did not run is written "not run" with the reason, never
as a number. The unit of each table is in its header (virtual seconds, real microseconds, real milliseconds)."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime

from evals.care.stats import Latency
from evals.ops.measure_claims import ClaimsReport
from evals.ops.measure_escalation import EscalationOutcome
from evals.ops.measure_notify import NotifyReport
from evals.ops.measure_queue import IdentityResult, QueueReport, seconds_summary


@dataclass(frozen=True)
class OpsResults:
    queue: QueueReport
    notify: NotifyReport
    escalation: tuple[EscalationOutcome, ...]
    claims: ClaimsReport | None
    claims_reason: str
    tests_note: str
    command: str


def _f(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def _lat(latency: Latency, digits: int = 1) -> str:
    return (
        f"{_f(latency.p50, digits)} / {_f(latency.p95, digits)} / {_f(latency.max, digits)} (n={latency.n})"
    )


def _secs(values: list[float]) -> str:
    p50, p95, top = seconds_summary(values)
    return f"{_f(p50)} / {_f(p95)} / {_f(top)} (n={len(values)})"


def _identity_rows(results: tuple[IdentityResult, ...]) -> list[str]:
    lines = [
        "| identity | gap s (min-max) | requested | left | refused: daily cap | refused: other | gaps under the minimum | queue wait s p50 / p95 / max | drain h |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for r in results:
        lines.append(
            f"| `{r.account_id}` | {r.gap_min_s}-{r.gap_max_s} | {r.requested} | {r.sent} | {r.rejected_cap} | "
            f"{r.rejected_other} | {r.gap_violations} of {max(len(r.gaps), 0)} | {_secs(r.waits)} | {_f(r.drain_s / 3600, 2)} |"
        )
    return lines


def render_queue(report: QueueReport) -> list[str]:
    p = report.parameters
    out = [
        "## 1. One identity under load (the send queue of O4, virtual time)",
        "",
        f"Scenario: {p.threads} threads on identity `long` arrive over {p.window_s // 60} minutes; "
        f"{p.operators} operators reply 20-120 s after a thread arrives; the care agent sends {p.agent_replies} automatic replies and the "
        f"scheduler {p.reminders} proactive reminders on the same identity; identity `long` has gap {p.gap_min_s}-{p.gap_max_s} s and a daily "
        f"cap of {p.daily_cap} proactive messages; a second identity `hoa` (gap {p.other_gap_min_s}-{p.other_gap_max_s} s, no cap) carries "
        f"{p.other_identity_replies} replies. Seed {p.seed}. The real `IdentitySendQueue`, a virtual clock: the seconds are what a "
        "customer would wait on a clinic with these limits, not wall time. These limits are the scenario's parameters, not clinic values.",
        "",
        "### 1a. Requests in time order",
        "",
        *_identity_rows(report.timed),
        "",
        "Queue wait by sender on `long` (seconds, p50 / p95 / max):",
        "",
        "| sender | wait s |",
        "|---|---|",
        *(f"| {sender} | {_lat(latency)} |" for sender, latency in report.wait_by_sender.items()),
        "",
        "### 1b. Burst: every request of `long` at the same instant, concurrently",
        "",
        *_identity_rows((report.burst,)),
        "",
        f"Gap violations over all runs: **{report.violations}**.",
        "",
    ]
    return out


def render_notify(report: NotifyReport) -> list[str]:
    p = report.parameters
    out = [
        "## 2. The notification chain (the consumer of O3, fake providers, timed)",
        "",
        f"Scenario: {p.operators} operators with {p.notices_per_operator} notices each, {p.group_notices} team-group notices, {p.on_call_notices} "
        f"on-call notices ({report.notices} outbox rows); push switched on (fake provider); ack timeout 180 s; {int(p.ack_share * 100)}% of the user "
        f"notices acknowledged before the bell. Providers are fakes: **no real Zalo, push service or bridge was involved**, so the time a real "
        "provider adds on the network is NOT measured.",
        "",
        "| provider | calls | code around the fake, real microseconds p50 / p95 / max | chain delay from due to call, virtual s (min - max) |",
        "|---|---:|---|---|",
        *(
            f"| {t.provider.value} | {t.calls} | {_lat(t.real_us, 1)} | {_f(t.chain_delay_s[0], 0)} - {_f(t.chain_delay_s[1], 0)} |"
            for t in report.by_provider
        ),
        "",
        f"Outcome of the {report.notices} rows: sent {report.sent}, skipped {report.skipped}, failed {report.failed}, still pending {report.pending_at_end}.",
        f"Acknowledged before the bell: {report.acked_before_bell}; the bell rang for **{report.bell_rung_after_ack}** of them (must be 0). "
        f"Not acknowledged: {report.unacked_total}; the bell rang for {report.bell_rung_unacked} of them.",
        f"Texts that reached the internal sender: {report.texts_checked}; carrying personal data by the PII mask: **{report.texts_with_pii}** (must be 0).",
        "",
    ]
    return out


def render_escalation(rows: tuple[EscalationOutcome, ...]) -> list[str]:
    nobody = [r for r in rows if not r.case.first_accepts]
    accepted = [r for r in rows if r.case.first_accepts]
    reached = [r for r in nobody if r.reached_on_call]
    waits = [r.minutes_to_on_call for r in reached if r.minutes_to_on_call is not None]
    out = [
        "## 3. Escalation (package M's routing with the durable checks of O3)",
        "",
        "Package M's own rig of fakes (the real `RoutingService` and `CareControl`) plus the real `DurableSlaScheduler` and `SlaCheckRunner` of O3 "
        "over an in-memory store; a virtual clock fires each check at its due time.",
        "",
        f"- Cases in which nobody accepts: {len(nobody)}; the 24/7 contact was notified in **{len(reached)}**; resolved by any means in "
        f"{sum(1 for r in nobody if r.resolved)}.",
        f"- Cases in which the first candidate accepts: {len(accepted)}; accepted {sum(1 for r in accepted if r.accepted)}; "
        f"the contact was notified in {sum(1 for r in accepted if r.reached_on_call)} of them (must be 0).",
        f"- Virtual minutes until the contact was notified (nobody accepts): {_f(min(waits)) if waits else 'n/a'} - {_f(max(waits)) if waits else 'n/a'}.",
        f"- Model calls during all of it: {sum(r.model_calls for r in rows)} (must be 0).",
        "",
        "| depth | urgency | staff | first accepts | outcome | staff told | on-call told | minutes to on-call |",
        "|---|---|---:|---|---|---:|---:|---:|",
        *(
            f"| {r.case.depth.value} | {r.case.urgency.value} | {r.case.staff} | {'yes' if r.case.first_accepts else 'no'} | "
            f"{r.outcome} | {r.staff_notified} | {r.on_call_notified} | "
            f"{_f(r.minutes_to_on_call) if r.minutes_to_on_call is not None else '-'} |"
            for r in rows
        ),
        "",
    ]
    return out


def render_claims(report: ClaimsReport | None, reason: str) -> list[str]:
    head = ["## 4. Claims and replies over a real Postgres (O2 and O4 actions)", ""]
    if report is None:
        return [*head, f"**Not run.** {reason}", ""]
    p = report.parameters
    return [
        *head,
        f"{p.threads} threads, {report.operators} operators racing on the same list in the same order, every {p.takeover_every}th thread taken over "
        "after the first reply. Wall time on this machine; real database, no network, fake delivery.",
        "",
        f"- Claim attempts {report.claim_attempts}: won {report.claims_won}, refused `thread_locked` {report.claims_locked}, other errors {report.other_errors or 0}.",
        f"- Takeovers {report.takeovers}; replies stored and sent {report.sends}; reached the fake channel {report.delivered_to_channel}.",
        f"- Wall time of the whole run: {_f(report.wall_s)} s.",
        f"- Threads with exactly one holder at the end: {report.threads_with_one_holder} of {p.threads}.",
        f"- Outbox rows written: team group {report.outbox_group_rows}, user {report.outbox_user_rows}.",
        "",
        "| step | milliseconds p50 / p95 / max |",
        "|---|---|",
        f"| claim won | {_lat(report.claim_won)} |",
        f"| claim refused (`thread_locked`) | {_lat(report.claim_locked)} |",
        f"| takeover | {_lat(report.takeover)} |",
        f"| reply (`send_message` through the fake delivery) | {_lat(report.send)} |",
        "",
        f"Invariants checked in SQL over every thread of the run (`evals/ops/invariants.py`): **{len(report.violations)} violations**."
        + (
            ""
            if not report.violations
            else " " + "; ".join(f"{v.rule}: {v.detail}" for v in report.violations[:10])
        ),
        "",
    ]


HANDOFF = """## 6. Handoff: what still needs M7 and the KMP push client

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
"""


def render(results: OpsResults) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Shared inbox evaluation: package O, step O7",
        "",
        f"Generated {stamp} by `evals.ops.run_eval`. Python {platform.python_version()} on {platform.system()}; "
        f"model: none; Postgres: {'throwaway database' if results.claims else 'not used'}.",
        "",
        "Command used:",
        "",
        "```bash",
        results.command,
        "```",
        "",
        "## 0. Read this first",
        "",
        "Everything here runs without a model, without Zalo and without a push service. The queue and the chain are the real code with fake "
        "clock, channel and senders, so a number tells how the RULES behave under load, not how fast Zalo or FCM is. The numbers in sections 1-4 are "
        'printed by the run above; a part that could not run says "not run" and why. The scenario parameters (limits, arrivals, counts) are '
        "choices of this eval, not clinic settings.",
        "",
        *render_queue(results.queue),
        *render_notify(results.notify),
        *render_escalation(results.escalation),
        *render_claims(results.claims, results.claims_reason),
        "## 5. Test suites of this step",
        "",
        results.tests_note.strip() or "Not run.",
        "",
        HANDOFF,
    ]
    return "\n".join(lines)

"""Staff routing, the SLA and the chain that always ends at the on-call contact (step 4 of the recipe).

New module (not a port). The whole of package M is wired to in-memory fakes with a fake clock
(``pema.care.testing_routing.make_routing_rig``), nothing sleeps: a "decline" is a call of the staff API, an
"ignored" request is a clock jump to the SLA deadline followed by the call S would make
(``RoutingService.on_sla_expired``). Every scenario is checked against invariants written here from PLAN-M
section 7, not read from the code under test:

* the chain is 1..``max_candidates`` long and its LAST element is the on-call contact, exactly once;
* when nobody accepts, the on-call contact is asked exactly once and nobody is asked after it;
* the SLA of a candidate is ``notified_at`` + 5 minutes (urgent, critical) or + 30 (normal) inside clinic
  hours, and the start of the person's next shift outside them;
* outside hours a handoff of D3 or deeper goes straight to the on-call contact;
* routing needs no model: neither the reply model nor the depth model is called.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from pema.care.handoff_types import Depth, Urgency
from pema.care.routing_types import Candidate, CandidateKind, CandidateStatus
from pema.care.testing_routing import MONDAY_10, MONDAY_22, RoutingRig, make_routing_rig, staff_context

IN_HOURS = "in hours (Mon 10:00)"
OUT_OF_HOURS = "out of hours (Mon 22:00)"
MAX_STEPS = 12


class Behavior(StrEnum):
    DECLINE_ALL = "everybody declines"
    IGNORE_ALL = "everybody is silent"
    FIRST_ACCEPTS = "first accepts"


@dataclass(frozen=True)
class Scenario:
    staff: int
    depth: Depth
    clock: str
    behavior: Behavior
    owner: bool = False
    """The first staff member also owns the patient (the chain keeps an owner even off shift)."""

    @property
    def label(self) -> str:
        owner = " +owner" if self.owner else ""
        return f"staff={self.staff}{owner} {self.depth.value} {self.clock} {self.behavior.value}"


@dataclass
class ScenarioResult:
    scenario: Scenario
    chain_ok: bool = True
    ends_at_on_call: bool = False
    accepted: bool = False
    on_call_notified: int = 0
    asked_after_on_call: int = 0
    sla_ok: bool = True
    minutes_to_on_call: float | None = None
    first_kind: str = ""
    staff_asked: int = 0
    models_called: int = 0
    problems: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class RoutingReport:
    scenarios: int
    chain_ok: int
    ends_at_on_call: int
    expected_to_end_at_on_call: int
    on_call_exactly_once: int
    nobody_after_on_call: int
    sla_ok: int
    sla_checked: int
    no_model_calls: int
    accepted_ok: int
    accepted_expected: int
    direct_to_on_call_out_of_hours: int
    direct_expected: int
    time_to_on_call: list[tuple[str, str, int, float]]
    """``(clock, urgency, staff asked, minutes)`` for the silent-staff scenarios that reached the on-call."""
    problems: list[str]


def _urgency(depth: Depth) -> Urgency:
    return Urgency.URGENT if depth.rank >= Depth.D4.rank else Urgency.NORMAL


def _expected_minutes(urgency: Urgency) -> int:
    return 30 if urgency is Urgency.NORMAL else 5


def _current(rig: RoutingRig) -> Candidate:
    return rig.chain()[rig.request.current_idx]


def _staff_asked(rig: RoutingRig) -> int:
    return len(rig.notifier.staff)


async def run_scenario(scenario: Scenario) -> ScenarioResult:
    now = MONDAY_10 if scenario.clock == IN_HOURS else MONDAY_22
    rig = make_routing_rig(now=now)
    users: list[UUID] = []
    for index in range(scenario.staff):
        users.append(rig.directory.add_staff("doctor" if index % 3 == 0 else "cs_staff", load=index % 4))
    if scenario.owner and users:
        rig.directory.own(rig.agent.patient_id, cs_owner=users[0], doctor=users[0])
    urgency = _urgency(scenario.depth)
    await rig.open_round(scenario.depth, urgency)
    result = ScenarioResult(scenario)
    start = rig.clock.now
    chain = rig.chain()
    result.first_kind = chain[0].kind.value
    max_len = rig.routing_config.config.max_candidates

    if not 1 <= len(chain) <= max_len:
        result.chain_ok = False
        result.problems.append(f"{scenario.label}: chain length {len(chain)}")
    if (
        chain[-1].kind is not CandidateKind.ON_CALL
        or [c.kind for c in chain].count(CandidateKind.ON_CALL) != 1
    ):
        result.chain_ok = False
        result.problems.append(f"{scenario.label}: chain does not end in exactly one on-call entry")

    in_hours = scenario.clock == IN_HOURS
    for step in range(MAX_STEPS):
        candidate = _current(rig)
        if candidate.kind is CandidateKind.ON_CALL:
            break
        # SLA of this candidate
        due = candidate.sla_due_at
        if due is None or candidate.notified_at is None:
            result.sla_ok = False
            result.problems.append(f"{scenario.label}: candidate {step} has no SLA")
        elif in_hours:
            if due - candidate.notified_at != timedelta(minutes=_expected_minutes(urgency)):
                result.sla_ok = False
                result.problems.append(
                    f"{scenario.label}: SLA of candidate {step} is {due - candidate.notified_at}"
                )
        elif candidate.next_shift_at is not None and due != candidate.next_shift_at:
            result.sla_ok = False
            result.problems.append(
                f"{scenario.label}: out-of-hours SLA of candidate {step} is not the next shift"
            )
        assert candidate.user_id is not None  # noqa: S101  - a staff candidate always has a user
        if scenario.behavior is Behavior.FIRST_ACCEPTS:
            await rig.control.accept(staff_context(candidate.user_id), rig.agent.patient_id)
            result.accepted = True
            break
        if scenario.behavior is Behavior.DECLINE_ALL:
            await rig.control.decline(
                staff_context(candidate.user_id), rig.agent.patient_id, "dang ban", None
            )
        else:
            assert due is not None  # noqa: S101
            rig.clock.now = max(rig.clock.now, due)
            await rig.service.on_sla_expired(rig.request.id, rig.request.current_idx)

    final_chain = rig.chain()
    result.on_call_notified = len(rig.notifier.on_call)
    reached = _current(rig).kind is CandidateKind.ON_CALL and not result.accepted
    result.ends_at_on_call = reached and rig.request.outcome == "exhausted_to_oncall"
    if reached:
        asked_staff = [
            c
            for c in final_chain
            if c.kind is CandidateKind.STAFF and c.status is not CandidateStatus.PENDING
        ]
        result.asked_after_on_call = _staff_asked(rig) - len(asked_staff)
        result.minutes_to_on_call = (rig.clock.now - start).total_seconds() / 60
    result.staff_asked = _staff_asked(rig)
    result.models_called = rig.harness.calls + len(rig.llm.calls)
    return result


def scenarios() -> list[Scenario]:
    return [
        Scenario(staff, depth, clock, behavior, owner)
        for staff, depth, clock, behavior, owner in itertools.product(
            (0, 1, 2, 4, 7, 9),
            (Depth.D1, Depth.D2, Depth.D3, Depth.D4, Depth.D5),
            (IN_HOURS, OUT_OF_HOURS),
            tuple(Behavior),
            (False, True),
        )
        if staff > 0 or not owner
    ]


async def measure_routing() -> RoutingReport:
    results = [await run_scenario(s) for s in scenarios()]
    problems: list[str] = []
    for r in results:
        problems.extend(r.problems)

    expected_end = [r for r in results if r.scenario.behavior is not Behavior.FIRST_ACCEPTS]
    accept_expected = [
        r for r in results if r.scenario.behavior is Behavior.FIRST_ACCEPTS and r.first_kind == "staff"
    ]
    direct = [
        r for r in results if r.scenario.clock == OUT_OF_HOURS and r.scenario.depth.rank >= Depth.D3.rank
    ]
    silent_in_hours: dict[tuple[str, str, int], float] = {}
    for r in results:
        if r.scenario.behavior is Behavior.IGNORE_ALL and r.minutes_to_on_call is not None:
            key = (r.scenario.clock, _urgency(r.scenario.depth).value, r.staff_asked)
            silent_in_hours[key] = r.minutes_to_on_call
    table = sorted(
        (clock, urgency, asked, minutes) for (clock, urgency, asked), minutes in silent_in_hours.items()
    )

    for r in expected_end:
        if not r.ends_at_on_call:
            problems.append(f"{r.scenario.label}: did not end at the on-call contact")
        if r.on_call_notified != 1:
            problems.append(f"{r.scenario.label}: on-call notified {r.on_call_notified} times")
        if r.asked_after_on_call:
            problems.append(
                f"{r.scenario.label}: {r.asked_after_on_call} staff asked after the on-call contact"
            )
    for r in direct:
        if r.first_kind != "on_call":
            problems.append(f"{r.scenario.label}: not sent straight to the on-call contact")
    return RoutingReport(
        scenarios=len(results),
        chain_ok=sum(1 for r in results if r.chain_ok),
        ends_at_on_call=sum(1 for r in expected_end if r.ends_at_on_call),
        expected_to_end_at_on_call=len(expected_end),
        on_call_exactly_once=sum(1 for r in expected_end if r.on_call_notified == 1),
        nobody_after_on_call=sum(1 for r in expected_end if r.asked_after_on_call == 0),
        sla_ok=sum(1 for r in results if r.sla_ok),
        sla_checked=len(results),
        no_model_calls=sum(1 for r in results if r.models_called == 0),
        accepted_ok=sum(1 for r in accept_expected if r.accepted),
        accepted_expected=len(accept_expected),
        direct_to_on_call_out_of_hours=sum(1 for r in direct if r.first_kind == "on_call"),
        direct_expected=len(direct),
        time_to_on_call=table,
        problems=problems[:30],
    )

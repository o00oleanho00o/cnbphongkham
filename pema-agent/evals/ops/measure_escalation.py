"""Escalation: does a handoff nobody takes always reach the 24/7 contact? New module, no zalo-agent original.

The care side is package M's own rig of fakes (``pema.care.testing_routing.make_routing_rig``: the real
``RoutingService`` and ``CareControl`` over in-memory stores). The two adapters of package O3 are the real ones
over their in-memory stores: ``DurableSlaScheduler`` and ``SlaCheckRunner`` (the durable checks that move the
chain on when the current candidate does not answer in time). The runner fires each check at its due time on a
virtual clock, so a case that takes hours of waiting runs in milliseconds.

A case is: a depth and an urgency, a number of staff candidates (0 to 3) and what they do (nobody accepts, or the
first one does). Counted: the cases in which the 24/7 contact was notified (``exhausted_to_oncall``), in which a
person accepted, and in which neither happened (a defect), plus the virtual minutes it took to reach the contact.
No model is called anywhere (the rig's harness counts the calls and the eval checks the count stays 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import product

from pema.care.handoff_types import Depth, Urgency
from pema.care.testing_routing import RoutingRig, make_routing_rig, staff_context
from pema.notify.sla import DurableSlaScheduler, SlaCheckRunner
from pema.notify.testing import InMemorySlaStore

SKILLS = ("general", "medical")
"""Every synthetic staff member has both skills; D4 and D5 go to doctors only (package M's role rule), so those
cases use doctors and D2 uses CS staff. A chain with nobody qualified goes straight to the 24/7 contact."""
MAX_ROUNDS = 8
"""More rounds than any chain has links; a case that is still open after them did not escalate."""

CASES_DEPTH_URGENCY: tuple[tuple[Depth, Urgency], ...] = (
    (Depth.D2, Urgency.NORMAL),
    (Depth.D4, Urgency.URGENT),
    (Depth.D5, Urgency.CRITICAL),
)
STAFF_COUNTS = (0, 1, 2, 3)


@dataclass(frozen=True)
class EscalationCase:
    depth: Depth
    urgency: Urgency
    staff: int
    first_accepts: bool


@dataclass(frozen=True)
class EscalationOutcome:
    case: EscalationCase
    outcome: str | None
    staff_notified: int
    on_call_notified: int
    minutes_to_on_call: float | None
    model_calls: int

    @property
    def reached_on_call(self) -> bool:
        return self.on_call_notified > 0

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"

    @property
    def resolved(self) -> bool:
        """Somebody was told in the end: a person accepted or the 24/7 contact was notified."""
        return self.accepted or self.reached_on_call


async def run_case(case: EscalationCase) -> EscalationOutcome:
    rig: RoutingRig = make_routing_rig()
    role = "doctor" if case.depth.rank >= Depth.D4.rank else "cs_staff"  # D4 and D5 are for doctors only (M)
    for index in range(case.staff):
        rig.directory.add_staff(role, skills=SKILLS, load=index)
    started = rig.clock.now
    store = InMemorySlaStore()
    durable = DurableSlaScheduler(store)
    runner = SlaCheckRunner(store, rig.service, clock=rig.clock)
    await rig.open_round(case.depth, case.urgency)
    scheduled = 0
    minutes: float | None = (
        0.0 if rig.notifier.on_call else None
    )  # no staff at all: the contact is told at once
    if case.first_accepts and rig.notifier.staff:
        first = rig.notifier.staff[0][0]
        await rig.control.accept(staff_context(first), rig.agent.patient_id)
    for _ in range(MAX_ROUNDS):
        for check in rig.sla.checks[scheduled:]:
            await durable.schedule_check(check)
        scheduled = len(rig.sla.checks)
        pending = [row["due_at"] for row in store.rows.values() if row["state"] == "pending"]
        if not pending:
            break
        rig.clock.now = max(rig.clock.now, min(pending)) + timedelta(seconds=1)
        await runner.run_once()
        if rig.notifier.on_call and minutes is None:
            minutes = (rig.clock.now - started).total_seconds() / 60
    return EscalationOutcome(
        case,
        rig.request.outcome,
        len(rig.notifier.staff),
        len(rig.notifier.on_call),
        minutes,
        rig.harness.calls,
    )


async def measure_escalation() -> tuple[EscalationOutcome, ...]:
    cases = [
        EscalationCase(depth, urgency, staff, accepts)
        for (depth, urgency), staff, accepts in product(CASES_DEPTH_URGENCY, STAFF_COUNTS, (False, True))
        if not (accepts and staff == 0)
    ]
    return tuple([await run_case(case) for case in cases])

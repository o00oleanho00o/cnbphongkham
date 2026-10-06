"""``SlaScheduler`` and ``StaffNotify`` of package M on the notification outbox (package O, step O3).

New tests (no zalo-agent original). The care side is M's own rig of fakes (``make_routing_rig``); the SLA
adapter and its runner are the real ones over ``InMemorySlaStore``. Covered: M's checks are stored and
deduplicated; a due check calls ``on_sla_expired`` and is marked done only afterwards; a handler that raises
leaves the check for a retry; escalation reaches the on-call contact when nobody accepts (fakes); an accept
before the deadline makes the later check a no-op. The SQL side of the adapters is in ``test_o3_actions.py``.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from pema.care.handoff_types import Depth, Urgency
from pema.care.testing_routing import RoutingRig, make_routing_rig, staff_context
from pema.clinic.actions.sla_checks import MAX_ATTEMPTS
from pema.notify.sla import DurableSlaScheduler, SlaCheckRunner
from pema.notify.testing import InMemorySlaStore
from pema.notify.types import SlaStore


async def hand_over(rig: RoutingRig, durable: DurableSlaScheduler) -> None:
    """Give the adapter what M's routing asked for (the rig's fake scheduler recorded it)."""
    for check in rig.sla.checks:
        await durable.schedule_check(check)


async def test_a_check_of_m_is_stored_once_whatever_the_repeats() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    store = InMemorySlaStore()
    durable = DurableSlaScheduler(store)
    await hand_over(rig, durable)
    await hand_over(rig, durable)
    assert len(store.rows) == len(rig.sla.checks) == 1
    ((key, row),) = store.rows.items()
    assert key == rig.sla.last.dedupe_key
    assert (row["request_id"], row["idx"], row["state"]) == (rig.request.id, 0, "pending")


async def test_nobody_accepting_reaches_the_on_call_contact_through_the_durable_checks() -> None:
    rig = make_routing_rig()
    first = rig.directory.add_staff("cs_staff", load=0)
    second = rig.directory.add_staff("cs_staff", load=1)
    store: SlaStore = InMemorySlaStore()
    durable = DurableSlaScheduler(store)
    runner = SlaCheckRunner(store, rig.service, clock=rig.clock)

    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert [u for u, _ in rig.notifier.staff] == [first]
    seen = 0
    for _ in range(3):  # three checks: first, second, then the chain ends at the on-call contact
        for check in rig.sla.checks[seen:]:
            await durable.schedule_check(check)
        seen = len(rig.sla.checks)
        rig.clock.advance(timedelta(minutes=31))
        await runner.run_once()

    assert [u for u, _ in rig.notifier.staff] == [first, second]
    assert rig.request.outcome == "exhausted_to_oncall"
    ((contact, notice),) = rig.notifier.on_call
    assert contact.zalo_number == "0000000001"
    assert notice.is_on_call
    assert rig.harness.calls == 0  # no model anywhere in the escalation


async def test_a_check_after_an_accept_does_nothing_and_is_still_marked_done() -> None:
    rig = make_routing_rig()
    me = rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    store = InMemorySlaStore()
    await hand_over(rig, DurableSlaScheduler(store))
    await rig.control.accept(staff_context(me), rig.agent.patient_id)
    rig.clock.advance(timedelta(minutes=31))
    assert await SlaCheckRunner(store, rig.service, clock=rig.clock).run_once() == 1
    assert rig.request.outcome == "accepted"
    assert rig.notifier.on_call == []
    assert {row["state"] for row in store.rows.values()} == {"done"}


async def test_a_check_that_is_not_due_yet_is_left_alone() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    store = InMemorySlaStore()
    await hand_over(rig, DurableSlaScheduler(store))
    rig.clock.advance(timedelta(minutes=1))
    assert await SlaCheckRunner(store, rig.service, clock=rig.clock).run_once() == 0
    assert {row["state"] for row in store.rows.values()} == {"pending"}


class RaisingHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def on_sla_expired(self, request_id: UUID, idx: int, now: object = None) -> object:
        self.calls += 1
        raise RuntimeError("care loop not reachable")


async def test_a_handler_that_raises_leaves_the_check_pending_then_gives_up_loudly() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    store = InMemorySlaStore()
    await hand_over(rig, DurableSlaScheduler(store))
    handler = RaisingHandler()
    runner = SlaCheckRunner(store, handler, clock=rig.clock)
    rig.clock.advance(timedelta(minutes=31))
    (row,) = store.rows.values()
    assert await runner.run_once() == 0
    assert row["state"] == "pending"  # "never ran" is never turned into "ran"
    assert row["attempts"] == 1
    for _ in range(MAX_ATTEMPTS - 1):
        rig.clock.advance(timedelta(hours=2))
        await runner.run_once()
    assert row["state"] == "failed"
    assert handler.calls == MAX_ATTEMPTS

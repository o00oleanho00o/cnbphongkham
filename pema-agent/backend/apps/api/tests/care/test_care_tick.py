"""The 06:00 tick, the priority queue, the send window and the event mapping (package M, step M2a).

New tests (no zalo-agent original). No database: fakes and a fake clock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, time
from uuid import UUID

import pytest

from pema.care.events import (
    CareEvent,
    EventKind,
    Initiator,
    Priority,
    event_from_rule,
    event_kind_for_rule,
    is_proactive,
    priority_of,
)
from pema.care.loop import CareTurnRunner, CareTurnWorker
from pema.care.ports import CareAgentSnapshot, HarnessDecision, TickFinding
from pema.care.priority import CarePriorityQueue
from pema.care.testing import (
    AlwaysAutoSend,
    FakeChannel,
    FakeClock,
    FakeContextLoader,
    FakeGuard,
    FakeHarness,
    FakeReview,
    FakeScheduler,
    FakeTickRules,
    FixedWindow,
    InMemoryCareStore,
    vn,
)
from pema.care.tick import daily_tick, next_tick_at, seconds_until_next_tick
from pema.care.window import ChannelPolicySendWindow, SendWindow
from pema.scheduler.ports import ChannelPolicy
from pema_contracts.crm import RuleKey


def make_event(kind: EventKind, initiator: Initiator, minute: int = 0) -> CareEvent:
    return CareEvent(
        kind=kind, initiator=initiator, patient_ref="P900", occurred_at=vn(2026, 10, 3, 9, minute)
    )


# --------------------------------------------------------------------------------------- tick
async def test_the_tick_over_100_patients_calls_the_llm_only_for_patients_that_need_a_draft() -> None:
    store = InMemoryCareStore()
    agents = [store.add_patient(f"P{n:03d}") for n in range(100)]
    needs = {f"P{n:03d}": True for n in (3, 17, 18, 42, 77, 91, 99)}  # 7 patients with something to draft
    quiet = {f"P{n:03d}": False for n in (5, 6, 60)}  # a finding that needs no text
    rules = FakeTickRules(
        needs_draft={**needs, **quiet}, refs={a.id: ref for ref, a in zip(store.refs, agents, strict=True)}
    )
    queue = CarePriorityQueue()
    harness = FakeHarness(HarnessDecision(text="Nhắc (mẫu)"))
    runner = CareTurnRunner(
        store=store,
        context_loader=FakeContextLoader(),
        harness=harness,
        channel=FakeChannel(),
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=FixedWindow(),
        guard=FakeGuard(),
        clock=FakeClock(vn(2026, 10, 3, 6, 0)),
        autonomy=AlwaysAutoSend(),
        cap_per_day=5,
    )

    report = await daily_tick(
        agents[0].clinic_id, vn(2026, 10, 3, 6, 0), store=store, rules=rules, queue=queue
    )
    await CareTurnWorker(queue, runner).run_until_idle()

    assert report.agents_checked == 100
    assert report.findings == 10
    assert report.drafts_enqueued == 7
    assert harness.calls == 7  # not one per patient
    assert len(store.last_tick) == 100  # the tick touched every agent


async def test_the_rules_are_asked_once_per_batch_not_once_per_patient() -> None:
    store = InMemoryCareStore()
    for n in range(95):
        store.add_patient(f"P{n:03d}")
    rules = FakeTickRules()
    report = await daily_tick(
        next(iter(store.agents.values())).clinic_id,
        vn(2026, 10, 3, 6, 0),
        store=store,
        rules=rules,
        queue=CarePriorityQueue(),
        batch_size=30,
    )
    assert report.batches == rules.batches == 4  # 30 + 30 + 30 + 5
    assert report.agents_checked == 95


async def test_a_patient_with_two_findings_costs_one_draft_event() -> None:
    store = InMemoryCareStore()
    agent = store.add_patient("P900")
    queue = CarePriorityQueue()

    class TwoFindings:
        async def findings(self, agents: Sequence[CareAgentSnapshot], now: datetime) -> Sequence[TickFinding]:
            return [
                TickFinding(agent.id, "P900", "missed_milestone", needs_draft=True),
                TickFinding(agent.id, "P900", "stale_pending", needs_draft=True),
            ]

    report = await daily_tick(
        agent.clinic_id, vn(2026, 10, 3, 6), store=store, rules=TwoFindings(), queue=queue
    )
    assert report.drafts_enqueued == 1
    assert len(queue) == 1
    item = queue.pop_nowait()
    assert item is not None
    assert [f["kind"] for f in item.event.payload["findings"]] == ["missed_milestone", "stale_pending"]
    assert item.event.kind is EventKind.DAILY_TICK


async def test_paused_agents_are_left_out_of_the_tick() -> None:
    store = InMemoryCareStore()
    store.add_patient("P900")
    store.add_patient("P901", paused=True)
    report = await daily_tick(
        next(iter(store.agents.values())).clinic_id,
        vn(2026, 10, 3, 6),
        store=store,
        rules=FakeTickRules(),
        queue=CarePriorityQueue(),
    )
    assert report.agents_checked == 1


def test_the_next_tick_is_the_next_06h00_in_ho_chi_minh() -> None:
    assert next_tick_at(vn(2026, 10, 3, 5, 59)) == vn(2026, 10, 3, 6, 0)
    assert next_tick_at(vn(2026, 10, 3, 6, 0)) == vn(2026, 10, 4, 6, 0)
    assert next_tick_at(vn(2026, 10, 3, 23, 0)) == vn(2026, 10, 4, 6, 0)
    assert seconds_until_next_tick(vn(2026, 10, 3, 5, 0)) == 3600


# ----------------------------------------------------------------------------------- priority
def test_priority_levels_follow_the_plan() -> None:
    assert priority_of(make_event(EventKind.PATIENT_MESSAGE, Initiator.PATIENT)) is Priority.PATIENT_MESSAGE
    assert priority_of(make_event(EventKind.DAILY_TICK, Initiator.SYSTEM)) is Priority.TICK
    for kind in (
        EventKind.SESSION_COMPLETED,
        EventKind.MILESTONE_DUE,
        EventKind.VISIT_OVERDUE,
        EventKind.NO_SHOW,
        EventKind.DORMANT,
        EventKind.BIRTHDAY,
        EventKind.STAFF_COMMAND,
        EventKind.DOCTOR_EDIT,
    ):
        assert priority_of(make_event(kind, Initiator.SYSTEM)) is Priority.DUE_EVENT


def test_within_a_level_the_oldest_event_goes_first_then_arrival_order() -> None:
    queue = CarePriorityQueue()
    agent = UUID(int=1)
    late = make_event(EventKind.NO_SHOW, Initiator.SYSTEM, minute=30)
    early = make_event(EventKind.DORMANT, Initiator.SYSTEM, minute=10)
    twin = make_event(EventKind.BIRTHDAY, Initiator.SYSTEM, minute=10)
    for item in (late, early, twin):
        queue.push(agent, item)
    assert queue.depth_by_priority() == {Priority.PATIENT_MESSAGE: 0, Priority.DUE_EVENT: 3, Priority.TICK: 0}
    order = [queue.pop_nowait() for _ in range(3)]
    assert [o.event.kind for o in order if o is not None] == [
        EventKind.DORMANT,
        EventKind.BIRTHDAY,
        EventKind.NO_SHOW,
    ]
    assert queue.pop_nowait() is None


async def test_pop_waits_for_the_next_event() -> None:
    queue = CarePriorityQueue()
    waiter = asyncio.ensure_future(queue.pop())
    await asyncio.sleep(0)
    assert not waiter.done()
    queue.push(UUID(int=1), make_event(EventKind.DORMANT, Initiator.SYSTEM))
    item = await asyncio.wait_for(waiter, timeout=1)
    assert item.event.kind is EventKind.DORMANT


async def test_run_forever_stops_when_asked() -> None:
    store = InMemoryCareStore()
    agent = store.add_patient("P900")
    harness = FakeHarness()
    runner = CareTurnRunner(
        store=store,
        context_loader=FakeContextLoader(),
        harness=harness,
        channel=FakeChannel(),
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=FixedWindow(),
        guard=FakeGuard(),
        clock=FakeClock(vn(2026, 10, 3, 10)),
        autonomy=AlwaysAutoSend(),
        cap_per_day=5,
    )
    queue = CarePriorityQueue()
    stop = asyncio.Event()
    task = asyncio.ensure_future(CareTurnWorker(queue, runner).run_forever(stop))
    queue.push(agent.id, make_event(EventKind.PATIENT_MESSAGE, Initiator.PATIENT))
    for _ in range(50):
        await asyncio.sleep(0)
        if harness.calls:
            break
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert harness.calls == 1


# ---------------------------------------------------------------------------------- events
def test_every_crm_rule_but_manual_maps_to_a_care_event_kind() -> None:
    mapped = {rule: event_kind_for_rule(rule) for rule in RuleKey}
    assert mapped[RuleKey.MANUAL] is None
    assert all(kind is not None for rule, kind in mapped.items() if rule is not RuleKey.MANUAL)
    assert mapped[RuleKey.OVERDUE] is EventKind.VISIT_OVERDUE
    assert mapped[RuleKey.BIRTHDAY] is EventKind.BIRTHDAY
    assert {mapped[RuleKey.D1], mapped[RuleKey.D3], mapped[RuleKey.D7]} == {EventKind.MILESTONE_DUE}


def test_a_rule_event_is_a_system_event_with_a_code_and_no_free_text() -> None:
    made = event_from_rule(RuleKey.D3, "P900", vn(2026, 10, 3, 9))
    assert made is not None
    assert (made.kind, made.initiator, made.patient_ref) == (
        EventKind.MILESTONE_DUE,
        Initiator.SYSTEM,
        "P900",
    )
    assert made.payload == {"rule": "d3"}
    assert event_from_rule(RuleKey.MANUAL, "P900", vn(2026, 10, 3, 9)) is None


def test_only_the_patient_writing_makes_a_reply_non_proactive() -> None:
    assert not is_proactive(make_event(EventKind.PATIENT_MESSAGE, Initiator.PATIENT))
    assert is_proactive(make_event(EventKind.STAFF_COMMAND, Initiator.STAFF))
    assert is_proactive(make_event(EventKind.DAILY_TICK, Initiator.SYSTEM))


def test_a_care_event_refuses_an_empty_patient_ref() -> None:
    with pytest.raises(ValueError, match="patient_ref"):
        CareEvent(
            kind=EventKind.DORMANT, initiator=Initiator.SYSTEM, patient_ref="", occurred_at=vn(2026, 10, 3)
        )


# ----------------------------------------------------------------------------------- window
def test_the_default_window_is_08h00_to_20h00_and_next_open_is_the_next_start() -> None:
    window = SendWindow()
    assert (window.start, window.end) == (time(8, 0), time(20, 0))
    assert window.is_open(vn(2026, 10, 3, 8, 0))
    assert window.is_open(vn(2026, 10, 3, 19, 59))
    assert not window.is_open(vn(2026, 10, 3, 20, 0))
    assert not window.is_open(vn(2026, 10, 3, 7, 59))
    assert window.next_open(vn(2026, 10, 3, 20, 0)) == vn(2026, 10, 4, 8, 0)
    assert window.next_open(vn(2026, 10, 3, 7, 59)) == vn(2026, 10, 3, 8, 0)
    now = vn(2026, 10, 3, 12, 0)
    assert window.next_open(now) == now


def test_a_window_across_midnight_and_an_always_open_window() -> None:
    night = SendWindow(start=time(22, 0), end=time(6, 0))
    assert night.is_open(vn(2026, 10, 3, 23, 0))
    assert night.is_open(vn(2026, 10, 3, 5, 0))
    assert not night.is_open(vn(2026, 10, 3, 12, 0))
    assert night.next_open(vn(2026, 10, 3, 12, 0)) == vn(2026, 10, 3, 22, 0)
    assert SendWindow(start=time(0, 0), end=time(0, 0)).is_open(vn(2026, 10, 3, 3, 0))


class _Policy:
    def __init__(self, policy: ChannelPolicy | None) -> None:
        self._policy = policy

    async def get_channel_policy(self, clinic_id: UUID, channel: str) -> ChannelPolicy | None:
        return self._policy


async def test_the_window_comes_from_the_channel_setting_and_defaults_when_absent() -> None:
    clinic = UUID(int=5)
    row = ChannelPolicy(True, False, None, "09:30", "18:00")
    window = await ChannelPolicySendWindow(_Policy(row), "zalo_bot").get(clinic)
    assert (window.start, window.end) == (time(9, 30), time(18, 0))
    for missing in (
        None,
        ChannelPolicy(True, False, None, None, None),
        ChannelPolicy(True, False, None, "xx", "yy"),
    ):
        window = await ChannelPolicySendWindow(_Policy(missing), "zalo_bot").get(clinic)
        assert (window.start, window.end) == (time(8, 0), time(20, 0))

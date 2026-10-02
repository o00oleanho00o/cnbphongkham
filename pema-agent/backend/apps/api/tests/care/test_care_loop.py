"""The turn loop of a care agent (package M, step M2a). New tests (no zalo-agent original).

All fakes, fake clock, fake "LLM": no database needed. The DB side (``SqlCareStore``) is in ``test_care_store``.
Times are wall times of Asia/Ho_Chi_Minh through ``vn``; the send window is the default 08:00-20:00.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import pytest

from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.loop import (
    DEFERRED_TO_WINDOW,
    DRAFT_PREFIX,
    FAILED_HARNESS,
    HANDOFF_REQUESTED,
    NO_ACTION,
    PAUSED_PROACTIVE_CAP,
    CareEventBus,
    CareTurnRunner,
    CareTurnWorker,
    Clock,
    TurnStatus,
)
from pema.care.models import ControlState
from pema.care.ports import (
    CareAgentSnapshot,
    HandoffAction,
    HandoffDecider,
    HandoffVerdict,
    HarnessDecision,
    PatientContext,
)
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
    FixedWindow,
    InMemoryCareStore,
    vn,
)
from pema.config.runtime_tuning_settings import bot_time_zone
from pema.shared.zone_time import today_key

REF = "P900"


@dataclass
class Rig:
    store: InMemoryCareStore
    harness: FakeHarness
    channel: FakeChannel
    scheduler: FakeScheduler
    review: FakeReview
    guard: FakeGuard
    clock: FakeClock
    loader: FakeContextLoader
    runner: CareTurnRunner
    agent: CareAgentSnapshot


def make_rig(
    *,
    now: datetime | None = None,
    auto_send: bool = True,
    cap: int | None = 2,
    harness: FakeHarness | None = None,
    channel: FakeChannel | None = None,
    review: FakeReview | None = None,
    loader: FakeContextLoader | None = None,
    handoff: HandoffDecider | None = None,
    store: InMemoryCareStore | None = None,
    clock_fn: Clock | None = None,
) -> Rig:
    store = store or InMemoryCareStore()
    agent = store.add_patient(REF)
    harness = harness or FakeHarness()
    channel = channel or FakeChannel()
    scheduler = FakeScheduler()
    review = review or FakeReview()
    guard = FakeGuard()
    clock = FakeClock(now or vn(2026, 10, 3, 10, 0))
    loader = loader or FakeContextLoader()
    runner = CareTurnRunner(
        store=store,
        context_loader=loader,
        harness=harness,
        channel=channel,
        scheduler=scheduler,
        review=review,
        window=FixedWindow(),
        guard=guard,
        clock=clock_fn or clock,
        autonomy=AlwaysAutoSend() if auto_send else None,
        handoff=handoff,
        cap_per_day=cap,
    )
    return Rig(store, harness, channel, scheduler, review, guard, clock, loader, runner, agent)


def event(
    kind: EventKind = EventKind.MILESTONE_DUE,
    initiator: Initiator = Initiator.SYSTEM,
    at: datetime | None = None,
) -> CareEvent:
    return CareEvent(kind=kind, initiator=initiator, patient_ref=REF, occurred_at=at or vn(2026, 10, 3, 9, 0))


def patient_message(at: datetime | None = None) -> CareEvent:
    return event(EventKind.PATIENT_MESSAGE, Initiator.PATIENT, at)


def actions_of(rig: Rig) -> list[tuple[str, str]]:
    return [(row.action_type, row.disposition) for row in rig.store.actions]


# ------------------------------------------------------------------------------------ priority
async def test_a_patient_message_arriving_after_a_due_event_is_still_processed_first() -> None:
    rig = make_rig()
    queue = CarePriorityQueue()
    bus = CareEventBus(rig.store, queue)
    due = event(EventKind.MILESTONE_DUE, at=vn(2026, 10, 3, 9, 0))
    tick = event(EventKind.DAILY_TICK, at=vn(2026, 10, 3, 6, 0))
    message = patient_message(at=vn(2026, 10, 3, 9, 30))
    assert await bus.publish(tick)
    assert await bus.publish(due)
    assert await bus.publish(message)

    processed = await CareTurnWorker(queue, rig.runner).run_until_idle()

    assert processed == 3
    assert [r.event.kind for r in rig.harness.requests] == [
        EventKind.PATIENT_MESSAGE,
        EventKind.MILESTONE_DUE,
        EventKind.DAILY_TICK,
    ]


async def test_an_event_for_a_patient_without_care_agent_is_dropped() -> None:
    rig = make_rig()
    queue = CarePriorityQueue()
    unknown = CareEvent(
        kind=EventKind.DORMANT, initiator=Initiator.SYSTEM, patient_ref="P901", occurred_at=vn(2026, 10, 3, 9)
    )
    assert not await CareEventBus(rig.store, queue).publish(unknown)
    assert len(queue) == 0


async def test_a_turn_for_an_unknown_care_agent_does_nothing() -> None:
    rig = make_rig()
    outcome = await rig.runner.run_turn(UUID(int=1), event())
    assert outcome.status is TurnStatus.UNKNOWN_AGENT
    assert rig.harness.calls == 0
    assert rig.store.actions == []


async def test_a_crashing_turn_does_not_stop_the_worker() -> None:
    class BrokenStore(InMemoryCareStore):
        async def touch_last_tick(self, care_agent_ids: Sequence[UUID], at: datetime) -> None:
            raise RuntimeError("database gone")

    rig = make_rig(store=BrokenStore())
    queue = CarePriorityQueue()
    queue.push(rig.agent.id, event(at=vn(2026, 10, 3, 8, 0)))
    queue.push(rig.agent.id, event(at=vn(2026, 10, 3, 8, 1)))
    processed = await CareTurnWorker(queue, rig.runner).run_until_idle()
    assert processed == 2
    assert len(queue) == 0


# ------------------------------------------------------------------------------- send window
async def test_a_22h00_message_is_deferred_to_08h00_the_next_day() -> None:
    rig = make_rig(now=vn(2026, 10, 3, 22, 0))
    outcome = await rig.runner.run_turn(rig.agent.id, event())
    assert outcome.status is TurnStatus.DEFERRED
    assert outcome.run_at == vn(2026, 10, 4, 8, 0)
    assert rig.channel.sent == []
    assert [d.run_at for d in rig.scheduler.deferred] == [vn(2026, 10, 4, 8, 0)]
    assert rig.guard.counts == {}  # a deferred message has not taken a cap slot yet
    assert actions_of(rig) == [(DEFERRED_TO_WINDOW, "paused")]


async def test_a_05h00_message_is_deferred_to_08h00_the_same_day() -> None:
    rig = make_rig(now=vn(2026, 10, 3, 5, 0))
    outcome = await rig.runner.run_turn(rig.agent.id, event())
    assert outcome.run_at == vn(2026, 10, 3, 8, 0)


async def test_the_reply_to_a_patient_who_wrote_at_night_waits_for_the_window_too() -> None:
    rig = make_rig(now=vn(2026, 10, 3, 22, 30))
    outcome = await rig.runner.run_turn(rig.agent.id, patient_message(vn(2026, 10, 3, 22, 29)))
    assert outcome.status is TurnStatus.DEFERRED
    assert rig.channel.sent == []


async def test_inside_the_window_the_message_is_sent() -> None:
    rig = make_rig(now=vn(2026, 10, 3, 19, 59))
    outcome = await rig.runner.run_turn(rig.agent.id, event())
    assert outcome.status is TurnStatus.SENT
    assert len(rig.channel.sent) == 1
    assert rig.channel.sent[0][2] is True  # proactive
    assert actions_of(rig) == [("reply", "auto_sent")]


# ------------------------------------------------------------------------------- daily cap
async def test_over_the_daily_cap_nothing_is_sent() -> None:
    rig = make_rig(cap=2)
    statuses = [(await rig.runner.run_turn(rig.agent.id, event())).status for _ in range(3)]
    assert statuses == [TurnStatus.SENT, TurnStatus.SENT, TurnStatus.CAPPED]
    assert len(rig.channel.sent) == 2
    assert actions_of(rig)[-1] == (PAUSED_PROACTIVE_CAP, "paused")


async def test_the_cap_is_per_patient_and_per_day() -> None:
    rig = make_rig(cap=1)
    other = rig.store.add_patient("P902")
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.SENT
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.CAPPED
    assert (await rig.runner.run_turn(other.id, event())).status is TurnStatus.SENT  # another patient
    rig.clock.now = vn(2026, 10, 4, 10, 0)
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.SENT  # next day
    assert today_key(bot_time_zone(), vn(2026, 10, 3, 10)) != today_key(bot_time_zone(), vn(2026, 10, 4, 10))


async def test_a_reply_to_the_patient_is_not_counted_against_the_proactive_cap() -> None:
    rig = make_rig(cap=1)
    for _ in range(3):
        assert (await rig.runner.run_turn(rig.agent.id, patient_message())).status is TurnStatus.SENT
    assert rig.guard.counts == {}
    assert all(proactive is False for _, _, proactive in rig.channel.sent)


async def test_a_failed_send_gives_the_cap_slot_back() -> None:
    rig = make_rig(cap=1, channel=FakeChannel(ok=False))
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.FAILED
    assert sum(rig.guard.counts.values()) == 0
    rig.channel.ok = True
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.SENT


# --------------------------------------------------------------------------- conversation state
@pytest.mark.parametrize("state", [ControlState.HANDOFF_ROUTING, ControlState.STAFF])
async def test_when_the_state_is_not_auto_nothing_is_sent_and_no_model_is_called(state: ControlState) -> None:
    rig = make_rig()
    rig.store.states[rig.agent.patient_id] = state
    outcome = await rig.runner.run_turn(rig.agent.id, patient_message())
    assert outcome.status is TurnStatus.SKIPPED_STATE
    assert rig.harness.calls == 0
    assert rig.channel.sent == []
    assert rig.review.drafts == []
    assert actions_of(rig) == [(f"turn:skipped_state_{state.value.lower()}", "paused")]


async def test_a_paused_agent_does_nothing() -> None:
    rig = make_rig()
    rig.store.agents[rig.agent.id] = CareAgentSnapshot(
        id=rig.agent.id,
        clinic_id=rig.agent.clinic_id,
        patient_id=rig.agent.patient_id,
        profile="patient_channel",
        paused=True,
    )
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.SKIPPED_PAUSED
    assert rig.harness.calls == 0
    assert rig.channel.sent == []


# ------------------------------------------------------------------------------- autonomy
async def test_without_an_autonomy_policy_everything_is_a_draft_for_a_person() -> None:
    rig = make_rig(auto_send=False)
    outcome = await rig.runner.run_turn(rig.agent.id, patient_message())
    assert outcome.status is TurnStatus.DRAFTED
    assert rig.channel.sent == []
    assert [(d[1], d[3]) for d in rig.review.drafts] == [(REF, "autonomy")]
    assert actions_of(rig) == [(DRAFT_PREFIX + "autonomy", "paused")]


async def test_a_birthday_message_is_never_sent_automatically() -> None:
    rig = make_rig(auto_send=True)
    outcome = await rig.runner.run_turn(rig.agent.id, event(EventKind.BIRTHDAY))
    assert outcome.status is TurnStatus.DRAFTED
    assert rig.channel.sent == []
    assert rig.review.drafts[0][3] == "birthday_never_auto"


async def test_a_patient_without_a_verified_channel_gets_a_draft_for_staff_to_send_by_hand() -> None:
    rig = make_rig(loader=FakeContextLoader(channel=None))
    outcome = await rig.runner.run_turn(rig.agent.id, event())
    assert outcome.status is TurnStatus.DRAFTED
    assert rig.channel.sent == []
    assert rig.review.drafts[0][3] == "no_verified_channel"


async def test_a_draft_that_cannot_be_created_is_a_failed_turn_and_sends_nothing() -> None:
    rig = make_rig(auto_send=False, review=FakeReview(ok=False))
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.FAILED
    assert rig.channel.sent == []


async def test_marketing_to_a_patient_who_opted_out_is_blocked() -> None:
    rig = make_rig(
        harness=FakeHarness(HarnessDecision(text="Ưu đãi (mẫu)", marketing=True)),
        loader=FakeContextLoader(marketing_opt_out=True),
    )
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.BLOCKED_OPT_OUT
    assert rig.channel.sent == []
    assert rig.review.drafts == []


# ------------------------------------------------------------------------------- the pipeline
async def test_the_harness_gets_the_care_persona_the_patient_channel_profile_and_a_code_only_context() -> (
    None
):
    rig = make_rig()
    await rig.runner.run_turn(rig.agent.id, event())
    request = rig.harness.requests[0]
    assert request.persona == "care_agent"
    assert request.profile == "patient_channel"
    assert request.context.patient_ref == REF
    assert request.care_agent_id == rig.agent.id


async def test_a_handoff_verdict_stops_the_turn_before_the_model() -> None:
    class Handoff:
        async def decide(
            self, agent: CareAgentSnapshot, event: CareEvent, context: PatientContext
        ) -> HandoffVerdict:
            return HandoffVerdict(HandoffAction.HANDOFF, "needs a person")

    rig = make_rig(handoff=Handoff())
    outcome = await rig.runner.run_turn(rig.agent.id, patient_message())
    assert outcome.status is TurnStatus.HANDOFF
    assert rig.harness.calls == 0
    assert actions_of(rig) == [(HANDOFF_REQUESTED, "paused")]


async def test_nothing_to_say_is_logged_as_no_action() -> None:
    rig = make_rig(harness=FakeHarness(HarnessDecision(text="   ")))
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.NO_ACTION
    assert actions_of(rig) == [(NO_ACTION, "paused")]


async def test_a_failing_model_is_a_failed_turn_with_a_log_row_and_no_send() -> None:
    rig = make_rig(harness=FakeHarness(fail=True))
    assert (await rig.runner.run_turn(rig.agent.id, event())).status is TurnStatus.FAILED
    assert actions_of(rig) == [(FAILED_HARNESS, "paused")]
    assert rig.channel.sent == []


async def test_every_turn_writes_one_action_row_and_sets_last_tick_at() -> None:
    rig = make_rig(now=vn(2026, 10, 3, 10, 0))
    await rig.runner.run_turn(rig.agent.id, event())
    rig.clock.now = vn(2026, 10, 3, 11, 0)
    rig.store.states[rig.agent.patient_id] = ControlState.STAFF
    await rig.runner.run_turn(rig.agent.id, patient_message())
    assert len(rig.store.actions) == 2
    assert rig.store.last_tick[rig.agent.id] == vn(2026, 10, 3, 11, 0)
    assert [row.at for row in rig.store.actions] == [vn(2026, 10, 3, 10, 0), vn(2026, 10, 3, 11, 0)]


async def test_the_clock_is_read_once_per_turn() -> None:
    calls = 0
    base = FakeClock(vn(2026, 10, 3, 10, 0))

    def counting() -> datetime:
        nonlocal calls
        calls += 1
        return base()

    rig = make_rig(clock_fn=counting)
    await rig.runner.run_turn(rig.agent.id, event())
    assert calls == 1

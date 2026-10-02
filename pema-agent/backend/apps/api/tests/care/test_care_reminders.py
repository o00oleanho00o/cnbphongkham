"""Reminders while a person handles the patient: pause, show to staff, reconcile on release (package M, M2c).

New tests (no zalo-agent original). Fakes and a fake clock, no database (the SQL side is
``test_care_routing_store``). The rule under test (PLAN-M section 8, decision 2 of section 15): in
``HANDOFF_ROUTING`` and ``STAFF`` the agent sends NO reminder of any kind; on release it judges what is left.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_types import Depth, Urgency
from pema.care.loop import TurnStatus
from pema.care.models import ControlState
from pema.care.reminders import LATE_ORIGINAL_AT, REMINDER_KINDS, drop_reason
from pema.care.routing_types import (
    DueReminder,
    PausedReminder,
    ReminderRules,
    ReminderStatus,
    RoutingConfig,
)
from pema.care.testing import AlwaysAutoSend, vn
from pema.care.testing_routing import (
    MONDAY_10,
    REF,
    RoutingRig,
    make_routing_rig,
    staff_context,
)
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType

DAY = timedelta(days=1)


def reminder_event(
    rule: str | None, due: datetime, *, kind: EventKind = EventKind.MILESTONE_DUE, anchor: str | None = None
) -> CareEvent:
    payload: dict[str, object] = {}
    if rule is not None:
        payload["rule"] = rule
    if anchor is not None:
        payload["anchor"] = anchor
    return CareEvent(kind=kind, initiator=Initiator.SYSTEM, patient_ref=REF, payload=payload, occurred_at=due)


async def to_staff(rig: RoutingRig) -> UUID:
    """Open a round and let a staff member accept it; the staff member's id."""
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    me = uuid4()
    await rig.control.accept(staff_context(me), rig.agent.patient_id)
    assert rig.state is ControlState.STAFF
    return me


async def fire(rig: RoutingRig, event: CareEvent) -> TurnStatus:
    return (await rig.runner.run_turn(rig.agent.id, event)).status


def sent_texts(rig: RoutingRig) -> list[str]:
    return [text for _, text, _ in rig.channel.sent]


# ------------------------------------------------------------------------------------------ pausing
async def test_in_staff_a_due_reminder_is_not_sent_and_a_paused_record_exists() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    holding = len(rig.channel.sent)
    status = await fire(rig, reminder_event("d3", MONDAY_10))
    assert status is TurnStatus.REMINDER_PAUSED
    assert len(rig.channel.sent) == holding  # nothing new reached the patient
    assert rig.harness.calls == 0
    assert len(rig.queue) == 0  # and no task or event was made out of it
    (paused,) = rig.reminder_store.rows
    assert paused.status is ReminderStatus.PAUSED
    assert paused.rule == "d3"
    assert paused.kind is EventKind.MILESTONE_DUE
    assert paused.patient_ref == REF
    assert paused.owner_user_id == me
    assert paused.prepared_text is not None
    assert "3 ngày" in paused.prepared_text
    assert "reminder:paused:d3" in rig.actions()


async def test_the_owning_staff_member_sees_it_with_the_prepared_text() -> None:
    rig = make_routing_rig()
    me = await to_staff(rig)
    await fire(rig, reminder_event("d1", MONDAY_10))
    shown = await rig.reminder_store.list_for_owner(me, limit=10)
    assert [(r.rule, r.status) for r in shown] == [("d1", ReminderStatus.PAUSED)]
    assert shown[0].prepared_text
    assert await rig.reminder_store.list_for_owner(uuid4(), limit=10) == []


async def test_a_reminder_is_paused_while_the_round_is_still_routing() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    owner = rig.directory.add_staff("cs_staff")
    rig.directory.own(rig.agent.patient_id, cs_owner=owner)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    holding = len(rig.channel.sent)
    assert rig.state is ControlState.HANDOFF_ROUTING
    assert await fire(rig, reminder_event("due", MONDAY_10)) is TurnStatus.REMINDER_PAUSED
    assert len(rig.channel.sent) == holding
    (paused,) = rig.reminder_store.rows
    assert paused.owner_user_id == owner  # nobody has accepted yet: the CS owner


async def test_the_same_reminder_arriving_twice_is_one_record() -> None:
    rig = make_routing_rig()
    await to_staff(rig)
    event = reminder_event("d3", MONDAY_10)
    await fire(rig, event)
    await fire(rig, event)
    assert len(rig.reminder_store.rows) == 1
    assert rig.actions().count("reminder:paused:d3") == 1


@pytest.mark.parametrize(
    "kind",
    [
        EventKind.MILESTONE_DUE,
        EventKind.VISIT_OVERDUE,
        EventKind.NO_SHOW,
        EventKind.DORMANT,
        EventKind.BIRTHDAY,
        EventKind.SESSION_COMPLETED,
    ],
)
async def test_every_kind_of_reminder_is_paused_in_staff(kind: EventKind) -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    await to_staff(rig)
    holding = len(rig.channel.sent)
    assert kind in REMINDER_KINDS
    assert await fire(rig, reminder_event(None, MONDAY_10, kind=kind)) is TurnStatus.REMINDER_PAUSED
    assert len(rig.channel.sent) == holding
    assert len(rig.reminder_store.rows) == 1


async def test_the_daily_tick_and_staff_events_are_not_reminders() -> None:
    rig = make_routing_rig()
    await to_staff(rig)
    for kind in (EventKind.DAILY_TICK, EventKind.STAFF_COMMAND, EventKind.DOCTOR_EDIT):
        assert await fire(rig, reminder_event(None, MONDAY_10, kind=kind)) is TurnStatus.SKIPPED_STATE
    assert rig.reminder_store.rows == []


async def test_a_patient_reply_in_staff_goes_to_staff_and_the_agent_does_not_act() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    await to_staff(rig)
    holding = len(rig.channel.sent)
    outcome = await rig.message()
    assert outcome.status is TurnStatus.SUGGESTED  # a suggestion for staff, never sent
    assert len(rig.channel.sent) == holding
    assert rig.reminder_store.rows == []


async def test_reminders_that_are_already_queued_are_paused_when_the_round_opens() -> None:
    queued = [
        DueReminder(EventKind.MILESTONE_DUE, "d3", MONDAY_10, "s:d3", REF, {"anchor": "S1"}),
        DueReminder(EventKind.VISIT_OVERDUE, "overdue", MONDAY_10, "s:overdue", REF),
    ]
    rig = make_routing_rig(reminders_due=queued)
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert sorted(r.dedupe_key for r in rig.reminder_store.rows) == ["s:d3", "s:overdue"]
    assert sorted(rig.due.held) == ["s:d3", "s:overdue"]  # S / B2 are told not to fire them
    assert {r.status for r in rig.reminder_store.rows} == {ReminderStatus.PAUSED}
    assert rig.reminder_store.rows[0].payload.get("anchor") in ("S1", None)


async def test_a_pause_that_fails_does_not_stop_the_round() -> None:
    rig = make_routing_rig(reminders_due=[DueReminder(EventKind.NO_SHOW, "no_show", MONDAY_10, "k", REF)])

    async def boom(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("database down")

    rig.reminder_store.add = boom  # type: ignore[method-assign]
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert rig.state is ControlState.HANDOFF_ROUTING
    assert len(rig.notifier.staff) == 1  # routing still started


# ---------------------------------------------------------------------------------------- reconcile
async def test_release_after_one_day_sends_d3_at_the_nearest_slot_with_the_late_label() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    holding = len(rig.channel.sent)
    assert await fire(rig, reminder_event("d3", MONDAY_10)) is TurnStatus.REMINDER_PAUSED

    rig.clock.advance(DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "đã xử lý xong")
    assert rig.state is ControlState.AUTO
    assert [r.status for r in rig.reminder_store.rows] == [ReminderStatus.RESUMED]
    assert len(rig.queue) == 1

    assert await rig.drain() == 1
    new = sent_texts(rig)[holding:]
    assert len(new) == 1
    assert new[0].startswith("(nhắc trễ, lịch gốc 10:00) ")
    assert "reminder:resumed:d3" in rig.actions()
    assert rig.channel.sent[-1][2] is True  # proactive: it counts against the daily cap


async def test_a_resumed_reminder_waits_for_the_send_window_like_any_message() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))
    rig.clock.now = vn(2026, 10, 6, 22, 30)  # released late in the evening, still inside D3's life
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    holding = len(rig.channel.sent)
    outcome = await rig.runner.run_turn(rig.agent.id, rig.queue.pop_nowait().event)  # type: ignore[union-attr]
    assert outcome.status is TurnStatus.DEFERRED
    assert outcome.run_at == vn(2026, 10, 7, 8, 0)
    assert len(rig.channel.sent) == holding


async def test_release_after_ten_days_drops_d1_and_d3_and_logs_it() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    holding = len(rig.channel.sent)
    await fire(rig, reminder_event("d1", MONDAY_10))
    await fire(rig, reminder_event("d3", MONDAY_10 + 2 * DAY))

    rig.clock.advance(10 * DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert {r.status for r in rig.reminder_store.rows} == {ReminderStatus.DROPPED}
    assert len(rig.queue) == 0
    assert await rig.drain() == 0
    assert len(rig.channel.sent) == holding
    assert "reminder:dropped:past_meaning:d1" in rig.actions()
    assert "reminder:dropped:past_meaning:d3" in rig.actions()
    assert {r.resolution for r in rig.reminder_store.rows} == {"past_meaning"}


async def test_d1_is_dropped_when_d3_has_already_passed_and_d3_is_still_sent() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    holding = len(rig.channel.sent)
    await fire(rig, reminder_event("d1", MONDAY_10))
    await fire(rig, reminder_event("d3", MONDAY_10 + timedelta(hours=30)))

    rig.clock.advance(timedelta(hours=46))  # D+1 is 46 h late (inside its window) but D+3 is due
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    by_rule = {r.rule: r.status for r in rig.reminder_store.rows}
    assert by_rule == {"d1": ReminderStatus.DROPPED, "d3": ReminderStatus.RESUMED}
    assert "reminder:dropped:superseded:d1" in rig.actions()
    await rig.drain()
    assert len(sent_texts(rig)[holding:]) == 1


async def test_a_later_reminder_of_another_series_does_not_supersede() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    await fire(rig, reminder_event("d1", MONDAY_10, anchor="S1"))
    await fire(rig, reminder_event("d3", MONDAY_10 + timedelta(hours=30), anchor="S2"))
    rig.clock.advance(timedelta(hours=40))
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert {r.status for r in rig.reminder_store.rows} == {ReminderStatus.RESUMED}


async def test_a_reminder_sent_by_hand_is_not_resumed() -> None:
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))
    (paused,) = rig.reminder_store.rows
    assert await rig.reminders.mark_sent_by_staff(staff_context(me), paused.id)
    assert not await rig.reminders.mark_sent_by_staff(staff_context(me), paused.id)  # only once
    rig.clock.advance(DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert len(rig.queue) == 0
    assert [r.status for r in rig.reminder_store.rows] == [ReminderStatus.SENT_BY_STAFF]


async def test_only_staff_can_mark_a_reminder_as_sent() -> None:
    rig = make_routing_rig()
    await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))
    (paused,) = rig.reminder_store.rows
    agent = ActionContext(clinic_id=UUID(int=1), actor_type=ActorType.AGENT, actor_user_id=uuid4())
    with pytest.raises(PermissionError):
        await rig.reminders.mark_sent_by_staff(agent, paused.id)
    assert rig.reminder_store.rows[0].status is ReminderStatus.PAUSED


async def test_releasing_with_nothing_paused_changes_nothing() -> None:
    rig = make_routing_rig()
    me = await to_staff(rig)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert rig.state is ControlState.AUTO
    assert len(rig.queue) == 0
    assert rig.reminder_store.rows == []


async def test_a_failing_reconcile_does_not_undo_the_release() -> None:
    rig = make_routing_rig()
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))

    async def boom(care_agent_id: UUID) -> list[PausedReminder]:
        raise RuntimeError("database down")

    rig.reminder_store.list_paused = boom  # type: ignore[method-assign]
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert rig.state is ControlState.AUTO
    assert rig.reminder_store.rows[0].status is ReminderStatus.PAUSED  # still there for the next release


async def test_a_resumed_reminder_that_cannot_be_queued_is_logged() -> None:
    rig = make_routing_rig()
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))
    rig.care.refs.clear()  # the event bus no longer finds the care agent
    rig.clock.advance(DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert "reminder:resume_failed:d3" in rig.actions()
    assert len(rig.queue) == 0


async def test_the_reconciled_event_carries_the_original_schedule_and_the_rule() -> None:
    rig = make_routing_rig()
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10, anchor="S1"))
    rig.clock.advance(DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    item = rig.queue.pop_nowait()
    assert item is not None
    event = item.event
    assert event.kind is EventKind.MILESTONE_DUE
    assert event.initiator is Initiator.SYSTEM
    assert event.payload[LATE_ORIGINAL_AT] == MONDAY_10.isoformat()
    assert event.payload["rule"] == "d3"
    assert event.payload["anchor"] == "S1"
    assert event.occurred_at == rig.clock.now


async def test_the_prepared_texts_and_the_windows_are_configuration() -> None:
    rules = ReminderRules(max_late_hours={"d3": 1}, prepared_texts={"d3": "Mẫu riêng"})
    rig = make_routing_rig(routing_config=RoutingConfig(reminders=rules))
    me = await to_staff(rig)
    await fire(rig, reminder_event("d3", MONDAY_10))
    assert rig.reminder_store.rows[0].prepared_text == "Mẫu riêng"
    rig.clock.advance(timedelta(hours=2))
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")
    assert rig.reminder_store.rows[0].status is ReminderStatus.DROPPED


# ------------------------------------------------------------------------------------- the rules
def _paused(
    rule: str | None, due: datetime, *, kind: EventKind = EventKind.MILESTONE_DUE, anchor: object = None
) -> PausedReminder:
    return PausedReminder(
        id=uuid4(),
        care_agent_id=UUID(int=1),
        patient_id=UUID(int=2),
        patient_ref=REF,
        kind=kind,
        rule=rule,
        due_at=due,
        dedupe_key=str(uuid4()),
        prepared_text=None,
        owner_user_id=None,
        status=ReminderStatus.PAUSED,
        payload={} if anchor is None else {"anchor": anchor},
    )


def test_the_default_windows_keep_d3_for_a_day_and_drop_it_after_ten() -> None:
    rules = ReminderRules()
    due = MONDAY_10
    item = _paused("d3", due)
    assert drop_reason(item, [item], due + DAY, rules) is None
    assert drop_reason(item, [item], due + 10 * DAY, rules) == "past_meaning"


def test_a_type_without_a_window_uses_the_default_and_a_birthday_lasts_a_day() -> None:
    rules = ReminderRules()
    odd = _paused("something_new", MONDAY_10)
    assert drop_reason(odd, [odd], MONDAY_10 + timedelta(hours=71), rules) is None
    assert drop_reason(odd, [odd], MONDAY_10 + timedelta(hours=73), rules) == "past_meaning"
    birthday = _paused(None, MONDAY_10, kind=EventKind.BIRTHDAY)
    assert drop_reason(birthday, [birthday], MONDAY_10 + timedelta(hours=23), rules) is None
    assert drop_reason(birthday, [birthday], MONDAY_10 + timedelta(hours=25), rules) == "past_meaning"


def test_supersession_needs_the_later_one_to_be_due_and_in_the_same_series() -> None:
    rules = ReminderRules()
    d1 = _paused("d1", MONDAY_10)
    d3 = _paused("d3", MONDAY_10 + 2 * DAY)
    assert drop_reason(d1, [d1, d3], MONDAY_10 + DAY, rules) is None  # D+3 is not due yet
    assert drop_reason(d1, [d1, d3], MONDAY_10 + 2 * DAY, rules) == "superseded"
    assert drop_reason(d1, [d1, d3], MONDAY_10 + 2 * DAY + timedelta(hours=1), rules) == "past_meaning"
    near = MONDAY_10 + timedelta(hours=47)
    d3_early = _paused("d3", MONDAY_10 + timedelta(hours=40))
    assert drop_reason(d1, [d1, d3_early], near, rules) == "superseded"
    assert drop_reason(d3_early, [d1, d3_early], near, rules) is None  # the later one is never superseded
    other = _paused("d3", MONDAY_10 + timedelta(hours=40), anchor="S2")
    assert drop_reason(d1, [d1, other], near, rules) is None

"""Reminder pause and reconcile while a person handles the patient (step 7 of the recipe).

New module (not a port). The scenarios of the acceptance of M2c, counted, plus a matrix of every reminder type
released after 6 hours ... 60 days, on the same in-memory rig and fake clock as the routing measurement.
The expectations are written here from PLAN-AI01-M section 8:

* in ``STAFF`` and in ``HANDOFF_ROUTING`` no reminder of any kind reaches the patient, no model is called, no
  task or event is made, and a record is kept for the owning staff member;
* on release a reminder that is later than the window of its type is dropped (and logged); one that is not is
  handed back to the normal pipeline with the label "(nhắc trễ, lịch gốc HH:MM)"; D+1 is dropped when D+3 of
  the same series has already passed; a reminder sent by hand is never resumed.

The windows (``ReminderRules.max_late_hours``) are the TEMPORARY configuration defaults, awaiting the doctor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_types import Depth, Urgency
from pema.care.loop import TurnStatus
from pema.care.models import ControlState
from pema.care.reminders import LATE_ORIGINAL_AT, REMINDER_KINDS
from pema.care.routing_types import DueReminder, ReminderStatus, RoutingConfig
from pema.care.testing import AlwaysAutoSend
from pema.care.testing_routing import MONDAY_10, REF, RoutingRig, make_routing_rig, staff_context

DAY = timedelta(days=1)
DELAYS: tuple[timedelta, ...] = (
    timedelta(hours=6),
    DAY,
    3 * DAY,
    5 * DAY,
    6 * DAY,
    10 * DAY,
    30 * DAY,
    60 * DAY,
)
LABEL_PREFIX = "(nhắc trễ, lịch gốc "
RULE_OF_KIND: dict[EventKind, str | None] = {
    EventKind.MILESTONE_DUE: "d3",
    EventKind.VISIT_OVERDUE: "overdue",
    EventKind.NO_SHOW: "no_show",
    EventKind.DORMANT: "dormant90",
    EventKind.BIRTHDAY: "birthday",
    EventKind.SESSION_COMPLETED: None,
}
"""The CRM rule that produces each kind of event (``event_kind_for_rule``); the text is keyed by it."""


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
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    me = uuid4()
    await rig.control.accept(staff_context(me), rig.agent.patient_id)
    return me


@dataclass
class Tally:
    name: str
    total: int = 0
    passed: int = 0
    failures: list[str] = field(default_factory=list[str])

    def check(self, ok: bool, label: str) -> None:
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failures.append(label)


@dataclass(frozen=True)
class ReminderReport:
    tallies: list[Tally]
    resumed: int
    dropped_past_meaning: int
    dropped_superseded: int
    sent_by_hand_not_resumed: int
    sent_to_patient_while_staff: int
    """Messages that reached the patient while a person had the conversation (must be 0)."""
    model_calls_while_staff: int
    late_label_ok: int
    late_label_checked: int
    scenarios: int
    failures: list[str]


async def _sent_count(rig: RoutingRig) -> int:
    return len(rig.channel.sent)


async def _release_and_run(rig: RoutingRig, me: UUID) -> list[TurnStatus]:
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "done")
    statuses: list[TurnStatus] = []
    while (item := rig.queue.pop_nowait()) is not None:
        statuses.append((await rig.runner.run_turn(item.care_agent_id, item.event)).status)
    return statuses


async def measure_reminders() -> ReminderReport:
    cfg = RoutingConfig().reminders
    pause = Tally("paused in STAFF: nothing sent, no model, no task, one record")
    routing_pause = Tally("paused while the round is still routing")
    matrix = Tally("released after 6 h ... 60 d: resumed or dropped by the window of its type")
    series = Tally("D+1 dropped once D+3 of the same series is due")
    named = Tally("other acceptance scenarios (duplicate, reply in STAFF, hand-sent, nothing paused, queued)")
    totals = {
        "resumed": 0,
        "past": 0,
        "superseded": 0,
        "hand": 0,
        "sent_staff": 0,
        "models": 0,
        "label_ok": 0,
        "label_n": 0,
    }

    kinds = sorted(REMINDER_KINDS, key=lambda kind: kind.value)

    # ---- paused in STAFF, every kind
    for kind in kinds:
        rig = make_routing_rig(autonomy=AlwaysAutoSend())
        await to_staff(rig)
        before = await _sent_count(rig)
        calls = rig.harness.calls + len(rig.llm.calls)
        rule = RULE_OF_KIND.get(kind)
        outcome = await rig.runner.run_turn(rig.agent.id, reminder_event(rule, MONDAY_10, kind=kind))
        sent = await _sent_count(rig) - before
        models = rig.harness.calls + len(rig.llm.calls) - calls
        needs_text = rule is not None and rule in cfg.prepared_texts
        totals["sent_staff"] += sent
        totals["models"] += models
        pause.check(
            outcome.status is TurnStatus.REMINDER_PAUSED
            and sent == 0
            and models == 0
            and len(rig.queue) == 0
            and len(rig.reminder_store.rows) == 1
            and rig.reminder_store.rows[0].status is ReminderStatus.PAUSED
            and (rig.reminder_store.rows[0].prepared_text is not None or not needs_text),
            f"STAFF {kind.value}",
        )

    # ---- paused while routing
    for kind in kinds:
        rig = make_routing_rig(autonomy=AlwaysAutoSend())
        rig.directory.add_staff("cs_staff")
        await rig.open_round(Depth.D2, Urgency.NORMAL)
        before = await _sent_count(rig)
        outcome = await rig.runner.run_turn(rig.agent.id, reminder_event(None, MONDAY_10, kind=kind))
        sent = await _sent_count(rig) - before
        totals["sent_staff"] += sent
        routing_pause.check(
            rig.state is ControlState.HANDOFF_ROUTING
            and outcome.status is TurnStatus.REMINDER_PAUSED
            and sent == 0
            and len(rig.reminder_store.rows) == 1,
            f"ROUTING {kind.value}",
        )

    # ---- matrix: every type released after every delay
    types: list[tuple[str | None, EventKind]] = [
        ("d1", EventKind.MILESTONE_DUE),
        ("d3", EventKind.MILESTONE_DUE),
        ("d7", EventKind.MILESTONE_DUE),
        (None, EventKind.MILESTONE_DUE),
        (None, EventKind.VISIT_OVERDUE),
        (None, EventKind.NO_SHOW),
        (None, EventKind.DORMANT),
        (None, EventKind.SESSION_COMPLETED),
        (None, EventKind.BIRTHDAY),
    ]
    for rule, kind in types:
        key = rule if rule is not None else kind.value
        for delay in DELAYS:
            rig = make_routing_rig(autonomy=AlwaysAutoSend())
            me = await to_staff(rig)
            await rig.runner.run_turn(rig.agent.id, reminder_event(rule, MONDAY_10, kind=kind))
            rig.clock.advance(delay)
            sent_before = await _sent_count(rig)
            statuses = await _release_and_run(rig, me)
            (row,) = rig.reminder_store.rows
            expect_resumed = delay <= cfg.max_late(key)
            label = f"{key} released after {delay}"
            if expect_resumed:
                ok = row.status is ReminderStatus.RESUMED and len(statuses) == 1
                totals["resumed"] += 1
                new_texts = [text for _, text, _ in rig.channel.sent[sent_before:]]
                if new_texts:
                    totals["label_n"] += 1
                    totals["label_ok"] += 1 if new_texts[0].startswith(LABEL_PREFIX) else 0
                    ok = ok and new_texts[0].startswith(LABEL_PREFIX)
                ok = ok and rig.queue.pop_nowait() is None
                if kind is EventKind.BIRTHDAY:  # a birthday is never sent by the agent: a draft for staff
                    ok = ok and not new_texts and statuses == [TurnStatus.DRAFTED]
            else:
                ok = (
                    row.status is ReminderStatus.DROPPED
                    and row.resolution == "past_meaning"
                    and statuses == []
                    and f"reminder:dropped:past_meaning:{key}" in rig.actions()
                )
                totals["past"] += 1
            matrix.check(ok, label)

    # ---- series: D+1 and D+3 of the same anchor
    for delay in (DAY, 2 * DAY, 3 * DAY, 5 * DAY, 6 * DAY, 10 * DAY):
        rig = make_routing_rig(autonomy=AlwaysAutoSend())
        me = await to_staff(rig)
        d3_due = MONDAY_10 + 2 * DAY
        await rig.runner.run_turn(rig.agent.id, reminder_event("d1", MONDAY_10, anchor="S1"))
        await rig.runner.run_turn(rig.agent.id, reminder_event("d3", d3_due, anchor="S1"))
        rig.clock.advance(delay)
        await _release_and_run(rig, me)
        by_rule = {row.rule: row for row in rig.reminder_store.rows}
        d3_is_due = rig.clock.now >= d3_due
        d1_expected = (
            ReminderStatus.DROPPED if d3_is_due or delay > cfg.max_late("d1") else ReminderStatus.RESUMED
        )
        d3_expected = (
            ReminderStatus.RESUMED if rig.clock.now - d3_due <= cfg.max_late("d3") else ReminderStatus.DROPPED
        )
        ok = by_rule["d1"].status is d1_expected and by_rule["d3"].status is d3_expected
        if d3_is_due and delay <= cfg.max_late("d1"):
            ok = ok and by_rule["d1"].resolution == "superseded"
            totals["superseded"] += 1
        series.check(ok, f"d1+d3 released after {delay}")

    # ---- named scenarios
    # a duplicate delivery is one record
    rig = make_routing_rig()
    await to_staff(rig)
    event = reminder_event("d3", MONDAY_10)
    await rig.runner.run_turn(rig.agent.id, event)
    await rig.runner.run_turn(rig.agent.id, event)
    named.check(
        len(rig.reminder_store.rows) == 1 and rig.actions().count("reminder:paused:d3") == 1,
        "duplicate event",
    )

    # the daily tick and staff events are not reminders
    rig = make_routing_rig()
    await to_staff(rig)
    statuses = [
        (await rig.runner.run_turn(rig.agent.id, reminder_event(None, MONDAY_10, kind=kind))).status
        for kind in (EventKind.DAILY_TICK, EventKind.STAFF_COMMAND, EventKind.DOCTOR_EDIT)
    ]
    named.check(
        statuses == [TurnStatus.SKIPPED_STATE] * 3 and rig.reminder_store.rows == [],
        "tick and staff events are not reminders",
    )

    # a patient's reply in STAFF goes to staff; the agent writes only a suggestion
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    await to_staff(rig)
    before = await _sent_count(rig)
    reply = await rig.message()
    sent = await _sent_count(rig) - before
    totals["sent_staff"] += sent
    named.check(reply.status is TurnStatus.SUGGESTED and sent == 0, "reply in STAFF goes to the person")

    # a reminder sent by hand is not resumed
    rig = make_routing_rig(autonomy=AlwaysAutoSend())
    me = await to_staff(rig)
    await rig.runner.run_turn(rig.agent.id, reminder_event("d3", MONDAY_10))
    (paused,) = rig.reminder_store.rows
    first = await rig.reminders.mark_sent_by_staff(staff_context(me), paused.id)
    again = await rig.reminders.mark_sent_by_staff(staff_context(me), paused.id)
    rig.clock.advance(DAY)
    statuses = await _release_and_run(rig, me)
    hand_ok = (
        first
        and not again
        and statuses == []
        and rig.reminder_store.rows[0].status is ReminderStatus.SENT_BY_STAFF
    )
    totals["hand"] += 1 if hand_ok else 0
    named.check(hand_ok, "sent by hand is never resumed")

    # nothing paused: release changes nothing
    rig = make_routing_rig()
    me = await to_staff(rig)
    statuses = await _release_and_run(rig, me)
    named.check(
        rig.state is ControlState.AUTO and statuses == [] and rig.reminder_store.rows == [],
        "release with nothing paused",
    )

    # reminders already queued in S/B2 when the round opens are paused and held
    queued = [
        DueReminder(EventKind.MILESTONE_DUE, "d3", MONDAY_10, "s:d3", REF, {"anchor": "S1"}),
        DueReminder(EventKind.VISIT_OVERDUE, "overdue", MONDAY_10, "s:overdue", REF),
    ]
    rig = make_routing_rig(reminders_due=queued)
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    named.check(
        sorted(r.dedupe_key for r in rig.reminder_store.rows) == ["s:d3", "s:overdue"]
        and sorted(rig.due.held) == ["s:d3", "s:overdue"],
        "reminders already queued are paused and held",
    )

    # the reconciled event carries the original schedule
    rig = make_routing_rig()
    me = await to_staff(rig)
    await rig.runner.run_turn(rig.agent.id, reminder_event("d3", MONDAY_10, anchor="S1"))
    rig.clock.advance(DAY)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "done")
    item = rig.queue.pop_nowait()
    named.check(
        item is not None
        and item.event.payload.get(LATE_ORIGINAL_AT) == MONDAY_10.isoformat()
        and item.event.payload.get("rule") == "d3",
        "the resumed event carries the original schedule",
    )

    tallies = [pause, routing_pause, matrix, series, named]
    return ReminderReport(
        tallies=tallies,
        resumed=totals["resumed"],
        dropped_past_meaning=totals["past"],
        dropped_superseded=totals["superseded"],
        sent_by_hand_not_resumed=totals["hand"],
        sent_to_patient_while_staff=totals["sent_staff"],
        model_calls_while_staff=totals["models"],
        late_label_ok=totals["label_ok"],
        late_label_checked=totals["label_n"],
        scenarios=sum(t.total for t in tallies),
        failures=[f"{t.name}: {f}" for t in tallies for f in t.failures][:30],
    )

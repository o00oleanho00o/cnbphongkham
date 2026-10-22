"""Reminders as cases on the case engine (docs/PLAN-case-loop.md 6, PLAN-crm-plugin.md 3.5, 3.7): every rule
that stops a reminder, the quiet hours, one reminder per mark however often the loop wakes, the wait for the
mark, an event of the CRM ending a waiting case at once, a failed send checked again before it is retried, the
daily cap shared with every case, and reconciliation with the CRM. The engine is the real one with its memory
store; a fake outbox stands for the chat's queue."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from agent_app.cases import CaseEngine, CasesConfig, InMemoryCaseStore
from agent_app.plugins import Cases, PluginError, PluginHost, ProactiveSent, discover
from agent_app.runtime import BUNDLED_PLUGINS
from agentcore.cases import CASE_MARK, CaseRecord
from plugins.crm.client import CrmClient
from plugins.crm.reminders import (
    KIND,
    Mark,
    ReminderCase,
    ReminderPolicy,
    Reminders,
    case_key,
    decide,
    instruction_for,
    reminder_case,
)
from plugins.crm.store import MemoryReminderStore, Person, Visit

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
POLICY = ReminderPolicy(zone=ZONE)
DAY, HOURS3 = POLICY.marks
VISIT_AT = datetime(2026, 10, 23, 14, 0, tzinfo=ZONE)
BOOKED_AT = datetime(2026, 10, 20, 10, 0, tzinfo=ZONE)


def _visit(**over: Any) -> Visit:
    base = Visit(
        appointment_id=uuid4(),
        channel="zalo-a",
        external_id="u1",
        starts_at=VISIT_AT,
        duration_min=30,
        status="booked",
        version=1,
        changed_at=BOOKED_AT,
        actor_type="agent",
        last_event_id=uuid4(),
    )
    return replace(base, **over)


PERSON = Person("zalo-a", "u1", True, BOOKED_AT, "u1")


# --- decide: one test per rule -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("visit", "person", "mark", "now", "sent_today", "verdict", "reason"),
    [
        (_visit(), PERSON, DAY, VISIT_AT - timedelta(hours=24), 0, "send", ""),
        (_visit(status="cancelled"), PERSON, DAY, VISIT_AT - timedelta(hours=24), 0, "skip", "over"),
        (_visit(), PERSON, HOURS3, VISIT_AT + timedelta(minutes=1), 0, "skip", "over"),
        (
            _visit(),
            replace(PERSON, messages_consent=None),
            DAY,
            VISIT_AT - timedelta(hours=24),
            0,
            "skip",
            "no_consent",
        ),
        (_visit(), None, DAY, VISIT_AT - timedelta(hours=24), 0, "skip", "no_consent"),
        (_visit(status="confirmed"), PERSON, DAY, VISIT_AT - timedelta(hours=24), 0, "skip", "confirmed"),
        (_visit(status="confirmed"), PERSON, HOURS3, VISIT_AT - timedelta(hours=3), 0, "send", ""),
        (
            _visit(
                changed_at=VISIT_AT - timedelta(hours=2)
            ),  # booked two hours before: both marks had passed
            PERSON,
            HOURS3,
            VISIT_AT - timedelta(hours=1),
            0,
            "skip",
            "set_after_mark",
        ),
        (_visit(), PERSON, DAY, VISIT_AT - timedelta(hours=5), 0, "skip", "too_late"),
        (_visit(), PERSON, HOURS3, VISIT_AT - timedelta(minutes=20), 0, "skip", "too_late"),
        (
            _visit(),
            replace(PERSON, conversation_id=None),
            DAY,
            VISIT_AT - timedelta(hours=24),
            0,
            "skip",
            "no_chat",
        ),
        (_visit(), PERSON, DAY, VISIT_AT - timedelta(hours=24), 2, "skip", "daily_cap"),
    ],
)
def test_each_rule_of_the_decision(
    visit: Visit, person: Person | None, mark: Mark, now: datetime, sent_today: int, verdict: str, reason: str
) -> None:
    decision = decide(POLICY, visit, person, mark, now, POLICY.per_day - sent_today)
    assert (decision.verdict, decision.reason) == (verdict, reason)


def test_in_the_quiet_hours_a_due_reminder_waits_for_their_end() -> None:
    now = datetime(2026, 10, 22, 22, 30, tzinfo=ZONE)
    visit = _visit(starts_at=datetime(2026, 10, 23, 22, 0, tzinfo=ZONE))  # its 24h mark fell at 22:00
    decision = decide(POLICY, visit, PERSON, DAY, now, POLICY.per_day)

    assert decision.verdict == "wait"
    assert decision.until == datetime(2026, 10, 23, 7, 0, tzinfo=ZONE)


def test_the_policy_reads_its_settings_and_refuses_nonsense() -> None:
    policy = ReminderPolicy.of(
        {"reminder_marks": "48:720,2:20", "quiet_hours": "22:00-06:30", "reminders_per_day": 1}, ZONE
    )
    assert [(m.hours, m.min_left) for m in policy.marks] == [
        (48, timedelta(hours=12)),
        (2, timedelta(minutes=20)),
    ]
    assert (policy.quiet_from, policy.quiet_to, policy.per_day) == (time(22), time(6, 30), 1)
    with pytest.raises(ValueError, match="positive"):
        ReminderPolicy.of({"reminder_marks": "0:30"}, ZONE)
    with pytest.raises(ValueError, match="values to unpack"):
        ReminderPolicy.of({"quiet_hours": "late"}, ZONE)


def _case(visit: Visit, mark: Mark = DAY) -> ReminderCase:
    return ReminderCase(
        appointment_id=visit.appointment_id, starts_at=visit.starts_at, mark=mark.name, status=visit.status
    )


def test_the_instruction_carries_the_time_written_by_code_and_a_way_to_decline() -> None:
    visit = _visit()
    text = instruction_for(_case(visit), VISIT_AT - timedelta(hours=3), ZONE)

    assert "14:00 hôm nay (23/10/2026)" in text
    assert str(visit.appointment_id) in text
    assert "SKIP" in text
    assert "ngày mai" in instruction_for(_case(visit), VISIT_AT - timedelta(hours=24), ZONE)


# --- the cases on the engine -----------------------------------------------------------------------


class Outbox:
    """The chat's queue: records each turn; ``fail`` makes the next sends raise (the queue is unreachable)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = 0

    async def send_to(self, **message: str) -> ProactiveSent:
        if self.fail:
            self.fail -= 1
            raise ConnectionError("the queue is unreachable")
        self.sent.append(message)
        return ProactiveSent(True)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class World:
    """The plugin's store and loop, the engine with its memory store, one outbox and one clock."""

    def __init__(self, now: datetime, *, ready: bool = True) -> None:
        self.clock = Clock(now)
        self.store = MemoryReminderStore(now=self.clock)
        self.outbox = Outbox()
        self.config = CasesConfig(enabled=True, per_person_per_day=2)
        self.ready = ready
        self.cases = InMemoryCaseStore()
        self.reminders = Reminders(
            self.store, lambda: Cases(self.engine, "crm"), self._ready, POLICY, None, clock=self.clock
        )
        spec = reminder_case(self.reminders)
        self.engine = CaseEngine(
            self.cases,
            lambda: {KIND: ("crm", spec)},
            config=lambda: self.config,
            zone=lambda: ZONE,
            clock=self.clock,
        )

        async def session_for(channel: str, conversation_id: str) -> str:
            return f"session-{conversation_id}"

        self.engine.attach(self.outbox, session_for)

    def _ready(self) -> Outbox:
        if not self.ready:
            raise PluginError("crm", "no running service")
        return self.outbox

    async def add(self, *visits: Visit, person: Person | None = PERSON) -> None:
        for v in visits:
            await self.store.apply_visit(v)
        if person is not None:
            await self.store.apply_consent(
                person.channel, person.external_id, person.messages_consent, BOOKED_AT
            )
            if person.conversation_id:
                await self.store.remember_chat(person.channel, person.external_id, person.conversation_id)

    async def run(self) -> None:
        """One pass of the loop (opens cases), then one of the engine (runs what is due)."""
        await self.reminders.pass_once()
        await self.engine.pass_once()

    async def case(self, visit: Visit, mark: Mark = DAY) -> CaseRecord:
        key = case_key(visit.appointment_id, visit.starts_at, mark.name)
        found = [r for r in await self.cases.list() if r.key == key]
        assert len(found) == 1
        return found[0]


async def test_a_due_mark_is_sent_once_to_the_persons_chat_however_often_the_loop_wakes() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23, minutes=50))
    await world.add(visit)

    await world.run()
    await world.run()

    (sent,) = world.outbox.sent
    assert (sent["channel"], sent["conversation_id"], sent["user_id"]) == ("zalo-a", "u1", "u1")
    assert sent["message_id"].startswith("case:")
    assert sent["instruction"].startswith(CASE_MARK)
    assert "14:00 ngày mai" in sent["instruction"]
    assert (await world.case(visit)).status == "done"
    waiting = await world.case(visit, HOURS3)  # opened too, waiting for its own mark
    assert (waiting.status, waiting.wake_at) == ("waiting", VISIT_AT - timedelta(hours=3))

    world.clock.now = VISIT_AT - timedelta(hours=2, minutes=55)
    await world.run()
    assert len(world.outbox.sent) == 2


async def test_a_case_waits_for_its_mark_by_the_clock() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=24, minutes=30))
    await world.add(visit)

    await world.run()
    assert world.outbox.sent == []
    assert (await world.case(visit)).wake_at == VISIT_AT - timedelta(hours=24)

    world.clock.now = VISIT_AT - timedelta(hours=24)
    await world.engine.pass_once()
    assert len(world.outbox.sent) == 1


async def test_a_skipped_mark_ends_its_case_with_the_reason_and_is_never_opened_again() -> None:
    visit = _visit(status="confirmed")
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(visit)

    await world.run()
    await world.run()

    assert world.outbox.sent == []
    case = await world.case(visit)
    assert (case.status, case.end_reason) == ("stopped", "skip:confirmed")


async def test_an_event_ends_the_waiting_cases_of_a_cancelled_visit_at_once() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=24, minutes=30))
    await world.add(visit)
    await world.run()

    world.clock.now = VISIT_AT - timedelta(hours=24, minutes=20)
    await world.store.apply_visit(replace(visit, status="cancelled", version=2))
    await world.reminders.changed(visit)
    await world.engine.pass_once()

    assert world.outbox.sent == []
    for mark in (DAY, HOURS3):
        case = await world.case(visit, mark)
        assert (case.status, case.end_reason, case.closed_at) == ("stopped", "skip:over", world.clock.now)


async def test_a_moved_visit_ends_its_old_cases_and_gets_the_marks_of_its_new_time() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(visit)
    await world.run()
    assert len(world.outbox.sent) == 1

    moved = replace(visit, starts_at=VISIT_AT + timedelta(days=1), version=2)
    world.clock.now = VISIT_AT - timedelta(hours=20)
    await world.store.apply_visit(replace(moved, changed_at=world.clock.now))
    await world.reminders.changed(visit)
    await world.engine.pass_once()
    assert (await world.case(visit, HOURS3)).end_reason == "skip:moved"

    world.clock.now = moved.starts_at - timedelta(hours=23)
    await world.run()
    assert len(world.outbox.sent) == 2
    assert (await world.case(moved)).status == "done"


async def test_quiet_hours_send_nothing_and_wait_for_their_end() -> None:
    late = datetime(2026, 10, 22, 23, 0, tzinfo=ZONE)
    visit = _visit(starts_at=late + timedelta(hours=23))
    world = World(late)
    await world.add(visit)

    await world.run()
    assert world.outbox.sent == []
    assert (await world.case(visit)).wake_at == datetime(2026, 10, 23, 7, 0, tzinfo=ZONE)

    world.clock.now = datetime(2026, 10, 23, 7, 0, tzinfo=ZONE)
    await world.engine.pass_once()
    assert len(world.outbox.sent) == 1


async def test_two_messages_a_day_at_most_per_person_and_the_third_mark_is_skipped() -> None:
    visits = [_visit(starts_at=VISIT_AT + timedelta(minutes=i)) for i in range(3)]
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(*visits)

    await world.run()

    assert len(world.outbox.sent) == 2
    reasons = {(await world.case(v)).end_reason for v in visits}
    assert reasons == {"end of the graph", "skip:daily_cap"}


async def test_a_mark_handled_before_the_switch_is_not_opened_again() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(visit)
    await world.store.claim_mark(visit, DAY.name, "sent")

    await world.run()

    assert world.outbox.sent == []
    assert [r.key for r in await world.cases.list()] == [case_key(visit.appointment_id, VISIT_AT, "3h")]


async def test_nothing_is_claimed_or_opened_while_the_service_cannot_send() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23), ready=False)
    await world.add(visit)

    assert await world.reminders.pass_once() == 0
    assert await world.store.handled([visit.appointment_id]) == set()


async def test_a_send_that_failed_is_checked_again_and_a_visit_cancelled_meanwhile_gets_nothing() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(visit)
    world.outbox.fail = 1

    await world.run()
    case = await world.case(visit)
    assert (case.node, case.status, case.state["retries"]) == ("check", "waiting", 1)

    await world.store.apply_visit(replace(visit, status="cancelled", version=2))
    world.clock.now += timedelta(minutes=5)
    await world.engine.pass_once()

    assert world.outbox.sent == []
    assert (await world.case(visit)).end_reason == "skip:over"


async def test_a_failed_send_goes_out_once_if_the_check_still_holds_and_three_failures_end_it() -> None:
    visit = _visit()
    world = World(VISIT_AT - timedelta(hours=23))
    await world.add(visit)
    world.outbox.fail = 1

    await world.run()
    world.clock.now += timedelta(minutes=5)
    await world.engine.pass_once()
    await world.engine.pass_once()
    assert len(world.outbox.sent) == 1

    other = _visit(starts_at=VISIT_AT + timedelta(hours=1))
    await world.add(other)
    world.outbox.fail = 10
    for _ in range(4):
        await world.run()
        world.clock.now += timedelta(minutes=5)
    case = await world.case(other)
    assert (case.status, case.end_reason) == ("stopped", "retries reached 3")
    assert len(world.outbox.sent) == 1


async def test_with_cases_switched_off_nothing_is_sent() -> None:
    world = World(VISIT_AT - timedelta(hours=23))
    world.config = CasesConfig(enabled=False)
    await world.add(_visit())

    await world.run()

    assert world.outbox.sent == []


# --- reconciliation --------------------------------------------------------------------------------


async def test_reconciliation_adds_what_the_crm_lists_and_marks_gone_what_it_no_longer_does() -> None:
    now = VISIT_AT - timedelta(hours=30)
    known_gone = _visit(starts_at=VISIT_AT + timedelta(hours=1))
    missed_id = uuid4()
    listed = [
        {
            "appointment_id": str(missed_id),
            "channel": "zalo-a",
            "external_id": "u1",
            "starts_at": VISIT_AT.isoformat(),
            "duration_min": 30,
            "status": "booked",
            "updated_at": BOOKED_AT.isoformat(),
        }
    ]
    seen: list[httpx.Request] = []

    def crm(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=listed)

    client = CrmClient(
        "http://crm-signer:8090/agent-gateway", timeout_s=5, transport=httpx.MockTransport(crm)
    )
    clock = Clock(now)
    store = MemoryReminderStore(now=clock)
    await store.apply_visit(known_gone)
    await store.apply_consent("zalo-a", "u1", True, BOOKED_AT)

    def no_cases() -> Cases:
        raise PluginError("crm", "no running service")

    await Reminders(store, no_cases, Outbox, POLICY, client, clock=clock).reconcile()

    assert seen[0].url.path.endswith("/reminders")
    assert seen[0].url.params["hours"] == "48"
    added = await store.visit(missed_id)
    assert added is not None
    assert (added.version, added.actor_type) == (0, "reconcile")
    gone = await store.visit(known_gone.appointment_id)
    assert gone is not None
    assert gone.status == "gone"
    # an event of the CRM still wins over what reconciliation wrote
    assert await store.apply_visit(replace(added, version=1, status="cancelled"))


# --- wiring --------------------------------------------------------------------------------------


def test_the_loop_and_its_case_come_only_when_switched_on() -> None:
    def added(config: dict[str, Any]) -> tuple[list[str], list[str]]:
        host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, {})
        host.enable("crm", config)
        found = host.contributions()
        return [j.name for j in found.jobs], [spec.kind for _, spec in found.cases]

    assert added({}) == ([], [])
    assert added({"reminders_enabled": True}) == (["reminders"], [KIND])

"""The reminder loop (docs/PLAN-crm-plugin.md 3.5, 3.7): every rule that stops a reminder, the quiet hours, one
reminder per mark however often the loop wakes, claimed before it is sent, the daily cap, and reconciliation
with the CRM. A fake outbox stands for ``ctx.proactive``; the store is the memory one (Postgres: _db file)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from agent_app.plugins import PluginError, PluginHost, ProactiveSent, discover
from agent_app.runtime import BUNDLED_PLUGINS
from plugins.crm.client import CrmClient
from plugins.crm.reminders import (
    INSTRUCTION_MARK,
    Mark,
    ReminderPolicy,
    Reminders,
    decide,
    instruction_for,
    message_id,
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
    decision = decide(POLICY, visit, person, mark, now, sent_today)
    assert (decision.verdict, decision.reason) == (verdict, reason)


def test_in_the_quiet_hours_a_due_reminder_waits_for_their_end() -> None:
    now = datetime(2026, 10, 22, 22, 30, tzinfo=ZONE)
    visit = _visit(starts_at=datetime(2026, 10, 23, 22, 0, tzinfo=ZONE))  # its 24h mark fell at 22:00
    decision = decide(POLICY, visit, PERSON, DAY, now, 0)

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


def test_the_instruction_carries_the_time_written_by_code_and_a_way_to_decline() -> None:
    visit = _visit()
    text = instruction_for(visit, VISIT_AT - timedelta(hours=3), ZONE)

    assert text.startswith(INSTRUCTION_MARK)
    assert "14:00 hôm nay (23/10/2026)" in text
    assert str(visit.appointment_id) in text
    assert "SKIP" in text
    assert "ngày mai" in instruction_for(visit, VISIT_AT - timedelta(hours=24), ZONE)


# --- the loop ------------------------------------------------------------------------------------


class Outbox:
    def __init__(self, counted: bool = True) -> None:
        self.sent: list[dict[str, str]] = []
        self.counted = counted

    async def send_to(self, **message: str) -> ProactiveSent:
        self.sent.append(message)
        return ProactiveSent(self.counted)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _loop(
    *visits: Visit, person: Person | None = PERSON, now: datetime, outbox: Outbox | None = None
) -> tuple[Reminders, MemoryReminderStore, Outbox, Clock]:
    clock = Clock(now)
    store = MemoryReminderStore(now=clock)
    for v in visits:
        await store.apply_visit(v)
    if person is not None:
        await store.apply_consent(person.channel, person.external_id, person.messages_consent, BOOKED_AT)
        if person.conversation_id:
            await store.remember_chat(person.channel, person.external_id, person.conversation_id)
    box = outbox or Outbox()
    return Reminders(store, lambda: box, POLICY, None, clock=clock), store, box, clock


async def test_a_due_mark_is_sent_once_to_the_persons_chat_however_often_the_loop_wakes() -> None:
    visit = _visit()
    loop, _, box, clock = await _loop(visit, now=VISIT_AT - timedelta(hours=23, minutes=50))

    next_at = await loop.pass_once()
    await loop.pass_once()

    (sent,) = box.sent
    assert (sent["channel"], sent["conversation_id"], sent["user_id"]) == ("zalo-a", "u1", "u1")
    assert sent["message_id"] == message_id(visit, DAY)
    assert "14:00 ngày mai" in sent["instruction"]
    assert next_at == VISIT_AT - timedelta(hours=3)  # the next mark is when it wakes next

    clock.now = VISIT_AT - timedelta(hours=2, minutes=55)
    await loop.pass_once()
    assert len(box.sent) == 2


async def test_a_skipped_mark_is_recorded_with_its_reason_and_never_looked_at_again() -> None:
    visit = _visit(status="confirmed")
    loop, store, box, _ = await _loop(visit, now=VISIT_AT - timedelta(hours=23))

    await loop.pass_once()
    await loop.pass_once()

    assert box.sent == []
    assert await store.handled([visit.appointment_id]) == {(visit.appointment_id, VISIT_AT, "24h")}
    assert await store.sent_since(BOOKED_AT) == {}  # a skip is not a reminder sent


async def test_a_moved_visit_gets_the_marks_of_its_new_time() -> None:
    visit = _visit()
    loop, store, box, clock = await _loop(visit, now=VISIT_AT - timedelta(hours=23))
    await loop.pass_once()
    moved_to = VISIT_AT + timedelta(days=1)
    clock.now = VISIT_AT - timedelta(hours=20)
    await store.apply_visit(replace(visit, starts_at=moved_to, version=2, changed_at=clock.now))
    clock.now = moved_to - timedelta(hours=23)
    await loop.pass_once()

    assert len(box.sent) == 2
    assert box.sent[1]["message_id"] == message_id(replace(visit, starts_at=moved_to), DAY)


async def test_quiet_hours_send_nothing_and_set_the_wake_for_their_end() -> None:
    late = datetime(2026, 10, 22, 23, 0, tzinfo=ZONE)
    loop, store, box, _ = await _loop(_visit(starts_at=late + timedelta(hours=23)), now=late)

    next_at = await loop.pass_once()

    assert box.sent == []
    assert next_at == datetime(2026, 10, 23, 7, 0, tzinfo=ZONE)
    assert await store.sent_since(late - timedelta(days=1)) == {}


async def test_two_reminders_a_day_at_most_per_person() -> None:
    now = VISIT_AT - timedelta(hours=23)
    visits = [_visit(starts_at=VISIT_AT + timedelta(minutes=i)) for i in range(3)]
    loop, store, box, _ = await _loop(*visits, now=now)

    await loop.pass_once()

    assert len(box.sent) == 2
    outcomes = await store.sent_since(POLICY.day_start(now))
    assert outcomes == {("zalo-a", "u1"): 2}


async def test_nothing_is_claimed_while_there_is_no_outbox() -> None:
    clock = Clock(VISIT_AT - timedelta(hours=23))
    store = MemoryReminderStore(now=clock)
    await store.apply_visit(_visit())
    await store.apply_consent("zalo-a", "u1", True, BOOKED_AT)
    await store.remember_chat("zalo-a", "u1", "u1")

    def no_outbox() -> Outbox:
        raise PluginError("crm", "no running service")

    await Reminders(store, no_outbox, POLICY, None, clock=clock).pass_once()

    assert await store.sent_since(BOOKED_AT) == {}


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

    await Reminders(store, Outbox, POLICY, client, clock=clock).reconcile()

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


def test_the_loop_runs_only_when_switched_on() -> None:
    def jobs(config: dict[str, Any]) -> list[str]:
        host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, {})
        host.enable("crm", config)
        return [j.name for j in host.contributions().jobs]

    assert jobs({}) == []
    assert jobs({"reminders_enabled": True}) == ["reminders"]

"""The reminder loop (docs/PLAN-crm-plugin.md 3.5, 3.6 V1 and V3), in the owner's frame of a loop
(docs/IDEAS-agent-loops.md 5):

* trigger: the clock reaching a mark (``starts_at`` minus 24 or 3 hours), or an event of the CRM that changed
  a visit (``wake``); a local one-hour safety net, never a poll of the CRM;
* goal: the person hears of their visit once per mark, in time, only if they agreed;
* verify: ``decide`` reads the local state again right before each send;
* stop: every rule of ``decide`` that skips (visit over, cancelled, no consent, set after the mark, too late,
  daily cap) and the claim row that makes a mark happen at most once;
* memory: ``crm_reminder`` (visits), ``crm_person`` (consent, chat), ``crm_reminder_sent`` (marks handled).

The thresholds are data (``ReminderPolicy``, from the plugin's settings), not code, so they can be tuned or
replaced by a schema without touching the loop. Reconciliation (V3) asks the CRM once at start and every 24
hours for the visits it would remind of, to patch events the outbox gave up on.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Final, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from agent_app.plugins import PluginError, Proactive

from .client import CrmClient, CrmError
from .store import ACTIVE, Person, ReminderStore, Visit

INSTRUCTION_MARK: Final = "[Hệ thống · nhắc lịch]"
"""Starts the instruction the loop gives the agent; it marks the text as not the customer's words."""
SAFETY_NET: Final = timedelta(hours=1)
RECONCILE_EVERY: Final = timedelta(hours=24)
RECONCILE_RETRY: Final = timedelta(hours=1)
RECONCILE_HOURS: Final = 48
NO_EVENT: Final = UUID(int=0)
"""``last_event_id`` of a visit learnt by reconciliation rather than by an event."""
WEEKDAYS: Final = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Mark:
    hours: int
    """The reminder goes out this many hours before the visit."""
    min_left: timedelta
    """Skipped when less than this is left before the visit (a late reminder is noise)."""

    @property
    def name(self) -> str:
        return f"{self.hours}h"


@dataclass(frozen=True, slots=True)
class ReminderPolicy:
    marks: tuple[Mark, ...] = (Mark(24, timedelta(hours=6)), Mark(3, timedelta(minutes=30)))
    quiet_from: time = time(21, 0)
    quiet_to: time = time(7, 0)
    per_day: int = 2
    """Reminders one person may get in one local day."""
    zone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Ho_Chi_Minh"))

    @classmethod
    def of(cls, config: Mapping[str, Any], zone: ZoneInfo) -> ReminderPolicy:
        """From the plugin's settings: ``reminder_marks`` ("24:360,3:30", hours:minimum minutes left),
        ``quiet_hours`` ("21:00-07:00"), ``reminders_per_day``."""
        marks = tuple(
            Mark(int(h), timedelta(minutes=int(m)))
            for h, m in (
                part.split(":") for part in str(config.get("reminder_marks") or "24:360,3:30").split(",")
            )
        )
        start, end = str(config.get("quiet_hours") or "21:00-07:00").split("-")
        per_day = int(config.get("reminders_per_day") or 2)
        if not marks or any(m.hours <= 0 for m in marks) or per_day < 1:
            raise ValueError("reminder_marks and reminders_per_day must be positive")
        return cls(marks, time.fromisoformat(start), time.fromisoformat(end), per_day, zone)

    def quiet_until(self, now: datetime) -> datetime | None:
        """The end of the quiet hours ``now`` falls in, or None outside them."""
        local = now.astimezone(self.zone)
        clock = local.time()
        overnight = self.quiet_from > self.quiet_to
        inside = (
            (clock >= self.quiet_from or clock < self.quiet_to)
            if overnight
            else (self.quiet_from <= clock < self.quiet_to)
        )
        if not inside:
            return None
        end = datetime.combine(local.date(), self.quiet_to, self.zone)
        return end if end > local else end + timedelta(days=1)

    def day_start(self, now: datetime) -> datetime:
        local = now.astimezone(self.zone)
        return datetime.combine(local.date(), time(0), self.zone)


Verdict = Literal["send", "skip", "wait"]


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    reason: str = ""
    until: datetime | None = None
    """``wait`` only: when to look again."""


def due_at(visit: Visit, mark: Mark) -> datetime:
    return visit.starts_at - timedelta(hours=mark.hours)


def decide(
    policy: ReminderPolicy, visit: Visit, person: Person | None, mark: Mark, now: datetime, sent_today: int
) -> Decision:
    """Whether the due ``mark`` of ``visit`` goes out now; pure, so every rule has its own test."""
    if visit.status not in ACTIVE or visit.starts_at <= now:
        return Decision("skip", "over")
    if person is None or person.messages_consent is not True:
        return Decision("skip", "no_consent")
    if mark.hours >= 24 and visit.status == "confirmed":
        return Decision("skip", "confirmed")
    if visit.changed_at >= due_at(visit, mark):
        return Decision("skip", "set_after_mark")
    if visit.starts_at - now < mark.min_left:
        return Decision("skip", "too_late")
    if not person.conversation_id:
        return Decision("skip", "no_chat")
    until = policy.quiet_until(now)
    if until is not None:
        return Decision("wait", "quiet", until)
    if sent_today >= policy.per_day:
        return Decision("skip", "daily_cap")
    return Decision("send")


def instruction_for(visit: Visit, now: datetime, zone: ZoneInfo) -> str:
    """The time and date are written by code; the model only adds a greeting and must not change them."""
    at = visit.starts_at.astimezone(zone)
    today = now.astimezone(zone).date()
    when = (
        "hôm nay"
        if at.date() == today
        else "ngày mai"
        if at.date() == today + timedelta(days=1)
        else f"{WEEKDAYS[at.weekday()]}"
    )
    hour = f"{at:%H:%M}"
    day = f"{at:%d/%m/%Y}"
    ask = (
        "Lịch đã được xác nhận, chỉ cần nhắc và chúc khách."
        if visit.status == "confirmed"
        else "Mời khách trả lời 'đồng ý' để giữ lịch, hoặc nhắn nếu cần đổi giờ hay hủy."
    )
    return (
        f"{INSTRUCTION_MARK} Nhắn khách nhắc lịch hẹn ở phòng khám lúc {hour} {when} ({day}), mã lịch "
        f"{visit.appointment_id}. Giữ đúng giờ và ngày này, không đổi. {ask} Viết một tin ngắn, lịch sự, "
        "không kèm giá hay dịch vụ. Nếu cuộc trò chuyện cho thấy không nên nhắn (khách vừa nói không đến, "
        "vừa đổi lịch) thì trả lời đúng một chữ SKIP."
    )


def message_id(visit: Visit, mark: Mark) -> str:
    return f"crm-reminder:{visit.appointment_id}:{int(visit.starts_at.timestamp())}:{mark.name}"


class Reminders:
    def __init__(
        self,
        store: ReminderStore,
        proactive: Callable[[], Proactive],
        policy: ReminderPolicy,
        client: CrmClient | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._proactive = proactive
        self._policy = policy
        self._client = client
        self._clock = clock
        self._wake = asyncio.Event()
        self._reconcile_at: datetime | None = None

    def wake(self) -> None:
        """An event changed a visit or a consent: look again now."""
        self._wake.set()

    async def pass_once(self) -> datetime | None:
        """Handles every mark that is due; returns when the next one will be (None: nothing ahead)."""
        policy = self._policy
        now = self._clock()
        longest = max(m.hours for m in policy.marks)
        visits = await self._store.upcoming(now, now + timedelta(hours=longest) + SAFETY_NET)
        handled = await self._store.handled([v.appointment_id for v in visits])
        sent = await self._store.sent_since(policy.day_start(now))
        next_at: datetime | None = None
        for visit in visits:
            person = await self._store.person(visit.channel, visit.external_id)
            for mark in policy.marks:
                due = due_at(visit, mark)
                if (visit.appointment_id, visit.starts_at, mark.name) in handled:
                    continue
                if due > now:
                    next_at = due if next_at is None else min(next_at, due)
                    continue
                key = (visit.channel, visit.external_id)
                decision = decide(policy, visit, person, mark, now, sent.get(key, 0))
                if decision.verdict == "wait" and decision.until is not None:
                    next_at = decision.until if next_at is None else min(next_at, decision.until)
                    continue
                if decision.verdict == "skip":
                    await self._store.claim_mark(visit, mark.name, f"skip:{decision.reason}")
                    continue
                if person is None or not person.conversation_id:  # ``decide`` sends only with both
                    continue
                if await self._send(visit, person.conversation_id, mark, now):
                    sent[key] = sent.get(key, 0) + 1
        return next_at

    async def _send(self, visit: Visit, conversation_id: str, mark: Mark, now: datetime) -> bool:
        try:
            sender = self._proactive()
        except PluginError:
            return False  # outside ``agent serve``: try again on the next pass
        # claimed BEFORE it is sent: a crash in between loses this mark rather than sending it twice
        if not await self._store.claim_mark(visit, mark.name, "sent"):
            return False
        try:
            result = await sender.send_to(
                channel=visit.channel,
                conversation_id=conversation_id,
                user_id=visit.external_id,
                message_id=message_id(visit, mark),
                instruction=instruction_for(visit, now, self._policy.zone),
            )
        except Exception as err:  # one reminder failing never stops the loop
            logger.warning("reminder %s of a visit was not sent (%s)", mark.name, type(err).__name__)
            return True
        if not result.counted:
            logger.info("reminder %s of a visit was not sent: %s", mark.name, result.note)
        return True

    async def reconcile(self) -> None:
        """Asks the CRM which visits of the next hours it would remind of: unknown ones are added (version
        0, so any event wins), and known upcoming ones of consenting people it no longer lists are marked
        gone."""
        if self._client is None:
            return
        now = self._clock()
        rows = await self._client.call("GET", "/reminders", params={"hours": RECONCILE_HOURS})
        listed: set[UUID] = set()
        for row in rows:
            appointment_id = UUID(str(row["appointment_id"]))
            listed.add(appointment_id)
            if await self._store.visit(appointment_id) is not None:
                continue
            updated = datetime.fromisoformat(str(row["updated_at"]))
            await self._store.apply_visit(
                Visit(
                    appointment_id=appointment_id,
                    channel=str(row["channel"]),
                    external_id=str(row["external_id"]),
                    starts_at=datetime.fromisoformat(str(row["starts_at"])),
                    duration_min=int(row["duration_min"]),
                    status=str(row["status"]),
                    version=0,
                    changed_at=updated,
                    actor_type="reconcile",
                    last_event_id=NO_EVENT,
                )
            )
            await self._store.apply_consent(str(row["channel"]), str(row["external_id"]), True, updated)
        gone = await self._store.mark_gone(now, now + timedelta(hours=RECONCILE_HOURS), listed)
        logger.info("reconciled with the CRM: %d listed, %d gone", len(listed), gone)

    async def _reconcile_if_due(self) -> None:
        now = self._clock()
        if self._reconcile_at is not None and now < self._reconcile_at:
            return
        try:
            await self.reconcile()
            self._reconcile_at = now + RECONCILE_EVERY
        except (CrmError, ValueError, KeyError, TypeError) as err:
            logger.warning("reconciliation with the CRM failed (%s)", type(err).__name__)
            self._reconcile_at = now + RECONCILE_RETRY

    async def run(self) -> None:
        while True:
            self._wake.clear()
            wait = SAFETY_NET.total_seconds()
            try:
                await self._reconcile_if_due()
                next_at = await self.pass_once()
                if next_at is not None:
                    wait = min(wait, max(1.0, (next_at - self._clock()).total_seconds()))
            except asyncio.CancelledError:
                raise
            except Exception as err:  # the loop outlives any error of one pass
                logger.warning("reminder pass failed (%s)", type(err).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=wait)

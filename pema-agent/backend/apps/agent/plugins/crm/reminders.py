"""Reminders of visits as cases on the agent's case engine (docs/PLAN-case-loop.md 6): one case of kind
``reminder`` per mark of a visit (``starts_at`` minus 24 or 3 hours), in the owner's frame of a loop
(docs/IDEAS-agent-loops.md 5):

* trigger: the clock reaching the mark, or an event of the CRM that changed the visit (``changed`` wakes the
  case at once); the loop below only opens cases, every hour and after each event;
* goal: the person hears of their visit once per mark, in time, only if they agreed;
* verify: the case's ``check`` reads the local state again right before each send, also before a send that
  is tried again after an error (the error edge leads back to it);
* stop: every rule of ``decide`` that skips (visit over or moved, no consent, set after the mark, too late,
  quiet hours wait, no room left today) and the claim row that opens a mark at most once;
* memory: ``crm_reminder`` (visits), ``crm_person`` (consent, chat), ``crm_reminder_sent`` (marks opened) and
  the case's own record and log (``agent_case``).

The engine sends (``check`` then the model's turn ``send``), counts every message a person gets from all cases
and logs each step. The thresholds are data (``ReminderPolicy``, from the plugin's settings). Reconciliation
(V3) asks the CRM once at start and every 24 hours for the visits it would remind of, to patch events the
outbox gave up on.
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

from pydantic import BaseModel

from agent_app.plugins import Cases, PluginError
from agentcore.cases import Budget, CaseSpec, CodeNode, Edge, Graph, StopRules, Trigger, TurnNode
from agentcore.cases import Decision as Step

from .client import CrmClient, CrmError
from .store import ACTIVE, Person, ReminderStore, Visit

KIND: Final = "reminder"
EVENT: Final = "appointment_changed"
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
    policy: ReminderPolicy, visit: Visit, person: Person | None, mark: Mark, now: datetime, room_today: int
) -> Decision:
    """Whether the due ``mark`` of ``visit`` goes out now; pure, so every rule has its own test.
    ``room_today`` is how many more messages the person may get today (the engine's count,
    ``ctx.cases.room_today``)."""
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
    if room_today <= 0:
        return Decision("skip", "daily_cap")
    return Decision("send")


class ReminderCase(BaseModel):
    """The state of a reminder case: which mark of which visit, at the time it had when the case opened."""

    appointment_id: UUID
    starts_at: datetime
    mark: str
    status: str = "booked"
    """As ``check`` last read it; the instruction asks for a confirmation only while it is ``booked``."""
    looks: int = 0
    retries: int = 0


def case_key(appointment_id: UUID, starts_at: datetime, mark: str) -> str:
    """A visit moved to another time is another case."""
    return f"{appointment_id}:{int(starts_at.timestamp())}:{mark}"


def instruction_for(case: ReminderCase, now: datetime, zone: ZoneInfo) -> str:
    """The time and date are written by code; the model only adds a greeting and must not change them."""
    at = case.starts_at.astimezone(zone)
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
        if case.status == "confirmed"
        else "Mời khách trả lời 'đồng ý' để giữ lịch, hoặc nhắn nếu cần đổi giờ hay hủy."
    )
    return (
        f"Nhắn khách nhắc lịch hẹn ở phòng khám lúc {hour} {when} ({day}), mã lịch {case.appointment_id}. "
        f"Giữ đúng giờ và ngày này, không đổi. {ask} Viết một tin ngắn, lịch sự, không kèm giá hay dịch vụ. "
        "Nếu cuộc trò chuyện cho thấy không nên nhắn (khách vừa nói không đến, vừa đổi lịch) thì trả lời "
        "đúng một chữ SKIP."
    )


def reminder_case(reminders: Reminders) -> CaseSpec:
    """``check`` decides and waits; ``send`` is the model's one turn. A send that raised goes back through
    ``check`` (the error edge), so nothing is sent that was not checked right before."""
    policy = reminders.policy

    def goal(case: ReminderCase) -> str:
        at = case.starts_at.astimezone(policy.zone)
        return f"Khách biết lịch hẹn lúc {at:%H:%M %d/%m/%Y} (nhắc mốc {case.mark})"

    def verify(case: ReminderCase) -> str:
        return "crm_reminder: lịch còn booked hay confirmed; tin nhắc nằm trong cuộc chat"

    def instruction(case: ReminderCase, now: datetime) -> str:
        return instruction_for(case, now, policy.zone)

    return CaseSpec(
        kind=KIND,
        state_model=ReminderCase,
        goal=goal,
        triggers=(Trigger("clock"), Trigger("event", EVENT)),
        graph=Graph(
            start="check",
            nodes=(CodeNode("check", reminders.check), TurnNode("send", instruction)),
            edges=(
                Edge("check", "send"),
                Edge("check", "check", counter="looks"),
                Edge("send", "check", counter="retries", on="error"),
            ),
        ),
        verify=verify,
        stop=StopRules(
            max_turns=1, max_proactive=1, max_age=timedelta(days=2), counters={"looks": 20, "retries": 3}
        ),
        budget=Budget(per_person_per_day=policy.per_day),
    )


class Reminders:
    """Opens the cases (``pass_once``, the job ``reminders``), checks each one at its mark (``check``, the
    case's code node), wakes them on an event (``changed``) and reconciles with the CRM."""

    def __init__(
        self,
        store: ReminderStore,
        cases: Callable[[], Cases],
        ready: Callable[[], object],
        policy: ReminderPolicy,
        client: CrmClient | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """``ready`` raises ``PluginError`` while the service cannot send (only ``agent serve`` can)."""
        self._store = store
        self._cases = cases
        self._ready = ready
        self.policy = policy
        self._client = client
        self._clock = clock
        self._wake = asyncio.Event()
        self._reconcile_at: datetime | None = None

    async def pass_once(self) -> int:
        """Opens a case for every mark of the visits ahead that has none yet; how many it opened."""
        try:
            self._ready()
            cases = self._cases()
        except PluginError:
            return 0  # outside ``agent serve``: nothing is claimed, the next pass tries again
        policy = self.policy
        now = self._clock()
        longest = max(m.hours for m in policy.marks)
        visits = await self._store.upcoming(now, now + timedelta(hours=longest) + SAFETY_NET)
        handled = await self._store.handled([v.appointment_id for v in visits])
        opened = 0
        for visit in visits:
            person = await self._store.person(visit.channel, visit.external_id)
            if person is None or person.messages_consent is not True or not person.conversation_id:
                continue  # nothing claimed: consent or a chat may still come before the mark
            for mark in policy.marks:
                if (visit.appointment_id, visit.starts_at, mark.name) in handled:
                    continue
                if visit.starts_at - now < mark.min_left:
                    continue  # too late for this mark: no case to open
                # claimed BEFORE the case opens: a failure in between loses the mark rather than sending twice
                if not await self._store.claim_mark(visit, mark.name, "case"):
                    continue
                state = ReminderCase(
                    appointment_id=visit.appointment_id,
                    starts_at=visit.starts_at,
                    mark=mark.name,
                    status=visit.status,
                )
                try:
                    await cases.open(
                        KIND,
                        case_key(visit.appointment_id, visit.starts_at, mark.name),
                        channel=visit.channel,
                        conversation_id=person.conversation_id,
                        user_id=visit.external_id,
                        state=state,
                    )
                    opened += 1
                except Exception as err:  # one case failing never stops the pass
                    name = type(err).__name__
                    logger.warning("reminder %s of a visit was not opened (%s)", mark.name, name)
        return opened

    async def check(self, case: ReminderCase, now: datetime) -> Step:
        """The case's code node: waits for the mark, then reads the visit and the person again and decides."""
        mark = next((m for m in self.policy.marks if m.name == case.mark), None)
        visit = await self._store.visit(case.appointment_id)
        if mark is None:
            return Step(stop="skip:no_mark", note="the plugin's marks changed")
        if visit is None or visit.status not in ACTIVE:  # ends a woken case now, not at its mark
            return Step(stop="skip:over")
        if visit.starts_at != case.starts_at:
            return Step(stop="skip:moved")
        due = due_at(visit, mark)
        if now < due:
            return Step(next="check", wait_for="clock", wake_at=due)
        person = await self._store.person(visit.channel, visit.external_id)
        room = await self._cases().room_today(KIND, visit.channel, visit.external_id)
        verdict = decide(self.policy, visit, person, mark, now, room)
        if verdict.verdict == "wait" and verdict.until is not None:
            return Step(next="check", wait_for="clock", wake_at=verdict.until, note=verdict.reason)
        if verdict.verdict != "send":
            return Step(stop=f"skip:{verdict.reason}")
        return Step(next="send", patch={"status": visit.status})

    async def changed(self, before: Visit | None) -> None:
        """An event of the CRM was applied: the cases of the visit as it was look again now (a cancelled or
        moved visit ends them), and the loop looks for marks to open."""
        self._wake.set()
        if before is None:
            return
        try:
            cases = self._cases()
            for mark in self.policy.marks:
                await cases.wake(KIND, case_key(before.appointment_id, before.starts_at, mark.name))
        except PluginError:
            return
        except Exception as err:  # the event is applied; the case still checks at its mark
            logger.warning("waking the reminders of a visit failed (%s)", type(err).__name__)

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
            try:
                await self._reconcile_if_due()
                await self.pass_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # the loop outlives any error of one pass
                logger.warning("reminder pass failed (%s)", type(err).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=SAFETY_NET.total_seconds())

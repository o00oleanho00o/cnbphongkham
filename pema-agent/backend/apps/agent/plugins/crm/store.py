"""What the CRM told the agent, kept as STATE (docs/PLAN-crm-plugin.md 3.4): the latest version of each visit
and the newest consent of each person. Applying an event twice, late or out of order changes nothing it should
not, so the route needs no list of events already seen.

Rules every store follows:

* a visit is written when it is new or its ``version`` is higher than the one held;
* ``changed_at`` is the event's ``occurred_at`` when the visit is new or its time moved; a status change alone
  (confirmed, cancelled) keeps it, so a reminder mark is skipped only when the TIME was set after it was due;
* a consent is written when it is newer (``occurred_at``) than the one held.

``MemoryReminderStore`` serves an agent without a database and the tests; ``PostgresReminderStore`` the
service.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ACTIVE: Final = ("booked", "confirmed")
GONE: Final = "gone"
"""A visit the CRM no longer lists for reminders, found by reconciliation."""


@dataclass(frozen=True, slots=True)
class Visit:
    appointment_id: UUID
    channel: str
    external_id: str
    starts_at: datetime
    duration_min: int
    status: str
    version: int
    changed_at: datetime
    actor_type: str
    last_event_id: UUID


@dataclass(frozen=True, slots=True)
class Person:
    channel: str
    external_id: str
    messages_consent: bool | None
    consent_at: datetime | None
    conversation_id: str | None = None


class ReminderStore(Protocol):
    async def apply_visit(self, visit: Visit) -> bool:
        """True when it changed what is held."""
        ...

    async def apply_consent(
        self, channel: str, external_id: str, consent: bool | None, at: datetime
    ) -> bool: ...

    async def visit(self, appointment_id: UUID) -> Visit | None: ...

    async def person(self, channel: str, external_id: str) -> Person | None: ...

    async def remember_chat(self, channel: str, external_id: str, conversation_id: str) -> None:
        """The one-to-one chat of the person, where a reminder goes; the consent stays as it is."""
        ...

    async def upcoming(self, after: datetime, until: datetime) -> list[Visit]:
        """Booked or confirmed visits starting after ``after`` and at the latest ``until``, soonest first."""
        ...

    async def handled(self, appointment_ids: Collection[UUID]) -> set[tuple[UUID, datetime, str]]:
        """(visit, its time, mark) already sent or skipped, for these visits."""
        ...

    async def sent_since(self, since: datetime) -> dict[tuple[str, str], int]:
        """Reminders sent to each person (channel, external id) since ``since``."""
        ...

    async def claim_mark(self, visit: Visit, mark: str, outcome: str) -> bool:
        """Records the mark of the visit at its current time as handled; False when it already was."""
        ...

    async def mark_gone(self, after: datetime, until: datetime, keep: Collection[UUID]) -> int:
        """Marks ``gone`` the booked or confirmed visits in the window whose person agreed to reminders but
        that the CRM no longer lists (cancelled, moved away); the version stays, so events still win."""
        ...


class MemoryReminderStore:
    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._visits: dict[UUID, Visit] = {}
        self._people: dict[tuple[str, str], Person] = {}
        self._marks: dict[tuple[UUID, datetime, str], tuple[tuple[str, str], str, datetime]] = {}
        self._now = now

    async def apply_visit(self, visit: Visit) -> bool:
        held = self._visits.get(visit.appointment_id)
        if held is not None and visit.version <= held.version:
            return False
        if held is not None and held.starts_at == visit.starts_at:
            visit = replace(visit, changed_at=held.changed_at)
        self._visits[visit.appointment_id] = visit
        return True

    async def apply_consent(self, channel: str, external_id: str, consent: bool | None, at: datetime) -> bool:
        held = self._people.get((channel, external_id))
        if held is not None and held.consent_at is not None and at <= held.consent_at:
            return False
        chat = held.conversation_id if held is not None else None
        self._people[(channel, external_id)] = Person(channel, external_id, consent, at, chat)
        return True

    async def remember_chat(self, channel: str, external_id: str, conversation_id: str) -> None:
        held = self._people.get((channel, external_id)) or Person(channel, external_id, None, None)
        self._people[(channel, external_id)] = replace(held, conversation_id=conversation_id)

    async def upcoming(self, after: datetime, until: datetime) -> list[Visit]:
        found = [v for v in self._visits.values() if v.status in ACTIVE and after < v.starts_at <= until]
        return sorted(found, key=lambda v: v.starts_at)

    async def handled(self, appointment_ids: Collection[UUID]) -> set[tuple[UUID, datetime, str]]:
        wanted = set(appointment_ids)
        return {key for key in self._marks if key[0] in wanted}

    async def sent_since(self, since: datetime) -> dict[tuple[str, str], int]:
        counts: dict[tuple[str, str], int] = {}
        for person, outcome, at in self._marks.values():
            if outcome == "sent" and at >= since:
                counts[person] = counts.get(person, 0) + 1
        return counts

    async def claim_mark(self, visit: Visit, mark: str, outcome: str) -> bool:
        key = (visit.appointment_id, visit.starts_at, mark)
        if key in self._marks:
            return False
        self._marks[key] = ((visit.channel, visit.external_id), outcome, self._now())
        return True

    async def mark_gone(self, after: datetime, until: datetime, keep: Collection[UUID]) -> int:
        gone = 0
        for visit in await self.upcoming(after, until):
            person = self._people.get((visit.channel, visit.external_id))
            if visit.appointment_id in keep or person is None or person.messages_consent is not True:
                continue
            self._visits[visit.appointment_id] = replace(visit, status=GONE)
            gone += 1
        return gone

    async def visit(self, appointment_id: UUID) -> Visit | None:
        return self._visits.get(appointment_id)

    async def person(self, channel: str, external_id: str) -> Person | None:
        return self._people.get((channel, external_id))


_APPLY_VISIT = text(
    "INSERT INTO agent_rt.crm_reminder (tenant_id, agent, appointment_id, channel, external_id, starts_at, "
    "duration_min, status, version, changed_at, actor_type, last_event_id) "
    "VALUES (:tenant_id, :agent, :appointment_id, :channel, :external_id, :starts_at, :duration_min, "
    ":status, :version, :changed_at, :actor_type, :last_event_id) "
    "ON CONFLICT (tenant_id, agent, appointment_id) DO UPDATE SET "
    "channel = EXCLUDED.channel, external_id = EXCLUDED.external_id, starts_at = EXCLUDED.starts_at, "
    "duration_min = EXCLUDED.duration_min, status = EXCLUDED.status, version = EXCLUDED.version, "
    "changed_at = CASE WHEN agent_rt.crm_reminder.starts_at = EXCLUDED.starts_at "
    "THEN agent_rt.crm_reminder.changed_at ELSE EXCLUDED.changed_at END, "
    "actor_type = EXCLUDED.actor_type, last_event_id = EXCLUDED.last_event_id, received_at = now() "
    "WHERE EXCLUDED.version > agent_rt.crm_reminder.version "
    "RETURNING 1"
)
_APPLY_CONSENT = text(
    "INSERT INTO agent_rt.crm_person (tenant_id, agent, channel, external_id, messages_consent, consent_at) "
    "VALUES (:tenant_id, :agent, :channel, :external_id, :consent, :at) "
    "ON CONFLICT (tenant_id, agent, channel, external_id) DO UPDATE SET "
    "messages_consent = EXCLUDED.messages_consent, consent_at = EXCLUDED.consent_at "
    "WHERE agent_rt.crm_person.consent_at IS NULL OR EXCLUDED.consent_at > agent_rt.crm_person.consent_at "
    "RETURNING 1"
)
_VISIT = text(
    "SELECT appointment_id, channel, external_id, starts_at, duration_min, status, version, changed_at, "
    "actor_type, last_event_id FROM agent_rt.crm_reminder "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND appointment_id = :appointment_id"
)
_REMEMBER_CHAT = text(
    "INSERT INTO agent_rt.crm_person (tenant_id, agent, channel, external_id, conversation_id) "
    "VALUES (:tenant_id, :agent, :channel, :external_id, :conversation_id) "
    "ON CONFLICT (tenant_id, agent, channel, external_id) DO UPDATE SET "
    "conversation_id = EXCLUDED.conversation_id "
    "WHERE agent_rt.crm_person.conversation_id IS DISTINCT FROM EXCLUDED.conversation_id"
)
_PERSON = text(
    "SELECT channel, external_id, messages_consent, consent_at, conversation_id FROM agent_rt.crm_person "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND channel = :channel AND external_id = :external_id"
)


_UPCOMING = text(
    "SELECT appointment_id, channel, external_id, starts_at, duration_min, status, version, changed_at, "
    "actor_type, last_event_id FROM agent_rt.crm_reminder "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND status IN ('booked', 'confirmed') "
    "AND starts_at > :after AND starts_at <= :until ORDER BY starts_at, appointment_id"
)
_HANDLED = text(
    "SELECT appointment_id, starts_at, mark FROM agent_rt.crm_reminder_sent "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND appointment_id = ANY(:ids)"
)
_SENT_SINCE = text(
    "SELECT channel, external_id, count(*) FROM agent_rt.crm_reminder_sent "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND outcome = 'sent' AND sent_at >= :since "
    "GROUP BY channel, external_id"
)
_CLAIM = text(
    "INSERT INTO agent_rt.crm_reminder_sent (tenant_id, agent, appointment_id, starts_at, mark, channel, "
    "external_id, outcome) VALUES (:tenant_id, :agent, :appointment_id, :starts_at, :mark, :channel, "
    ":external_id, :outcome) ON CONFLICT DO NOTHING RETURNING 1"
)
_MARK_GONE = text(
    "UPDATE agent_rt.crm_reminder r SET status = 'gone' FROM agent_rt.crm_person p "
    "WHERE r.tenant_id = :tenant_id AND r.agent = :agent AND r.status IN ('booked', 'confirmed') "
    "AND r.starts_at > :after AND r.starts_at <= :until AND NOT (r.appointment_id = ANY(:keep)) "
    "AND p.tenant_id = r.tenant_id AND p.agent = r.agent AND p.channel = r.channel "
    "AND p.external_id = r.external_id AND p.messages_consent IS TRUE "
    "RETURNING 1"
)


class PostgresReminderStore:
    def __init__(self, engine: AsyncEngine, *, tenant_id: str, agent: str) -> None:
        self._engine = engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def apply_visit(self, visit: Visit) -> bool:
        values = {
            "appointment_id": visit.appointment_id,
            "channel": visit.channel,
            "external_id": visit.external_id,
            "starts_at": visit.starts_at,
            "duration_min": visit.duration_min,
            "status": visit.status,
            "version": visit.version,
            "changed_at": visit.changed_at,
            "actor_type": visit.actor_type,
            "last_event_id": visit.last_event_id,
        }
        async with self._engine.begin() as conn:
            return (await conn.execute(_APPLY_VISIT, {**self._scope, **values})).first() is not None

    async def apply_consent(self, channel: str, external_id: str, consent: bool | None, at: datetime) -> bool:
        values = {"channel": channel, "external_id": external_id, "consent": consent, "at": at}
        async with self._engine.begin() as conn:
            return (await conn.execute(_APPLY_CONSENT, {**self._scope, **values})).first() is not None

    async def visit(self, appointment_id: UUID) -> Visit | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_VISIT, {**self._scope, "appointment_id": appointment_id})).first()
        return None if row is None else Visit(*row)

    async def person(self, channel: str, external_id: str) -> Person | None:
        values = {"channel": channel, "external_id": external_id}
        async with self._engine.connect() as conn:
            row = (await conn.execute(_PERSON, {**self._scope, **values})).first()
        return None if row is None else Person(*row)

    async def remember_chat(self, channel: str, external_id: str, conversation_id: str) -> None:
        values = {"channel": channel, "external_id": external_id, "conversation_id": conversation_id}
        async with self._engine.begin() as conn:
            await conn.execute(_REMEMBER_CHAT, {**self._scope, **values})

    async def upcoming(self, after: datetime, until: datetime) -> list[Visit]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(_UPCOMING, {**self._scope, "after": after, "until": until})
            return [Visit(*row) for row in rows]

    async def handled(self, appointment_ids: Collection[UUID]) -> set[tuple[UUID, datetime, str]]:
        if not appointment_ids:
            return set()
        async with self._engine.connect() as conn:
            rows = await conn.execute(_HANDLED, {**self._scope, "ids": list(appointment_ids)})
            return {(row[0], row[1], row[2]) for row in rows}

    async def sent_since(self, since: datetime) -> dict[tuple[str, str], int]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(_SENT_SINCE, {**self._scope, "since": since})
            return {(row[0], row[1]): int(row[2]) for row in rows}

    async def claim_mark(self, visit: Visit, mark: str, outcome: str) -> bool:
        values = {
            "appointment_id": visit.appointment_id,
            "starts_at": visit.starts_at,
            "mark": mark,
            "channel": visit.channel,
            "external_id": visit.external_id,
            "outcome": outcome[:80],
        }
        async with self._engine.begin() as conn:
            return (await conn.execute(_CLAIM, {**self._scope, **values})).first() is not None

    async def mark_gone(self, after: datetime, until: datetime, keep: Collection[UUID]) -> int:
        values = {"after": after, "until": until, "keep": list(keep)}
        async with self._engine.begin() as conn:
            return len((await conn.execute(_MARK_GONE, {**self._scope, **values})).all())

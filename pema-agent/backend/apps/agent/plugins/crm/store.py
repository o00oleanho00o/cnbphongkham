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

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


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


class MemoryReminderStore:
    def __init__(self) -> None:
        self._visits: dict[UUID, Visit] = {}
        self._people: dict[tuple[str, str], Person] = {}

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

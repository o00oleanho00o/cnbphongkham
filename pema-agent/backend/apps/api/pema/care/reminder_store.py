"""``ReminderStore`` over Postgres (``agent.paused_reminders``, migration ``m_0002_paused_reminders``).

New module (not a port). One short unit of work per call. ``add`` is ``INSERT ... ON CONFLICT DO NOTHING``
on ``(care_agent_id, dedupe_key)``: the same reminder arriving twice is one row and the second call returns
``False``. ``resolve`` is one conditional UPDATE (``WHERE status = 'paused'``): of two callers that race (the
release reconcile and a staff member who sends the text by hand) exactly one wins. A bulk UPDATE does not go
through the ORM version counter, so it bumps ``version`` itself. Works with either runtime role.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pema.care.events import EventKind
from pema.care.models import PausedReminderRow
from pema.care.routing_types import NewPausedReminder, PausedReminder, ReminderStatus
from pema.core.db import ClinicDatabase


def _reminder(row: PausedReminderRow) -> PausedReminder:
    return PausedReminder(
        id=row.id,
        care_agent_id=row.care_agent_id,
        patient_id=row.patient_id,
        patient_ref=row.patient_ref,
        kind=EventKind(row.event_kind),
        rule=row.rule,
        due_at=row.due_at,
        dedupe_key=row.dedupe_key,
        prepared_text=row.prepared_text,
        owner_user_id=row.owner_user_id,
        status=ReminderStatus(row.status),
        payload=dict(row.payload),
        paused_at=row.paused_at,
        resolved_at=row.resolved_at,
        resolution=row.resolution,
    )


class SqlReminderStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def add(self, reminder: NewPausedReminder) -> bool:
        values: dict[str, object] = {
            "clinic_id": reminder.clinic_id,
            "care_agent_id": reminder.care_agent_id,
            "patient_id": reminder.patient_id,
            "patient_ref": reminder.patient_ref,
            "event_kind": reminder.kind.value,
            "rule": reminder.rule,
            "due_at": reminder.due_at,
            "dedupe_key": reminder.dedupe_key,
            "prepared_text": reminder.prepared_text,
            "owner_user_id": reminder.owner_user_id,
            "payload": dict(reminder.payload),
        }
        if reminder.paused_at is not None:
            values["paused_at"] = reminder.paused_at
        async with self._db.session() as session:
            inserted = await session.scalar(
                pg_insert(PausedReminderRow)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[PausedReminderRow.care_agent_id, PausedReminderRow.dedupe_key]
                )
                .returning(PausedReminderRow.id)
            )
        return inserted is not None

    async def list_paused(self, care_agent_id: UUID) -> Sequence[PausedReminder]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(PausedReminderRow)
                .where(PausedReminderRow.care_agent_id == care_agent_id, PausedReminderRow.status == "paused")
                .order_by(PausedReminderRow.due_at, PausedReminderRow.id)
            )
            return [_reminder(row) for row in rows]

    async def list_for_owner(self, owner_user_id: UUID, *, limit: int) -> Sequence[PausedReminder]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(PausedReminderRow)
                .where(PausedReminderRow.owner_user_id == owner_user_id, PausedReminderRow.status == "paused")
                .order_by(PausedReminderRow.due_at, PausedReminderRow.id)
                .limit(limit)
            )
            return [_reminder(row) for row in rows]

    async def resolve(self, reminder_id: UUID, status: ReminderStatus, resolution: str, at: datetime) -> bool:
        async with self._db.session() as session:
            done = await session.scalar(
                update(PausedReminderRow)
                .where(PausedReminderRow.id == reminder_id, PausedReminderRow.status == "paused")
                .values(
                    status=status.value,
                    resolution=resolution,
                    resolved_at=at,
                    version=PausedReminderRow.version + 1,
                )
                .returning(PausedReminderRow.id)
                .execution_options(synchronize_session=False)
            )
        return done is not None

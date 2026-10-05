"""``CareStore`` and ``PatientDirectory`` over Postgres (tables of ``m_0001_care_tables``).

New module (not a port). Meant for the worker process, i.e. the role ``agent_worker``: it reads and writes
``agent.*`` (granted to both runtime roles) and reads the patient code from the view
``clinic_agent.patient_ref`` (never ``clinic.patient``). Each method is one short unit of work with its own
session, so a slow harness call never holds a transaction open.

``record_action`` is the audit line of a turn. The table has no ``reason`` column (the schema of M1 is final),
so the reason travels in ``action_type`` as ``<what>:<why>`` (see ``pema.care.loop``); the ``disposition`` is
one of the three of the table CHECK. ``touch_last_tick`` is one UPDATE for a whole batch of agents and bumps
``version`` itself (a bulk UPDATE does not go through the ORM version counter).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text, update

from pema.care.models import ActionLog, CareAgent, ControlState, ConversationControl
from pema.care.ports import CareAgentSnapshot
from pema.core.db import ClinicDatabase


def snapshot_of(row: CareAgent) -> CareAgentSnapshot:
    return CareAgentSnapshot(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        profile=row.profile,
        paused=row.paused,
        autonomy_levels=row.autonomy_levels,
        autonomy_override=row.autonomy_override,
    )


class SqlCareStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_care_agent(self, care_agent_id: UUID) -> CareAgentSnapshot | None:
        async with self._db.session() as session:
            row = await session.get(CareAgent, care_agent_id)
            return None if row is None else snapshot_of(row)

    async def get_control_state(self, patient_id: UUID) -> ControlState:
        async with self._db.session() as session:
            state = await session.scalar(
                select(ConversationControl.state).where(ConversationControl.patient_id == patient_id)
            )
        return ControlState.AUTO if state is None else ControlState(state)

    async def list_active_care_agents(self, *, after: UUID | None, limit: int) -> Sequence[CareAgentSnapshot]:
        statement = select(CareAgent).where(CareAgent.paused.is_(False)).order_by(CareAgent.id).limit(limit)
        if after is not None:
            statement = statement.where(CareAgent.id > after)
        async with self._db.session() as session:
            return [snapshot_of(row) for row in await session.scalars(statement)]

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None:
        async with self._db.session() as session:
            clinic_id = await session.scalar(select(CareAgent.clinic_id).where(CareAgent.id == care_agent_id))
            if clinic_id is None:
                raise LookupError("care agent not found")
            session.add(
                ActionLog(
                    clinic_id=clinic_id,
                    care_agent_id=care_agent_id,
                    action_type=action_type,
                    depth=depth,
                    disposition=disposition,
                    at=at,
                )
            )

    async def touch_last_tick(self, care_agent_ids: Sequence[UUID], at: datetime) -> None:
        if not care_agent_ids:
            return
        async with self._db.session() as session:
            await session.execute(
                update(CareAgent)
                .where(CareAgent.id.in_(list(care_agent_ids)))
                .values(last_tick_at=at, version=CareAgent.version + 1)
                .execution_options(synchronize_session=False)
            )

    async def care_agent_id_for(self, patient_ref: str) -> UUID | None:
        async with self._db.session() as session:
            found = await session.scalar(
                text(
                    "SELECT ca.id FROM agent.care_agents ca "
                    "JOIN clinic_agent.patient_ref p ON p.id = ca.patient_id WHERE p.code = :code"
                ),
                {"code": patient_ref},
            )
        return None if found is None else UUID(str(found))

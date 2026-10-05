"""Pairing of a patient with its care agent: exactly one ``agent.care_agents`` row per patient.

New module (not a port). ``ensure_care_agent`` is idempotent and safe under concurrency: it relies on
``UNIQUE (patient_id)`` and ``INSERT ... ON CONFLICT DO NOTHING``, then reads the row, so two callers racing
on the same patient both get the one row and none fails. It works in the caller's session, so the pairing
commits or rolls back together with the patient (the hook runs in the unit of work that created it).

``clinic_id`` is the installation id (single tenant): taken from ``pema_contracts.installation`` unless the
caller passes it. A patient that does not exist makes the foreign key fail (``IntegrityError``).

``CareAgentPairing`` implements ``pema.care.ports.PatientCreatedHook``. B1's ``create_patient`` has no hook
point yet; until it calls this, callers (and the tests) invoke ``on_patient_created`` after creating a
patient.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.models import PATIENT_CHANNEL_PROFILE, CareAgent
from pema_contracts.installation import installation_clinic_id

logger = logging.getLogger(__name__)


async def ensure_care_agent(
    session: AsyncSession, patient_id: UUID, *, clinic_id: UUID | None = None
) -> CareAgent:
    """The care agent of ``patient_id``; created if missing (autonomy L0 everywhere, ``patient_channel``)."""
    existing = await session.scalar(select(CareAgent).where(CareAgent.patient_id == patient_id))
    if existing is not None:
        return existing
    statement = (
        pg_insert(CareAgent)
        .values(
            clinic_id=clinic_id if clinic_id is not None else installation_clinic_id(),
            patient_id=patient_id,
            profile=PATIENT_CHANNEL_PROFILE,
        )
        .on_conflict_do_nothing(index_elements=[CareAgent.patient_id])
        .returning(CareAgent.id)
    )
    created_id = await session.scalar(statement)
    row = await session.scalar(
        select(CareAgent).where(CareAgent.patient_id == patient_id).execution_options(populate_existing=True)
    )
    if (
        row is None
    ):  # the foreign key (clinic_id, patient_id) refuses unknown patients, so this is unreachable
        raise RuntimeError("care agent missing right after its insert")
    if created_id is not None:
        logger.info("care agent created", extra={"care_agent_id": str(row.id)})
    return row


class CareAgentPairing:
    """``PatientCreatedHook`` that pairs the new patient with its care agent."""

    async def on_patient_created(self, session: AsyncSession, patient_id: UUID) -> None:
        await ensure_care_agent(session, patient_id)

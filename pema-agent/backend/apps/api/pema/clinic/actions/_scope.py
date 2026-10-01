"""Record-level scope: what a doctor may open.

New module. docs/ARCH-PB01.md and AGENT.md (CRM01): "Doctors only open records they own or are scheduled
for". ``rbac.matrix`` gives the doctor ``patient.read``; this module narrows it to the doctor's own
patients (``patient.doctor_id``) and the patients with an active appointment of that doctor.
Every other role keeps the whole clinic (RLS already limits it to one clinic).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.domain.appointments import FREE_STATUSES
from pema.clinic.models import Appointment, Patient
from pema.clinic.rbac import is_doctor_scoped
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode

_FREE = [s.value for s in FREE_STATUSES]


def patient_scope(ctx: ActionContext) -> ColumnElement[bool] | None:
    """SQL condition on ``Patient`` for a doctor, ``None`` for roles that see the whole clinic."""
    if not is_doctor_scoped(ctx) or ctx.actor_user_id is None:
        return None
    me = ctx.actor_user_id
    scheduled = exists().where(
        and_(
            Appointment.clinic_id == Patient.clinic_id,
            Appointment.patient_id == Patient.id,
            Appointment.doctor_id == me,
            Appointment.status.notin_(_FREE),
        )
    )
    return or_(Patient.doctor_id == me, scheduled)


async def can_open_patient(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> bool:
    scope = patient_scope(ctx)
    if scope is None:
        return True
    found = await session.scalar(
        select(Patient.id).where(Patient.id == patient_id, Patient.clinic_id == ctx.clinic_id, scope)
    )
    return found is not None


async def require_patient_access(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> None:
    """Raise 403 when a doctor reaches for a record outside their scope. (404 for a patient of another
    clinic is the caller's job: the row is simply not visible.)"""
    if not await can_open_patient(session, ctx, patient_id):
        raise DomainError(
            ErrorCode.FORBIDDEN, "Hồ sơ này không thuộc bác sĩ phụ trách.", details={"scope": "doctor"}
        )

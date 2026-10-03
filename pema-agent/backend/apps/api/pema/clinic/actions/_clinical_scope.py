"""Record-level scope and lookups shared by the Patient 360 tab actions (package U, step U3). New module.

``docs/ARCH-PB01.md`` authorization matrix: "Ghi session: bác sĩ yes, chăm sóc theo phân công, lễ tân no" and
"Xem ảnh clinical: bác sĩ yes, chăm sóc theo phân công". The flat permission is the ceiling
(``session.read``, ``session.write``, ``media.read``, ``media.write``); this module narrows it:

* a doctor opens the patients they own or are scheduled for (``_scope.require_patient_access``);
* a care staff member (``cs_staff``) opens the patients whose ``cs_owner_id`` is them: "theo phân công" is the
  assignment of the patient to a care owner;
* every other role that holds the permission (owner) is not narrowed.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.actions._scope import require_patient_access
from pema.clinic.models import Consent, Patient, UserAccount
from pema.clinic.rbac import is_role
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patients import ConsentKind
from pema_contracts.roles import Role

CLINICIAN_ROLES = (Role.DOCTOR, Role.OWNER)
"""Roles that record sessions and see clinical photos whatever the consent says."""


async def require_clinical_scope(session: AsyncSession, ctx: ActionContext, patient: Patient) -> None:
    """Raise 403 when the caller may not open this patient's clinical tabs."""
    if is_role(ctx, Role.CS_STAFF):
        if ctx.actor_user_id is None or patient.cs_owner_id != ctx.actor_user_id:
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "Hồ sơ này không thuộc người bệnh bạn phụ trách.",
                details={"scope": "assignment"},
            )
        return
    await require_patient_access(session, ctx, patient.id)


async def current_media_consent(
    session: AsyncSession, ctx: ActionContext, patient_id: UUID
) -> Consent | None:
    """The newest ``media`` consent row of the patient when it is a grant, else ``None``.

    ``clinic.consent`` is an append-only history: the newest row of a kind is the current one."""
    newest = await session.scalar(
        select(Consent)
        .where(
            Consent.clinic_id == ctx.clinic_id,
            Consent.patient_id == patient_id,
            Consent.kind == ConsentKind.MEDIA.value,
        )
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .limit(1)
    )
    if newest is None or not newest.granted or newest.revoked_at is not None:
        return None
    return newest


async def names_of(
    session: AsyncSession, ctx: ActionContext, user_ids: Iterable[UUID | None]
) -> dict[UUID, str]:
    """Display names of the given staff (one query)."""
    wanted = {uid for uid in user_ids if uid is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        select(UserAccount.id, UserAccount.display_name).where(
            UserAccount.clinic_id == ctx.clinic_id, UserAccount.id.in_(wanted)
        )
    )
    return {row.id: row.display_name for row in rows}

"""Patients: search, create, update, and Patient 360 (actions behind ``routers/patients.py``).

New module (the prototype kept patients in ``localStorage``). Rules:

* ``patient.read`` for list and get; a doctor only sees own or scheduled patients (``_scope``);
* ``patient.write`` for create and update, with optimistic locking on ``version``;
* ``patient.read_360`` for the 360 read model; reading it is audited (ARCH-PB01: audit for reads of
  sensitive content);
* audit details carry ids and the NAMES of changed fields, never values.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pema.clinic import audit
from pema.clinic.actions._common import (
    check_version,
    escape_like,
    lost_race_is_conflict,
    not_found,
    now,
)
from pema.clinic.actions._mappers import patient_out
from pema.clinic.actions._scope import patient_scope, require_patient_access
from pema.clinic.actions.assignees import load_assignable_user
from pema.clinic.models import Patient, UserAccount
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ, Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patients import PatientCreate, PatientOut, PatientUpdate
from pema_contracts.roles import Permission, Role

DOCTOR_ROLES = (Role.DOCTOR.value, Role.OWNER.value)
CS_OWNER_ROLES = (Role.CS_STAFF.value, Role.MANAGER.value, Role.OWNER.value)
CODE_RETRIES = 5

_NULLABLE_UPDATE_FIELDS = ("phone", "birth_date", "doctor_id", "cs_owner_id")
_ASSIGNEE_FIELDS = ("doctor_id", "cs_owner_id")
_NON_NULL_UPDATE_FIELDS = ("full_name", "gender", "marketing_opt_out")


def _id_or_none(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


async def load_patient(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> Patient:
    row = await session.scalar(
        select(Patient).where(Patient.id == patient_id, Patient.clinic_id == ctx.clinic_id)
    )
    if row is None:
        raise not_found("bệnh nhân")
    return row


async def _names(session: AsyncSession, ctx: ActionContext, *user_ids: UUID | None) -> dict[UUID, str]:
    wanted = [u for u in user_ids if u is not None]
    if not wanted:
        return {}
    rows = await session.execute(
        select(UserAccount.id, UserAccount.display_name).where(
            UserAccount.clinic_id == ctx.clinic_id, UserAccount.id.in_(wanted)
        )
    )
    return {row.id: row.display_name for row in rows}


async def patient_to_out(session: AsyncSession, ctx: ActionContext, row: Patient) -> PatientOut:
    names = await _names(session, ctx, row.doctor_id, row.cs_owner_id)
    return patient_out(
        row,
        names.get(row.doctor_id) if row.doctor_id else None,
        names.get(row.cs_owner_id) if row.cs_owner_id else None,
    )


async def _check_assignee(
    session: AsyncSession, ctx: ActionContext, user_id: UUID, roles: tuple[str, ...], label: str
) -> None:
    """The treating doctor / the CSKH owner of a patient: active, of this installation, and a role that
    is both assignable (``ASSIGNABLE_ROLES``) and the one this slot asks for."""
    await load_assignable_user(
        session, ctx, user_id, roles=roles, message=f"Người phụ trách ({label}) không hợp lệ."
    )


async def list_patients(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    q: str | None = None,
    doctor_id: UUID | None = None,
    cs_owner_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[PatientOut]:
    require(ctx, Permission.PATIENT_READ)
    doctor = aliased(UserAccount)
    cs = aliased(UserAccount)
    conditions: list[Any] = [Patient.clinic_id == ctx.clinic_id]
    scope = patient_scope(ctx)
    if scope is not None:
        conditions.append(scope)
    if doctor_id is not None:
        conditions.append(Patient.doctor_id == doctor_id)
    if cs_owner_id is not None:
        conditions.append(Patient.cs_owner_id == cs_owner_id)
    if q:
        pattern = f"%{escape_like(q.lower())}%"
        conditions.append(
            or_(
                func.lower(Patient.full_name).like(pattern, escape="\\"),
                func.lower(Patient.code).like(pattern, escape="\\"),
                Patient.phone.like(f"%{escape_like(q)}%", escape="\\"),
            )
        )
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(Patient).where(*conditions)) or 0
        rows = await session.execute(
            select(Patient, doctor.display_name, cs.display_name)
            .outerjoin(doctor, (doctor.id == Patient.doctor_id) & (doctor.clinic_id == Patient.clinic_id))
            .outerjoin(cs, (cs.id == Patient.cs_owner_id) & (cs.clinic_id == Patient.clinic_id))
            .where(*conditions)
            .order_by(func.lower(Patient.full_name), Patient.code)
            .limit(limit)
            .offset(offset)
        )
        items = [patient_out(p, d, c) for p, d, c in rows.all()]
    return Page[PatientOut](items=items, total=total, limit=limit, offset=offset)


async def get_patient(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> PatientOut:
    require(ctx, Permission.PATIENT_READ)
    async with db.session() as session:
        row = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        return await patient_to_out(session, ctx, row)


async def _next_code(session: AsyncSession, ctx: ActionContext) -> str:
    highest = await session.scalar(
        select(func.max(cast(func.substring(Patient.code, r"^P([0-9]+)$"), Integer))).where(
            Patient.clinic_id == ctx.clinic_id
        )
    )
    return f"P{(highest or 0) + 1:03d}"


async def create_patient(db: ClinicDatabase, ctx: ActionContext, payload: PatientCreate) -> PatientOut:
    require(ctx, Permission.PATIENT_WRITE)
    today = now().astimezone(VN_TZ).date()
    async with db.session() as session:
        if payload.doctor_id is not None:
            await _check_assignee(session, ctx, payload.doctor_id, DOCTOR_ROLES, "bác sĩ")
        if payload.cs_owner_id is not None:
            await _check_assignee(session, ctx, payload.cs_owner_id, CS_OWNER_ROLES, "CSKH")
        row: Patient | None = None
        for _ in range(CODE_RETRIES):
            candidate = Patient(
                clinic_id=ctx.clinic_id,
                code=payload.code or await _next_code(session, ctx),
                full_name=payload.full_name,
                phone=payload.phone,
                birth_date=payload.birth_date,
                gender=payload.gender.value,
                doctor_id=payload.doctor_id,
                cs_owner_id=payload.cs_owner_id,
                first_contact_at=today,
                source=payload.source,
            )
            try:
                async with session.begin_nested():
                    session.add(candidate)
                    await session.flush()
            except IntegrityError as exc:  # the savepoint rollback already dropped the pending row
                if payload.code:
                    raise DomainError(ErrorCode.VALIDATION_FAILED, "Mã bệnh nhân đã tồn tại.") from exc
                continue
            row = candidate
            break
        if row is None:
            raise DomainError(ErrorCode.INTERNAL, "Không tạo được mã bệnh nhân. Vui lòng thử lại.")
        details: dict[str, Any] = {"code": row.code}
        for name in _ASSIGNEE_FIELDS:
            if getattr(row, name) is not None:
                details[f"{name}_to"] = _id_or_none(getattr(row, name))
        await audit.record(session, ctx, "patient.create", "patient", row.id, details)
        return await patient_to_out(session, ctx, row)


async def update_patient(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: PatientUpdate
) -> PatientOut:
    require(ctx, Permission.PATIENT_WRITE)
    async with db.session() as session:
        row = await load_patient(session, ctx, patient_id)
        check_version(row.version, payload.version)
        changed: list[str] = []
        sent = payload.model_fields_set
        owners_before = {name: getattr(row, name) for name in _ASSIGNEE_FIELDS}
        # Validate BEFORE touching the row: the lookup autoflushes, and an unknown id would reach the foreign
        # key (a 500) instead of the 422 below.
        if "doctor_id" in sent and payload.doctor_id is not None:
            await _check_assignee(session, ctx, payload.doctor_id, DOCTOR_ROLES, "bác sĩ")
        if "cs_owner_id" in sent and payload.cs_owner_id is not None:
            await _check_assignee(session, ctx, payload.cs_owner_id, CS_OWNER_ROLES, "CSKH")
        for name in _NULLABLE_UPDATE_FIELDS:
            if name in sent:
                setattr(row, name, getattr(payload, name))
                changed.append(name)
        for name in _NON_NULL_UPDATE_FIELDS:
            value = getattr(payload, name)
            if name in sent and value is not None:
                setattr(row, name, value.value if name == "gender" else value)
                changed.append(name)
        with lost_race_is_conflict():
            await session.flush()
        details: dict[str, Any] = {"changed_fields": changed}
        for name in _ASSIGNEE_FIELDS:  # who now looks after the patient: ids only, never a name
            if getattr(row, name) != owners_before[name]:
                details[f"{name}_from"] = _id_or_none(owners_before[name])
                details[f"{name}_to"] = _id_or_none(getattr(row, name))
        await audit.record(session, ctx, "patient.update", "patient", row.id, details)
        return await patient_to_out(session, ctx, row)


def today_vn() -> date:
    return now().astimezone(VN_TZ).date()


__all__ = [
    "create_patient",
    "get_patient",
    "list_patients",
    "load_patient",
    "patient_to_out",
    "today_vn",
    "update_patient",
]

# ported from: prototype/shared/crm-automation.js (queue, addActivity, validate, finish, resolve)
"""CRM tasks and the contact log (actions behind ``routers/crm.py``). The rules that CREATE tasks are B2's.

Forced deviations from the JS prototype: ``localStorage`` snapshots become one Postgres transaction (task,
activity, patient fields, optional appointment and optional doctor hand-over commit together or not at all);
the fixed demo day becomes the clock of ``_common.now``; ``run()`` after a command (re-evaluating which
tasks are superseded) is B2's engine, not called here.

Rules kept from ``validate`` / ``finish``:

* only an open or rescheduled task can be resolved ("Viec da duoc xu ly hoac khong con hop le");
* ``unanswered``, ``callback`` and ``busy`` need a next-action time in the future;
* ``booked`` needs a valid booking for the SAME patient, saved in the same transaction;
* the task is ``rescheduled`` when a next action is set and nothing was booked, otherwise ``resolved``;
* ``optout`` sets ``marketing_opt_out``; ``doctor``, ``reaction`` and ``complaint`` hand over to a doctor.
  In the
  JS that was a row in ``followups``; here it is a ``triage_alert`` review item (``requires_doctor``) that
  carries the activity id, never the note text;
* a doctor handles D+7 review tasks of their own patients only; nobody else does medical review.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.actions._mappers import activity_out, task_out
from pema.clinic.actions._scope import patient_scope, require_patient_access
from pema.clinic.actions.appointments import book_in_session
from pema.clinic.actions.patients import CS_OWNER_ROLES, load_patient
from pema.clinic.models import CrmActivity, CrmTask, Patient, ReviewItem, UserAccount
from pema.clinic.rbac import is_doctor_scoped, require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ, Page
from pema_contracts.crm import (
    CrmActivityCreate,
    CrmActivityOut,
    CrmChannel,
    CrmOutcome,
    CrmTaskOut,
    CrmTaskResolve,
    RuleKey,
    TaskStatus,
)
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.review import ReviewKind, ReviewOrigin, RiskLevel
from pema_contracts.roles import Permission, Role

OPEN_STATUSES = (TaskStatus.OPEN.value, TaskStatus.RESCHEDULED.value)
NEEDS_NEXT_ACTION = frozenset({CrmOutcome.UNANSWERED, CrmOutcome.CALLBACK, CrmOutcome.BUSY})
HAND_OVER_TO_DOCTOR = frozenset({CrmOutcome.DOCTOR, CrmOutcome.REACTION, CrmOutcome.COMPLAINT})
OWNER_ROLES = (Role.CS_STAFF.value, Role.MANAGER.value, Role.OWNER.value, Role.DOCTOR.value)
DOCTOR_TASK_RULE = RuleKey.D7.value
"""JS: ``Tai khoan bac si chi xu ly review D+7 cua ho so phu trach``."""


def _doctor_task_condition(ctx: ActionContext) -> list[Any]:
    """Extra conditions on ``CrmTask`` for a doctor: D+7 reviews of patients in their scope."""
    scope = patient_scope(ctx)
    if scope is None:
        return []
    return [
        CrmTask.rule_key == DOCTOR_TASK_RULE,
        CrmTask.patient_id.in_(select(Patient.id).where(Patient.clinic_id == ctx.clinic_id, scope)),
    ]


async def _load_task(
    session: AsyncSession, ctx: ActionContext, task_id: UUID
) -> tuple[CrmTask, str, str | None]:
    owner = aliased(UserAccount)
    row = (
        await session.execute(
            select(CrmTask, Patient.code, owner.display_name)
            .join(Patient, (Patient.id == CrmTask.patient_id) & (Patient.clinic_id == CrmTask.clinic_id))
            .outerjoin(owner, (owner.id == CrmTask.owner_user_id) & (owner.clinic_id == CrmTask.clinic_id))
            .where(CrmTask.id == task_id, CrmTask.clinic_id == ctx.clinic_id, *_doctor_task_condition(ctx))
        )
    ).first()
    if row is None:
        raise not_found("việc CSKH")
    return row[0], row[1], row[2]


async def list_tasks(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    status: TaskStatus | None = None,
    rule_key: RuleKey | None = None,
    owner_user_id: UUID | None = None,
    patient_id: UUID | None = None,
    due_by: Any = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[CrmTaskOut]:
    """Queue ordered as the JS ``queue``: D+1/3/7 first, then priority, then due time."""
    require(ctx, Permission.CRM_TASK_READ)
    conditions: list[Any] = [CrmTask.clinic_id == ctx.clinic_id, *_doctor_task_condition(ctx)]
    if status is not None:
        conditions.append(CrmTask.status == status.value)
    if rule_key is not None:
        conditions.append(CrmTask.rule_key == rule_key.value)
    if owner_user_id is not None:
        conditions.append(CrmTask.owner_user_id == owner_user_id)
    if patient_id is not None:
        conditions.append(CrmTask.patient_id == patient_id)
    if due_by is not None:
        end_of_day = datetime.combine(due_by, datetime.min.time(), tzinfo=VN_TZ) + timedelta(days=1)
        conditions.append(CrmTask.due_at < end_of_day)
    rank = case((CrmTask.rule_key.in_(("d1", "d3", "d7")), 0), else_=1)
    priority = case((CrmTask.priority == "high", 0), (CrmTask.priority == "normal", 1), else_=2)
    owner = aliased(UserAccount)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(CrmTask).where(*conditions)) or 0
        rows = await session.execute(
            select(CrmTask, Patient.code, owner.display_name)
            .join(Patient, (Patient.id == CrmTask.patient_id) & (Patient.clinic_id == CrmTask.clinic_id))
            .outerjoin(owner, (owner.id == CrmTask.owner_user_id) & (owner.clinic_id == CrmTask.clinic_id))
            .where(*conditions)
            .order_by(rank, priority, CrmTask.due_at, CrmTask.id)
            .limit(limit)
            .offset(offset)
        )
        items = [task_out(t, code, name) for t, code, name in rows.all()]
    return Page[CrmTaskOut](items=items, total=total, limit=limit, offset=offset)


async def get_task(db: ClinicDatabase, ctx: ActionContext, task_id: UUID) -> CrmTaskOut:
    require(ctx, Permission.CRM_TASK_READ)
    async with db.session() as session:
        row, code, name = await _load_task(session, ctx, task_id)
        return task_out(row, code, name)


def _validate_resolve(payload: CrmTaskResolve, stamp: datetime) -> None:
    if payload.outcome in NEEDS_NEXT_ACTION and payload.next_action_at is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Cần ngày giờ gọi lại.")
    if payload.next_action_at is not None and payload.next_action_at <= stamp:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Bước tiếp theo phải sau thời điểm hiện tại.")
    if payload.outcome is CrmOutcome.BOOKED and payload.booking is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Cần lưu lịch hẹn hợp lệ trước khi hoàn tất việc.")
    if payload.outcome is not CrmOutcome.BOOKED and payload.booking is not None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Chỉ kết quả 'đồng ý đặt lịch' mới kèm lịch hẹn.")


async def resolve_task(
    db: ClinicDatabase, ctx: ActionContext, task_id: UUID, payload: CrmTaskResolve
) -> CrmTaskOut:
    require(ctx, Permission.CRM_TASK_RESOLVE)
    async with db.session() as session:
        task, code, _ = await _load_task(session, ctx, task_id)
        if await audit.find_replay(session, ctx, "crm_task.resolve", task.id):
            owner_name = await _owner_name(session, ctx, task.owner_user_id)
            return task_out(task, code, owner_name)
        check_version(task.version, payload.version)
        if task.status not in OPEN_STATUSES:
            raise DomainError(
                ErrorCode.INVALID_STATE, "Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách."
            )
        stamp = now()
        _validate_resolve(payload, stamp)
        owner = await session.scalar(
            select(UserAccount).where(
                UserAccount.id == payload.owner_user_id,
                UserAccount.clinic_id == ctx.clinic_id,
                UserAccount.active.is_(True),
                UserAccount.role.in_(OWNER_ROLES),
            )
        )
        if owner is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Chọn người phụ trách hợp lệ.")
        patient = await load_patient(session, ctx, task.patient_id)

        appointment_id: UUID | None = None
        if payload.booking is not None:
            if payload.booking.patient_id != task.patient_id:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, "Lịch phải thuộc đúng bệnh nhân của việc CSKH."
                )
            if is_doctor_scoped(ctx) and payload.booking.doctor_id != ctx.actor_user_id:
                raise DomainError(
                    ErrorCode.FORBIDDEN, "Bác sĩ chỉ xếp lịch cho chính mình.", details={"scope": "doctor"}
                )
            booked, _ = await book_in_session(session, ctx, payload.booking)
            appointment_id = booked.id

        activity = CrmActivity(
            clinic_id=ctx.clinic_id,
            patient_id=task.patient_id,
            task_id=task.id,
            kind="complaint" if payload.outcome is CrmOutcome.COMPLAINT else "cskh",
            channel=payload.channel.value,
            outcome=payload.outcome.value,
            note=payload.note,
            actor_user_id=ctx.actor_user_id,
            occurred_at=stamp,
            next_action_at=payload.next_action_at,
            related_appointment_id=appointment_id,
        )
        session.add(activity)

        rescheduled = payload.next_action_at is not None and appointment_id is None
        task.status = TaskStatus.RESCHEDULED.value if rescheduled else TaskStatus.RESOLVED.value
        task.owner_user_id = owner.id
        if payload.priority is not None:
            task.priority = payload.priority.value
        task.resolution = payload.outcome.value
        task.resolved_at = None if rescheduled else stamp
        if rescheduled and payload.next_action_at is not None:
            task.due_at = payload.next_action_at
        if appointment_id is not None:
            task.related_appointment_id = appointment_id

        patient.last_contact_at = stamp
        patient.latest_outcome = payload.outcome.value
        patient.next_action_at = payload.next_action_at
        patient.next_action_type = None
        if owner.role in CS_OWNER_ROLES:
            patient.cs_owner_id = owner.id
        if payload.outcome is CrmOutcome.OPTOUT:
            patient.marketing_opt_out = True

        with lost_race_is_conflict():
            await session.flush()

        handed_over = False
        if payload.outcome in HAND_OVER_TO_DOCTOR:
            session.add(
                ReviewItem(
                    clinic_id=ctx.clinic_id,
                    kind=ReviewKind.TRIAGE_ALERT.value,
                    origin=ReviewOrigin.CRM_RULE.value,
                    patient_id=task.patient_id,
                    job_id=f"crm-handover:{activity.id}",
                    payload={"crm_activity_id": str(activity.id), "outcome": payload.outcome.value},
                    risk_level=RiskLevel.ATTENTION.value,
                    requires_doctor=True,
                )
            )
            await session.flush()
            handed_over = True

        await audit.record(
            session,
            ctx,
            "crm_task.resolve",
            "crm_task",
            task.id,
            {
                "outcome": payload.outcome.value,
                "status": task.status,
                "activity_id": str(activity.id),
                "appointment_id": str(appointment_id) if appointment_id else None,
                "handed_over_to_doctor": handed_over,
            },
        )
        resolved = task_out(task, code, owner.display_name)
    emit_live(LiveEventType.TASKS_CHANGED, task_id)
    if handed_over:
        emit_live(LiveEventType.REVIEW_CHANGED)
    return resolved


async def _owner_name(session: AsyncSession, ctx: ActionContext, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    return await session.scalar(
        select(UserAccount.display_name).where(
            UserAccount.id == user_id, UserAccount.clinic_id == ctx.clinic_id
        )
    )


async def list_activities(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    patient_id: UUID | None = None,
    task_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[CrmActivityOut]:
    require(ctx, Permission.CRM_TASK_READ)
    conditions: list[Any] = [CrmActivity.clinic_id == ctx.clinic_id]
    scope = patient_scope(ctx)
    if scope is not None:
        conditions.append(
            CrmActivity.patient_id.in_(select(Patient.id).where(Patient.clinic_id == ctx.clinic_id, scope))
        )
    if patient_id is not None:
        conditions.append(CrmActivity.patient_id == patient_id)
    if task_id is not None:
        conditions.append(CrmActivity.task_id == task_id)
    actor = aliased(UserAccount)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(CrmActivity).where(*conditions)) or 0
        rows = await session.execute(
            select(CrmActivity, actor.display_name)
            .outerjoin(
                actor, (actor.id == CrmActivity.actor_user_id) & (actor.clinic_id == CrmActivity.clinic_id)
            )
            .where(*conditions)
            .order_by(CrmActivity.occurred_at.desc(), CrmActivity.id)
            .limit(limit)
            .offset(offset)
        )
        items = [activity_out(a, name) for a, name in rows.all()]
    return Page[CrmActivityOut](items=items, total=total, limit=limit, offset=offset)


async def create_activity(
    db: ClinicDatabase, ctx: ActionContext, payload: CrmActivityCreate
) -> CrmActivityOut:
    """Manual contact log or internal note that does not close a task."""
    require(ctx, Permission.CRM_ACTIVITY_WRITE)
    stamp = now()
    if payload.next_action_at is not None and payload.next_action_at <= stamp:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Bước tiếp theo phải sau thời điểm hiện tại.")
    async with db.session() as session:
        patient = await load_patient(session, ctx, payload.patient_id)
        await require_patient_access(session, ctx, payload.patient_id)
        if payload.task_id is not None:
            owns = await session.scalar(
                select(CrmTask.id).where(
                    CrmTask.id == payload.task_id,
                    CrmTask.clinic_id == ctx.clinic_id,
                    CrmTask.patient_id == payload.patient_id,
                )
            )
            if owns is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "Việc CSKH không thuộc bệnh nhân này.")
        is_note = payload.channel is CrmChannel.INTERNAL_NOTE
        row = CrmActivity(
            clinic_id=ctx.clinic_id,
            patient_id=payload.patient_id,
            task_id=payload.task_id,
            kind="note" if is_note and payload.outcome is None else "cskh",
            channel=payload.channel.value,
            outcome=payload.outcome.value if payload.outcome else None,
            note=payload.note,
            actor_user_id=ctx.actor_user_id,
            occurred_at=stamp,
            next_action_at=payload.next_action_at,
        )
        session.add(row)
        if not is_note:
            patient.last_contact_at = stamp
            if payload.outcome is not None:
                patient.latest_outcome = payload.outcome.value
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "crm_activity.create",
            "crm_activity",
            row.id,
            {"patient_id": str(payload.patient_id), "channel": payload.channel.value},
        )
        return activity_out(row, await _owner_name(session, ctx, ctx.actor_user_id))

# ported from: prototype/shared/operations-data.js (validate, saveAppointment, setStatus, cancel) and
# prototype/shared/crm-automation.js (reception, bookingGuard)
"""Appointments: list, book (conflict check in this layer), reschedule, reception transitions.

Forced deviations from the JS prototype: Postgres instead of ``localStorage`` (a transaction plus an advisory
lock replaces ``transact()`` snapshot/rollback; the double-booking check runs under the lock so two
concurrent bookings of the same doctor or patient cannot both pass), no rooms/services/buffers (see
``domain.appointments``).

Authorization (ARCH-PB01): ``appointment.read`` lists; ``appointment.write`` books, edits and cancels;
``appointment.check_in`` drives arrived/in-progress/completed/missed; confirming (booked to confirmed) is
``appointment.write``. A doctor edits only their own
appointments ("gioi han"); a CS member books only through a CRM task (``crm.task.resolve`` + ``crm_task_id``).

Package U, step U2 adds the day/week board (``list_schedule``), the first free slot (``find_free_slot``), the
``confirm`` transition and the announcement after a commit: ``appointments.changed`` for the open schedules
and the dashboard, and ``appointment_events.notify`` so the CRM rules run soon (no_show, due, reactivation).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions import appointment_events
from pema.clinic.actions._common import (
    check_version,
    lost_race_is_conflict,
    not_found,
    now,
)
from pema.clinic.actions._mappers import appointment_out
from pema.clinic.actions.appointment_events import AppointmentChange
from pema.clinic.domain import appointments as rules
from pema.clinic.models import Appointment, CrmTask, Patient, UserAccount
from pema.clinic.rbac import has_permission, is_doctor_scoped, require, require_any
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatus,
    AppointmentTransition,
    AppointmentUpdate,
    FreeSlotOut,
    ScheduleDoctor,
    ScheduleItem,
    ScheduleOut,
    ScheduleView,
)
from pema_contracts.common import VN_TZ, Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.roles import Permission, Role

DOCTOR_ROLES = (Role.DOCTOR.value, Role.OWNER.value)
_MAX_DURATION = timedelta(minutes=480)
_FREE = [s.value for s in rules.FREE_STATUSES]
OPEN_TASK_STATUSES = ("open", "rescheduled")
SCHEDULE_LIMIT = 500
"""Most rows one board call returns: a clinic day holds a few dozen, a week a few hundred."""
SLOT_STEP_MIN = 15
"""JS ``suggest``: the search walks the day in steps of 15 minutes from the opening time."""


def announce(appointment_id: UUID, patient_id: UUID, kind: str, status: AppointmentStatus) -> None:
    """After the commit: the schedules and the dashboard reload, and the CRM rules run soon. Never raises."""
    emit_live(LiveEventType.APPOINTMENTS_CHANGED, appointment_id)
    appointment_events.notify(
        AppointmentChange(
            appointment_id=appointment_id, patient_id=patient_id, kind=kind, status=status.value
        )
    )


def _own_only(ctx: ActionContext, doctor_id: UUID | None) -> None:
    """A doctor edits only their own appointments."""
    if is_doctor_scoped(ctx) and doctor_id != ctx.actor_user_id:
        raise DomainError(
            ErrorCode.FORBIDDEN, "Bác sĩ chỉ thao tác trên lịch của chính mình.", details={"scope": "doctor"}
        )


async def _lock(session: AsyncSession, ctx: ActionContext, patient_id: UUID, doctor_id: UUID | None) -> None:
    """Serialise bookings that could collide (same doctor, same patient). Locks are taken in a fixed order
    so two bookings that share both keys cannot deadlock; they release at COMMIT/ROLLBACK."""
    keys = sorted(
        {f"appt:{ctx.clinic_id}:patient:{patient_id}"}
        | ({f"appt:{ctx.clinic_id}:doctor:{doctor_id}"} if doctor_id is not None else set())
    )
    for key in keys:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


async def _candidates(
    session: AsyncSession,
    ctx: ActionContext,
    *,
    patient_id: UUID,
    doctor_id: UUID | None,
    starts_at: datetime,
    duration_min: int,
) -> list[rules.Slot]:
    """Active appointments of the doctor or the patient that could overlap ``[start, end)``."""
    end = starts_at + timedelta(minutes=duration_min)
    owner = Appointment.patient_id == patient_id
    if doctor_id is not None:
        owner = owner | (Appointment.doctor_id == doctor_id)
    rows = await session.scalars(
        select(Appointment).where(
            Appointment.clinic_id == ctx.clinic_id,
            Appointment.status.notin_(_FREE),
            Appointment.starts_at < end,
            Appointment.starts_at > starts_at - _MAX_DURATION,
            owner,
        )
    )
    return [
        rules.Slot(
            patient_id=a.patient_id,
            doctor_id=a.doctor_id,
            starts_at=a.starts_at,
            duration_min=a.duration_min,
            appointment_id=a.id,
            status=AppointmentStatus(a.status),
        )
        for a in rows
    ]


async def _check_doctor(session: AsyncSession, ctx: ActionContext, doctor_id: UUID | None) -> None:
    if doctor_id is None:
        return
    ok = await session.scalar(
        select(UserAccount.id).where(
            UserAccount.id == doctor_id,
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.active.is_(True),
            UserAccount.role.in_(DOCTOR_ROLES),
        )
    )
    if ok is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Bác sĩ không hợp lệ.")


async def _patient_code(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> str:
    code = await session.scalar(
        select(Patient.code).where(Patient.id == patient_id, Patient.clinic_id == ctx.clinic_id)
    )
    if code is None:
        raise not_found("bệnh nhân")
    return code


async def validate_and_check(
    session: AsyncSession,
    ctx: ActionContext,
    *,
    patient_id: UUID,
    doctor_id: UUID | None,
    starts_at: datetime,
    duration_min: int,
    exclude: UUID | None = None,
    require_future: bool = False,
) -> None:
    """The one schedule validator: hours, break, past dates, then doctor/patient overlap under a lock.
    The UI path, the CRM booking, the review approval and the agent proposal all call this."""
    rules.validate_slot(starts_at, duration_min, now(), require_future=require_future)
    await _lock(session, ctx, patient_id, doctor_id)
    existing = await _candidates(
        session,
        ctx,
        patient_id=patient_id,
        doctor_id=doctor_id,
        starts_at=starts_at,
        duration_min=duration_min,
    )
    candidate = rules.Slot(
        patient_id=patient_id,
        doctor_id=doctor_id,
        starts_at=starts_at,
        duration_min=duration_min,
        appointment_id=exclude,
    )
    conflict = rules.find_conflict(candidate, existing)
    if conflict is not None:
        rules.raise_for_conflict(conflict)


async def book_in_session(
    session: AsyncSession, ctx: ActionContext, payload: AppointmentCreate
) -> tuple[Appointment, str]:
    """Create the appointment inside the caller's transaction (CRM resolve and review approval share it)."""
    patient_code = await _patient_code(session, ctx, payload.patient_id)
    await _check_doctor(session, ctx, payload.doctor_id)
    await validate_and_check(
        session,
        ctx,
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        duration_min=payload.duration_min,
    )
    row = Appointment(
        clinic_id=ctx.clinic_id,
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        duration_min=payload.duration_min,
        status=AppointmentStatus.BOOKED.value,
        note=payload.note,
        created_by=ctx.actor_user_id,
    )
    session.add(row)
    with lost_race_is_conflict():
        await session.flush()
    await audit.record(
        session,
        ctx,
        "appointment.create",
        "appointment",
        row.id,
        {
            "patient_id": str(row.patient_id),
            "doctor_id": str(row.doctor_id) if row.doctor_id else None,
            "starts_at": row.starts_at.isoformat(),
        },
    )
    return row, patient_code


async def _load(session: AsyncSession, ctx: ActionContext, appointment_id: UUID) -> tuple[Appointment, str]:
    row = (
        await session.execute(
            select(Appointment, Patient.code)
            .join(
                Patient, (Patient.id == Appointment.patient_id) & (Patient.clinic_id == Appointment.clinic_id)
            )
            .where(Appointment.id == appointment_id, Appointment.clinic_id == ctx.clinic_id)
        )
    ).first()
    if row is None:
        raise not_found("lịch hẹn")
    return row[0], row[1]


async def list_appointments(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    patient_id: UUID | None = None,
    doctor_id: UUID | None = None,
    status: AppointmentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[AppointmentOut]:
    require(ctx, Permission.APPOINTMENT_READ)
    conditions: list[Any] = [Appointment.clinic_id == ctx.clinic_id]
    if starts_from is not None:
        conditions.append(Appointment.starts_at >= starts_from)
    if starts_to is not None:
        conditions.append(Appointment.starts_at < starts_to)
    if patient_id is not None:
        conditions.append(Appointment.patient_id == patient_id)
    if doctor_id is not None:
        conditions.append(Appointment.doctor_id == doctor_id)
    if status is not None:
        conditions.append(Appointment.status == status.value)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(Appointment).where(*conditions)) or 0
        rows = await session.execute(
            select(Appointment, Patient.code)
            .join(
                Patient, (Patient.id == Appointment.patient_id) & (Patient.clinic_id == Appointment.clinic_id)
            )
            .where(*conditions)
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(limit)
            .offset(offset)
        )
        items = [appointment_out(a, code) for a, code in rows.all()]
    return Page[AppointmentOut](items=items, total=total, limit=limit, offset=offset)


async def get_appointment(db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID) -> AppointmentOut:
    require(ctx, Permission.APPOINTMENT_READ)
    async with db.session() as session:
        row, code = await _load(session, ctx, appointment_id)
        return appointment_out(row, code)


async def create_appointment(
    db: ClinicDatabase, ctx: ActionContext, payload: AppointmentCreate
) -> AppointmentOut:
    if payload.crm_task_id is not None:
        require_any(ctx, (Permission.APPOINTMENT_WRITE, Permission.CRM_TASK_RESOLVE))
    else:
        require(ctx, Permission.APPOINTMENT_WRITE)
    if is_doctor_scoped(ctx):
        _own_only(ctx, payload.doctor_id)
    async with db.session() as session:
        task: CrmTask | None = None
        if payload.crm_task_id is not None:
            task = await session.scalar(
                select(CrmTask).where(CrmTask.id == payload.crm_task_id, CrmTask.clinic_id == ctx.clinic_id)
            )
            if task is None:
                raise not_found("việc CSKH")
            if task.status not in OPEN_TASK_STATUSES:
                raise DomainError(
                    ErrorCode.INVALID_STATE, "Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách."
                )
            if task.patient_id != payload.patient_id:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, "Lịch phải thuộc đúng bệnh nhân của việc CSKH."
                )
        row, code = await book_in_session(session, ctx, payload)
        if task is not None:
            # The task is only LINKED here; closing it (outcome, note, owner) is POST /crm/tasks/{id}/resolve
            # with `booking`, which books and closes in one transaction.
            task.related_appointment_id = row.id
            with lost_race_is_conflict():
                await session.flush()
            await audit.record(
                session,
                ctx,
                "crm_task.link_appointment",
                "crm_task",
                task.id,
                {"appointment_id": str(row.id)},
            )
        created = appointment_out(row, code)
    announce(created.id, created.patient_id, "create", created.status)
    if task is not None:
        emit_live(LiveEventType.TASKS_CHANGED, task.id)
    return created


async def update_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentUpdate
) -> AppointmentOut:
    require(ctx, Permission.APPOINTMENT_WRITE)
    async with db.session() as session:
        row, code = await _load(session, ctx, appointment_id)
        _own_only(ctx, row.doctor_id)
        check_version(row.version, payload.version)
        if AppointmentStatus(row.status) not in rules.EDIT_FROM:
            raise DomainError(
                ErrorCode.INVALID_STATE, "Lịch đã bắt đầu, hoàn tất, hủy hoặc vắng; hãy tạo lịch mới."
            )
        sent = payload.model_fields_set
        doctor_id = payload.doctor_id if "doctor_id" in sent else row.doctor_id
        starts_at = payload.starts_at if payload.starts_at is not None else row.starts_at
        duration = payload.duration_min if payload.duration_min is not None else row.duration_min
        if "doctor_id" in sent:
            _own_only(ctx, doctor_id)
            await _check_doctor(session, ctx, doctor_id)
        changed = [n for n in ("doctor_id", "starts_at", "duration_min", "note") if _is_set(payload, n)]
        if {"doctor_id", "starts_at", "duration_min"} & set(changed):
            await validate_and_check(
                session,
                ctx,
                patient_id=row.patient_id,
                doctor_id=doctor_id,
                starts_at=starts_at,
                duration_min=duration,
                exclude=row.id,
            )
        row.doctor_id = doctor_id
        row.starts_at = starts_at
        row.duration_min = duration
        if "note" in sent:
            row.note = payload.note
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session, ctx, "appointment.update", "appointment", row.id, {"changed_fields": changed}
        )
        updated = appointment_out(row, code)
    announce(updated.id, updated.patient_id, "update", updated.status)
    return updated


def _is_set(payload: AppointmentUpdate, name: str) -> bool:
    if name not in payload.model_fields_set:
        return False
    return name in {"doctor_id", "note"} or getattr(payload, name) is not None


async def _transition(
    db: ClinicDatabase,
    ctx: ActionContext,
    appointment_id: UUID,
    payload: AppointmentTransition,
    *,
    verb: str,
    permission: Permission,
    allowed_from: frozenset[AppointmentStatus],
    target: AppointmentStatus,
    reason_required: bool = False,
) -> AppointmentOut:
    require(ctx, permission)
    action = f"appointment.{verb}"
    async with db.session() as session:
        row, code = await _load(session, ctx, appointment_id)
        _own_only(ctx, row.doctor_id)
        if await audit.find_replay(session, ctx, action, row.id):
            return appointment_out(row, code)
        check_version(row.version, payload.version)
        current = AppointmentStatus(row.status)
        if current not in allowed_from:
            raise DomainError(
                ErrorCode.INVALID_STATE, "Trạng thái lịch hiện tại không cho phép thao tác này."
            )
        reason = (payload.reason or "").strip()
        if reason_required and not reason:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Cần lý do cho thao tác này.")
        stamp = now()
        row.status = target.value
        if target is AppointmentStatus.CANCELLED:
            row.cancelled_at = stamp
            row.cancel_reason = reason
        if target is AppointmentStatus.MISSED:
            row.missed_at = stamp
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            action,
            "appointment",
            row.id,
            {"from": current.value, "to": target.value, "has_reason": bool(reason)},
        )
        changed = appointment_out(row, code)
    announce(changed.id, changed.patient_id, verb, target)
    return changed


async def confirm_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    """JS ``setStatus(id, 'confirmed')``: the desk confirmed the visit with the patient."""
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="confirm",
        permission=Permission.APPOINTMENT_WRITE,
        allowed_from=rules.CONFIRM_FROM,
        target=AppointmentStatus.CONFIRMED,
    )


async def check_in_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="check_in",
        permission=Permission.APPOINTMENT_CHECK_IN,
        allowed_from=rules.CHECK_IN_FROM,
        target=AppointmentStatus.ARRIVED,
    )


async def start_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="start",
        permission=Permission.APPOINTMENT_CHECK_IN,
        allowed_from=rules.START_FROM,
        target=AppointmentStatus.IN_PROGRESS,
    )


async def complete_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="complete",
        permission=Permission.APPOINTMENT_CHECK_IN,
        allowed_from=rules.COMPLETE_FROM,
        target=AppointmentStatus.COMPLETED,
    )


async def cancel_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="cancel",
        permission=Permission.APPOINTMENT_WRITE,
        allowed_from=rules.CANCEL_FROM,
        target=AppointmentStatus.CANCELLED,
        reason_required=True,
    )


async def miss_appointment(
    db: ClinicDatabase, ctx: ActionContext, appointment_id: UUID, payload: AppointmentTransition
) -> AppointmentOut:
    return await _transition(
        db,
        ctx,
        appointment_id,
        payload,
        verb="miss",
        permission=Permission.APPOINTMENT_CHECK_IN,
        allowed_from=rules.MISS_FROM,
        target=AppointmentStatus.MISSED,
    )


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=VN_TZ)


async def list_schedule(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    day: date,
    view: ScheduleView = ScheduleView.DAY,
    doctor_id: UUID | None = None,
) -> ScheduleOut:
    """JS ``schedule()``: the appointments of ``day`` (or the 7 days from it), optionally of one doctor. Every
    status is returned (the page hides cancelled and missed by default, as ``filtered`` did with
    ``O.active``). A doctor gets only their own appointments whatever ``doctor_id`` says (JS ``filtered``
    forces ``doctor`` to the signed-in doctor), so no patient of a colleague is named to them."""
    require(ctx, Permission.APPOINTMENT_READ)
    if is_doctor_scoped(ctx):
        doctor_id = ctx.actor_user_id
    days = 7 if view is ScheduleView.WEEK else 1
    starts = _day_start(day)
    ends = starts + timedelta(days=days)
    show_names = has_permission(ctx, Permission.PATIENT_READ)
    conditions: list[Any] = [
        Appointment.clinic_id == ctx.clinic_id,
        Appointment.starts_at >= starts,
        Appointment.starts_at < ends,
    ]
    if doctor_id is not None:
        conditions.append(Appointment.doctor_id == doctor_id)
    async with db.session() as session:
        rows = await session.execute(
            select(Appointment, Patient.code, Patient.full_name, UserAccount.display_name)
            .join(
                Patient, (Patient.id == Appointment.patient_id) & (Patient.clinic_id == Appointment.clinic_id)
            )
            .outerjoin(
                UserAccount,
                (UserAccount.id == Appointment.doctor_id) & (UserAccount.clinic_id == Appointment.clinic_id),
            )
            .where(*conditions)
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(SCHEDULE_LIMIT)
        )
        items = [
            ScheduleItem(
                **appointment_out(a, code).model_dump(),
                patient_name=full_name if show_names else None,
                doctor_name=doctor_name,
            )
            for a, code, full_name, doctor_name in rows.all()
        ]
        doctor_query = select(UserAccount.id, UserAccount.display_name).where(
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.active.is_(True),
            UserAccount.role.in_(DOCTOR_ROLES),
        )
        if is_doctor_scoped(ctx):
            doctor_query = doctor_query.where(UserAccount.id == ctx.actor_user_id)
        doctors = [
            ScheduleDoctor(id=uid, name=name)
            for uid, name in (await session.execute(doctor_query.order_by(UserAccount.display_name))).all()
        ]
    return ScheduleOut(
        view=view,
        from_day=day,
        to_day=day + timedelta(days=days - 1),
        doctor_id=doctor_id,
        items=items,
        doctors=doctors,
    )


async def find_free_slot(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    patient_id: UUID,
    doctor_id: UUID | None,
    day: date,
    duration_min: int = 30,
) -> FreeSlotOut:
    """JS ``suggest`` ("Tim gio trong"): the first start on ``day`` (steps of 15 minutes from 08:00) that the
    one validator accepts. One query loads the day's appointments of the doctor and the patient; the walk
    is in memory. A time that has already passed today is skipped."""
    require_any(ctx, (Permission.APPOINTMENT_WRITE, Permission.CRM_TASK_RESOLVE))
    if is_doctor_scoped(ctx):
        doctor_id = doctor_id or ctx.actor_user_id  # a doctor looks for a slot of their own
        _own_only(ctx, doctor_id)
    if duration_min < 5 or duration_min > 480:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thời lượng không hợp lệ.")
    opens = datetime.combine(day, rules.WORK_START, tzinfo=VN_TZ)
    closes = datetime.combine(day, rules.WORK_END, tzinfo=VN_TZ)
    owner = Appointment.patient_id == patient_id
    if doctor_id is not None:
        owner = owner | (Appointment.doctor_id == doctor_id)
    async with db.session() as session:
        await _patient_code(session, ctx, patient_id)
        await _check_doctor(session, ctx, doctor_id)
        found = await session.scalars(
            select(Appointment).where(
                Appointment.clinic_id == ctx.clinic_id,
                Appointment.status.notin_(_FREE),
                Appointment.starts_at < closes,
                Appointment.starts_at > opens - _MAX_DURATION,
                owner,
            )
        )
        existing = [
            rules.Slot(
                patient_id=a.patient_id,
                doctor_id=a.doctor_id,
                starts_at=a.starts_at,
                duration_min=a.duration_min,
                appointment_id=a.id,
                status=AppointmentStatus(a.status),
            )
            for a in found
        ]
    clock = now()
    start = opens
    while start + timedelta(minutes=duration_min) <= closes:
        candidate = rules.Slot(
            patient_id=patient_id, doctor_id=doctor_id, starts_at=start, duration_min=duration_min
        )
        try:
            rules.validate_slot(start, duration_min, clock)
        except DomainError:
            start += timedelta(minutes=SLOT_STEP_MIN)
            continue
        if start > clock and rules.find_conflict(candidate, existing) is None:
            return FreeSlotOut(starts_at=start)
        start += timedelta(minutes=SLOT_STEP_MIN)
    return FreeSlotOut(starts_at=None)


__all__ = [
    "announce",
    "book_in_session",
    "cancel_appointment",
    "check_in_appointment",
    "complete_appointment",
    "confirm_appointment",
    "create_appointment",
    "find_free_slot",
    "get_appointment",
    "list_appointments",
    "list_schedule",
    "miss_appointment",
    "start_appointment",
    "update_appointment",
    "validate_and_check",
]

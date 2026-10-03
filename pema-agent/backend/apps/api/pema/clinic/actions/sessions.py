# ported from: prototype/shared/clinic.js (``session``, ``save-session``)
"""Treatment sessions of the Buổi điều trị tab: list, record, complete, review (actions behind
``routers/patient_care.py``).

What the old ``save-session`` did, and where it is here (completion = the old "Lưu buổi điều trị"):

* a plan that already has all its sessions refuses a new one ("Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch
  trước khi thêm buổi mới.");
* the assessment before the session and the aftercare text are both required;
* the date must be valid, not in the future and not before the previous session (old: ``sessionDate >
  today`` and ``sessionDate < p.lastVisit``; the demo's fixed day 20/09/2026 is the real clock here);
* the plan counter ``completed_sessions`` goes up by one (the plan closes when it reaches the total);
* the record keeps date, type, protocol id (``laser-co2`` drives D+1/3/7/30), region, view, the consent the
  photos rest on, ``reviewed = true`` (a clinician recorded it);
* an appointment of that day that is ``arrived`` or ``in_progress`` becomes ``completed``;
* the doctor's wish for the next visit (``session-next``, default +30 days) becomes the patient's
  ``recommendation_at`` with source ``doctor_recommendation``;
* no photo with the session raises the task "Thiếu ảnh mốc đánh giá" (the old follow-up of priority
  ``missing``), owned by the patient's care owner; confirming a photo of the session resolves it;
* the CRM milestones D+1/3/7 are NOT written here: the completed session with its ``protocol_id`` is the event
  the rules of package B2 read (``crm_rules.sql_store`` loads completed sessions), so the next run of the
  runner produces the tasks. Nothing is sent to the patient: the aftercare text is stored for staff and
for the
  approved-template flow, never auto-sent (PLAN-AI01 section 5).

Forced deviations: localStorage -> ``clinic.treatment_session``; the browser built the timeline event and the
message to the patient in the same function, here the timeline is read from the rows (``patient_360``) and no
message is sent.

Rules: ``session.write`` (doctor, owner) writes, narrowed to a doctor's own patients; ``session.read`` reads
(doctor, owner, and care staff for the patients they look after). Audit details carry ids and field names,
never
the clinical text.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._care_mappers import session_detail_out
from pema.clinic.actions._clinical_scope import (
    CLINICIAN_ROLES,
    current_media_consent,
    names_of,
    require_clinical_scope,
)
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import Appointment, CrmTask, Patient, TreatmentPlan, TreatmentSession
from pema.clinic.rbac import is_role, require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.patient_care import SessionComplete, SessionCreate, SessionDetailOut, SessionReview
from pema_contracts.roles import Permission

PLAN_FULL_MESSAGE = "Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch trước khi thêm buổi mới."
NOTE_REQUIRED_MESSAGE = "Hãy ghi đánh giá trước buổi."
AFTERCARE_REQUIRED_MESSAGE = "Hãy nhập hướng dẫn chăm sóc sau buổi."
DATE_FUTURE_MESSAGE = "Ngày buổi không được ở tương lai."
DATE_BEFORE_LAST_MESSAGE = "Ngày buổi không được trước buổi điều trị gần nhất."
MISSING_PHOTO_REASON = "Thiếu ảnh mốc đánh giá"
MISSING_PHOTO_ACTION = "Chụp bổ sung ảnh mốc của buổi điều trị vừa lưu (cần đồng ý hình ảnh)."
RECOMMENDATION_AFTER_DAYS = 30
"""Old ``PemaCRMData.addDays(sessionDate, 30)``: the next assessment when the doctor gave no date."""
RECOMMENDATION_REASON = "Bác sĩ hẹn đánh giá sau buổi"
OPEN_TASK_STATUSES = ("open", "rescheduled")
_VISIT_STATUSES = ("arrived", "in_progress")


def missing_photo_task_key(session_id: UUID) -> str:
    return f"MANUAL:missing_photo:{session_id}"


def _performed_at(day: date) -> datetime:
    """The instant stored for a session of ``day``: the real time when it is today, noon otherwise."""
    stamp = now().astimezone(VN_TZ)
    if day == stamp.date():
        return stamp
    return datetime.combine(day, time(12, 0), tzinfo=VN_TZ)


def _local_day(moment: datetime) -> date:
    return moment.astimezone(VN_TZ).date()


def _clean(value: str | None) -> str:
    return (value or "").strip()


async def _load_session(session: AsyncSession, ctx: ActionContext, session_id: UUID) -> TreatmentSession:
    row = await session.scalar(
        select(TreatmentSession).where(
            TreatmentSession.clinic_id == ctx.clinic_id, TreatmentSession.id == session_id
        )
    )
    if row is None:
        raise not_found("buổi điều trị")
    return row


async def _load_plan(
    session: AsyncSession, ctx: ActionContext, plan_id: UUID, patient_id: UUID
) -> TreatmentPlan:
    plan = await session.scalar(
        select(TreatmentPlan).where(
            TreatmentPlan.clinic_id == ctx.clinic_id,
            TreatmentPlan.id == plan_id,
            TreatmentPlan.patient_id == patient_id,
        )
    )
    if plan is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Kế hoạch không thuộc người bệnh này.")
    return plan


async def _last_visit_day(
    session: AsyncSession, ctx: ActionContext, patient_id: UUID, *, excluding: UUID | None
) -> date | None:
    conditions = [
        TreatmentSession.clinic_id == ctx.clinic_id,
        TreatmentSession.patient_id == patient_id,
        TreatmentSession.status == "completed",
    ]
    if excluding is not None:
        conditions.append(TreatmentSession.id != excluding)
    newest = await session.scalar(
        select(TreatmentSession.performed_at)
        .where(*conditions)
        .order_by(TreatmentSession.performed_at.desc())
        .limit(1)
    )
    return _local_day(newest) if newest is not None else None


def _check_complete_inputs(note: str, aftercare: str) -> None:
    if not note:
        raise DomainError(ErrorCode.VALIDATION_FAILED, NOTE_REQUIRED_MESSAGE)
    if not aftercare:
        raise DomainError(ErrorCode.VALIDATION_FAILED, AFTERCARE_REQUIRED_MESSAGE)


async def _check_complete_date(
    session: AsyncSession, ctx: ActionContext, row: TreatmentSession, day: date
) -> None:
    if day > _local_day(now()):
        raise DomainError(ErrorCode.VALIDATION_FAILED, DATE_FUTURE_MESSAGE)
    last = await _last_visit_day(session, ctx, row.patient_id, excluding=row.id)
    if last is not None and day < last:
        raise DomainError(ErrorCode.VALIDATION_FAILED, DATE_BEFORE_LAST_MESSAGE)


async def _finish(
    session: AsyncSession,
    ctx: ActionContext,
    patient: Patient,
    row: TreatmentSession,
    *,
    with_photo: bool,
) -> tuple[bool, bool]:
    """Complete ``row`` in the caller's transaction; returns (task created, appointment completed).

    ``row`` already holds the final note, aftercare, date and next visit (validated by the caller)."""
    plan: TreatmentPlan | None = None
    if row.plan_id is not None:
        plan = await _load_plan(session, ctx, row.plan_id, row.patient_id)
        if plan.completed_sessions >= plan.total_sessions:
            raise DomainError(ErrorCode.INVALID_STATE, PLAN_FULL_MESSAGE)
        plan.completed_sessions += 1
        if plan.status == "planned":
            plan.status = "active"
        if plan.completed_sessions >= plan.total_sessions:
            plan.status = "completed"
    kind = row.session_type or "Buổi điều trị"
    row.title = f"Buổi {plan.completed_sessions}/{plan.total_sessions} · {kind}" if plan else kind
    row.status = "completed"
    row.reviewed = True
    row.reviewed_by = ctx.actor_user_id
    row.reviewed_at = now()
    if row.doctor_id is None:
        row.doctor_id = ctx.actor_user_id if is_role(ctx, *CLINICIAN_ROLES) else patient.doctor_id
    consent = await current_media_consent(session, ctx, row.patient_id)
    row.consent_id = consent.id if consent is not None else None

    day = _local_day(row.performed_at)
    visit = await session.scalar(
        select(Appointment)
        .where(
            Appointment.clinic_id == ctx.clinic_id,
            Appointment.patient_id == row.patient_id,
            Appointment.status.in_(_VISIT_STATUSES),
            Appointment.starts_at >= datetime.combine(day, time.min, tzinfo=VN_TZ),
            Appointment.starts_at < datetime.combine(day + timedelta(days=1), time.min, tzinfo=VN_TZ),
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    )
    if visit is not None:
        visit.status = "completed"

    patient.recommendation_at = row.next_visit_on or day + timedelta(days=RECOMMENDATION_AFTER_DAYS)
    patient.expected_visit_source = "doctor_recommendation"
    patient.expected_visit_reason = RECOMMENDATION_REASON

    task_created = False
    if not with_photo:
        existing = await session.scalar(
            select(CrmTask.id).where(
                CrmTask.clinic_id == ctx.clinic_id, CrmTask.task_key == missing_photo_task_key(row.id)
            )
        )
        if existing is None:
            session.add(
                CrmTask(
                    clinic_id=ctx.clinic_id,
                    task_key=missing_photo_task_key(row.id),
                    patient_id=row.patient_id,
                    rule_key="manual",
                    reason=MISSING_PHOTO_REASON,
                    priority="normal",
                    status="open",
                    owner_user_id=patient.cs_owner_id,
                    due_at=now(),
                    suggested_action=MISSING_PHOTO_ACTION,
                    source_event_id=str(row.id),
                    related_plan_id=row.plan_id,
                )
            )
            task_created = True
    with lost_race_is_conflict():
        await session.flush()
    return task_created, visit is not None


async def list_sessions(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> list[SessionDetailOut]:
    require(ctx, Permission.SESSION_READ)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        rows = (
            await session.scalars(
                select(TreatmentSession)
                .where(TreatmentSession.clinic_id == ctx.clinic_id, TreatmentSession.patient_id == patient_id)
                .order_by(TreatmentSession.performed_at.desc(), TreatmentSession.id)
            )
        ).all()
        names = await names_of(session, ctx, [r.doctor_id for r in rows])
        await audit.record(session, ctx, "session.list", "patient", patient_id)
        return [session_detail_out(r, names.get(r.doctor_id) if r.doctor_id else None) for r in rows]


async def create_session(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: SessionCreate
) -> SessionDetailOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        plan: TreatmentPlan | None = None
        if payload.plan_id is not None:
            plan = await _load_plan(session, ctx, payload.plan_id, patient_id)
        note = _clean(payload.note)
        aftercare = _clean(payload.aftercare)
        row = TreatmentSession(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            plan_id=payload.plan_id,
            doctor_id=ctx.actor_user_id
            if is_role(ctx, *CLINICIAN_ROLES)
            else (plan.doctor_id if plan is not None else patient.doctor_id),
            performed_at=_performed_at(payload.performed_on),
            protocol_id=payload.protocol_id or None,
            title=payload.session_type,
            note=note or None,
            status="scheduled",
            session_type=payload.session_type,
            region=payload.region,
            view=payload.view,
            next_visit_on=payload.next_visit_on,
            aftercare=aftercare or None,
            created_by=ctx.actor_user_id,
        )
        session.add(row)
        with lost_race_is_conflict():
            await session.flush()
        task_created = False
        visit_completed = False
        if payload.complete:
            _check_complete_inputs(note, aftercare)
            await _check_complete_date(session, ctx, row, payload.performed_on)
            task_created, visit_completed = await _finish(
                session, ctx, patient, row, with_photo=payload.with_photo
            )
        await audit.record(
            session,
            ctx,
            "session.complete" if payload.complete else "session.create",
            "treatment_session",
            row.id,
            {
                "patient_id": str(patient_id),
                "plan_id": str(row.plan_id) if row.plan_id else None,
                "protocol_id": row.protocol_id,
                "missing_photo_task": task_created,
                "appointment_completed": visit_completed,
            },
        )
        names = await names_of(session, ctx, [row.doctor_id])
        out = session_detail_out(row, names.get(row.doctor_id) if row.doctor_id else None)
    if task_created:
        emit_live(LiveEventType.TASKS_CHANGED)
    return out


async def complete_session(
    db: ClinicDatabase, ctx: ActionContext, session_id: UUID, payload: SessionComplete
) -> SessionDetailOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        row = await _load_session(session, ctx, session_id)
        patient = await load_patient(session, ctx, row.patient_id)
        await require_patient_access(session, ctx, row.patient_id)
        check_version(row.version, payload.version)
        if row.status != "scheduled":
            raise DomainError(ErrorCode.INVALID_STATE, "Buổi điều trị này đã được hoàn tất hoặc đã hủy.")
        if payload.note is not None:
            row.note = _clean(payload.note) or None
        if payload.aftercare is not None:
            row.aftercare = _clean(payload.aftercare) or None
        if payload.next_visit_on is not None:
            row.next_visit_on = payload.next_visit_on
        day = payload.performed_on or _local_day(row.performed_at)
        _check_complete_inputs(_clean(row.note), _clean(row.aftercare))
        await _check_complete_date(session, ctx, row, day)
        if payload.performed_on is not None:
            row.performed_at = _performed_at(day)
        task_created, visit_completed = await _finish(
            session, ctx, patient, row, with_photo=payload.with_photo
        )
        await audit.record(
            session,
            ctx,
            "session.complete",
            "treatment_session",
            row.id,
            {
                "patient_id": str(row.patient_id),
                "plan_id": str(row.plan_id) if row.plan_id else None,
                "protocol_id": row.protocol_id,
                "missing_photo_task": task_created,
                "appointment_completed": visit_completed,
            },
        )
        names = await names_of(session, ctx, [row.doctor_id])
        out = session_detail_out(row, names.get(row.doctor_id) if row.doctor_id else None)
    if task_created:
        emit_live(LiveEventType.TASKS_CHANGED)
    return out


async def review_session(
    db: ClinicDatabase, ctx: ActionContext, session_id: UUID, payload: SessionReview
) -> SessionDetailOut:
    """A clinician signs off a completed session. Reviewing a reviewed session changes nothing."""
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        row = await _load_session(session, ctx, session_id)
        await require_patient_access(session, ctx, row.patient_id)
        if row.status != "completed":
            raise DomainError(ErrorCode.INVALID_STATE, "Chỉ buổi đã hoàn tất mới cần duyệt.")
        if not row.reviewed:
            check_version(row.version, payload.version)
            row.reviewed = True
            row.reviewed_by = ctx.actor_user_id
            row.reviewed_at = now()
            with lost_race_is_conflict():
                await session.flush()
            await audit.record(
                session,
                ctx,
                "session.review",
                "treatment_session",
                row.id,
                {"patient_id": str(row.patient_id)},
            )
        names = await names_of(session, ctx, [row.doctor_id])
        return session_detail_out(row, names.get(row.doctor_id) if row.doctor_id else None)

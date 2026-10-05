# ported from: prototype/shared/clinic.js (send-message, save-care, approve-brief), data.js (brief)
"""What a doctor puts on the patient app timeline, and the templated brief (actions behind
``routers/patient_profile.py``).

Forced deviation: the prototype wrote ``p.messages``, ``p.aftercare`` and ``p.approvedBrief`` into the
one ``localStorage`` document that the Patient Mobile web also read. Here a note is a row of
``clinic.patient_app_event`` for the patient app to read. **No channel is used**: nothing is sent through
Zalo or SMS, and the proactive guard of the channels does not apply because nothing leaves the
installation.

* ``send_update`` kind ``message`` ("Nhắn tin") needs ``conversation.reply``; kind ``aftercare``
  ("Chăm sóc tại nhà") needs ``session.write`` (the old ``clinical`` capability). An empty text is refused;
* ``get_brief`` / ``approve_brief`` need ``session.write``: the brief is a draft for the doctor. **It is
  a template over existing records** (plan counters, the latest finished session, the next appointment or
  the recommended return date, the open follow-up tasks, the warning lines); no model is called and nothing
  is inferred. ``source_ids`` name the records (``kind:id`` like the timeline) and are recomputed by the BE
  at approval, never taken from the client.

Audit details carry ids, kinds and lengths, never the text.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._clinical_scope import names_of, require_clinical_scope
from pema.clinic.actions._common import now
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient, today_vn
from pema.clinic.domain.appointments import FREE_STATUSES
from pema.clinic.models import (
    Appointment,
    CrmTask,
    Patient,
    PatientAppEvent,
    PatientBrief,
    TreatmentPlan,
    TreatmentSession,
)
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patient_profile import (
    AFTERCARE_BLANK_MESSAGE,
    BRIEF_BLANK_MESSAGE,
    MESSAGE_BLANK_MESSAGE,
    AppUpdateCreate,
    AppUpdateKind,
    AppUpdateOut,
    BriefApprove,
    BriefApprovedOut,
    BriefDraftOut,
)
from pema_contracts.roles import Permission

LIST_LIMIT = 20
LIVE_PLAN_STATUSES = ("planned", "active")
OPEN_TASK_STATUSES = ("open", "rescheduled")
_NOT_A_VISIT = [*(s.value for s in FREE_STATUSES), AppointmentStatus.COMPLETED.value]
NEXT_STEP_SENTENCE = "Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch."


def _out(row: PatientAppEvent, names: dict[UUID, str]) -> AppUpdateOut:
    return AppUpdateOut(
        id=row.id,
        kind=AppUpdateKind(row.kind),
        body=row.body,
        created_at=row.created_at,
        by_name=names.get(row.created_by) if row.created_by else None,
    )


async def send_update(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: AppUpdateCreate
) -> AppUpdateOut:
    if payload.kind is AppUpdateKind.AFTERCARE:
        require(ctx, Permission.SESSION_WRITE)
    else:
        require(ctx, Permission.CONVERSATION_REPLY)
    text = payload.body.strip()
    if text == "":
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            AFTERCARE_BLANK_MESSAGE if payload.kind is AppUpdateKind.AFTERCARE else MESSAGE_BLANK_MESSAGE,
        )
    async with db.session() as session:
        await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        row = PatientAppEvent(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            kind=payload.kind.value,
            body=text,
            created_by=ctx.actor_user_id,
            created_at=now(),
        )
        session.add(row)
        await session.flush()
        await audit.record(
            session,
            ctx,
            "patient_app.send",
            "patient_app_event",
            row.id,
            {"patient_id": str(patient_id), "kind": payload.kind.value, "chars": len(text)},
        )
        names = await names_of(session, ctx, [row.created_by])
        return _out(row, names)


async def list_updates(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, kind: AppUpdateKind | None = None
) -> list[AppUpdateOut]:
    """The latest notes on the timeline, newest first (the dialog "Chăm sóc tại nhà" opens on the last
    ``aftercare``). Clinical text: ``session.read`` and the scope of the clinical tabs."""
    require(ctx, Permission.SESSION_READ)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        query = select(PatientAppEvent).where(
            PatientAppEvent.clinic_id == ctx.clinic_id, PatientAppEvent.patient_id == patient_id
        )
        if kind is not None:
            query = query.where(PatientAppEvent.kind == kind.value)
        rows = (
            await session.scalars(query.order_by(PatientAppEvent.created_at.desc()).limit(LIST_LIMIT))
        ).all()
        names = await names_of(session, ctx, [r.created_by for r in rows])
        return [_out(r, names) for r in rows]


# --------------------------------------------------------------------------------------------- the brief
def _day(value: date) -> str:
    """The old ``Pema.date``: ``6/9/2026``."""
    return f"{value.day}/{value.month}/{value.year}"


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


async def build_brief(session: AsyncSession, ctx: ActionContext, patient: Patient) -> tuple[str, list[str]]:
    """``Pema.brief(p)`` over the records of this system: the text and the ids of the records used."""
    cid, pid = ctx.clinic_id, patient.id
    today = today_vn()
    plans = list(
        (
            await session.scalars(
                select(TreatmentPlan)
                .where(TreatmentPlan.clinic_id == cid, TreatmentPlan.patient_id == pid)
                .order_by(TreatmentPlan.created_at.desc(), TreatmentPlan.id)
            )
        ).all()
    )
    live = [p for p in plans if p.status in LIVE_PLAN_STATUSES and p.completed_sessions < p.total_sessions]
    candidates = live or [p for p in plans if p.status in LIVE_PLAN_STATUSES] or plans
    lead = candidates[0] if candidates else None
    last = await session.scalar(
        select(TreatmentSession)
        .where(
            TreatmentSession.clinic_id == cid,
            TreatmentSession.patient_id == pid,
            TreatmentSession.status == "completed",
        )
        .order_by(TreatmentSession.performed_at.desc())
        .limit(1)
    )
    next_visit = await session.scalar(
        select(Appointment)
        .where(
            Appointment.clinic_id == cid,
            Appointment.patient_id == pid,
            Appointment.status.notin_(_NOT_A_VISIT),
            Appointment.starts_at >= datetime.combine(today, datetime.min.time(), tzinfo=VN_TZ),
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    )
    tasks = list(
        (
            await session.scalars(
                select(CrmTask)
                .where(
                    CrmTask.clinic_id == cid,
                    CrmTask.patient_id == pid,
                    CrmTask.status.in_(OPEN_TASK_STATUSES),
                )
                .order_by(CrmTask.due_at)
            )
        ).all()
    )

    sources: list[str] = []
    sentences: list[str] = []
    age = _age(patient.birth_date, today)
    sentences.append(f"{patient.full_name}{f', {age} tuổi' if age is not None else ''}.")
    if lead is None:
        sentences.append("Chưa có liệu trình được thiết lập.")
    else:
        sources.append(f"plan:{lead.id}")
        sentences.append(
            f"Liệu trình {lead.title}: đã hoàn tất {lead.completed_sessions}/{lead.total_sessions} buổi."
        )
    if last is None:
        sentences.append("Lần gần nhất: Chưa ghi nhận.")
        sentences.append("Chưa có cập nhật sau điều trị.")
    else:
        sources.append(f"session:{last.id}")
        sentences.append(f"Lần gần nhất: {_day(last.performed_at.astimezone(VN_TZ).date())}.")
        sentences.append(f"Buổi gần nhất: {last.title}.")
    upcoming = next_visit
    if upcoming is not None:
        sources.append(f"appointment:{upcoming.id}")
        sentences.append(f"Hẹn tiếp theo: {_day(upcoming.starts_at.astimezone(VN_TZ).date())}.")
    elif patient.recommendation_at is not None:
        late = (today - patient.recommendation_at).days
        sentences.append(
            f"Dự kiến quay lại {_day(patient.recommendation_at)}, đã quá hạn {late} ngày."
            if late > 0
            else f"Dự kiến quay lại: {_day(patient.recommendation_at)}."
        )
    else:
        sentences.append("Chưa có lịch hẹn tiếp theo.")
    if patient.alerts:
        sentences.append(f"Cần nhớ: {'; '.join(patient.alerts)}.")
    if tasks:
        sources.extend(f"crm_task:{t.id}" for t in tasks)
        sentences.append(f"Có {len(tasks)} mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo.")
    else:
        sentences.append("Không có mục theo dõi đang mở.")
    sentences.append(NEXT_STEP_SENTENCE)
    return " ".join(sentences), sources


async def _last_approved(
    session: AsyncSession, ctx: ActionContext, patient_id: UUID
) -> BriefApprovedOut | None:
    row = await session.scalar(
        select(PatientBrief)
        .where(PatientBrief.clinic_id == ctx.clinic_id, PatientBrief.patient_id == patient_id)
        .order_by(PatientBrief.approved_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    names = await names_of(session, ctx, [row.approved_by])
    return BriefApprovedOut(
        id=row.id,
        text=row.body,
        approved_by_name=names.get(row.approved_by) if row.approved_by else None,
        approved_at=row.approved_at,
        source_ids=list(row.source_ids or []),
    )


async def get_brief(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> BriefDraftOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        text, sources = await build_brief(session, ctx, patient)
        return BriefDraftOut(
            text=text, source_ids=sources, approved=await _last_approved(session, ctx, patient_id)
        )


async def approve_brief(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: BriefApprove
) -> BriefApprovedOut:
    require(ctx, Permission.SESSION_WRITE)
    text = payload.text.strip()
    if text == "":
        raise DomainError(ErrorCode.VALIDATION_FAILED, BRIEF_BLANK_MESSAGE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        _, sources = await build_brief(session, ctx, patient)
        row = PatientBrief(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            body=text,
            source_ids=sources,
            approved_by=ctx.actor_user_id,
            approved_at=now(),
        )
        session.add(row)
        await session.flush()
        await audit.record(
            session,
            ctx,
            "patient.brief_approve",
            "patient_brief",
            row.id,
            {"patient_id": str(patient_id), "source_count": len(sources), "chars": len(text)},
        )
        names = await names_of(session, ctx, [row.approved_by])
        return BriefApprovedOut(
            id=row.id,
            text=row.body,
            approved_by_name=names.get(row.approved_by) if row.approved_by else None,
            approved_at=row.approved_at,
            source_ids=list(sources),
        )


__all__ = ["approve_brief", "build_brief", "get_brief", "list_updates", "send_update"]

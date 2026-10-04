# ported from: prototype/shared/crm-automation.js (timeline, profile) and prototype/shared/clinic.js (360)
"""Patient 360: the read model that joins context. The original records stay the source of truth
(AGENT.md): every timeline row carries the id of the record it came from (``source_id``).

Forced deviation: the prototype built the timeline in the browser from ``localStorage`` arrays; here the
rows come from ``clinic.*``. Message bodies are NOT copied into the timeline (the conversation endpoints
own them, and read access to them is audited separately); a message row shows direction and time only.
Reading the 360 is itself audited (ARCH-PB01: audit for reads of sensitive content).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pema.clinic import audit
from pema.clinic.actions._common import now
from pema.clinic.actions._mappers import (
    activity_out,
    appointment_out,
    consent_out,
    task_out,
)
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.conversations import summaries
from pema.clinic.actions.patients import load_patient, patient_to_out
from pema.clinic.domain.appointments import FREE_STATUSES
from pema.clinic.domain.profile import ProfileFacts, compute_profile
from pema.clinic.models import (
    Appointment,
    Consent,
    Conversation,
    CrmActivity,
    CrmTask,
    Episode,
    Message,
    Patient,
    ReviewItem,
    TreatmentPlan,
    TreatmentSession,
    UserAccount,
)
from pema.clinic.rbac import has_permission, require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import VN_TZ
from pema_contracts.crm import CrmChannel, CrmOutcome
from pema_contracts.patients import (
    ConsentOut,
    EpisodeOut,
    Patient360,
    TimelineEvent,
    TreatmentPlanOut,
    TreatmentSessionOut,
)
from pema_contracts.roles import Permission

RECENT_SESSIONS = 10
RECENT_ACTIVITIES = 10
APPOINTMENT_WINDOW = 20
TIMELINE_LIMIT = 60
LIVE_PLAN_STATUSES = ("planned", "active")
OPEN_TASK_STATUSES = ("open", "rescheduled")
_FREE = [s.value for s in FREE_STATUSES]

APPOINTMENT_LABELS = {
    "booked": "Đặt hẹn",
    "confirmed": "Đã xác nhận",
    "arrived": "Đã đến",
    "in_progress": "Đang khám",
    "completed": "Hoàn tất",
    "cancelled": "Đã hủy",
    "missed": "Vắng hẹn",
}
CHANNEL_LABELS = {
    CrmChannel.CALL.value: "Gọi điện",
    CrmChannel.ZALO.value: "Zalo",
    CrmChannel.SMS.value: "SMS",
    CrmChannel.INTERNAL_NOTE.value: "Ghi chú nội bộ",
}
OUTCOME_LABELS = {
    CrmOutcome.UNANSWERED.value: "Không nghe máy",
    CrmOutcome.CALLBACK.value: "Gọi lại sau",
    CrmOutcome.NO_NEED.value: "Đã liên hệ, chưa có nhu cầu",
    CrmOutcome.BUSY.value: "Đang bận, hẹn gọi lại",
    CrmOutcome.BOOKED.value: "Đồng ý đặt lịch",
    CrmOutcome.DOCTOR.value: "Muốn bác sĩ tư vấn",
    CrmOutcome.REACTION.value: "Có phản hồi sau điều trị",
    CrmOutcome.COMPLAINT.value: "Khiếu nại",
    CrmOutcome.OPTOUT.value: "Không muốn nhận CSKH",
    CrmOutcome.INVALID.value: "Sai số / không liên hệ được",
}


async def _profile_facts(
    session: AsyncSession, ctx: ActionContext, patient: Patient, plans: list[TreatmentPlan]
) -> ProfileFacts:
    today = now().astimezone(VN_TZ).date()
    last_session_at = await session.scalar(
        select(TreatmentSession.performed_at)
        .where(
            TreatmentSession.clinic_id == ctx.clinic_id,
            TreatmentSession.patient_id == patient.id,
            TreatmentSession.status == "completed",
        )
        .order_by(TreatmentSession.performed_at.desc())
        .limit(1)
    )
    any_session = await session.scalar(
        select(TreatmentSession.id)
        .where(TreatmentSession.clinic_id == ctx.clinic_id, TreatmentSession.patient_id == patient.id)
        .limit(1)
    )
    next_appointment = await session.scalar(
        select(Appointment.starts_at)
        .where(
            Appointment.clinic_id == ctx.clinic_id,
            Appointment.patient_id == patient.id,
            Appointment.status.notin_([*_FREE, AppointmentStatus.COMPLETED.value]),
            Appointment.starts_at >= datetime.combine(today, datetime.min.time(), tzinfo=VN_TZ),
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    )
    live = [p for p in plans if p.status in LIVE_PLAN_STATUSES]
    return ProfileFacts(
        today=today,
        last_visit=last_session_at.astimezone(VN_TZ).date() if last_session_at else None,
        has_sessions=any_session is not None,
        total_sessions=sum(p.total_sessions for p in live),
        completed_sessions=sum(p.completed_sessions for p in live),
        next_appointment=next_appointment.astimezone(VN_TZ).date() if next_appointment else None,
        recommendation_at=patient.recommendation_at,
        expected_visit_source=patient.expected_visit_source,
        reactivated=patient.reactivated_at is not None,
        marketing_opt_out=patient.marketing_opt_out,
    )


def _timeline(
    sessions: list[TreatmentSession],
    appointments: list[Appointment],
    activities: list[CrmActivity],
    messages: list[Message],
    reviews: list[ReviewItem],
    consents: list[Consent],
    names: dict[UUID, str],
) -> list[TimelineEvent]:
    rows: list[TimelineEvent] = []
    for s in sessions:
        rows.append(
            TimelineEvent(
                id=f"session:{s.id}",
                at=s.performed_at,
                kind="session",
                title=s.title,
                by=names.get(s.doctor_id) if s.doctor_id else None,
                source_id=str(s.id),
            )
        )
    for a in appointments:
        rows.append(
            TimelineEvent(
                id=f"appointment:{a.id}",
                at=a.starts_at,
                kind="appointment",
                title="Lịch hẹn · " + APPOINTMENT_LABELS.get(a.status, a.status),
                by=names.get(a.created_by) if a.created_by else None,
                source_id=str(a.id),
            )
        )
    for c in activities:
        outcome = OUTCOME_LABELS.get(c.outcome or "", "Ghi chú")
        rows.append(
            TimelineEvent(
                id=f"crm_activity:{c.id}",
                at=c.occurred_at,
                kind="crm_activity",
                title=f"{CHANNEL_LABELS.get(c.channel, c.channel)} · {outcome}",
                by=names.get(c.actor_user_id) if c.actor_user_id else None,
                source_id=str(c.id),
            )
        )
    for m in messages:
        rows.append(
            TimelineEvent(
                id=f"message:{m.id}",
                at=m.created_at,
                kind="message",
                title="Tin nhắn đến" if m.direction == "inbound" else "Tin nhắn đi",
                source_id=str(m.id),
            )
        )
    for r in reviews:
        rows.append(
            TimelineEvent(
                id=f"review:{r.id}",
                at=r.created_at,
                kind="review",
                title=f"Duyệt nội dung · {r.status}",
                source_id=str(r.id),
            )
        )
    for k in consents:
        rows.append(
            TimelineEvent(
                id=f"consent:{k.id}",
                at=k.created_at,
                kind="consent",
                title=f"Đồng ý {k.kind} · {'có' if k.granted else 'rút'}",
                source_id=str(k.id),
            )
        )
    rows.sort(key=lambda e: e.at, reverse=True)
    return rows[:TIMELINE_LIMIT]


async def get_patient_360(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> Patient360:
    require(ctx, Permission.PATIENT_READ_360)
    cid = ctx.clinic_id
    async with db.session(cid) as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        patient_dto = await patient_to_out(session, ctx, patient)

        episodes = (
            await session.scalars(
                select(Episode)
                .where(Episode.clinic_id == cid, Episode.patient_id == patient_id)
                .order_by(Episode.started_on.desc())
            )
        ).all()
        plans = list(
            (
                await session.scalars(
                    select(TreatmentPlan)
                    .where(TreatmentPlan.clinic_id == cid, TreatmentPlan.patient_id == patient_id)
                    .order_by(TreatmentPlan.id)
                )
            ).all()
        )
        sessions = list(
            (
                await session.scalars(
                    select(TreatmentSession)
                    .where(TreatmentSession.clinic_id == cid, TreatmentSession.patient_id == patient_id)
                    .order_by(TreatmentSession.performed_at.desc())
                    .limit(RECENT_SESSIONS)
                )
            ).all()
        )
        appointments = list(
            (
                await session.scalars(
                    select(Appointment)
                    .where(Appointment.clinic_id == cid, Appointment.patient_id == patient_id)
                    .order_by(Appointment.starts_at.desc())
                    .limit(APPOINTMENT_WINDOW)
                )
            ).all()
        )
        owner = aliased(UserAccount)
        task_rows = (
            await session.execute(
                select(CrmTask, owner.display_name)
                .outerjoin(
                    owner, (owner.id == CrmTask.owner_user_id) & (owner.clinic_id == CrmTask.clinic_id)
                )
                .where(
                    CrmTask.clinic_id == cid,
                    CrmTask.patient_id == patient_id,
                    CrmTask.status.in_(OPEN_TASK_STATUSES),
                )
                .order_by(CrmTask.due_at)
            )
        ).all()
        actor = aliased(UserAccount)
        activity_rows = (
            await session.execute(
                select(CrmActivity, actor.display_name)
                .outerjoin(
                    actor,
                    (actor.id == CrmActivity.actor_user_id) & (actor.clinic_id == CrmActivity.clinic_id),
                )
                .where(CrmActivity.clinic_id == cid, CrmActivity.patient_id == patient_id)
                .order_by(CrmActivity.occurred_at.desc())
                .limit(RECENT_ACTIVITIES)
            )
        ).all()
        consent_history = list(
            (
                await session.scalars(
                    select(Consent)
                    .where(Consent.clinic_id == cid, Consent.patient_id == patient_id)
                    .order_by(Consent.created_at.desc(), Consent.id.desc())
                )
            ).all()
        )
        newest_per_kind: dict[str, Consent] = {}
        for c in consent_history:
            newest_per_kind.setdefault(c.kind, c)
        consents: list[ConsentOut] = [consent_out(c) for c in newest_per_kind.values()]

        conversations = []
        messages: list[Message] = []
        if has_permission(ctx, Permission.CONVERSATION_READ):
            conversations, _, _ = await summaries(
                session, ctx, [Conversation.patient_id == patient_id], limit=20, offset=0
            )
            conv_ids = [c.id for c in conversations]
            if conv_ids:
                messages = list(
                    (
                        await session.scalars(
                            select(Message)
                            .where(Message.clinic_id == cid, Message.conversation_id.in_(conv_ids))
                            .order_by(Message.created_at.desc())
                            .limit(20)
                        )
                    ).all()
                )
        reviews = list(
            (
                await session.scalars(
                    select(ReviewItem)
                    .where(ReviewItem.clinic_id == cid, ReviewItem.patient_id == patient_id)
                    .order_by(ReviewItem.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
        user_ids = {
            *(s.doctor_id for s in sessions if s.doctor_id),
            *(a.created_by for a in appointments if a.created_by),
            *(a.actor_user_id for a, _ in activity_rows if a.actor_user_id),
        }
        names: dict[UUID, str] = {}
        if user_ids:
            name_rows = await session.execute(
                select(UserAccount.id, UserAccount.display_name).where(
                    UserAccount.clinic_id == cid, UserAccount.id.in_(user_ids)
                )
            )
            names = {r.id: r.display_name for r in name_rows}

        facts = await _profile_facts(session, ctx, patient, plans)
        timeline = _timeline(
            sessions, appointments, [a for a, _ in activity_rows], messages, reviews, consent_history, names
        )
        code_by_patient = {patient.id: patient.code}
        dto = Patient360(
            patient=patient_dto,
            profile=compute_profile(facts),
            episodes=[
                EpisodeOut(
                    id=e.id, title=e.title, status=e.status, started_on=e.started_on, closed_on=e.closed_on
                )
                for e in episodes
            ],
            plans=[
                TreatmentPlanOut(
                    id=p.id,
                    episode_id=p.episode_id,
                    service_code=p.service_code,
                    title=p.title,
                    total_sessions=p.total_sessions,
                    completed_sessions=p.completed_sessions,
                    status=p.status,
                )
                for p in plans
            ],
            recent_sessions=[
                TreatmentSessionOut(
                    id=s.id,
                    plan_id=s.plan_id,
                    performed_at=s.performed_at,
                    doctor_id=s.doctor_id,
                    protocol_id=s.protocol_id,
                    title=s.title,
                    status=s.status,
                )
                for s in sessions
            ],
            appointments=[appointment_out(a, code_by_patient[a.patient_id]) for a in appointments],
            open_tasks=[task_out(t, patient.code, name) for t, name in task_rows],
            recent_activities=[activity_out(a, name) for a, name in activity_rows],
            consents=consents,
            conversations=conversations,
            timeline=timeline,
        )
        await audit.record(session, ctx, "patient.read_360", "patient", patient_id)
        return dto

"""``AgentFacingClinicActions``: the ONLY door through which the agent side reaches clinic data.

New module (implements ``pema_contracts.clinic_actions.AgentFacingClinicActions``). Every method goes through
the ``clinic_agent`` views and SECURITY DEFINER functions (migrations 0003 and b1_0004), never through a
``clinic.*`` table, so the same class works with the ``agent_worker`` role (which has no privilege on
``clinic.*``) and with ``be_app`` (API process: webhooks, CRM rules). The agent tool IS the function the
rest of the system calls (PLAN-AI01 principle 3).

Data minimisation (principle 4): ``CareContext`` is built from views that carry no phone, birth date,
address, free clinical text or photo; ``display_name`` appears only for a VERIFIED identity.

Decisions (product owner, 2026-10-01): in ``patient_channel`` ``appointment.book`` of the agent creates a
PROPOSAL, not an appointment. The Protocol's ``book_appointment(AppointmentCreate) -> AppointmentOut`` cannot
express that (the agent knows a patient code, not a patient id, and a proposal is not an appointment), so:

* ``propose_appointment(ctx, AppointmentProposalRequest) -> ReviewItemOut`` is what the tool
  ``appointment.book`` calls. It validates with the SAME schedule rules as the UI (``domain.appointments``),
  checks double booking against the ``patient_appointment`` view, requires a VERIFIED identity, and writes a
  ``reply_draft`` review item whose ``payload.proposal == 'appointment'``. A staff member confirming it
  (``review_items.approve_review_item``) books the appointment in the same transaction and sends the text;
* ``book_appointment`` stays on the Protocol for compatibility and refuses an agent actor with
  ``policy_denied``: the agent cannot book, it can only propose.
* ``create_escalation`` (tool ``escalation.create``) raises a ``triage_alert`` that only a doctor decides.

Every function audits (actor ``agent`` or ``system``) inside SQL. ``ctx.actor_type`` must be ``agent``,
``scheduler`` or ``system``: staff do not use this door.
"""

from __future__ import annotations

import json
from datetime import UTC, date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text as sql
from sqlalchemy.exc import DBAPIError

from pema.clinic.actions._common import not_found, now
from pema.clinic.domain import appointments as schedule
from pema.clinic.domain import review as review_rules
from pema.clinic.domain.profile import ProfileFacts, days_between, lifecycle_stage
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate, AppointmentOut, AppointmentStatus
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.clinic_actions import (
    AgentAppointmentView,
    AppointmentProposalRequest,
    CareContext,
    EscalationRequest,
    FollowupMilestone,
    IdentityLink,
    IdentityLinkStatus,
    InboxRef,
)
from pema_contracts.common import VN_TZ
from pema_contracts.conversations import MessageStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.review import (
    ReviewItemCreate,
    ReviewItemOut,
    ReviewKind,
    ReviewOrigin,
    ReviewStatus,
    RiskLevel,
    SourceCitation,
)
from pema_contracts.roles import ActorType, Permission

_FREE = {s.value for s in schedule.FREE_STATUSES}
_MILESTONES = {m.value for m in FollowupMilestone}
_OUTBOUND_STATUSES = {
    MessageStatus.QUEUED,
    MessageStatus.SENT,
    MessageStatus.FAILED,
    MessageStatus.REJECTED,
    MessageStatus.DRAFT,
}
DEFAULT_PROPOSAL_TEXT = (
    "Phòng khám đã ghi nhận đề xuất lịch hẹn lúc {when}. Nhân viên sẽ xác nhận lại với bạn sớm."
)


def _agent_actor(ctx: ActionContext) -> str:
    """``agent`` or ``system`` as written to ``audit_log.actor_type`` by the SQL functions."""
    require(ctx, Permission.AGENT_SUBMIT)
    return "agent" if ctx.actor_type in (ActorType.AGENT, ActorType.SCHEDULER) else "system"


def _flags_text(flags: list[str]) -> list[str]:
    return [f[:60] for f in flags]


class ClinicAgentFacingActions:
    """SQL-backed implementation. Build it with the database of the process that uses it: the worker's
    ``ClinicDatabase(worker_database_url)`` (role ``agent_worker``) or the API's (role ``be_app``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------ care context
    async def get_care_context(self, ctx: ActionContext, patient_ref: str) -> CareContext | None:
        _agent_actor(ctx)
        today = now().astimezone(VN_TZ).date()
        async with self._db.session(ctx.clinic_id) as session:
            ref = (
                await session.execute(
                    sql(
                        "SELECT id, code, full_name, marketing_opt_out, reactivated_at "
                        "FROM clinic_agent.patient_ref WHERE code = :code"
                    ),
                    {"code": patient_ref},
                )
            ).first()
            if ref is None:
                return None
            pid = ref.id
            verified = (
                await session.execute(
                    sql("SELECT 1 FROM clinic_agent.identity_verified WHERE patient_id = :p LIMIT 1"),
                    {"p": pid},
                )
            ).first() is not None
            last = (
                await session.execute(
                    sql(
                        "SELECT protocol_id, performed_at FROM clinic_agent.patient_last_session "
                        "WHERE patient_id = :p"
                    ),
                    {"p": pid},
                )
            ).first()
            plans = (
                await session.execute(
                    sql(
                        "SELECT total_sessions, completed_sessions FROM clinic_agent.patient_care_plan "
                        "WHERE patient_id = :p AND status IN ('planned', 'active')"
                    ),
                    {"p": pid},
                )
            ).all()
            appts = (
                await session.execute(
                    sql(
                        "SELECT starts_at, status FROM clinic_agent.patient_appointment WHERE patient_id = :p"
                    ),
                    {"p": pid},
                )
            ).all()
            milestone = (
                await session.execute(
                    sql(
                        "SELECT rule_key FROM clinic_agent.patient_open_task "
                        "WHERE patient_id = :p AND rule_key IN ('d1', 'd3', 'd7') ORDER BY due_at LIMIT 1"
                    ),
                    {"p": pid},
                )
            ).first()
            consent = (
                await session.execute(
                    sql(
                        "SELECT granted FROM clinic_agent.consent_current "
                        "WHERE patient_id = :p AND kind = 'messaging'"
                    ),
                    {"p": pid},
                )
            ).first()

        last_session_day: date | None = last.performed_at.astimezone(VN_TZ).date() if last else None
        completed_days = [a.starts_at.astimezone(VN_TZ).date() for a in appts if a.status == "completed"]
        visit_days = [d for d in (last_session_day, *completed_days) if d is not None and d <= today]
        last_visit = max(visit_days) if visit_days else None
        upcoming = sorted(
            a.starts_at.astimezone(VN_TZ).date()
            for a in appts
            if a.status not in _FREE
            and a.status != "completed"
            and a.starts_at.astimezone(VN_TZ).date() >= today
        )
        next_day = upcoming[0] if upcoming else None
        total = sum(p.total_sessions for p in plans)
        done = sum(p.completed_sessions for p in plans)
        facts = ProfileFacts(
            today=today,
            last_visit=last_session_day,
            has_sessions=last is not None,
            total_sessions=total,
            completed_sessions=done,
            next_appointment=next_day,
            recommendation_at=None,
            expected_visit_source=None,
            reactivated=ref.reactivated_at is not None,
            marketing_opt_out=ref.marketing_opt_out,
        )
        stage = lifecycle_stage(facts)
        return CareContext(
            patient_code=ref.code,
            identity_verified=verified,
            display_name=ref.full_name if verified else None,
            lifecycle_stage=stage,
            days_since_last_visit=days_between(last_visit, today) if last_visit else None,
            last_protocol_id=last.protocol_id if last else None,
            days_since_last_session=days_between(last_session_day, today) if last_session_day else None,
            remaining_sessions=max(0, total - done) if plans else None,
            days_to_next_appointment=days_between(today, next_day) if next_day else None,
            followup_milestone=FollowupMilestone(milestone.rule_key) if milestone else None,
            marketing_opt_out=ref.marketing_opt_out,
            consent_messaging=bool(consent.granted) if consent else False,
        )

    async def list_upcoming_appointments(
        self, ctx: ActionContext, patient_ref: str, limit: int = 5
    ) -> list[AgentAppointmentView]:
        _agent_actor(ctx)
        async with self._db.session(ctx.clinic_id) as session:
            rows = (
                await session.execute(
                    sql(
                        "SELECT a.id, a.starts_at, a.duration_min, a.status, a.doctor_id "
                        "FROM clinic_agent.patient_appointment a "
                        "JOIN clinic_agent.patient_ref p ON p.id = a.patient_id "
                        "WHERE p.code = :code AND a.starts_at >= :now "
                        "AND a.status NOT IN ('cancelled', 'missed', 'completed') "
                        "ORDER BY a.starts_at LIMIT :limit"
                    ),
                    {"code": patient_ref, "now": now(), "limit": max(1, min(limit, 20))},
                )
            ).all()
        return [
            AgentAppointmentView(
                id=r.id,
                starts_at=r.starts_at,
                duration_min=r.duration_min,
                status=r.status,
                doctor_id=r.doctor_id,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ booking (proposal only)
    async def book_appointment(self, ctx: ActionContext, request: AppointmentCreate) -> AppointmentOut:
        """Compatibility with the Protocol. An agent never books: use ``propose_appointment``."""
        raise DomainError(
            ErrorCode.POLICY_DENIED,
            "Trợ lý chỉ được đề xuất lịch hẹn; nhân viên xác nhận mới đặt lịch.",
            details={"use": "propose_appointment"},
        )

    async def propose_appointment(
        self, ctx: ActionContext, request: AppointmentProposalRequest
    ) -> ReviewItemOut:
        _agent_actor(ctx)
        stamp = now()
        schedule.validate_slot(request.starts_at, request.duration_min, stamp, require_future=True)
        async with self._db.session(ctx.clinic_id) as session:
            patient = (
                await session.execute(
                    sql("SELECT id, code FROM clinic_agent.patient_ref WHERE code = :code"),
                    {"code": request.patient_ref},
                )
            ).first()
            if patient is None:
                raise not_found("bệnh nhân")
            verified = (
                await session.execute(
                    sql("SELECT 1 FROM clinic_agent.identity_verified WHERE patient_id = :p LIMIT 1"),
                    {"p": patient.id},
                )
            ).first()
            if verified is None:
                raise DomainError(
                    ErrorCode.IDENTITY_NOT_VERIFIED,
                    "Chưa xác minh danh tính bệnh nhân nên chưa đề xuất lịch.",
                )
            end = request.starts_at + timedelta(minutes=request.duration_min)
            rows = (
                await session.execute(
                    sql(
                        "SELECT id, patient_id, doctor_id, starts_at, duration_min, status "
                        "FROM clinic_agent.patient_appointment "
                        "WHERE status NOT IN ('cancelled', 'missed') AND starts_at < :end "
                        "AND starts_at > :floor AND (patient_id = :p "
                        "OR (CAST(:d AS uuid) IS NOT NULL AND doctor_id = CAST(:d AS uuid)))"
                    ),
                    {
                        "end": end,
                        "floor": request.starts_at - timedelta(minutes=480),
                        "p": patient.id,
                        "d": str(request.doctor_id) if request.doctor_id else None,
                    },
                )
            ).all()
        existing = [
            schedule.Slot(
                patient_id=r.patient_id,
                doctor_id=r.doctor_id,
                starts_at=r.starts_at,
                duration_min=r.duration_min,
                appointment_id=r.id,
                status=AppointmentStatus(r.status),
            )
            for r in rows
        ]
        candidate = schedule.Slot(
            patient_id=patient.id,
            doctor_id=request.doctor_id,
            starts_at=request.starts_at,
            duration_min=request.duration_min,
        )
        conflict = schedule.find_conflict(candidate, existing)
        if conflict is not None:
            schedule.raise_for_conflict(conflict)
        when = request.starts_at.astimezone(VN_TZ).strftime("%H:%M ngày %d/%m")
        payload: dict[str, Any] = {
            "proposal": review_rules.APPOINTMENT_PROPOSAL,
            "starts_at": request.starts_at.isoformat(),
            "duration_min": request.duration_min,
            "doctor_id": str(request.doctor_id) if request.doctor_id else None,
            "note": request.note,
        }
        return await self.create_review_item(
            ctx,
            ReviewItemCreate(
                job_id=request.job_id,
                clinic_id=ctx.clinic_id,
                patient_ref=request.patient_ref,
                conversation_ref=request.conversation_ref,
                kind=ReviewKind.REPLY_DRAFT,
                origin=ReviewOrigin.AGENT_TURN,
                draft_text=request.draft_text or DEFAULT_PROPOSAL_TEXT.format(when=when),
                payload=payload,
                model=request.model,
                prompt_version=request.prompt_version,
            ),
        )

    # ------------------------------------------------------------------ review items and escalation
    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        _agent_actor(ctx)
        if request.clinic_id != ctx.clinic_id:
            raise DomainError(ErrorCode.FORBIDDEN, "Không được tạo mục chờ duyệt cho phòng khám khác.")
        async with self._db.session(ctx.clinic_id) as session:
            item_id = (
                await session.execute(
                    sql(
                        "SELECT clinic_agent.create_review_item(:job_id, :kind, :origin, :patient, "
                        "CAST(:conv AS uuid), :draft, CAST(:payload AS jsonb), CAST(:sources AS jsonb), "
                        ":risk, CAST(:flags AS text[]), :model, :prompt)"
                    ),
                    {
                        "job_id": request.job_id,
                        "kind": request.kind.value,
                        "origin": request.origin.value,
                        "patient": request.patient_ref,
                        "conv": request.conversation_ref,
                        "draft": request.draft_text,
                        "payload": json.dumps(request.payload) if request.payload is not None else None,
                        "sources": json.dumps([s.model_dump(mode="json") for s in request.sources]),
                        "risk": request.risk_level.value,
                        "flags": _flags_text(request.red_flags),
                        "model": request.model,
                        "prompt": request.prompt_version,
                    },
                )
            ).scalar_one()
            row = (
                await session.execute(
                    sql("SELECT * FROM clinic_agent.review_item_summary WHERE id = :id"), {"id": item_id}
                )
            ).one()
        return ReviewItemOut(
            id=row.id,
            kind=ReviewKind(row.kind),
            origin=ReviewOrigin(row.origin),
            status=ReviewStatus(row.status),
            conversation_id=row.conversation_id,
            patient_id=row.patient_id,
            patient_code=row.patient_code,
            draft_text=row.draft_text,
            payload=row.payload,
            sources=[SourceCitation.model_validate(s) for s in row.sources],
            risk_level=RiskLevel(row.risk_level),
            red_flags=list(row.red_flags),
            requires_doctor=row.requires_doctor,
            job_id=row.job_id,
            model=row.model,
            prompt_version=row.prompt_version,
            created_at=row.created_at,
            decided_at=row.decided_at,
            version=row.version,
        )

    async def create_escalation(self, ctx: ActionContext, request: EscalationRequest) -> ReviewItemOut:
        """Tool ``escalation.create``: a ``triage_alert`` that goes straight to a doctor."""
        return await self.create_review_item(
            ctx,
            ReviewItemCreate(
                job_id=request.job_id,
                clinic_id=ctx.clinic_id,
                patient_ref=request.patient_ref,
                conversation_ref=request.conversation_ref,
                kind=ReviewKind.TRIAGE_ALERT,
                origin=ReviewOrigin.POLICY,
                draft_text=request.summary,
                risk_level=RiskLevel.RED_FLAG,
                red_flags=request.red_flags,
            ),
        )

    # ------------------------------------------------------------------ identity and inbox
    async def resolve_identity(
        self, ctx: ActionContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityLink:
        _agent_actor(ctx)
        async with self._db.session(ctx.clinic_id) as session:
            row = (
                await session.execute(
                    sql("SELECT * FROM clinic_agent.resolve_identity(:c, :u)"),
                    {"c": channel.value, "u": external_user_id},
                )
            ).one()
        return IdentityLink(
            channel=channel,
            external_user_id=external_user_id,
            status=IdentityLinkStatus(row.status),
            patient_id=row.patient_id,
            patient_code=row.patient_code,
            verified_at=row.verified_at,
        )

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        """Inbox of record. Idempotent on ``update_id``: a duplicate delivery writes nothing."""
        actor = _agent_actor(ctx)
        async with self._db.session(ctx.clinic_id) as session:
            row = (
                await session.execute(
                    sql(
                        "SELECT * FROM clinic_agent.record_inbound_message(:channel, :update_id, :thread, "
                        ":uid, :name, :text, :sent_at, :actor)"
                    ),
                    {
                        "channel": message.channel.value,
                        "update_id": message.update_id,
                        "thread": message.thread_id,
                        "uid": message.sender_id,
                        "name": message.sender_name,
                        "text": message.text or None,
                        "sent_at": message.sent_at.astimezone(UTC),
                        "actor": actor,
                    },
                )
            ).one()
        return InboxRef(
            conversation_id=row.o_conversation_id,
            message_id=row.o_message_id,
            patient_id=row.o_patient_id,
            duplicate=row.o_duplicate,
        )

    async def record_outbound_message(
        self,
        ctx: ActionContext,
        *,
        conversation_id: UUID,
        text: str,
        status: MessageStatus,
        proactive: bool = False,
        review_item_id: UUID | None = None,
        error_code: str | None = None,
    ) -> InboxRef:
        actor = _agent_actor(ctx)
        if status not in _OUTBOUND_STATUSES:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Trạng thái tin nhắn đi không hợp lệ.")
        try:
            async with self._db.session(ctx.clinic_id) as session:
                row = (
                    await session.execute(
                        sql(
                            "SELECT * FROM clinic_agent.record_outbound_message(CAST(:conv AS uuid), :text, "
                            ":status, :proactive, CAST(:review AS uuid), :error, :actor)"
                        ),
                        {
                            "conv": str(conversation_id),
                            "text": text,
                            "status": status.value,
                            "proactive": proactive,
                            "review": str(review_item_id) if review_item_id else None,
                            "error": error_code,
                            "actor": actor,
                        },
                    )
                ).one()
        except DBAPIError as exc:
            if "conversation not found" in str(exc.orig):
                raise not_found("hội thoại") from exc
            raise
        return InboxRef(conversation_id=row.o_conversation_id, message_id=row.o_message_id)

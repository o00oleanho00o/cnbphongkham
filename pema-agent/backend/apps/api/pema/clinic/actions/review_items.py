"""Review queue: list, read, approve (optionally edited), reject, escalate (actions behind
``routers/review_items.py``). A human decision always precedes a send (PLAN-AI01 section 5).

New module. Creation is not here: items come from the agent worker, the CRM rules and the policy hooks
through ``agent_facing.create_review_item`` (the SECURITY DEFINER function of migration 0003).

Rules:

* a clinician (owner, doctor) decides items that ``requires_doctor`` (red flags, triage alerts, escalated
  items) with ``review.decide_clinical``; everyone else decides the rest with ``review.decide``; a CS member
  does not even see the clinical ones ("CSKH does not do medical review");
* decisions are final and idempotent: a repeated ``Idempotency-Key`` returns the same result without sending
  twice; a decided item cannot be decided again; ``version`` guards two people deciding at once;
* approving with ``send`` stores the approved text as a ``queued`` outbound message in the SAME transaction as
  the decision and hands it to the channel afterwards (``outbound.deliver_queued_message``); the message row
  is later marked sent or rejected ("danh dau da gui");
* an item that carries an appointment proposal (``payload.proposal == 'appointment'``, written by the agent)
  books the appointment in the same transaction through the SAME validator as the UI; a conflict leaves the
  item pending so staff can pick another time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.actions._mappers import review_out
from pema.clinic.actions.appointments import announce as announce_appointment
from pema.clinic.actions.appointments import book_in_session
from pema.clinic.actions.outbound import OutboundDelivery, deliver_queued_message
from pema.clinic.domain import review as rules
from pema.clinic.models import Conversation, Message, Patient, ReviewItem
from pema.clinic.rbac import is_clinical, is_doctor_scoped, require, require_any
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate, AppointmentStatus
from pema_contracts.common import Page
from pema_contracts.conversations import ConversationStatus, MessageDirection, MessageStatus, SenderType
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.review import (
    ReviewApprove,
    ReviewEscalate,
    ReviewItemOut,
    ReviewKind,
    ReviewOrigin,
    ReviewReject,
    ReviewStatus,
)
from pema_contracts.roles import Permission

MAX_SEND_CHARS = 2000
"""Zalo text limit (``ZALO_BOT_MAX_TEXT_CHARS``); a longer approved text is refused, not silently cut."""
OPEN_STATUSES = (ReviewStatus.PENDING.value, ReviewStatus.ESCALATED.value)


def _announce(item: ReviewItemOut) -> None:
    """After the commit: the review queue changed, and so did the conversation it belongs to (its status,
    its pending-review flag)."""
    emit_live(LiveEventType.REVIEW_CHANGED, item.id)
    if item.conversation_id is not None:
        emit_live(LiveEventType.INBOX_CHANGED, item.conversation_id)


def _visible_to(ctx: ActionContext) -> list[Any]:
    """Clinical items are for clinicians only."""
    if is_clinical(ctx):
        return []
    return [ReviewItem.requires_doctor.is_(False), ReviewItem.kind != ReviewKind.TRIAGE_ALERT.value]


def _needs_clinician(item: ReviewItem) -> bool:
    return rules.needs_clinician(requires_doctor=item.requires_doctor, kind=ReviewKind(item.kind))


def _authorize_decision(ctx: ActionContext, item: ReviewItem) -> None:
    require(ctx, Permission.REVIEW_DECIDE_CLINICAL if _needs_clinician(item) else Permission.REVIEW_DECIDE)


async def _load(session: AsyncSession, ctx: ActionContext, item_id: UUID) -> tuple[ReviewItem, str | None]:
    row = (
        await session.execute(
            select(ReviewItem, Patient.code)
            .outerjoin(
                Patient, (Patient.id == ReviewItem.patient_id) & (Patient.clinic_id == ReviewItem.clinic_id)
            )
            .where(ReviewItem.id == item_id, ReviewItem.clinic_id == ctx.clinic_id)
        )
    ).first()
    if row is None:
        raise not_found("mục chờ duyệt")
    item: ReviewItem = row[0]
    if _visible_to(ctx) and _needs_clinician(item):
        raise DomainError(
            ErrorCode.FORBIDDEN, "Mục này cần bác sĩ xử lý.", details={"permission": "review.decide_clinical"}
        )
    return item, row[1]


async def list_review_items(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    status: ReviewStatus | None = None,
    kind: ReviewKind | None = None,
    requires_doctor: bool | None = None,
    patient_id: UUID | None = None,
    conversation_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[ReviewItemOut]:
    require(ctx, Permission.REVIEW_READ)
    conditions: list[Any] = [ReviewItem.clinic_id == ctx.clinic_id, *_visible_to(ctx)]
    if status is not None:
        conditions.append(ReviewItem.status == status.value)
    if kind is not None:
        conditions.append(ReviewItem.kind == kind.value)
    if requires_doctor is not None:
        conditions.append(ReviewItem.requires_doctor.is_(requires_doctor))
    if patient_id is not None:
        conditions.append(ReviewItem.patient_id == patient_id)
    if conversation_id is not None:
        conditions.append(ReviewItem.conversation_id == conversation_id)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(ReviewItem).where(*conditions)) or 0
        rows = await session.execute(
            select(ReviewItem, Patient.code)
            .outerjoin(
                Patient, (Patient.id == ReviewItem.patient_id) & (Patient.clinic_id == ReviewItem.clinic_id)
            )
            .where(*conditions)
            .order_by(
                (ReviewItem.status == ReviewStatus.PENDING.value).desc(),
                ReviewItem.requires_doctor.desc(),
                ReviewItem.created_at,
                ReviewItem.id,
            )
            .limit(limit)
            .offset(offset)
        )
        items = [review_out(item, code) for item, code in rows.all()]
    return Page[ReviewItemOut](items=items, total=total, limit=limit, offset=offset)


async def get_review_item(db: ClinicDatabase, ctx: ActionContext, item_id: UUID) -> ReviewItemOut:
    require(ctx, Permission.REVIEW_READ)
    async with db.session() as session:
        item, code = await _load(session, ctx, item_id)
        return review_out(item, code)


async def _settle_conversation(
    session: AsyncSession, ctx: ActionContext, item: ReviewItem, *, handoff: bool = False
) -> None:
    """The conversation leaves ``pending_review`` / ``handoff`` when no other item of it is still open."""
    if item.conversation_id is None:
        return
    conv = await session.scalar(
        select(Conversation).where(
            Conversation.id == item.conversation_id, Conversation.clinic_id == ctx.clinic_id
        )
    )
    if conv is None or conv.status == ConversationStatus.CLOSED.value:
        return
    if handoff:
        conv.status = ConversationStatus.HANDOFF.value
        return
    others = await session.scalar(
        select(ReviewItem.id).where(
            ReviewItem.clinic_id == ctx.clinic_id,
            ReviewItem.conversation_id == item.conversation_id,
            ReviewItem.id != item.id,
            ReviewItem.status.in_(OPEN_STATUSES),
        )
    )
    if others is None and conv.status in (
        ConversationStatus.PENDING_REVIEW.value,
        ConversationStatus.HANDOFF.value,
    ):
        conv.status = ConversationStatus.OPEN.value


def _proposal_booking(item: ReviewItem, proposal: dict[str, Any]) -> AppointmentCreate:
    if item.patient_id is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Đề xuất lịch chưa gắn với bệnh nhân đã xác minh.")
    doctor = proposal.get("doctor_id")
    return AppointmentCreate(
        patient_id=item.patient_id,
        doctor_id=UUID(str(doctor)) if doctor else None,
        starts_at=datetime.fromisoformat(str(proposal["starts_at"])),
        duration_min=int(proposal.get("duration_min", 30)),
        note=proposal.get("note"),
    )


async def approve_review_item(
    db: ClinicDatabase,
    ctx: ActionContext,
    item_id: UUID,
    payload: ReviewApprove,
    *,
    delivery: OutboundDelivery | None = None,
) -> ReviewItemOut:
    require_any(ctx, (Permission.REVIEW_DECIDE, Permission.REVIEW_DECIDE_CLINICAL))
    async with db.session() as session:
        item, code = await _load(session, ctx, item_id)
        _authorize_decision(ctx, item)
        if await audit.find_replay(session, ctx, "review_item.approve", item.id):
            return review_out(item, code)
        check_version(item.version, payload.version)
        if ReviewStatus(item.status) not in rules.DECIDABLE_FROM:
            raise DomainError(ErrorCode.INVALID_STATE, "Mục này đã được quyết định.")

        edited = payload.final_text is not None and payload.final_text != item.draft_text
        text = payload.final_text if payload.final_text is not None else item.draft_text
        if payload.send:
            if not text:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "Không có nội dung để gửi.")
            if item.conversation_id is None:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, "Mục này không gắn với hội thoại nên không gửi được."
                )
            if len(text) > MAX_SEND_CHARS:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    f"Nội dung dài quá {MAX_SEND_CHARS} ký tự; hãy rút gọn trước khi gửi.",
                )

        appointment_id: UUID | None = None
        booked_patient_id: UUID | None = None
        proposal = rules.appointment_proposal(item.payload)
        if proposal is not None:
            require_any(ctx, (Permission.APPOINTMENT_WRITE, Permission.CRM_TASK_RESOLVE))
            booking = _proposal_booking(item, proposal)
            if is_doctor_scoped(ctx) and booking.doctor_id != ctx.actor_user_id:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "Bác sĩ chỉ xác nhận lịch của chính mình.",
                    details={"scope": "doctor"},
                )
            appointment, _ = await book_in_session(session, ctx, booking)
            appointment_id = appointment.id
            booked_patient_id = appointment.patient_id
            item.payload = {**(item.payload or {}), "appointment_id": str(appointment.id)}

        stamp = now()
        item.status = ReviewStatus.APPROVED.value
        item.final_text = text
        item.decided_by = ctx.actor_user_id
        item.decided_at = stamp
        item.decision_note = payload.note
        with lost_race_is_conflict():
            await session.flush()

        message_id: UUID | None = None
        if payload.send and text and item.conversation_id is not None:
            conv = await session.scalar(
                select(Conversation).where(
                    Conversation.id == item.conversation_id, Conversation.clinic_id == ctx.clinic_id
                )
            )
            if conv is None:
                raise not_found("hội thoại")
            message = Message(
                clinic_id=ctx.clinic_id,
                conversation_id=conv.id,
                channel=conv.channel,
                direction=MessageDirection.OUTBOUND.value,
                sender_type=SenderType.STAFF.value,
                sender_user_id=ctx.actor_user_id,
                body=text,
                status=MessageStatus.QUEUED.value,
                proactive=rules.is_proactive(ReviewOrigin(item.origin)),
                review_item_id=item.id,
            )
            session.add(message)
            conv.last_message_at = stamp
            await session.flush()
            message_id = message.id
        await _settle_conversation(session, ctx, item)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "review_item.approve",
            "review_item",
            item.id,
            {
                "send": payload.send,
                "edited": edited,
                "message_id": str(message_id) if message_id else None,
                "appointment_id": str(appointment_id) if appointment_id else None,
            },
        )
        result = review_out(item, code)
    _announce(result)
    if appointment_id is not None and booked_patient_id is not None:
        announce_appointment(appointment_id, booked_patient_id, "create", AppointmentStatus.BOOKED)
    if message_id is not None:
        await deliver_queued_message(db, ctx, message_id, delivery)
    return result


async def reject_review_item(
    db: ClinicDatabase, ctx: ActionContext, item_id: UUID, payload: ReviewReject
) -> ReviewItemOut:
    require_any(ctx, (Permission.REVIEW_DECIDE, Permission.REVIEW_DECIDE_CLINICAL))
    async with db.session() as session:
        item, code = await _load(session, ctx, item_id)
        _authorize_decision(ctx, item)
        if await audit.find_replay(session, ctx, "review_item.reject", item.id):
            return review_out(item, code)
        check_version(item.version, payload.version)
        if ReviewStatus(item.status) not in rules.DECIDABLE_FROM:
            raise DomainError(ErrorCode.INVALID_STATE, "Mục này đã được quyết định.")
        item.status = ReviewStatus.REJECTED.value
        item.decided_by = ctx.actor_user_id
        item.decided_at = now()
        item.decision_note = payload.reason
        with lost_race_is_conflict():
            await session.flush()
        await _settle_conversation(session, ctx, item)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(session, ctx, "review_item.reject", "review_item", item.id, {"kind": item.kind})
        rejected = review_out(item, code)
    _announce(rejected)
    return rejected


async def escalate_review_item(
    db: ClinicDatabase, ctx: ActionContext, item_id: UUID, payload: ReviewEscalate
) -> ReviewItemOut:
    require(ctx, Permission.REVIEW_DECIDE)
    async with db.session() as session:
        item, code = await _load(session, ctx, item_id)
        if await audit.find_replay(session, ctx, "review_item.escalate", item.id):
            return review_out(item, code)
        check_version(item.version, payload.version)
        if ReviewStatus(item.status) not in rules.ESCALATABLE_FROM:
            raise DomainError(ErrorCode.INVALID_STATE, "Chỉ chuyển bác sĩ được mục đang chờ duyệt.")
        item.status = ReviewStatus.ESCALATED.value
        item.requires_doctor = True
        item.decision_note = payload.note
        with lost_race_is_conflict():
            await session.flush()
        await _settle_conversation(session, ctx, item, handoff=True)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(session, ctx, "review_item.escalate", "review_item", item.id, {"kind": item.kind})
        escalated = review_out(item, code)
    _announce(escalated)
    return escalated

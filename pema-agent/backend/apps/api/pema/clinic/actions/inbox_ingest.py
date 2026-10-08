"""The door of the Inbox for a channel integration: record a message that came in, record one that went out,
open an item in the doctor follow-up queue (Theo dõi).

Kept from the removed agent-facing actions (branch feat/agent-v2) because the Inbox needs it whatever channel
or agent comes next. Both calls go through the SECURITY DEFINER functions of schema ``clinic_agent``
(``record_inbound_message`` / ``record_outbound_message``), which write the conversation, the message and the
audit row in one statement. The caller is a system or agent actor holding ``agent.submit``; staff messages
use ``conversations.send_message`` instead.
"""

from __future__ import annotations

import json
from datetime import UTC
from uuid import UUID

from sqlalchemy import text as sql
from sqlalchemy.exc import DBAPIError

from pema.clinic.actions._common import not_found
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.channel import InboundMessage
from pema_contracts.conversations import InboxRef, MessageStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
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

OUTBOUND_STATUSES = frozenset(
    {
        MessageStatus.QUEUED,
        MessageStatus.SENT,
        MessageStatus.FAILED,
        MessageStatus.REJECTED,
        MessageStatus.DRAFT,
    }
)


def _actor(ctx: ActionContext) -> str:
    """``agent`` or ``system`` as written to ``audit_log.actor_type`` by the SQL functions."""
    require(ctx, Permission.AGENT_SUBMIT)
    return "agent" if ctx.actor_type in (ActorType.AGENT, ActorType.SCHEDULER) else "system"


async def record_inbound_message(db: ClinicDatabase, ctx: ActionContext, message: InboundMessage) -> InboxRef:
    """Inbox of record. Idempotent on ``update_id``: a duplicate delivery writes nothing.

    The account that received the message (``message.account_id``) is stored on the conversation when it is
    still empty; an account the installation does not know is stored as ``NULL``."""
    actor = _actor(ctx)
    async with db.session() as session:
        row = (
            await session.execute(
                sql(
                    "SELECT * FROM clinic_agent.record_inbound_message(:channel, :update_id, :thread, "
                    ":uid, :name, :text, :sent_at, :actor, :account)"
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
                    "account": message.account_id or None,
                },
            )
        ).one()
    if not row.o_duplicate:
        emit_live(LiveEventType.INBOX_CHANGED, row.o_conversation_id)
    return InboxRef(
        conversation_id=row.o_conversation_id,
        message_id=row.o_message_id,
        patient_id=row.o_patient_id,
        duplicate=row.o_duplicate,
    )


async def record_outbound_message(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    conversation_id: UUID,
    text: str,
    status: MessageStatus,
    proactive: bool = False,
    review_item_id: UUID | None = None,
    error_code: str | None = None,
) -> InboxRef:
    actor = _actor(ctx)
    if status not in OUTBOUND_STATUSES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Trạng thái tin nhắn đi không hợp lệ.")
    try:
        async with db.session() as session:
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
    emit_live(LiveEventType.INBOX_CHANGED, row.o_conversation_id)
    return InboxRef(conversation_id=row.o_conversation_id, message_id=row.o_message_id)


async def create_review_item(
    db: ClinicDatabase, ctx: ActionContext, request: ReviewItemCreate
) -> ReviewItemOut:
    """Open an item of the follow-up queue (idempotent on ``job_id``, done by the SQL function)."""
    _actor(ctx)
    if request.clinic_id != ctx.clinic_id:
        raise DomainError(ErrorCode.FORBIDDEN, "Không được tạo mục chờ duyệt cho phòng khám khác.")
    async with db.session() as session:
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
                    "flags": [f[:60] for f in request.red_flags],
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
    emit_live(LiveEventType.REVIEW_CHANGED, row.id)
    if row.conversation_id is not None:
        emit_live(LiveEventType.INBOX_CHANGED, row.conversation_id)
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

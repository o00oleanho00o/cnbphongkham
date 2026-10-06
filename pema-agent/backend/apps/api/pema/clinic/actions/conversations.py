"""Inbox: conversations and messages (actions behind ``routers/conversations.py``).

New module. The Inbox of record is ``clinic.conversation`` / ``clinic.message``; the channel layer writes
inbound messages through ``clinic_agent.record_inbound_message`` (``agent_facing``), staff read and answer
here. Rules:

* ``conversation.read`` to list and read, ``conversation.reply`` to send, assign or close;
* a doctor sees only conversations of patients in their scope (and none that are not linked to a patient);
* reading message bodies is audited (they are PII-bearing clinical-adjacent text);
* a manual reply is written ``queued`` in one transaction, handed to the channel, and the result is written
  in a second one (``outbound.deliver_queued_message``). ``Idempotency-Key`` is stored as the message's
  ``update_id`` (``staff:<key>``), so the unique index of ``clinic.message`` makes a retry return the first
  message instead of sending twice;
* a proactive reply needs a linked patient with a granted messaging consent;
* package O, step O2: only the holder of a thread replies (``thread_locked`` 409 otherwise); the first
  reply on an unassigned thread claims it; a change of "Phụ trách" is an assignment (history, outbox
  notice, live event).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._assignment_core import (
    apply_assignment,
    enforce_reply_lock,
    locked_error,
)
from pema.clinic.actions._common import (
    check_version,
    escape_like,
    lost_race_is_conflict,
    not_found,
    now,
)
from pema.clinic.actions._mappers import conversation_out, conversation_summary, message_out
from pema.clinic.actions._scope import patient_scope
from pema.clinic.actions.assignees import load_assignable_user
from pema.clinic.actions.outbound import OutboundDelivery, deliver_queued_message
from pema.clinic.models import (
    ChannelIdentity,
    Consent,
    Conversation,
    Message,
    Patient,
    ReviewItem,
    UserAccount,
)
from pema.clinic.rbac import has_permission, require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.common import Page
from pema_contracts.conversations import (
    ConversationOut,
    ConversationStatus,
    ConversationSummary,
    ConversationUpdate,
    MessageCreate,
    MessageDirection,
    MessageOut,
    MessageStatus,
    SenderType,
)
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.ops import AssignmentKind
from pema_contracts.patients import ConsentKind
from pema_contracts.roles import Permission

OPEN_REVIEW_STATUSES = ("pending", "escalated")


def _scope_condition(ctx: ActionContext) -> ColumnElement[bool] | None:
    """A doctor only sees conversations of patients in their own scope."""
    scope = patient_scope(ctx)
    if scope is None:
        return None
    return Conversation.patient_id.in_(select(Patient.id).where(Patient.clinic_id == ctx.clinic_id, scope))


def _pending_review() -> ColumnElement[bool]:
    return exists().where(
        and_(
            ReviewItem.clinic_id == Conversation.clinic_id,
            ReviewItem.conversation_id == Conversation.id,
            ReviewItem.status.in_(OPEN_REVIEW_STATUSES),
        )
    )


async def summaries(
    session: AsyncSession,
    ctx: ActionContext,
    conditions: list[Any],
    *,
    limit: int,
    offset: int,
) -> tuple[list[ConversationSummary], int, dict[UUID, Conversation]]:
    """Conversation summaries with patient label, last message preview and pending-review flag."""
    last_body = (
        select(Message.body)
        .where(Message.clinic_id == Conversation.clinic_id, Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    where = [Conversation.clinic_id == ctx.clinic_id, *conditions]
    scope = _scope_condition(ctx)
    if scope is not None:
        where.append(scope)
    total = (
        await session.scalar(
            select(func.count())
            .select_from(Conversation)
            .outerjoin(
                Patient,
                and_(Patient.id == Conversation.patient_id, Patient.clinic_id == Conversation.clinic_id),
            )
            .outerjoin(
                ChannelIdentity,
                and_(
                    ChannelIdentity.id == Conversation.identity_id,
                    ChannelIdentity.clinic_id == Conversation.clinic_id,
                ),
            )
            .where(*where)
        )
        or 0
    )
    rows = await session.execute(
        select(
            Conversation,
            Patient.code,
            Patient.full_name,
            ChannelIdentity.display_name,
            UserAccount.display_name,
            last_body,
            _pending_review(),
        )
        .outerjoin(
            Patient, and_(Patient.id == Conversation.patient_id, Patient.clinic_id == Conversation.clinic_id)
        )
        .outerjoin(
            ChannelIdentity,
            and_(
                ChannelIdentity.id == Conversation.identity_id,
                ChannelIdentity.clinic_id == Conversation.clinic_id,
            ),
        )
        .outerjoin(
            UserAccount,
            and_(
                UserAccount.id == Conversation.assigned_user_id,
                UserAccount.clinic_id == Conversation.clinic_id,
            ),
        )
        .where(*where)
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id)
        .limit(limit)
        .offset(offset)
    )
    items: list[ConversationSummary] = []
    by_id: dict[UUID, Conversation] = {}
    for conv, code, full_name, identity_name, holder_name, body, pending in rows.all():
        items.append(
            conversation_summary(
                conv,
                patient_code=code,
                patient_display_name=full_name or identity_name,
                last_preview=body,
                has_pending_review=bool(pending),
                assigned_user_name=holder_name,
            )
        )
        by_id[conv.id] = conv
    return items, total, by_id


async def load_conversation(
    session: AsyncSession, ctx: ActionContext, conversation_id: UUID, *, for_update: bool = False
) -> Conversation:
    """The conversation if the caller may see it, else 404. ``for_update`` takes the row lock: the assignment
    actions and the send lock use it, so two changes of one thread run one after the other."""
    where = [Conversation.id == conversation_id, Conversation.clinic_id == ctx.clinic_id]
    scope = _scope_condition(ctx)
    if scope is not None:
        where.append(scope)
    query = select(Conversation).where(*where)
    if for_update:
        query = query.with_for_update(of=Conversation)
    row = await session.scalar(query)
    if row is None:
        raise not_found("hội thoại")
    return row


async def list_conversations(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    status: ConversationStatus | None = None,
    assigned_user_id: UUID | None = None,
    patient_id: UUID | None = None,
    has_pending_review: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[ConversationSummary]:
    require(ctx, Permission.CONVERSATION_READ)
    conditions: list[Any] = []
    if status is not None:
        conditions.append(Conversation.status == status.value)
    if assigned_user_id is not None:
        conditions.append(Conversation.assigned_user_id == assigned_user_id)
    if patient_id is not None:
        conditions.append(Conversation.patient_id == patient_id)
    if has_pending_review is not None:
        conditions.append(_pending_review() if has_pending_review else ~_pending_review())
    if q:
        pattern = f"%{escape_like(q.lower())}%"
        conditions.append(
            or_(
                func.lower(Patient.full_name).like(pattern, escape="\\"),
                func.lower(Patient.code).like(pattern, escape="\\"),
                func.lower(ChannelIdentity.display_name).like(pattern, escape="\\"),
            )
        )
    async with db.session() as session:
        items, total, _ = await summaries(session, ctx, conditions, limit=limit, offset=offset)
    return Page[ConversationSummary](items=items, total=total, limit=limit, offset=offset)


async def conversation_detail(
    session: AsyncSession, ctx: ActionContext, conversation_id: UUID
) -> ConversationOut:
    items, _, by_id = await summaries(session, ctx, [Conversation.id == conversation_id], limit=1, offset=0)
    if not items:
        raise not_found("hội thoại")
    return conversation_out(items[0], by_id[conversation_id])


async def get_conversation(db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID) -> ConversationOut:
    require(ctx, Permission.CONVERSATION_READ)
    async with db.session() as session:
        await load_conversation(session, ctx, conversation_id)
        return await conversation_detail(session, ctx, conversation_id)


async def require_conversation_access(db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID) -> None:
    """The same authorization as reading the conversation (``conversation.read``; a doctor only reaches the
    conversations of their own patients): 403 without the permission, 404 when it does not exist here or is
    out of scope. Presence uses it: whoever may read a conversation may say they are looking at it."""
    require(ctx, Permission.CONVERSATION_READ)
    async with db.session() as session:
        await load_conversation(session, ctx, conversation_id)


async def staff_display_names(
    db: ClinicDatabase, ctx: ActionContext, user_ids: list[UUID]
) -> dict[UUID, str]:
    """Display names of active staff accounts, one query (the colleagues shown next to a conversation)."""
    require(ctx, Permission.CONVERSATION_READ)
    if not user_ids:
        return {}
    async with db.session() as session:
        rows = await session.execute(
            select(UserAccount.id, UserAccount.display_name).where(
                UserAccount.clinic_id == ctx.clinic_id,
                UserAccount.id.in_(user_ids),
                UserAccount.active.is_(True),
            )
        )
        return {row.id: row.display_name for row in rows.all()}


async def update_conversation(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID, payload: ConversationUpdate
) -> ConversationOut:
    require(ctx, Permission.CONVERSATION_REPLY)
    async with db.session() as session:
        row = await load_conversation(session, ctx, conversation_id)
        check_version(row.version, payload.version)
        changed: list[str] = []
        if payload.status is not None and payload.status.value != row.status:
            if payload.status is ConversationStatus.PENDING_REVIEW:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, "Trạng thái chờ duyệt do hệ thống đặt, không đặt tay."
                )
            if payload.status is ConversationStatus.CLOSED:
                pending = await session.scalar(
                    select(ReviewItem.id).where(
                        ReviewItem.clinic_id == ctx.clinic_id,
                        ReviewItem.conversation_id == row.id,
                        ReviewItem.status.in_(OPEN_REVIEW_STATUSES),
                    )
                )
                if pending is not None:
                    raise DomainError(
                        ErrorCode.INVALID_STATE, "Còn mục chờ duyệt trong hội thoại này, chưa thể đóng."
                    )
            row.status = payload.status.value
            changed.append("status")
        details: dict[str, Any] = {}
        handed_over = False
        if "assigned_user_id" in payload.model_fields_set:
            if payload.assigned_user_id is not None:
                # active, of this installation and a role that can work conversations; one answer for all
                await load_assignable_user(session, ctx, payload.assigned_user_id)
            if payload.assigned_user_id != row.assigned_user_id:
                # package O step O2: the "Phụ trách" box goes through the assignment core (history, outbox,
                # audit, live event). A thread that a colleague holds is theirs: only an owner or a manager
                # (``thread.assign``) takes it away from them this way, everybody else takes it over.
                holder = row.assigned_user_id
                if (
                    holder is not None
                    and holder != ctx.actor_user_id
                    and not has_permission(ctx, Permission.THREAD_ASSIGN)
                ):
                    raise await locked_error(session, ctx, row)
                details["assignee_from"] = str(holder) if holder else None
                details["assignee_to"] = str(payload.assigned_user_id) if payload.assigned_user_id else None
                await apply_assignment(
                    session, ctx, row, kind=AssignmentKind.ASSIGN, new_user_id=payload.assigned_user_id
                )
                handed_over = True
            changed.append("assigned_user_id")
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "conversation.update",
            "conversation",
            row.id,
            {"changed_fields": changed, **details},
        )
        result = await conversation_detail(session, ctx, conversation_id)
    if handed_over:
        emit_live(LiveEventType.ASSIGNMENT_CHANGED, conversation_id)
    emit_live(LiveEventType.INBOX_CHANGED, conversation_id)
    return result


async def mark_conversation_read(db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID) -> None:
    require(ctx, Permission.CONVERSATION_READ)
    async with db.session() as session:
        row = await load_conversation(session, ctx, conversation_id)
        cleared = row.unread_count
        row.unread_count = 0
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session, ctx, "conversation.mark_read", "conversation", row.id, {"cleared": cleared}
        )
    emit_live(LiveEventType.INBOX_CHANGED, conversation_id)


async def list_messages(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID, *, limit: int = 50, offset: int = 0
) -> Page[MessageOut]:
    require(ctx, Permission.CONVERSATION_READ)
    async with db.session() as session:
        await load_conversation(session, ctx, conversation_id)
        base = (Message.clinic_id == ctx.clinic_id, Message.conversation_id == conversation_id)
        total = await session.scalar(select(func.count()).select_from(Message).where(*base)) or 0
        rows = (
            await session.scalars(
                select(Message)
                .where(*base)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items = [message_out(m) for m in rows]
        await audit.record(
            session, ctx, "conversation.read_messages", "conversation", conversation_id, {"count": len(items)}
        )
    return Page[MessageOut](items=items, total=total, limit=limit, offset=offset)


async def _messaging_consented(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> bool:
    newest = await session.scalar(
        select(Consent.granted)
        .where(
            Consent.clinic_id == ctx.clinic_id,
            Consent.patient_id == patient_id,
            Consent.kind == ConsentKind.MESSAGING.value,
        )
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .limit(1)
    )
    return bool(newest)


async def send_message(
    db: ClinicDatabase,
    ctx: ActionContext,
    conversation_id: UUID,
    payload: MessageCreate,
    *,
    delivery: OutboundDelivery | None = None,
) -> MessageOut:
    """Manual staff reply. Transaction 1 stores it ``queued`` (and audits), then the channel gets it, then
    transaction 2 records sent/rejected (``outbound.deliver_queued_message``)."""
    require(ctx, Permission.CONVERSATION_REPLY)
    update_id = f"staff:{ctx.idempotency_key}" if ctx.idempotency_key else None
    claimed = False
    async with db.session() as session:
        conv = await load_conversation(session, ctx, conversation_id, for_update=True)
        existing = None
        if update_id is not None:
            existing = await session.scalar(
                select(Message).where(
                    Message.clinic_id == ctx.clinic_id,
                    Message.channel == conv.channel,
                    Message.update_id == update_id,
                )
            )
        if existing is not None:
            if existing.conversation_id != conversation_id or existing.body != payload.text:
                raise DomainError(
                    ErrorCode.DUPLICATE_REQUEST, "Khóa Idempotency-Key đã dùng cho nội dung khác."
                )
            message_id = existing.id
        else:
            # the send lock (O2): the row is locked, so a takeover that is being applied waits for this send
            # to finish, and the next send of the old holder is refused
            claimed = await enforce_reply_lock(session, ctx, conv)
            if payload.proactive:
                if conv.patient_id is None:
                    raise DomainError(
                        ErrorCode.IDENTITY_NOT_VERIFIED,
                        "Chưa xác minh bệnh nhân của hội thoại này nên không nhắn chủ động.",
                    )
                if not await _messaging_consented(session, ctx, conv.patient_id):
                    raise DomainError(
                        ErrorCode.CONSENT_REQUIRED, "Bệnh nhân chưa đồng ý nhận tin nhắn từ phòng khám."
                    )
            row = Message(
                clinic_id=ctx.clinic_id,
                conversation_id=conv.id,
                channel=conv.channel,
                direction=MessageDirection.OUTBOUND.value,
                sender_type=SenderType.STAFF.value,
                sender_user_id=ctx.actor_user_id,
                body=payload.text,
                status=MessageStatus.QUEUED.value,
                proactive=payload.proactive,
                update_id=update_id,
            )
            session.add(row)
            conv.last_message_at = now()
            with lost_race_is_conflict():
                await session.flush()
            await audit.record(
                session,
                ctx,
                "message.send",
                "message",
                row.id,
                {"conversation_id": str(conv.id), "proactive": payload.proactive},
            )
            message_id = row.id
    if claimed:
        emit_live(LiveEventType.ASSIGNMENT_CHANGED, conversation_id)
    emit_live(LiveEventType.INBOX_CHANGED, conversation_id)
    result = await deliver_queued_message(db, ctx, message_id, delivery)
    if result is None:  # pragma: no cover - the row was just written
        raise not_found("tin nhắn")
    return result


__all__ = [
    "get_conversation",
    "list_conversations",
    "list_messages",
    "load_conversation",
    "mark_conversation_read",
    "require_conversation_access",
    "send_message",
    "staff_display_names",
    "summaries",
    "update_conversation",
]

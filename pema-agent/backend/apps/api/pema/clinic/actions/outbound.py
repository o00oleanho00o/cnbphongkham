"""The seam between the clinic and a channel: ``OutboundDelivery``.

New module. ``pema.clinic.actions`` never imports a channel (import-linter), yet a staff reply and an approved
review item must reach the patient. The action records the message as ``queued`` in one transaction, then
hands it to an ``OutboundDelivery`` OUTSIDE any transaction (a network call must not hold a database lock),
and records the result in a second transaction. Without a delivery (none wired yet, or the channel is not
running) the message stays ``queued`` and is visible in the Inbox as such.

The real implementation is wired by package G over ``ChannelRegistry`` / the shared send pipeline of C2
(which also applies the proactive guard: cap, kill switch, window, gap).
``FakeOutboundDelivery`` is for tests.

Package O, step O4 (the clinic identity). Every message leaves through the identity of its thread, whoever
sent it. Before the network call this module

* re-checks the send lock of O2: a staff message whose sender no longer holds the thread (a takeover between
  queue and send) is ``rejected`` with ``thread_locked`` and never reaches the channel. Approved review items
  are a decision of the approver and are not subject to the lock (O2 did not lock them either);
* resolves the identity: ``conversation.account_id``, else the channel's single enabled customer account, else
  the message stays ``queued`` with ``error_code = no_identity`` (visible in the Inbox). A delivery opts in
  with ``requires_identity = True`` (the real one does); ``FakeOutboundDelivery`` keeps the old behaviour by
  default so the tests written before O4 still pass;
* refuses an account whose ``purpose`` is ``internal`` (``policy_denied``): the notifier never faces a
  customer;
* hands the delivery the sender (``sender_type``, ``sender_user_id``) and the account. The text is exactly the
  stored body: no operator name and no signature is ever added (decision 2 of the plan).

The per-identity queue, gap and cap are in ``pema.channels.identity_send_queue``. After a send the adapter's
``external_message_id`` is stored and the status is ``sent``. There is no ``delivered`` state: no adapter
reports delivery of our messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import now
from pema.clinic.actions._mappers import message_out
from pema.clinic.models import Conversation, Message
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind, SendResult, SendStatus
from pema_contracts.common import ApiModel
from pema_contracts.conversations import MessageOut, MessageStatus, SenderType
from pema_contracts.errors import ErrorCode
from pema_contracts.live import LiveEventType

_log = create_logger("clinic.outbound")

NO_IDENTITY_DETAIL = "no_identity"
_INTERNAL = "internal"


class OutboundRequest(ApiModel):
    """One approved text to send. ``text`` is the human-approved content."""

    clinic_id: UUID
    message_id: UUID
    conversation_id: UUID
    channel: ChannelKind
    external_ref: str
    text: str
    proactive: bool = False
    review_item_id: UUID | None = None
    account_id: str | None = None
    """The identity to send through (O4). ``None`` only for a delivery that does not ask for one."""
    sender_type: SenderType | None = None
    sender_user_id: UUID | None = None


@runtime_checkable
class OutboundDelivery(Protocol):
    async def deliver(self, ctx: ActionContext, request: OutboundRequest) -> SendResult:
        """Send the text. A guard (cap, kill switch, not a friend) answers a rejected ``SendResult``; it
        does not raise."""
        ...


@dataclass
class FakeOutboundDelivery:
    """Test double: records requests and answers a canned result."""

    result: SendResult = field(
        default_factory=lambda: SendResult(status=SendStatus.SENT, external_message_id="fake-1")
    )
    requests: list[OutboundRequest] = field(default_factory=list[OutboundRequest])
    raises: Exception | None = None
    requires_identity: bool = False
    """True: the action resolves the identity (``no_identity``, internal guard) before it calls ``deliver``,
    like the real delivery does. False keeps the behaviour of the tests written before O4."""

    async def deliver(self, ctx: ActionContext, request: OutboundRequest) -> SendResult:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        return self.result


_STATUS = {
    SendStatus.SENT: MessageStatus.SENT,
    SendStatus.QUEUED: MessageStatus.QUEUED,
    SendStatus.REJECTED: MessageStatus.REJECTED,
}


@dataclass(frozen=True)
class _Resolved:
    account_id: str | None = None
    refusal: SendResult | None = None


async def _resolve_identity(
    session: AsyncSession, ctx: ActionContext, conv: Conversation, *, required: bool
) -> _Resolved:
    """The identity a message leaves through. Reads ``agent.accounts`` with ``id`` and ``purpose`` only
    (never a credential column)."""
    # ``account_id`` is a column of O1 that the ORM model of ``Conversation`` does not map: read it by SQL
    account_id: str | None = await session.scalar(
        text("SELECT account_id FROM clinic.conversation WHERE clinic_id = :clinic_id AND id = :id"),
        {"clinic_id": ctx.clinic_id, "id": conv.id},
    )
    if account_id is not None:
        purpose = await session.scalar(
            text("SELECT purpose FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :account_id"),
            {"clinic_id": ctx.clinic_id, "account_id": account_id},
        )
        if purpose == _INTERNAL:
            return _Resolved(
                refusal=SendResult(
                    status=SendStatus.REJECTED,
                    error_code=ErrorCode.POLICY_DENIED,
                    detail="internal_identity",
                )
            )
        return _Resolved(account_id=account_id)
    if not required:
        return _Resolved()
    ids = (
        await session.scalars(
            text(
                "SELECT id FROM agent.accounts WHERE clinic_id = :clinic_id AND channel = :channel "
                "AND purpose = 'customer' AND enabled ORDER BY id"
            ),
            {"clinic_id": ctx.clinic_id, "channel": conv.channel},
        )
    ).all()
    if len(ids) == 1:
        return _Resolved(account_id=ids[0])
    return _Resolved(
        refusal=SendResult(
            status=SendStatus.QUEUED, error_code=ErrorCode.NO_IDENTITY, detail=NO_IDENTITY_DETAIL
        )
    )


def _lost_the_lock(row: Message, conv: Conversation) -> bool:
    """The sender of a staff message was replaced as holder after the message was queued. Review approvals
    and messages of the agent or the system are not locked (see the module docstring)."""
    return (
        row.sender_type == SenderType.STAFF.value
        and row.review_item_id is None
        and row.sender_user_id is not None
        and conv.assigned_user_id is not None
        and conv.assigned_user_id != row.sender_user_id
    )


async def deliver_queued_message(
    db: ClinicDatabase,
    ctx: ActionContext,
    message_id: UUID,
    delivery: OutboundDelivery | None,
) -> MessageOut | None:
    """Hand a ``queued`` outbound message to the channel and record what happened ("danh dau da gui").

    Idempotent: a message that is no longer ``queued`` is returned untouched, so a retried request does not
    send twice. Returns ``None`` only when the message does not exist.
    """
    async with db.session() as session:
        row = await session.scalar(
            select(Message).where(Message.id == message_id, Message.clinic_id == ctx.clinic_id)
        )
        if row is None:
            return None
        if row.status != MessageStatus.QUEUED.value or delivery is None:
            return message_out(row)
        conv = await session.scalar(
            select(Conversation).where(
                Conversation.id == row.conversation_id, Conversation.clinic_id == ctx.clinic_id
            )
        )
        if conv is None or not row.body:
            return message_out(row)
        refusal: SendResult | None = None
        resolved = _Resolved()
        if _lost_the_lock(row, conv):
            refusal = SendResult(
                status=SendStatus.REJECTED, error_code=ErrorCode.THREAD_LOCKED, detail="holder_changed"
            )
        else:
            resolved = await _resolve_identity(
                session, ctx, conv, required=bool(getattr(delivery, "requires_identity", False))
            )
            refusal = resolved.refusal
        request = OutboundRequest(
            clinic_id=ctx.clinic_id,
            message_id=row.id,
            conversation_id=row.conversation_id,
            channel=ChannelKind(conv.channel),
            external_ref=conv.external_ref,
            text=row.body,
            proactive=row.proactive,
            review_item_id=row.review_item_id,
            account_id=resolved.account_id,
            sender_type=SenderType(row.sender_type),
            sender_user_id=row.sender_user_id,
        )

    if refusal is not None:
        result = refusal
    else:
        try:
            result = await delivery.deliver(ctx, request)
        except Exception as exc:
            _log.error("outbound delivery raised", err=exc, message_id=str(message_id))
            result = SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE)

    async with db.session() as session:
        row = await session.scalar(
            select(Message).where(Message.id == message_id, Message.clinic_id == ctx.clinic_id)
        )
        if row is None:
            return None
        if row.status == MessageStatus.QUEUED.value:
            row.status = _STATUS[result.status].value
            row.external_message_id = result.external_message_id
            row.error_code = result.error_code.value if result.error_code else None
            row.sent_at = result.sent_at if result.status is SendStatus.SENT else None
            if result.status is SendStatus.SENT and row.sent_at is None:
                row.sent_at = now()
            await session.flush()
            await audit.record(
                session,
                ctx,
                "message.delivery",
                "message",
                row.id,
                {"status": row.status, "error_code": row.error_code},
            )
        delivered = message_out(row)
    emit_live(LiveEventType.INBOX_CHANGED, delivered.conversation_id)
    return delivered

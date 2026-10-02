"""The seam between the clinic and a channel: ``OutboundDelivery``.

New module. ``pema.clinic.actions`` never imports a channel (import-linter), yet a staff reply and an approved
review item must reach the patient. The action records the message as ``queued`` in one transaction, then
hands it to an ``OutboundDelivery`` OUTSIDE any transaction (a network call must not hold a database lock),
and records the result in a second transaction. Without a delivery (none wired yet, or the channel is not
running) the message stays ``queued`` and is visible in the Inbox as such.

The real implementation is wired by package G over ``ChannelRegistry`` / the shared send pipeline of C2
(which also applies the proactive guard: cap, kill switch, window, gap).
``FakeOutboundDelivery`` is for tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.actions._common import now
from pema.clinic.actions._mappers import message_out
from pema.clinic.models import Conversation, Message
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind, SendResult, SendStatus
from pema_contracts.common import ApiModel
from pema_contracts.conversations import MessageOut, MessageStatus
from pema_contracts.errors import ErrorCode

_log = create_logger("clinic.outbound")


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
        request = OutboundRequest(
            clinic_id=ctx.clinic_id,
            message_id=row.id,
            conversation_id=row.conversation_id,
            channel=ChannelKind(conv.channel),
            external_ref=conv.external_ref,
            text=row.body,
            proactive=row.proactive,
            review_item_id=row.review_item_id,
        )

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
        return message_out(row)

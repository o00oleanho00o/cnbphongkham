"""Inbox: conversations, messages (B1 routes; C1/C2 webhook adapters write the inbound side)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security, status

from pema.api.dashboard_auth import Ctx, Database, Delivery
from pema.api.deps import ERROR_RESPONSES, IdempotencyKey, Limit, Offset, cookie_scheme
from pema.api.live_access import LiveDep, actor_id, with_viewers
from pema.clinic.actions import conversations
from pema_contracts.common import Page
from pema_contracts.conversations import (
    ConversationOut,
    ConversationStatus,
    ConversationSummary,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)
from pema_contracts.live import PresenceBeat

router = APIRouter(tags=["conversations"], responses=ERROR_RESPONSES)
staff = [Security(cookie_scheme)]


@router.get(
    "/conversations",
    response_model=Page[ConversationSummary],
    dependencies=staff,
    summary="Inbox list",
)
async def list_conversations(
    db: Database,
    ctx: Ctx,
    live: LiveDep,
    conversation_status: ConversationStatus | None = None,
    assigned_user_id: UUID | None = None,
    patient_id: UUID | None = None,
    has_pending_review: bool | None = None,
    q: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ConversationSummary]:
    page = await conversations.list_conversations(
        db,
        ctx,
        status=conversation_status,
        assigned_user_id=assigned_user_id,
        patient_id=patient_id,
        has_pending_review=has_pending_review,
        q=q,
        limit=limit,
        offset=offset,
    )
    return page.model_copy(update={"items": await with_viewers(db, ctx, live, page.items)})


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    dependencies=staff,
    summary="One conversation",
)
async def get_conversation(conversation_id: UUID, db: Database, ctx: Ctx, live: LiveDep) -> ConversationOut:
    conversation = await conversations.get_conversation(db, ctx, conversation_id)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    dependencies=staff,
    summary="Assign or change status",
)
async def update_conversation(
    conversation_id: UUID, body: ConversationUpdate, db: Database, ctx: Ctx, live: LiveDep
) -> ConversationOut:
    conversation = await conversations.update_conversation(db, ctx, conversation_id, body)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.post(
    "/conversations/{conversation_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=staff,
    summary="Mark inbound messages as read",
)
async def mark_conversation_read(conversation_id: UUID, db: Database, ctx: Ctx) -> None:
    await conversations.mark_conversation_read(db, ctx, conversation_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Page[MessageOut],
    dependencies=staff,
    summary="Messages, newest first",
)
async def list_messages(
    conversation_id: UUID,
    db: Database,
    ctx: Ctx,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[MessageOut]:
    return await conversations.list_messages(db, ctx, conversation_id, limit=limit, offset=offset)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=staff,
    summary="Send a manual staff reply through the channel",
)
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    db: Database,
    ctx: Ctx,
    delivery: Delivery,
    idempotency_key: IdempotencyKey = None,
) -> MessageOut:
    return await conversations.send_message(db, ctx, conversation_id, body, delivery=delivery)


@router.post(
    "/conversations/{conversation_id}/presence",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=staff,
    summary="Presence heartbeat: I am looking at or answering this conversation",
    description=(
        "Sent every 15 seconds while the conversation is open; an entry expires after 30 seconds. A WARNING "
        "shown to colleagues in `viewers`, never a lock: it does not block sending. Needs the right to read "
        "the conversation (403, or 404 when it is not visible). Answers 204 also when the presence store is "
        "unavailable."
    ),
)
async def touch_presence(
    conversation_id: UUID, body: PresenceBeat, db: Database, ctx: Ctx, live: LiveDep
) -> None:
    await conversations.require_conversation_access(db, ctx, conversation_id)
    if live is not None:
        await live.presence.beat(conversation_id, actor_id(ctx), body.state)


@router.delete(
    "/conversations/{conversation_id}/presence",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=staff,
    summary="Presence: I left this conversation",
)
async def leave_presence(conversation_id: UUID, db: Database, ctx: Ctx, live: LiveDep) -> None:
    await conversations.require_conversation_access(db, ctx, conversation_id)
    if live is not None:
        await live.presence.leave(conversation_id, actor_id(ctx))

"""The admin routes of the conversations plugin, under ``/v1/plugins/conversations``: the settings (which
channels keep conversations, who is staff, how long), the conversations and their messages, and who wrote in a
channel."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict

from agent_app.plugins import PluginError
from agentcore.channels import valid_channel_name

from .models import Conversation
from .plugin import ConversationsPlugin, Settings

ConversationId = Annotated[str, Path(pattern=r"^cv-[a-f0-9]{20}$")]


class ExcludeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded: bool


def conversations_routes(plugin: ConversationsPlugin) -> APIRouter:
    async def ready() -> None:
        try:
            await plugin.ready()
        except PluginError as err:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err

    router = APIRouter(dependencies=[Depends(ready)])
    store = plugin.store

    async def found(conversation_id: str) -> Conversation:
        conversation = await store.get(conversation_id)
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có cuộc trò chuyện này.")
        return conversation

    @router.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return (await plugin.settings()).model_dump()

    @router.put("/settings")
    async def put_settings(body: Settings) -> dict[str, Any]:
        return (await plugin.save_settings(body)).model_dump()

    @router.get("/conversations")
    async def list_conversations(
        channel: str | None = Query(default=None, max_length=64),
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        if channel is not None and not valid_channel_name(channel):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tên kênh không đúng.")
        rows, total = await store.conversations(channel=channel, query=q, limit=limit, offset=offset)
        return {"conversations": [c.shown() for c in rows], "total": total}

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(
        conversation_id: ConversationId, limit: int = Query(default=300, ge=1, le=1000)
    ) -> dict[str, Any]:
        conversation = await found(conversation_id)
        messages = await store.messages(conversation_id, limit=limit)
        return {"conversation": conversation.shown(), "messages": [m.shown() for m in messages]}

    @router.patch("/conversations/{conversation_id}")
    async def change_conversation(conversation_id: ConversationId, body: ExcludeBody) -> dict[str, Any]:
        await found(conversation_id)
        await store.set_excluded(conversation_id, body.excluded)
        return (await found(conversation_id)).shown()

    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: ConversationId) -> dict[str, Any]:
        await found(conversation_id)
        await store.delete(conversation_id)
        return {"deleted": True}

    @router.get("/people")
    async def people(channel: str = Query(max_length=64)) -> dict[str, Any]:
        if not valid_channel_name(channel):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tên kênh không đúng.")
        return {"people": [p.shown() for p in await store.people(channel)]}

    return router

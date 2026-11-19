"""The admin routes of the conversations plugin, under ``/v1/plugins/conversations``: the settings (which
channels keep conversations, who is staff, how long), the conversations and their messages, and who wrote in a
channel."""

from __future__ import annotations

import contextlib
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agent_app.plugins import PluginError
from agentcore.channels import valid_channel_name
from plugin_kit import EmbeddingUnavailableError

from .models import Conversation
from .plugin import ConversationsPlugin
from .scenario_models import Reach
from .settings import Settings

ConversationId = Annotated[str, Path(pattern=r"^cv-[a-f0-9]{20}$")]
EpisodeId = Annotated[str, Path(pattern=r"^ep-[a-f0-9]{20}$")]
MAX_DELETE: Final = 100


class ExcludeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded: bool


class DeleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[Annotated[str, StringConstraints(pattern=r"^cv-[a-f0-9]{20}$")]] = Field(
        min_length=1, max_length=MAX_DELETE
    )


class EnableBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class TrySearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=300)
    channel: str | None = Field(default=None, max_length=64)


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

    async def forget(conversation_ids: list[str]) -> dict[str, int]:
        """The scenarios cut from these conversations go too: the agent searches them, so leaving them would
        leave it remembering what was deleted."""
        scenarios = await plugin.episodes.delete_of_conversations(conversation_ids)
        return {"deleted": await store.delete_many(conversation_ids), "scenarios": scenarios}

    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: ConversationId) -> dict[str, Any]:
        await found(conversation_id)
        await forget([conversation_id])
        return {"deleted": True}

    @router.post("/conversations/delete")
    async def delete_conversations(body: DeleteBody) -> dict[str, int]:
        """Many at once; ids that do not exist are not an error."""
        return await forget(list(dict.fromkeys(body.ids)))

    @router.get("/people")
    async def people(channel: str = Query(max_length=64)) -> dict[str, Any]:
        if not valid_channel_name(channel):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tên kênh không đúng.")
        return {"people": [p.shown() for p in await store.people(channel)]}

    @router.get("/scenarios")
    async def list_scenarios(
        channel: str | None = Query(default=None, max_length=64),
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        if channel is not None and not valid_channel_name(channel):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tên kênh không đúng.")
        rows, total = await plugin.episodes.episodes(channel=channel, query=q, limit=limit, offset=offset)
        return {"scenarios": [e.shown() for e in rows], "total": total}

    @router.get("/scenarios/status")
    async def scenarios_status() -> dict[str, Any]:
        counts, connected = await plugin.scenarios.counts()
        return {
            "scenarios": counts.episodes,
            "without_vector": counts.without_vector,
            "embedding_connected": connected,
            "embedding_error": plugin.scenarios.embedding_error,
        }

    @router.post("/scenarios/refresh")
    async def refresh_scenarios() -> dict[str, Any]:
        """Cuts the conversations now, the ones still going included (the job waits for a chat to go quiet),
        and makes one batch of the vectors that wait."""
        cut = await plugin.scenarios.cut_once(idle_s=0)
        with contextlib.suppress(EmbeddingUnavailableError):
            await plugin.scenarios.embed_once()
        return {"conversations": cut.conversations, "new": cut.episodes, "joined": cut.joined}

    @router.post("/scenarios/search")
    async def try_search(body: TrySearchBody) -> dict[str, Any]:
        """What a question on a channel would be shown, so the staff can try the scenarios out."""
        if body.channel is not None and not valid_channel_name(body.channel):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tên kênh không đúng.")
        settings = (await plugin.settings()).scenarios
        reach = plugin.scenarios.reach_of(body.channel, settings) or Reach(channel="")
        hits = await plugin.scenarios.search(body.query, reach, settings)
        return {"hits": [h.shown() for h in hits], "scope": settings.scope}

    @router.patch("/scenarios/{episode_id}")
    async def change_scenario(episode_id: EpisodeId, body: EnableBody) -> dict[str, Any]:
        if not await plugin.episodes.set_enabled(episode_id, body.enabled):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có kịch bản này.")
        found = await plugin.episodes.get(episode_id)
        return {} if found is None else found.shown()

    @router.delete("/scenarios/{episode_id}")
    async def delete_scenario(episode_id: EpisodeId) -> dict[str, Any]:
        if not await plugin.episodes.delete(episode_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có kịch bản này.")
        return {"deleted": True}

    return router

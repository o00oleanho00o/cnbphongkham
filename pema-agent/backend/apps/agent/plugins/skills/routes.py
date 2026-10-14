"""The admin routes of the skills plugin, under ``/v1/plugins/skills``: list, create, change, the versions of
an item and going back to one, and a preview of what a channel gets."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field

from agent_app.plugins import PluginError
from agentcore import ModelError

from .check import ItemError
from .models import Item, Kind, Status, new_id
from .plugin import SkillsPlugin, render
from .store import NameTakenError
from .studio import Known, Studio

ItemId = Annotated[str, Path(pattern=r"^itm-[a-z0-9]{1,40}$")]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemBody(_Body):
    kind: Kind
    name: str = Field(max_length=64)
    description: str = Field(max_length=2000)
    body: str = Field(max_length=100_000)
    status: Status = "active"
    scopes: list[str] = Field(default_factory=list[str], max_length=100)
    meta: dict[str, Any] = Field(default_factory=dict[str, Any])


class ItemPatch(_Body):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, max_length=100_000)
    status: Status | None = None
    scopes: list[str] | None = Field(default=None, max_length=100)
    meta: dict[str, Any] | None = None
    reason: str = Field(default="", max_length=300)


class RestoreBody(_Body):
    version: int = Field(ge=1)


class ChatBody(_Body):
    conversation_id: str = Field(pattern=r"^[a-z0-9-]{8,64}$")
    text: str = Field(min_length=1, max_length=8000)
    channels: list[str] = Field(default_factory=list[str], max_length=50)
    plugins: list[str] = Field(default_factory=list[str], max_length=50)


def skills_routes(plugin: SkillsPlugin, studio: Studio) -> APIRouter:
    async def ready() -> None:
        try:
            await plugin.ready()
        except PluginError as err:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err

    router = APIRouter(dependencies=[Depends(ready)])
    store = plugin.store

    def actor(request: Request) -> str:
        principal = getattr(request.state, "principal", None)
        return str(getattr(principal, "subject", "") or "admin")

    async def found(item_id: str) -> Item:
        item = await store.get(item_id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có mục này.")
        return item

    async def save(item: Item, request: Request, reason: str = "") -> dict[str, Any]:
        try:
            saved, checked = await plugin.save_item(item, by=actor(request), reason=reason)
        except ItemError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
        except NameTakenError as err:
            raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err
        return {"item": saved.shown(), "warnings": checked.warnings}

    @router.get("/items")
    async def list_items(kind: Kind | None = None, item_status: Status | None = None) -> dict[str, Any]:
        items = await store.list(kind=kind, status=item_status)
        return {"items": [i.shown() for i in items], "total": len(items)}

    @router.post("/items", status_code=status.HTTP_201_CREATED)
    async def create_item(body: ItemBody, request: Request) -> dict[str, Any]:
        item = Item(
            id=new_id(),
            kind=body.kind,
            name=body.name.strip(),
            description=body.description.strip(),
            body=body.body,
            status=body.status,
            scopes=body.scopes,
            meta=body.meta,
        )
        return await save(item, request, "created")

    @router.get("/items/{item_id}")
    async def get_item(item_id: ItemId) -> dict[str, Any]:
        return (await found(item_id)).shown()

    @router.patch("/items/{item_id}")
    async def change_item(item_id: ItemId, body: ItemPatch, request: Request) -> dict[str, Any]:
        item = await found(item_id)
        given = body.model_dump(exclude_none=True, exclude={"reason"})
        for key in ("name", "description"):
            if key in given:
                given[key] = given[key].strip()
        return await save(replace(item, **given), request, body.reason)

    @router.get("/items/{item_id}/versions")
    async def item_versions(item_id: ItemId) -> dict[str, Any]:
        await found(item_id)
        return {"versions": [v.shown() for v in await store.versions(item_id)]}

    @router.post("/items/{item_id}/restore")
    async def restore_item(item_id: ItemId, body: RestoreBody, request: Request) -> dict[str, Any]:
        item = await found(item_id)
        old = next((v for v in await store.versions(item_id) if v.version == body.version), None)
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có phiên bản này.")
        snap = old.snapshot
        restored = replace(
            item,
            name=str(snap.get("name", item.name)),
            description=str(snap.get("description", item.description)),
            body=str(snap.get("body", item.body)),
            status=snap.get("status", item.status),
            scopes=[str(s) for s in snap.get("scopes", [])],
            meta=dict(snap.get("meta", {})),
        )
        return await save(restored, request, f"restored version {body.version}")

    @router.post("/author/chat")
    async def author_chat(body: ChatBody, request: Request) -> dict[str, Any]:
        """One turn of the chat that helps staff write items; the items it saved come back with it."""
        known = Known(channels=body.channels, plugins=body.plugins)
        try:
            reply = await studio.chat(body.conversation_id, body.text, known, by=actor(request))
        except ModelError as err:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Chưa gọi được model ({err.kind}): {err}"
            ) from err
        except PluginError as err:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err
        return {
            "reply": reply.text,
            "stop": reply.stop,
            "items": [{"item": t.item.shown(), "before_version": t.before_version} for t in reply.touched],
        }

    @router.get("/effective")
    async def effective(channel: str | None = None) -> dict[str, Any]:
        """What a question on ``channel`` carries: the items that apply, broad first, and their block."""
        await plugin.refresh()
        applying = plugin.applicable(channel)
        return {
            "channel": channel,
            "plugin": plugin.plugin_of(channel) if channel else None,
            "items": [
                {"id": i.id, "kind": i.kind, "name": i.name, "rank": rank, "scopes": i.scopes}
                for rank, i in applying
            ],
            "text": render(applying, index_chars=plugin.index_chars, context_chars=plugin.context_chars),
        }

    return router

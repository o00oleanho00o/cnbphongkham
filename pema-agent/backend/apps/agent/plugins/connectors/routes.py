"""The routes of the connectors plugin.

Admin (under ``/v1/plugins/connectors``, admin token): list the connectors and their channels, add one (its key
shows once), revoke one.

Hooks (under ``/v1/hooks/connectors``, open): what a connector pushes, as ``docs/CONNECTOR-PROTOCOL.md`` section 3
says. Every call is signed with the connector's key; the signature is checked before the body is read, a failure
is a bare 401 (an unknown, a revoked and a wrong key look alike), and a connector may touch only the channels
named like itself or starting with ``<connector>-``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal, TypeVar

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from agentcore.channels import InboundMessage, ObservedMessage, valid_channel_name

from .channel import ChannelSettings
from .plugin import NAME, ConnectorError, ConnectorsPlugin, owns_channel
from .signing import connector_of, verify

PROTOCOL: Final = 1
MAX_BODY_BYTES: Final = 1_000_000
Id = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Metadata = Annotated[dict[str, str], Field(max_length=50)]

T = TypeVar("T", bound=BaseModel)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=NAME.pattern)


class ChannelBody(BaseModel):
    protocol: int
    callback_url: str = Field(min_length=8, max_length=500, pattern=r"^https?://[^\s/]+")
    max_text_chars: int | None = Field(default=None, ge=1, le=100_000)
    markdown: bool = False
    rules: str = Field(default="", max_length=4000)
    disabled_tools: list[Annotated[str, StringConstraints(max_length=64)]] = Field(
        default_factory=list, max_length=100
    )


class InboundBody(BaseModel):
    conversation_id: Id
    user_id: Id
    message_id: Id
    text: str
    metadata: Metadata = Field(default_factory=dict)


class ObservedBody(BaseModel):
    conversation_id: Id
    message_id: Id
    text: str
    origin: Literal["inbound", "own", "agent"]
    sender_id: str = Field(default="", max_length=300)
    is_group: bool = False
    sender_name: str = Field(default="", max_length=300)
    user_id: str = Field(default="", max_length=300)
    answered: bool = False
    at: str = ""
    metadata: Metadata = Field(default_factory=dict)


class TypingBody(BaseModel):
    conversation_id: Id


def connector_admin_routes(plugin: ConnectorsPlugin) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def list_connectors() -> dict[str, Any]:
        return {"connectors": await plugin.connectors()}

    @router.post("/", status_code=status.HTTP_201_CREATED)
    async def create_connector(body: CreateBody) -> dict[str, str]:
        try:
            return {"name": body.name, "key": await plugin.create(body.name)}
        except ConnectorError as err:
            raise HTTPException(err.status, str(err)) from err

    @router.delete("/{name}")
    async def revoke_connector(name: str) -> dict[str, str]:
        if not await plugin.revoke(name):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có connector này.")
        return {"revoked": name}

    return router


def connector_hook_routes(plugin: ConnectorsPlugin) -> APIRouter:
    router = APIRouter()

    async def signed(request: Request) -> tuple[str, bytes]:
        """The connector that signed the request and the raw body, or a bare 401."""
        body = await request.body()
        name = connector_of(request.headers)
        key = await plugin.key(name) if name and NAME.match(name) else None
        if name is None or key is None or not verify(key, request.headers, request.method, request.scope["path"], body):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(413, "body too large")
        return name, body

    def own(connector: str, channel: str) -> None:
        if not valid_channel_name(channel) or not owns_channel(connector, channel):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "channel not allowed for this connector")

    def parsed(model: type[T], body: bytes) -> T:
        try:
            return model.model_validate_json(body)
        except ValidationError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid body") from err

    @router.put("/channels/{name}")
    async def put_channel(name: str, request: Request) -> dict[str, Any]:
        connector, raw = await signed(request)
        own(connector, name)
        body = parsed(ChannelBody, raw)
        if body.protocol != PROTOCOL:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"protocol {PROTOCOL} only")
        try:
            await plugin.put_channel(
                connector,
                name,
                ChannelSettings(
                    connector=connector,
                    callback_url=body.callback_url,
                    max_text_chars=body.max_text_chars,
                    markdown=body.markdown,
                    rules=body.rules,
                    disabled_tools=body.disabled_tools,
                ),
            )
        except ConnectorError as err:
            raise HTTPException(err.status, str(err)) from err
        return {}

    @router.delete("/channels/{name}")
    async def delete_channel(name: str, request: Request) -> dict[str, Any]:
        connector, _ = await signed(request)
        own(connector, name)
        try:
            await plugin.delete_channel(connector, name)
        except ConnectorError as err:
            raise HTTPException(err.status, str(err)) from err
        return {}

    @router.post("/channels/{name}/inbound")
    async def inbound(name: str, request: Request) -> dict[str, Any]:
        connector, raw = await signed(request)
        own(connector, name)
        body = parsed(InboundBody, raw)
        channel = plugin.channel_of(connector, name)
        if channel is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not registered")
        await plugin.touch(name)
        if not body.text.strip():
            return {"ingress_id": None}  # nothing to answer; the connector may drop it
        try:
            ingress_id = await channel.handle_inbound(
                InboundMessage(
                    channel=name,
                    conversation_id=body.conversation_id,
                    user_id=body.user_id,
                    message_id=body.message_id,
                    text=body.text,
                    metadata=body.metadata,
                )
            )
        except RuntimeError as err:  # the hub has not started the channel yet: the connector tries again
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "channel is starting", headers={"Retry-After": "3"}
            ) from err
        return {"ingress_id": ingress_id}

    @router.post("/channels/{name}/observed")
    async def observed(name: str, request: Request) -> dict[str, Any]:
        connector, raw = await signed(request)
        own(connector, name)
        body = parsed(ObservedBody, raw)
        if plugin.channel_of(connector, name) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not registered")
        await plugin.touch(name)
        await plugin.observe(
            ObservedMessage(
                channel=name,
                conversation_id=body.conversation_id,
                sender_id=body.sender_id,
                message_id=body.message_id,
                text=body.text,
                origin=body.origin,
                is_group=body.is_group,
                sender_name=body.sender_name,
                user_id=body.user_id,
                answered=body.answered,
                at=_moment(body.at),
                metadata=body.metadata,
            )
        )
        return {}

    @router.post("/channels/{name}/typing")
    async def typing(name: str, request: Request) -> dict[str, Any]:
        connector, raw = await signed(request)
        own(connector, name)
        body = parsed(TypingBody, raw)
        channel = plugin.channel_of(connector, name)
        if channel is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not registered")
        await plugin.touch(name)
        channel.handle_typing(body.conversation_id)
        return {}

    return router


def _moment(text: str) -> datetime:
    """The ISO 8601 time the connector gave; now when it is missing or unreadable."""
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    return found if found.tzinfo is not None else found.replace(tzinfo=UTC)

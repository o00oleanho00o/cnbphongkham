"""The plugin at run time: the connectors (their sealed keys) and one channel per channel a connector registered.

Everything is kept in ``ctx.storage``:

* ``connector:<name>``: ``{key_sealed, created_at, revoked_at}``; a revoked connector keeps its row, so its name
  is not given out again by mistake;
* ``channel:<name>``: ``{connector, callback_url, max_text_chars, markdown, rules, disabled_tools, seen_at}``.

The channels live in the hub as ``ConnectorChannel`` adapters. A background job registers the stored ones when the
service starts, so they exist again after a restart without the connector registering them anew. All changes to
the channels go through one lock. Known limit: like every plugin channel, they run in the one process of
``agent serve``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Final

from agent_app.plugins import Disposer, PluginContext, PluginError
from agentcore import PromptEnv, TurnInfo, TurnSection
from agentcore.channels import ObservedMessage, valid_channel_name
from agentcore.harness.hooks import ALLOW, Deny, HookContext, PreToolHook, ToolDecision
from agentcore.messages import ToolUseBlock

from .channel import ChannelSettings, ConnectorChannel
from .signing import new_key

NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SEEN_EVERY_S: Final = 60.0
"""How seldom a busy channel's ``seen_at`` is written."""

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """A request the plugin refuses, with the HTTP status its route answers."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def owns_channel(connector: str, channel: str) -> bool:
    """A connector may register the channel named like itself or starting with ``<connector>-``."""
    return channel == connector or channel.startswith(f"{connector}-")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ConnectorsPlugin:
    def __init__(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        self._storage = ctx.storage
        self._channels: dict[str, ConnectorChannel] = {}
        self._disposers: dict[str, Disposer] = {}
        self._seen_written: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def register(self) -> None:
        ctx = self._ctx
        ctx.register_prompt_section(TurnSection("channel_rules", self._channel_rules))
        ctx.register_hook(PreToolHook("channel_tools", self._tool_allowed))
        ctx.register_job("restore", self._restore)
        ctx.on_disable(self._forget)

    # --- connectors ---

    async def create(self, name: str) -> str:
        """A new connector; its key, shown to the caller once and kept sealed."""
        async with self._lock:
            if await self._storage.get(f"connector:{name}") is not None:
                raise ConnectorError(409, "Tên connector đã dùng (kể cả connector đã thu hồi).")
            key = new_key()
            try:
                sealed = self._ctx.encrypt(key)
            except PluginError as err:
                raise ConnectorError(409, "Agent chưa có khóa bí mật để mã hóa (chạy bằng agent serve).") from err
            await self._storage.put(
                f"connector:{name}", {"key_sealed": sealed, "created_at": _now(), "revoked_at": None}
            )
        return key

    async def key(self, name: str) -> str | None:
        """The connector's key; None when it is unknown or revoked."""
        row = await self._storage.get(f"connector:{name}")
        if not isinstance(row, dict) or row.get("revoked_at"):
            return None
        try:
            return self._ctx.decrypt(str(row["key_sealed"]))
        except (PluginError, KeyError):
            logger.warning("the key of connector %s cannot be read", name)
            return None

    async def revoke(self, name: str) -> bool:
        """False when there is no such connector. Its channels leave the hub and the storage."""
        async with self._lock:
            row = await self._storage.get(f"connector:{name}")
            if not isinstance(row, dict):
                return False
            if not row.get("revoked_at"):
                await self._storage.put(f"connector:{name}", {**row, "revoked_at": _now()})
            for channel, settings in await self._channel_rows():
                if settings.get("connector") == name:
                    self._drop(channel)
                    await self._storage.delete(f"channel:{channel}")
        return True

    async def connectors(self) -> list[dict[str, Any]]:
        """For the admin page; never the key."""
        rows = await self._channel_rows()
        shown: list[dict[str, Any]] = []
        for key, row in await self._storage.list("connector:"):
            name = key.removeprefix("connector:")
            channels = [
                {
                    "name": channel,
                    "seen_at": settings.get("seen_at"),
                    "markdown": bool(settings.get("markdown")),
                    "max_text_chars": settings.get("max_text_chars"),
                    "listening": (found := self._channels.get(channel)) is not None and found.listening,
                }
                for channel, settings in rows
                if settings.get("connector") == name
            ]
            shown.append(
                {
                    "name": name,
                    "created_at": row.get("created_at"),
                    "revoked": bool(row.get("revoked_at")),
                    "revoked_at": row.get("revoked_at"),
                    "channels": channels,
                }
            )
        return shown

    # --- channels ---

    async def observe(self, message: ObservedMessage) -> None:
        await self._ctx.observe(message)

    def channel_of(self, connector: str, name: str) -> ConnectorChannel | None:
        """The registered channel when it belongs to this connector."""
        found = self._channels.get(name)
        return found if found is not None and found.settings.connector == connector else None

    async def put_channel(self, connector: str, name: str, settings: ChannelSettings) -> None:
        """Registers or updates a channel. A running channel is updated in place, so the hub keeps its start."""
        async with self._lock:
            row = await self._storage.get(f"channel:{name}")
            if isinstance(row, dict) and row.get("connector") != connector:
                raise ConnectorError(409, "Kênh này thuộc connector khác.")
            self._install(name, settings)
            await self._storage.put(f"channel:{name}", {**asdict(settings), "seen_at": _now()})
            self._seen_written[name] = time.monotonic()

    async def delete_channel(self, connector: str, name: str) -> None:
        async with self._lock:
            row = await self._storage.get(f"channel:{name}")
            if isinstance(row, dict) and row.get("connector") != connector:
                raise ConnectorError(409, "Kênh này thuộc connector khác.")
            self._drop(name)
            await self._storage.delete(f"channel:{name}")

    async def touch(self, name: str) -> None:
        """Notes that the connector spoke for this channel (written at most once a ``SEEN_EVERY_S``)."""
        now = time.monotonic()
        if now - self._seen_written.get(name, -SEEN_EVERY_S) < SEEN_EVERY_S:
            return
        async with self._lock:
            row = await self._storage.get(f"channel:{name}")
            if name in self._channels and isinstance(row, dict):
                await self._storage.put(f"channel:{name}", {**row, "seen_at": _now()})
                self._seen_written[name] = now

    def _install(self, name: str, settings: ChannelSettings) -> None:
        found = self._channels.get(name)
        if found is not None:
            found.settings = settings
            return
        channel = ConnectorChannel(name, settings, self.key)
        try:
            self._disposers[name] = self._ctx.register_channel(channel)
        except PluginError as err:
            raise ConnectorError(409, "Tên kênh không dùng được.") from err
        self._channels[name] = channel

    def _drop(self, name: str) -> None:
        self._channels.pop(name, None)
        dispose = self._disposers.pop(name, None)
        if dispose is not None:
            dispose()
        self._seen_written.pop(name, None)

    def _forget(self) -> None:
        self._channels.clear()
        self._disposers.clear()

    async def _channel_rows(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (key.removeprefix("channel:"), row)
            for key, row in await self._storage.list("channel:")
            if isinstance(row, dict)
        ]

    async def _restore(self) -> None:
        """Gives the hub the stored channels of the connectors that are not revoked, then waits (a job that
        ends is started again)."""
        try:
            async with self._lock:
                for name, row in await self._channel_rows():
                    connector = str(row.get("connector", ""))
                    if name in self._channels or not valid_channel_name(name) or not owns_channel(connector, name):
                        continue
                    if await self.key(connector) is None:
                        continue
                    try:
                        self._install(name, _settings_of(row))
                    except ConnectorError as err:
                        logger.warning("channel %s was not restored: %s", name, err)
        except Exception as err:  # the connectors register again by themselves
            logger.warning("connector channels could not be restored (%s)", type(err).__name__)
        await asyncio.Event().wait()

    # --- what the model is told and may use ---

    def _channel_rules(self, env: PromptEnv, turn: TurnInfo) -> str | None:
        found = self._channels.get(turn.channel or "")
        return (found.settings.rules.strip() or None) if found is not None else None

    async def _tool_allowed(self, use: ToolUseBlock, spec: Any, hook: HookContext) -> ToolDecision:
        found = self._channels.get(hook.channel or "")
        if found is not None and use.name in found.settings.disabled_tools:
            return Deny(f"the tool {use.name} is switched off for the channel {found.name}")
        return ALLOW


def _settings_of(row: dict[str, Any]) -> ChannelSettings:
    limit = row.get("max_text_chars")
    return ChannelSettings(
        connector=str(row["connector"]),
        callback_url=str(row["callback_url"]),
        max_text_chars=limit if isinstance(limit, int) else None,
        markdown=bool(row.get("markdown")),
        rules=str(row.get("rules") or ""),
        disabled_tools=[str(t) for t in row.get("disabled_tools") or []],
    )

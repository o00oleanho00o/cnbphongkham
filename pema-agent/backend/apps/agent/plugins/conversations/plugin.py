"""The conversations plugin at run time: hears every message the channels tell of
(``ctx.on_message``), decides its role, and keeps it when the channel is switched on.

Roles: ``agent`` for the agent's own replies, ``staff`` for what the account's owner typed and for people
on the channel's staff list, ``customer`` for everyone else. A channel keeps nothing until it is switched
on in the settings; a conversation can be left out on its own.

The settings are a record in the plugin's storage, read into memory for a few seconds so a message does
not wait on the database."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final

from agent_app.plugins import EMBEDDINGS, EmbeddingService, PluginContext, PluginDatabase
from agentcore.channels import ObservedMessage

from .episode_store import EpisodeStore, InMemoryEpisodeStore, PostgresEpisodeStore
from .models import NewMessage, Role, conversation_id
from .scenarios import Scenarios
from .settings import ChannelSetting, Settings
from .store import ConversationStore, InMemoryConversationStore, PostgresConversationStore

SETTINGS_KEY: Final = "settings"
SETTINGS_TTL_S: Final = 5.0
MAX_TEXT_CHARS: Final = 8000
CLEAN_EVERY_S: Final = 3600.0

logger = logging.getLogger(__name__)


class ConversationsPlugin:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        store: ConversationStore | None = None,
        episodes: EpisodeStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ctx = ctx
        database = ctx.database
        self._database: PluginDatabase | None = database
        self.store: ConversationStore = store or (
            InMemoryConversationStore()
            if database is None
            else PostgresConversationStore(
                database.engine, tenant_id=database.tenant_id, agent=database.agent
            )
        )
        self.episodes: EpisodeStore = episodes or (
            InMemoryEpisodeStore(clock)
            if database is None
            else PostgresEpisodeStore(database.engine, tenant_id=database.tenant_id, agent=database.agent)
        )
        self._clock = clock
        self._monotonic = monotonic
        self._settings: Settings | None = None
        self._read_at = float("-inf")
        self.scenarios = Scenarios(
            conversations=self.store,
            episodes=self.episodes,
            settings=self.settings,
            embeddings=lambda: ctx.use(EMBEDDINGS, EmbeddingService),
            plugin_of=ctx.channel_plugin,
            clock=clock,
            logger=ctx.logger,
        )

    def register(self) -> None:
        ctx = self._ctx
        ctx.on_message(self.hear)
        ctx.register_job("retention", self._keep_clean)
        ctx.register_tool(self.scenarios.tool())
        ctx.register_hook(self.scenarios.hook())
        ctx.register_job("cut", self.scenarios.keep_cutting)
        ctx.register_job("embed", self.scenarios.keep_embedding)

    async def ready(self) -> None:
        if self._database is not None:
            await self._database.require_migrations()

    # --- settings ---

    async def settings(self) -> Settings:
        if self._settings is not None and self._monotonic() - self._read_at < SETTINGS_TTL_S:
            return self._settings
        stored = await self._ctx.storage.get(SETTINGS_KEY)
        settings = Settings.model_validate(stored) if isinstance(stored, dict) else Settings()
        self._settings, self._read_at = settings, self._monotonic()
        return settings

    async def save_settings(self, settings: Settings) -> Settings:
        """Stores the settings and gives earlier messages of people newly put on (or taken off) a staff
        list the role they now have."""
        before = await self.settings()
        await self._ctx.storage.put(SETTINGS_KEY, settings.model_dump())
        self._settings, self._read_at = settings, self._monotonic()
        for channel in settings.channels.keys() | before.channels.keys():
            was = set(before.channels.get(channel, ChannelSetting()).staff)
            now = set(settings.channels.get(channel, ChannelSetting()).staff)
            await self.store.relabel(channel, now - was, "staff")
            await self.store.relabel(channel, was - now, "customer")
        return settings

    # --- hearing ---

    async def hear(self, message: ObservedMessage) -> None:
        settings = await self.settings()
        channel = settings.channels.get(message.channel)
        if channel is None or not channel.enabled:
            return
        text = message.text.strip()[:MAX_TEXT_CHARS]
        if not text or not message.conversation_id or not message.message_id:
            return
        role = role_of(message, channel)
        await self.store.add(
            NewMessage(
                conversation_id=conversation_id(message.channel, message.conversation_id),
                channel=message.channel,
                external_id=message.conversation_id,
                is_group=message.is_group,
                title_hint=message.sender_name if role == "customer" and not message.is_group else "",
                message_id=message.message_id,
                sender_id=message.sender_id,
                sender_name=message.sender_name,
                role=role,
                origin=message.origin,
                at=message.at,
                text=text,
                answered=message.answered,
            )
        )

    # --- retention ---

    async def clean(self) -> int:
        """Deletes the messages older than the retention; how many."""
        days = (await self.settings()).retention_days
        if days <= 0:
            return 0
        return await self.store.purge_before(self._clock() - timedelta(days=days))

    async def _keep_clean(self) -> None:
        while True:
            await asyncio.sleep(CLEAN_EVERY_S)
            with contextlib.suppress(Exception):  # the next round tries again
                gone = await self.clean()
                if gone:
                    logger.info("conversations: %d old messages deleted", gone)


def role_of(message: ObservedMessage, channel: ChannelSetting) -> Role:
    if message.origin == "agent":
        return "agent"
    if message.origin == "own" or message.sender_id in channel.staff:
        return "staff"
    return "customer"

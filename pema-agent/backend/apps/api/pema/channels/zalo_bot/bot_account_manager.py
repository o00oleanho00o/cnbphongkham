"""Start, stop and restart the BOT accounts of this process.

New module (no TypeScript source for the bot half: ``account-manager.ts`` keeps both kinds in one file and
package C2 ports it for the personal accounts). It owns the running bot accounts of this process, reads the
decrypted token from the ``AccountStore`` (the one audited path, ``get_bot_token``) and decides polling vs
webhook from the settings.

``start_all`` is what a process calls at start-up. A bot without a token, a disabled account, or a token Zalo
rejects is logged and skipped, never fatal for the other accounts. A rejected token leaves the account stopped
(no loop that errors every round); the operator fixes it on the admin screen, which calls ``restart``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_bot.bot_account_runner import (
    ClientFactory,
    RunningBotAccount,
    WebhookRegistration,
    chay_tai_khoan_bot,
)
from pema.channels.zalo_bot.bot_message_router import BotMessageRouter
from pema.channels.zalo_bot.settings import ZaloBotSettings, derive_webhook_secret, webhook_url_for
from pema.channels.zalo_bot.zalo_bot_api_client import LoiZaloBotApi
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.channel import ChannelKind

_log = create_logger("bot-account-manager")


class BotAccountManager:
    def __init__(
        self,
        *,
        accounts: AccountStore,
        router: BotMessageRouter,
        registry: InMemoryChannelRegistry,
        settings: ZaloBotSettings,
        clinic_slug_of: Callable[[UUID], Awaitable[str | None]] | None = None,
        client_factory: ClientFactory | None = None,
        listen: bool = True,
    ) -> None:
        self._listen = listen
        self._accounts = accounts
        self._router = router
        self._registry = registry
        self._settings = settings
        self._clinic_slug_of = clinic_slug_of
        self._client_factory = client_factory
        self._running: dict[tuple[UUID, str], RunningBotAccount] = {}

    def is_running(self, clinic_id: UUID, account_id: str) -> bool:
        return (clinic_id, account_id) in self._running

    async def _webhook_for(self, clinic_id: UUID, account_id: str) -> WebhookRegistration | None:
        if self._settings.mode != "webhook":
            return None
        if not self._settings.webhook_base_url or self._clinic_slug_of is None:
            raise LoiZaloBotApi("Webhook mode cần PEMA_ZALO_BOT_WEBHOOK_BASE_URL", "setWebhook")
        slug = await self._clinic_slug_of(clinic_id)
        if slug is None:
            raise LoiZaloBotApi("Không tìm được clinic của account", "setWebhook")
        return WebhookRegistration(
            url=webhook_url_for(self._settings.webhook_base_url, slug, account_id),
            secret=derive_webhook_secret(clinic_id, account_id),
        )

    async def start(self, config: AccountConfig) -> bool:
        """Start one account. Returns ``False`` when it cannot run (not a bot, disabled, no token); raises
        ``LoiZaloBotApi`` when Zalo rejects the token."""
        if config.channel is not ChannelKind.ZALO_BOT or not config.enabled:
            return False
        key = (config.clinic_id, config.id)
        if key in self._running:
            return True
        token = await self._accounts.get_bot_token(config.clinic_id, config.id)
        if not token:
            _log.info("Tài khoản bot chưa có token - không khởi động", account_id=config.id)
            return False
        running = await chay_tai_khoan_bot(
            clinic_id=config.clinic_id,
            account_id=config.id,
            token=token,
            router=self._router,
            registry=self._registry,
            # A send-only account registers nothing, so it needs neither the URL nor the clinic slug (the worker
            # cannot read ``clinic.clinic`` and must not need to).
            webhook=await self._webhook_for(config.clinic_id, config.id) if self._listen else None,
            client_factory=self._client_factory,
            listen=self._listen,
        )
        self._running[key] = running
        return True

    async def stop(self, clinic_id: UUID, account_id: str) -> None:
        running = self._running.pop((clinic_id, account_id), None)
        if running is not None:
            await running.dung()

    async def restart(self, config: AccountConfig) -> bool:
        await self.stop(config.clinic_id, config.id)
        return await self.start(config)

    async def start_all(self) -> int:
        """Start every enabled bot account of every clinic. Returns how many are running."""
        started = 0
        for config in await self._accounts.list_all_enabled_accounts():
            if config.channel is not ChannelKind.ZALO_BOT:
                continue
            try:
                if await self.start(config):
                    started += 1
            except Exception as err:
                _log.error("Không khởi động được tài khoản bot", err=err, account_id=config.id)
        return started

    async def stop_all(self) -> None:
        for clinic_id, account_id in list(self._running):
            await self.stop(clinic_id, account_id)

"""The plugin at run time: keeps one channel per Zalo account that can run, in step with the stored accounts.

``sync`` compares the accounts with the channels: an enabled bot account with a token gets a channel, a
disabled or deleted one (or one whose token changed) loses it; a settings change reaches the running channel
without a restart. The admin routes call it after each change; a background job calls it every
``SYNC_EVERY_S`` so a change made through another process arrives too.

Known limit: every process of the service that runs the plugin polls the same bot. Run the plugin's channels
in one process (``agent serve``) until a lease is added.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from agent_app.plugins import Disposer, PluginContext
from agentcore import PromptEnv, TurnInfo, TurnSection
from agentcore.harness.hooks import ALLOW, Deny, HookContext, PreToolHook, ToolDecision
from agentcore.messages import ToolUseBlock

from .accounts import AccountStore
from .bot.channel import ZaloBotChannel, channel_name
from .bot.client import BotApiClient, tao_zalo_bot_client
from .models import AccountConfig, ChannelKind

SYNC_EVERY_S: Final = 15.0
HOOK_PREFIX: Final = "/v1/hooks/zalo"

LUAT_KENH_BOT: Final = (
    "Bạn đang trả lời qua TÀI KHOẢN BOT của Zalo. Kênh này chỉ hiện chữ thường (không in đậm, không tiêu đề) "
    "và mỗi tin tối đa 2000 ký tự. Kênh này KHÔNG gửi được file, tài liệu, ảnh tự tạo, video, không thả được "
    "cảm xúc, không tag được ai trong nhóm và không xem được thành viên nhóm - đó là giới hạn của nền tảng "
    "Zalo, KHÔNG phải bạn bị lỗi. Ai nhờ mấy việc đó thì nói thẳng là tài khoản bot không làm được."
)
"""Hiding a tool is not enough: told why, the model states the real cause instead of looking broken."""

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Running:
    channel: ZaloBotChannel
    dispose: Disposer
    token_digest: str


class ZaloPlugin:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        bot_client: Callable[[str], BotApiClient] = tao_zalo_bot_client,
    ) -> None:
        self._ctx = ctx
        self.store = AccountStore(ctx.storage, encrypt=ctx.encrypt, decrypt=ctx.decrypt)
        self.bot_client = bot_client
        self._bots: dict[str, _Running] = {}
        self._accounts: dict[str, AccountConfig] = {}
        """Every account by its channel name, as of the last ``sync``."""
        self._lock = asyncio.Lock()

    def register(self) -> None:
        ctx = self._ctx
        ctx.register_prompt_section(TurnSection("zalo_channel", self._channel_rules))
        ctx.register_hook(PreToolHook("zalo_disabled_tools", self._tool_allowed))
        ctx.register_job("accounts", self._keep_in_sync)
        ctx.on_disable(self._forget)

    async def sync(self) -> None:
        async with self._lock:
            accounts = {account.id: account for account in await self.store.list()}
            self._accounts = {channel_name(a.id): a for a in accounts.values()}
            for account_id, run in list(self._bots.items()):
                account = accounts.get(account_id)
                token = await self._bot_token(account)
                if token is None or _digest(token) != run.token_digest:
                    self._drop(account_id)
                elif account is not None:
                    run.channel.account = account
            for account_id, account in accounts.items():
                if account_id in self._bots:
                    continue
                token = await self._bot_token(account)
                if token is not None:
                    self._start_bot(account, token)

    def running(self, account_id: str) -> bool:
        run = self._bots.get(account_id)
        return run is not None and run.channel.listening

    def bot_channel(self, account_id: str) -> ZaloBotChannel | None:
        run = self._bots.get(account_id)
        return None if run is None else run.channel

    async def _bot_token(self, account: AccountConfig | None) -> str | None:
        if account is None or not account.enabled or account.channel is not ChannelKind.ZALO_BOT:
            return None
        return await self.store.secret(account.id)

    def _start_bot(self, account: AccountConfig, token: str) -> None:
        config = self._ctx.config
        public_url = str(config.get("public_url") or "").rstrip("/")
        channel = ZaloBotChannel(
            account,
            token,
            client_factory=self.bot_client,
            webhook_url=f"{public_url}{HOOK_PREFIX}/bot/{account.id}" if public_url else None,
            poll_timeout_s=max(5, min(60, int(config.get("poll_timeout_s") or 30))),
        )
        try:
            dispose = self._ctx.register_channel(channel)
        except ValueError as err:
            logger.warning("Zalo account %s has no channel: %s", account.id, err)
            return
        self._bots[account.id] = _Running(channel, dispose, _digest(token))
        logger.info("Zalo bot account %s has its channel %s", account.id, channel.name)

    def _drop(self, account_id: str) -> None:
        run = self._bots.pop(account_id)
        run.dispose()
        logger.info("Zalo bot account %s lost its channel", account_id)

    def _forget(self) -> None:
        self._bots.clear()
        self._accounts.clear()

    async def _keep_in_sync(self) -> None:
        while True:
            try:
                await self.sync()
            except Exception as err:  # the next round tries again
                logger.warning("Zalo accounts could not be synced (%s)", type(err).__name__)
            await asyncio.sleep(SYNC_EVERY_S)

    def _channel_rules(self, env: PromptEnv, turn: TurnInfo) -> str | None:
        account = self._accounts.get(turn.channel or "")
        if account is None or account.channel is not ChannelKind.ZALO_BOT:
            return None
        return LUAT_KENH_BOT

    async def _tool_allowed(self, use: ToolUseBlock, spec: Any, hook: HookContext) -> ToolDecision:
        account = self._accounts.get(hook.channel or "")
        if account is not None and use.name in account.disabled_tools:
            return Deny(f"the tool {use.name} is switched off for the Zalo account {account.id}")
        return ALLOW


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

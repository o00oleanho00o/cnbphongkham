"""The plugin at run time: keeps one channel per Zalo account that can run, in step with the stored accounts,
and the Node bridge running while a personal account needs it.

``sync`` compares the accounts with the channels:

* a bot account gets a channel when it is enabled and has a token; a new token restarts it;
* a personal account gets one when it is enabled, logged in (a stored credential), not locked out (``state``
  ``logged_out``, ``session_dead``, ``blocked`` wait for a new QR scan) and the bridge runs; a new credential
  or a new bridge process restarts it;
* everything else loses its channel; a settings change reaches the running channel without a restart.

The admin routes call it after each change; a background job calls it every ``SYNC_EVERY_S`` so a change
made through another process arrives too.

Known limit: every process of the service that runs the plugin polls the same bot and starts its own bridge.
Run the plugin's channels in one process (``agent serve``) until a lease is added.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from agent_app.plugins import Disposer, PluginContext
from agentcore import PromptEnv, TurnInfo, TurnSection
from agentcore.harness.hooks import ALLOW, Deny, HookContext, PreToolHook, ToolDecision
from agentcore.messages import ToolUseBlock

from .accounts import AccountStore
from .bot.channel import ZaloBotChannel, channel_name
from .bot.client import BotApiClient, tao_zalo_bot_client
from .models import AccountConfig, ChannelKind
from .personal.channel import ZaloPersonalChannel
from .personal.client import BridgeClient
from .personal.supervisor import BridgeSupervisor

SYNC_EVERY_S: Final = 15.0
HOOK_PREFIX: Final = "/v1/hooks/zalo"
LOCKED_OUT: Final = frozenset({"logged_out", "session_dead", "blocked"})
"""Bridge states after which a personal account waits for a new QR scan."""

LUAT_KENH_BOT: Final = (
    "Bạn đang trả lời qua TÀI KHOẢN BOT của Zalo. Kênh này chỉ hiện chữ thường (không in đậm, không tiêu đề) "
    "và mỗi tin tối đa 2000 ký tự. Kênh này KHÔNG gửi được file, tài liệu, ảnh tự tạo, video, không thả được "
    "cảm xúc, không tag được ai trong nhóm và không xem được thành viên nhóm - đó là giới hạn của nền tảng "
    "Zalo, KHÔNG phải bạn bị lỗi. Ai nhờ mấy việc đó thì nói thẳng là tài khoản bot không làm được."
)
"""Hiding a tool is not enough: told why, the model states the real cause instead of looking broken."""

logger = logging.getLogger(__name__)

Channel = ZaloBotChannel | ZaloPersonalChannel


@dataclass(slots=True)
class _Running:
    channel: Channel
    dispose: Disposer
    digest: str
    """What the channel was started with (token, credential, bridge run); a change restarts it."""


class ZaloPlugin:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        bot_client: Callable[[str], BotApiClient] = tao_zalo_bot_client,
        bridge: BridgeClient | None = None,
    ) -> None:
        self._ctx = ctx
        self.store = AccountStore(ctx.storage, encrypt=ctx.encrypt, decrypt=ctx.decrypt)
        self.bot_client = bot_client
        self.bridge = BridgeSupervisor(
            lambda: ctx.data_dir, self_url=lambda: ctx.self_url, on_restart=self._soon_sync, external=bridge
        )
        self._channels: dict[str, _Running] = {}
        self._accounts: dict[str, AccountConfig] = {}
        """Every account by its channel name, as of the last ``sync``."""
        self._states: dict[str, str] = {}
        """The bridge's last word on each personal account (``connected``, ``logged_out`` ...)."""
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._install: asyncio.Task[None] | None = None

    def register(self) -> None:
        ctx = self._ctx
        ctx.register_prompt_section(TurnSection("zalo_channel", self._channel_rules))
        ctx.register_hook(PreToolHook("zalo_disabled_tools", self._tool_allowed))
        ctx.register_job("accounts", self._keep_in_sync)
        ctx.register_job("bridge", lambda: self.bridge.keep_running(self._bridge_wanted))
        ctx.on_disable(self._forget)

    # --- channels ---

    async def sync(self) -> None:
        async with self._lock:
            accounts = {account.id: account for account in await self.store.list()}
            self._accounts = {channel_name(a.id): a for a in accounts.values()}
            self._states = {a.id: state for a in accounts.values() if (state := await self.store.state(a.id))}
            for account_id, run in list(self._channels.items()):
                account = accounts.get(account_id)
                wanted = await self._wanted(account)
                if wanted is None or wanted[1] != run.digest:
                    self._drop(account_id)
                elif account is not None:
                    run.channel.account = account
            for account_id, account in accounts.items():
                if account_id in self._channels:
                    continue
                wanted = await self._wanted(account)
                if wanted is not None:
                    self._start(account, *wanted)

    def running(self, account_id: str) -> bool:
        run = self._channels.get(account_id)
        return run is not None and run.channel.listening

    def state(self, account_id: str) -> str | None:
        return self._states.get(account_id)

    def bot_channel(self, account_id: str) -> ZaloBotChannel | None:
        run = self._channels.get(account_id)
        return run.channel if run is not None and isinstance(run.channel, ZaloBotChannel) else None

    def personal_channel(self, account_id: str) -> ZaloPersonalChannel | None:
        run = self._channels.get(account_id)
        return run.channel if run is not None and isinstance(run.channel, ZaloPersonalChannel) else None

    async def _wanted(self, account: AccountConfig | None) -> tuple[str, str] | None:
        """The secret to start the account's channel with and what it depends on; None when it should not
        run."""
        if account is None or not account.enabled or account.channel is ChannelKind.ZALO_OA:
            return None
        if account.channel is ChannelKind.ZALO_PERSONAL and (
            self.bridge.client is None or self._states.get(account.id) in LOCKED_OUT
        ):
            return None
        secret = await self.store.secret(account.id)
        if secret is None:
            return None
        if account.channel is ChannelKind.ZALO_PERSONAL:
            return secret, f"{self.bridge.generation}:{_digest(secret)}"
        return secret, _digest(secret)

    def _start(self, account: AccountConfig, secret: str, digest: str) -> None:
        config = self._ctx.config
        channel: Channel
        if account.channel is ChannelKind.ZALO_BOT:
            public_url = str(config.get("public_url") or "").rstrip("/")
            channel = ZaloBotChannel(
                account,
                secret,
                client_factory=self.bot_client,
                webhook_url=f"{public_url}{HOOK_PREFIX}/bot/{account.id}" if public_url else None,
                poll_timeout_s=max(5, min(60, int(config.get("poll_timeout_s") or 30))),
            )
        else:
            channel = ZaloPersonalChannel(
                account,
                bridge=lambda: self.bridge.client,
                store=self.store,
                rich_text=bool(config.get("rich_text", True)),
                generation=self.bridge.generation,
            )
        try:
            dispose = self._ctx.register_channel(channel)
        except ValueError as err:
            logger.warning("Zalo account %s has no channel: %s", account.id, err)
            return
        self._channels[account.id] = _Running(channel, dispose, digest)
        logger.info("Zalo account %s has its channel %s", account.id, channel.name)

    def _drop(self, account_id: str) -> None:
        run = self._channels.pop(account_id)
        run.dispose()
        logger.info("Zalo account %s lost its channel", account_id)

    def _forget(self) -> None:
        self._channels.clear()
        self._accounts.clear()
        if self._install is not None:
            self._install.cancel()

    async def _keep_in_sync(self) -> None:
        while True:
            try:
                await self.sync()
            except Exception as err:  # the next round tries again
                logger.warning("Zalo accounts could not be synced (%s)", type(err).__name__)
            await asyncio.sleep(SYNC_EVERY_S)

    def _soon_sync(self) -> None:
        task = asyncio.get_running_loop().create_task(self.sync(), name="zalo sync")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- the bridge ---

    def _bridge_wanted(self) -> bool:
        return any(a.enabled and a.channel is ChannelKind.ZALO_PERSONAL for a in self._accounts.values())

    def start_install(self) -> bool:
        """Starts installing the bridge in the background; False when an install already runs."""
        if self._install is not None and not self._install.done():
            return False

        async def install() -> None:
            try:
                await self.bridge.install()
            except ValueError as err:
                logger.warning("Zalo bridge install failed: %s", err)

        self._install = asyncio.get_running_loop().create_task(install(), name="zalo bridge install")
        return True

    async def bridge_event(self, account_id: str, payload: Mapping[str, Any]) -> None:
        """One signed event of the bridge. Logs ids and kinds only: messages carry personal content and
        ``credential_updated`` a secret."""
        kind = payload.get("type")
        if kind == "message":
            channel = self.personal_channel(account_id)
            message = payload.get("message")
            if channel is None or not isinstance(message, Mapping):
                logger.warning(
                    "a message for personal account %s, which is not running, was dropped", account_id
                )
                return
            await channel.handle(cast(Mapping[str, Any], message))
        elif kind == "credential_updated":
            credential = payload.get("credential")
            if not isinstance(credential, Mapping) or not credential:
                logger.warning("credential_updated without a credential for %s", account_id)
                return
            if await self.store.get(account_id) is None:
                return
            await self.store.set_secret(account_id, json.dumps(credential))
            await self.store.set_state(account_id, None)
            logger.info("the login of personal account %s was stored (sealed)", account_id)
            await self.sync()
        elif kind == "account_state":
            state = str(payload.get("state", ""))
            if state in LOCKED_OUT:
                await self.store.set_state(account_id, state)
                logger.warning("personal account %s is %s: it needs a new QR scan", account_id, state)
            elif state in ("connected", "disconnected"):
                self._states[account_id] = state
            await self.sync()
        else:
            logger.debug("bridge event %s for %s ignored", kind, account_id)

    # --- what the model is told and may use ---

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


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

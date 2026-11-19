"""The service at run time: keeps one channel per Zalo account that can run, in step with the stored accounts,
and the Bun bridge running while a personal account needs it. Was ``plugin.py`` of the agent's Zalo plugin;
what it asked of the agent's plugin context now goes through ``AgentClient`` (registration, inbound traffic)
or the service's own config and store.

``sync`` compares the accounts with the channels:

* a bot account gets a channel when it is enabled and has a token; a new token restarts it;
* a personal account gets one when it is enabled, logged in (a stored credential), not locked out (``state``
  ``logged_out``, ``session_dead``, ``blocked`` wait for a new QR scan) and the bridge runs; a new credential
  or a new bridge process restarts it;
* everything else loses its channel; a settings change reaches the running channel without a restart.

A channel is registered with the agent (name, rules, disabled tools) as soon as it exists and unregistered when
it is dropped. Its ``start`` (token check, webhook or polling, the bridge login) runs apart from ``sync``: a
channel that cannot start is tried again every ``START_RETRY_S``.

The admin routes call ``sync`` after each change; a background job calls it every ``SYNC_EVERY_S`` so a change
made through another process arrives too.

Known limit: every process of this service polls the same bot and starts its own bridge. Run one.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final, cast

from .access import keeps_chat
from .accounts import AccountStore
from .agent_client import AgentClient
from .bot.channel import ZaloBotChannel, channel_name
from .bot.client import BotApiClient, tao_zalo_bot_client
from .channels import InboundMessage, Receive
from .config import Config
from .contacts import ContactBook, GroupNames, group_name
from .inbound import ZaloInbound
from .models import AccountConfig, ChannelKind
from .personal.channel import ECHO_WAIT_S, ZaloPersonalChannel
from .personal.client import BridgeAccountApi, BridgeClient
from .personal.friends import SWEEP_EVERY_S, FriendRequests, auto_accept_round, handle_friend_event
from .personal.supervisor import BridgeSupervisor
from .seal import Seal
from .store import Store

SYNC_EVERY_S: Final = 15.0
START_TIMEOUT_S: Final = 30.0
START_RETRY_S: Final = 30.0
HOOK_PREFIX: Final = "/v1/hooks/zalo"
LOCKED_OUT: Final = frozenset({"logged_out", "session_dead", "blocked"})
"""Bridge states after which a personal account waits for a new QR scan."""

LUAT_KENH_BOT: Final = (
    "Bạn đang trả lời qua TÀI KHOẢN BOT của Zalo. Kênh này chỉ hiện chữ thường (không in đậm, không tiêu đề) "
    "và mỗi tin tối đa 2000 ký tự. Kênh này KHÔNG gửi được file, tài liệu, ảnh tự tạo, video, không thả được "
    "cảm xúc, không tag được ai trong nhóm và không xem được thành viên nhóm - đó là giới hạn của nền tảng "
    "Zalo, KHÔNG phải bạn bị lỗi. Ai nhờ mấy việc đó thì nói thẳng là tài khoản bot không làm được."
)
"""Hiding a tool is not enough: told why, the model states the real cause instead of looking broken. Sent to the
agent as the ``rules`` of a bot channel."""

logger = logging.getLogger(__name__)

Channel = ZaloBotChannel | ZaloPersonalChannel


@dataclass(slots=True)
class _Running:
    channel: Channel
    digest: str
    """What the channel was started with (token, credential, bridge run); a change restarts it."""
    started: bool = False
    error: str | None = None
    retry_at: float = 0.0


class ZaloService:
    def __init__(
        self,
        config: Config,
        store: Store,
        seal: Seal,
        agent: AgentClient,
        *,
        bot_client: Callable[[str], BotApiClient] = tao_zalo_bot_client,
        bridge: BridgeClient | None = None,
    ) -> None:
        self._config = config
        self._agent = agent
        self.store = AccountStore(store, encrypt=seal.encrypt, decrypt=seal.decrypt)
        self.contacts = ContactBook(store)
        self.groups = GroupNames(store)
        self.friend_requests = FriendRequests(store)
        self.bot_client = bot_client
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.bridge = BridgeSupervisor(
            lambda: config.data_dir,
            self_url=lambda: f"http://127.0.0.1:{config.port}",
            on_restart=self._soon_sync,
            external=bridge,
            bundled=config.bridge_dir,
        )
        self._channels: dict[str, _Running] = {}
        self._accounts: dict[str, AccountConfig] = {}
        """Every account by its channel name, as of the last ``sync``."""
        self._states: dict[str, str] = {}
        """The bridge's last word on each personal account (``connected``, ``logged_out`` ...)."""
        self._lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._jobs: list[asyncio.Task[None]] = []
        self._install: asyncio.Task[None] | None = None
        self._groups_asked: set[tuple[str, str]] = set()
        """Groups whose name was looked up (or is being) by this process."""

    def start(self) -> None:
        """The three jobs of the old plugin: sync the accounts, keep the bridge running, auto-accept friends."""
        loop = asyncio.get_running_loop()
        self._jobs = [
            loop.create_task(self._keep_in_sync(), name="zalo accounts"),
            loop.create_task(self.bridge.keep_running(self._bridge_wanted), name="zalo bridge"),
            loop.create_task(self._keep_accepting(), name="zalo friend auto-accept"),
        ]

    async def close(self) -> None:
        for job in [*self._jobs, *self._tasks]:
            job.cancel()
        await asyncio.gather(*self._jobs, *self._tasks, return_exceptions=True)
        if self._install is not None:
            self._install.cancel()
        for account_id in list(self._channels):
            await self._drop(account_id, unregister=False)

    # --- channels ---

    async def sync(self) -> None:
        async with self._lock:
            accounts = {account.id: account for account in await self.store.list()}
            for name in set(self._accounts) - {channel_name(a.id) for a in accounts.values()}:
                await self._agent.forget_channel(name)  # the account is gone: what it heard is not pushed
            self._accounts = {channel_name(a.id): a for a in accounts.values()}
            self._states = {a.id: state for a in accounts.values() if (state := await self.store.state(a.id))}
            for account_id, run in list(self._channels.items()):
                account = accounts.get(account_id)
                wanted = await self._wanted(account)
                if wanted is None or wanted[1] != run.digest:
                    await self._drop(account_id)
                elif account is not None:
                    run.channel.account = account
                    self._announce(run.channel)
            for account_id, account in accounts.items():
                if account_id in self._channels:
                    continue
                wanted = await self._wanted(account)
                if wanted is not None:
                    self._create(account, *wanted)
        self._background(self._start_pending(), "zalo start")

    def running(self, account_id: str) -> bool:
        run = self._channels.get(account_id)
        return run is not None and run.channel.listening

    def state(self, account_id: str) -> str | None:
        return self._states.get(account_id)

    def channel_state(self, channel: str) -> tuple[bool, Channel | None]:
        """(the account of this channel name exists, its channel when it is running)."""
        account = self._accounts.get(channel)
        if account is None:
            return False, None
        run = self._channels.get(account.id)
        return True, run.channel if run is not None and run.channel.listening else None

    def bot_channel(self, account_id: str) -> ZaloBotChannel | None:
        run = self._channels.get(account_id)
        return run.channel if run is not None and isinstance(run.channel, ZaloBotChannel) else None

    def personal_channel(self, account_id: str) -> ZaloPersonalChannel | None:
        run = self._channels.get(account_id)
        return run.channel if run is not None and isinstance(run.channel, ZaloPersonalChannel) else None

    def personal_api(self, account_id: str) -> BridgeAccountApi | None:
        """The personal account on the bridge while its channel runs."""
        channel = self.personal_channel(account_id)
        return None if channel is None else channel.api

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

    def _create(self, account: AccountConfig, secret: str, digest: str) -> None:
        config = self._config
        channel: Channel
        if account.channel is ChannelKind.ZALO_BOT:
            channel = ZaloBotChannel(
                account,
                secret,
                client_factory=self.bot_client,
                webhook_url=f"{config.public_url}{HOOK_PREFIX}/bot/{account.id}" if config.public_url else None,
                poll_timeout_s=config.poll_timeout_s,
                heard=self._heard,
                observe=self._agent.observed,
            )
        else:
            channel = ZaloPersonalChannel(
                account,
                bridge=lambda: self.bridge.client,
                store=self.store,
                rich_text=config.rich_text,
                generation=self.bridge.generation,
                heard=self._heard,
                observe=self._agent.observed,
                echo_wait_s=ECHO_WAIT_S,
            )
            channel.on_typing(lambda conversation_id, name=channel.name: self._agent.typing(name, conversation_id))
        self._channels[account.id] = _Running(channel, digest)
        self._announce(channel)
        logger.info("Zalo account %s has its channel %s", account.id, channel.name)

    def _announce(self, channel: Channel) -> None:
        """Registers the channel with the agent, or updates it: the rules the model gets on every turn, the
        tools this account switches off (the old ``zalo_disabled_tools`` hook), whether it may write markdown."""
        account = channel.account
        self._agent.set_channel(
            channel.name,
            rules=LUAT_KENH_BOT if account.channel is ChannelKind.ZALO_BOT else "",
            disabled_tools=list(account.disabled_tools),
            markdown=channel.capabilities.markdown,
        )

    async def _drop(self, account_id: str, *, unregister: bool = True) -> None:
        run = self._channels.pop(account_id)
        if unregister:
            self._agent.remove_channel(run.channel.name)
        try:
            if run.started:
                await asyncio.wait_for(run.channel.stop(), START_TIMEOUT_S)
        except Exception as err:  # it is gone either way
            logger.warning("Zalo account %s did not stop cleanly (%s)", account_id, type(err).__name__)
        logger.info("Zalo account %s lost its channel", account_id)

    async def _start_pending(self) -> None:
        """Starts the channels that are not running yet; a failure is kept and tried again later, and never
        stops the others."""
        async with self._start_lock:
            for account_id, run in list(self._channels.items()):
                if run.started or time.monotonic() < run.retry_at:
                    continue
                try:
                    await asyncio.wait_for(run.channel.start(self._receiver(run.channel.name)), START_TIMEOUT_S)
                except Exception as err:
                    run.error = f"{type(err).__name__}: {err}"[:300]
                    run.retry_at = time.monotonic() + START_RETRY_S
                    logger.warning("channel %s did not start (%s)", run.channel.name, type(err).__name__)
                    continue
                if self._channels.get(account_id) is not run:  # dropped while it started
                    await run.channel.stop()
                    continue
                run.started, run.error = True, None
                logger.info("channel %s started", run.channel.name)

    def _receiver(self, name: str) -> Receive:
        async def receive(inbound: InboundMessage) -> None:
            # A channel speaks only for itself: the one that heard the message names it.
            await self._agent.inbound(replace(inbound, channel=name))

        return receive

    async def _keep_in_sync(self) -> None:
        while True:
            try:
                await self.sync()
            except Exception as err:  # the next round tries again
                logger.warning("Zalo accounts could not be synced (%s)", type(err).__name__)
            await asyncio.sleep(SYNC_EVERY_S)

    def _soon_sync(self) -> None:
        self._background(self.sync(), "zalo sync")

    def _background(self, work: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.get_running_loop().create_task(work, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- address book and friends ---

    async def _heard(self, msg: ZaloInbound) -> None:
        """Every message from someone else: the sender goes into the address book, and the name of a group
        a personal account sees for the first time is looked up (so the group can be offered in the list to
        listen to). The sender of a group the account does not listen to is not kept. A failure here never
        costs the message."""
        account = self._accounts.get(channel_name(msg.account_id))
        if account is None or keeps_chat(account, thread_id=msg.thread_id, is_group=msg.is_group):
            try:
                await self.contacts.record(msg.account_id, msg.sender_id, msg.sender_name, datetime.now(UTC))
            except Exception as err:  # the storage's own errors included
                logger.warning("Zalo account %s: no contact kept (%s)", msg.account_id, type(err).__name__)
        key = (msg.account_id, msg.thread_id)
        if msg.is_group and key not in self._groups_asked and self.personal_api(msg.account_id) is not None:
            self._groups_asked.add(key)
            self._background(self._name_group(*key), "zalo group name")

    async def _name_group(self, account_id: str, thread_id: str) -> None:
        api = self.personal_api(account_id)
        try:
            if api is None or await self.groups.get(account_id, thread_id) is not None:
                return
            name = group_name(await api.get_group_info(thread_id), thread_id)
            if name is not None:
                await self.groups.set(account_id, thread_id, name)
        except Exception as err:  # the bridge's and the storage's errors
            self._groups_asked.discard((account_id, thread_id))  # asked again on its next message
            logger.debug("personal account %s: group name not found (%s)", account_id, type(err).__name__)

    async def _friend_event(self, account_id: str, event: Mapping[str, Any]) -> None:
        if await self.store.get(account_id) is None:
            return
        api = self.personal_api(account_id)
        await handle_friend_event(
            self.friend_requests,
            account_id,
            event,
            user_info=None if api is None else api.get_user_info,
            now=datetime.now(UTC),
        )

    async def _keep_accepting(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_EVERY_S)
            running = [
                (account, api)
                for account in self._accounts.values()
                if (api := self.personal_api(account.id)) is not None
            ]
            try:
                await auto_accept_round(self.friend_requests, running, datetime.now(UTC))
            except Exception as err:  # the next round tries again
                logger.warning("Zalo friend auto-accept round failed (%s)", type(err).__name__)

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
        elif kind == "typing":
            typing_channel = self.personal_channel(account_id)
            if typing_channel is not None:
                typing_channel.handle_typing(payload)
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
        elif kind == "friend_event":
            event = payload.get("event")
            if isinstance(event, Mapping):
                await self._friend_event(account_id, cast(Mapping[str, Any], event))
        else:
            logger.debug("bridge event %s for %s ignored", kind, account_id)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

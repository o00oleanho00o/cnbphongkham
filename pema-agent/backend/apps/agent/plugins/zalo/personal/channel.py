# ported from: src/zalo/kenh-ca-nhan.ts, src/zalo/account-manager.ts (start/attach),
# src/zalo/send-reply-in-parts.ts
"""One personal Zalo account as a channel of the agent, through the Node bridge.

Starting attaches to a session the bridge already holds (the QR login just ended, or another start did it):
every Zalo login is a risk of a lock, so it logs in with the stored credential only when there is no live
session. Replies keep Zalo rich text (bold, italic, headings, lists) when the plugin's ``rich_text`` is on;
when the Zalo server refuses a message with styles, it is sent again without them.

zca-js is UNOFFICIAL: the account can be locked. Use a secondary account.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any, Final

from agentcore.channels import ChannelCapabilities, ChannelSendError, OutboundMessage, Receive

from ..access import should_respond
from ..accounts import AccountStore
from ..format.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from ..inbound import THREAD_GROUP, to_inbound
from ..models import AccountConfig
from .client import BridgeAccountApi, BridgeClient, ThreadKind, ZaloBridgeError
from .parser import parse_incoming_message

MAX_TEXT_CHARS: Final = 2000
RETRYABLE_KINDS: Final = frozenset({"transport", "rate_limited", "not_running"})

logger = logging.getLogger(__name__)


class ZaloPersonalChannel:
    def __init__(
        self,
        account: AccountConfig,
        *,
        bridge: Callable[[], BridgeClient | None],
        store: AccountStore,
        rich_text: bool,
        generation: int,
    ) -> None:
        self.name = f"zalo-{account.id}"
        self.account = account
        """Replaced by the plugin when the settings change; read on every message."""
        self.capabilities = ChannelCapabilities(max_text_chars=MAX_TEXT_CHARS, markdown=rich_text)
        self.generation = generation
        """The bridge run this channel was started on."""
        self.listening = False
        self._bridge = bridge
        self._store = store
        self._rich_text = rich_text
        self._api: BridgeAccountApi | None = None
        self._receive: Receive | None = None

    @property
    def own_id(self) -> str:
        return "" if self._api is None else self._api.own_id

    async def start(self, receive: Receive) -> None:
        client = self._bridge()
        if client is None:
            raise RuntimeError("the Zalo bridge is not running (install it, or wait for it to start)")
        account_id = self.account.id
        state = await client.get_state(account_id)
        if state.state == "connected" and state.own_id:
            own_id = state.own_id
        else:
            stored = await self._store.secret(account_id)
            if stored is None:
                raise RuntimeError("not logged in: scan the QR code of this account")
            own_id = await client.start_account(account_id, json.loads(stored))
        self._api = client.account(account_id, own_id)
        self._receive = receive
        self.listening = True

    async def stop(self) -> None:
        self.listening = False
        self._api = None
        client = self._bridge()
        if client is None:
            return
        try:
            await client.stop_account(self.account.id)
        except ZaloBridgeError as err:
            logger.info("personal account %s: stop refused (%s)", self.account.id, err.kind)

    async def handle(self, message: Mapping[str, Any]) -> None:
        """One ``message`` event of the bridge: filtered, then handed to the agent."""
        receive = self._receive
        if receive is None or not self.listening:
            return
        msg = parse_incoming_message(self.account.id, self.own_id, message)
        if not msg.thread_id or not msg.sender_id or not msg.message_id:
            logger.warning("personal account %s: a message without ids was dropped", self.account.id)
            return
        decision = should_respond(self.account, msg)
        if not decision.respond:
            logger.debug("personal account %s: not answered (%s)", self.account.id, decision.reason)
            return
        await receive(to_inbound(msg))

    def prepare(self, text: str) -> str | None:
        cleaned = lam_sach_theo_cau_hinh(text, rich_text=self._rich_text)
        if cleaned.chan:
            logger.error(
                "personal account %s: a reply that leaks the system prompt was not sent", self.account.id
            )
            return None
        return cleaned.text

    async def send(self, message: OutboundMessage) -> None:
        api = self._api
        if api is None:
            raise ChannelSendError("the account is not running")
        kind = ThreadKind.GROUP if message.metadata.get("thread_type") == THREAD_GROUP else ThreadKind.USER
        formatted = dinh_dang_neu_bat(message.text, rich_text=self._rich_text)
        try:
            await api.send_message(
                text=formatted.text,
                thread_id=message.conversation_id,
                thread_type=kind,
                styles=formatted.styles,
            )
        except ZaloBridgeError as err:
            if err.kind == "zalo_rejected" and formatted.styles:
                # The server answered and delivered nothing: the same words without styles are safe to send.
                logger.warning(
                    "personal account %s: styles refused (code %s); sent plain", self.account.id, err.code
                )
                await self._send_plain(api, formatted.text, message.conversation_id, kind)
                return
            raise ChannelSendError(str(err), retryable=err.kind in RETRYABLE_KINDS) from None

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None:
        api = self._api
        if api is not None and self.account.typing_indicator_enabled:
            kind = ThreadKind.GROUP if metadata.get("thread_type") == THREAD_GROUP else ThreadKind.USER
            await api.send_typing_event(conversation_id, kind)

    async def _send_plain(self, api: BridgeAccountApi, text: str, thread_id: str, kind: ThreadKind) -> None:
        try:
            await api.send_message(text=text, thread_id=thread_id, thread_type=kind)
        except ZaloBridgeError as err:
            raise ChannelSendError(str(err), retryable=err.kind in RETRYABLE_KINDS) from None

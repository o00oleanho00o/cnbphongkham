# ported from: src/zalo/kenh-ca-nhan.ts, src/zalo/account-manager.ts (start/attach),
# src/zalo/send-reply-in-parts.ts
"""One personal Zalo account as a channel of the agent, through the Bun bridge.

Starting attaches to a session the bridge already holds (the QR login just ended, or another start did it):
every Zalo login is a risk of a lock, so it logs in with the stored credential only when there is no live
session. Replies keep Zalo rich text (bold, italic, headings, lists) when the plugin's ``rich_text`` is on,
and in a group the first part quotes the message it answers; when the Zalo server refuses a message with
styles or a quote, it is sent again plain.

Like a real Zalo client the channel reports "delivered" for every message that arrives and "seen" for those
the agent takes up, and (if the account wants it) reacts to them with its icon. These are courtesies: they
run in the background and a failure is only logged.

zca-js is UNOFFICIAL: the account can be locked. Use a secondary account.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable, Coroutine, Mapping
from typing import Any, Final, cast

from ..channels import (
    PROACTIVE,
    ChannelCapabilities,
    ChannelSendError,
    Observe,
    OutboundMessage,
    Receive,
)

from ..access import keeps_chat, should_respond
from ..accounts import AccountStore
from ..format.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from ..inbound import THREAD_GROUP, Heard, ZaloInbound, to_inbound, to_observed
from ..models import AccountConfig
from ..reaction_icons import to_zalo_reaction
from .client import BridgeAccountApi, BridgeClient, ThreadKind, ZaloBridgeError
from .parser import parse_incoming_message
from .receipts import quote_from, receipt_params

MAX_TEXT_CHARS: Final = 2000
RETRYABLE_KINDS: Final = frozenset({"transport", "rate_limited", "not_running"})
ECHO_WAIT_S: Final = 3.0
"""How long a message the account itself sent waits before it is kept as the owner's: the agent's own
replies come back as the account's messages, and the answer to a send may arrive after its echo."""
SENT_REMEMBERED: Final = 400

QUOTE: Final = "quote"
"""Metadata key of the zca-js quote of a group message, as JSON; it comes back on the reply."""

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
        heard: Heard | None = None,
        observe: Observe | None = None,
        echo_wait_s: float = ECHO_WAIT_S,
    ) -> None:
        self.name = f"zalo-{account.id}"
        self.account = account
        """Replaced by the service when the settings change; read on every message."""
        self.capabilities = ChannelCapabilities(max_text_chars=MAX_TEXT_CHARS, markdown=rich_text)
        self.generation = generation
        """The bridge run this channel was started on."""
        self.listening = False
        self._bridge = bridge
        self._store = store
        self._rich_text = rich_text
        self._heard = heard
        self._observe = observe
        self._echo_wait_s = echo_wait_s
        self._sent: deque[tuple[str, str]] = deque(maxlen=SENT_REMEMBERED)
        """What this channel sent lately, as (message id, thread and text): the echoes to tell from the
        owner's own."""
        self._api: BridgeAccountApi | None = None
        self._receive: Receive | None = None
        self._typing: Callable[[str], None] | None = None
        self._courtesies: set[asyncio.Task[None]] = set()

    @property
    def own_id(self) -> str:
        return "" if self._api is None else self._api.own_id

    @property
    def api(self) -> BridgeAccountApi | None:
        """The account on the bridge while the channel runs (friends, profiles, groups)."""
        return self._api

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
        for task in list(self._courtesies):
            task.cancel()
        client = self._bridge()
        if client is None:
            return
        try:
            await client.stop_account(self.account.id)
        except ZaloBridgeError as err:
            logger.info("personal account %s: stop refused (%s)", self.account.id, err.kind)

    def on_typing(self, notify: Callable[[str], None]) -> None:
        """Where the channel hub wants to hear that a person is typing (``ReportsTyping``)."""
        self._typing = notify

    def handle_typing(self, event: Mapping[str, Any]) -> None:
        """One ``typing`` event of the bridge. Only a person of a one-to-one chat counts; the agent just waits
        a little longer for their next message, so nothing else is checked."""
        notify = self._typing
        thread_id = event.get("thread_id")
        if notify is None or not self.listening or event.get("is_group") is not False:
            return
        if isinstance(thread_id, str) and thread_id and thread_id != self.own_id:
            notify(thread_id)

    async def handle(self, message: Mapping[str, Any]) -> None:
        """One ``message`` event of the bridge: filtered, then handed to the agent."""
        receive = self._receive
        api = self._api
        if receive is None or api is None or not self.listening:
            return
        msg = parse_incoming_message(self.account.id, self.own_id, message)
        if not msg.thread_id or not msg.sender_id or not msg.message_id:
            logger.warning("personal account %s: a message without ids was dropped", self.account.id)
            return
        if msg.is_self:
            self._courtesy(self._owner_wrote(msg))
        else:
            self._courtesy(self._delivered(api, msg))
            if self._heard is not None:
                await self._heard(msg)
        decision = should_respond(self.account, msg)
        if not msg.is_self:
            await self._tell(msg, answered=decision.respond)
        if not decision.respond:
            logger.debug("personal account %s: not answered (%s)", self.account.id, decision.reason)
            return
        quote = quote_from(msg.raw, is_group=msg.is_group)
        await receive(
            to_inbound(
                msg,
                {QUOTE: json.dumps(quote, ensure_ascii=False)} if quote else None,
                observe=keeps_chat(self.account, thread_id=msg.thread_id, is_group=msg.is_group),
            )
        )
        self._courtesy(self._seen(api, msg))
        if self.account.auto_react_enabled:
            self._courtesy(self._react(api, msg))

    async def _tell(self, msg: ZaloInbound, *, answered: bool) -> None:
        if self._observe is None:
            return
        if not keeps_chat(self.account, thread_id=msg.thread_id, is_group=msg.is_group):
            return
        observed = to_observed(self.name, msg, answered=answered)
        if observed is not None:
            await self._observe(observed)

    async def _owner_wrote(self, msg: ZaloInbound) -> None:
        """A message of the account itself: the owner typed it on another device, or it is the echo of
        what the agent sent. Told to the plugins that listen only in the first case."""
        if self._observe is None:
            return
        await asyncio.sleep(self._echo_wait_s)
        if self._is_echo(msg):
            return
        await self._tell(msg, answered=False)

    def _is_echo(self, msg: ZaloInbound) -> bool:
        text = msg.text.strip()
        key = _sent_key(msg.thread_id, text)
        return any(sent_id == msg.message_id or sent_key == key for sent_id, sent_key in self._sent)

    def _remember_sent(self, answer: Mapping[str, Any], thread_id: str, text: str) -> None:
        self._sent.append((str(answer.get("msg_id") or ""), _sent_key(thread_id, text)))

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
        # Only the first part quotes: the quote says which message the whole reply answers.
        quote = _quote(message.metadata) if message.part == 1 and kind is ThreadKind.GROUP else None
        proactive = message.metadata.get(PROACTIVE) == "1"
        try:
            answer = await api.send_message(
                text=formatted.text,
                thread_id=message.conversation_id,
                thread_type=kind,
                styles=formatted.styles,
                quote=quote,
                proactive=proactive,
            )
            self._remember_sent(answer, message.conversation_id, formatted.text)
        except ZaloBridgeError as err:
            if err.kind == "zalo_rejected" and (formatted.styles or quote is not None):
                # The server answered and delivered nothing: the same words, plain, are safe to send.
                logger.warning(
                    "personal account %s: styles or quote refused (code %s); sent plain",
                    self.account.id,
                    err.code,
                )
                await self._send_plain(api, formatted.text, message.conversation_id, kind, proactive)
                return
            raise ChannelSendError(str(err), retryable=err.kind in RETRYABLE_KINDS) from None

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None:
        api = self._api
        if api is not None and self.account.typing_indicator_enabled:
            kind = ThreadKind.GROUP if metadata.get("thread_type") == THREAD_GROUP else ThreadKind.USER
            await api.send_typing_event(conversation_id, kind)

    async def _send_plain(
        self, api: BridgeAccountApi, text: str, thread_id: str, kind: ThreadKind, proactive: bool
    ) -> None:
        try:
            answer = await api.send_message(
                text=text, thread_id=thread_id, thread_type=kind, proactive=proactive
            )
            self._remember_sent(answer, thread_id, text)
        except ZaloBridgeError as err:
            raise ChannelSendError(str(err), retryable=err.kind in RETRYABLE_KINDS) from None

    def _courtesy(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work, name=f"zalo courtesy {self.account.id}")
        self._courtesies.add(task)
        task.add_done_callback(self._courtesies.discard)

    async def _delivered(self, api: BridgeAccountApi, msg: ZaloInbound) -> None:
        params = receipt_params(msg.raw)
        if params is None:
            return
        try:
            await api.send_delivered_event([params], _kind(msg))
        except ZaloBridgeError as err:
            logger.debug("personal account %s: delivered receipt failed (%s)", self.account.id, err.kind)

    async def _seen(self, api: BridgeAccountApi, msg: ZaloInbound) -> None:
        params = receipt_params(msg.raw)
        if params is None:
            return
        try:
            await api.send_seen_event([params], _kind(msg))
        except ZaloBridgeError as err:
            logger.debug("personal account %s: seen receipt failed (%s)", self.account.id, err.kind)

    async def _react(self, api: BridgeAccountApi, msg: ZaloInbound) -> None:
        msg_id = str(msg.raw.get("msgId") or "")
        if not msg_id:
            return
        try:
            await api.add_reaction(
                to_zalo_reaction(self.account.auto_react_icon),
                msg_id=msg_id,
                cli_msg_id=str(msg.raw.get("cliMsgId") or msg_id),
                thread_id=msg.thread_id,
                thread_type=_kind(msg),
            )
        except ZaloBridgeError as err:
            logger.debug("personal account %s: auto-react failed (%s)", self.account.id, err.kind)


def _sent_key(thread_id: str, text: str) -> str:
    return f"{thread_id}|{text.strip()}"


def _kind(msg: ZaloInbound) -> ThreadKind:
    return ThreadKind.GROUP if msg.is_group else ThreadKind.USER


def _quote(metadata: Mapping[str, str]) -> dict[str, Any] | None:
    raw = metadata.get(QUOTE)
    if not raw:
        return None
    try:
        quote = json.loads(raw)
    except ValueError:
        return None
    return cast(dict[str, Any], quote) if isinstance(quote, dict) else None

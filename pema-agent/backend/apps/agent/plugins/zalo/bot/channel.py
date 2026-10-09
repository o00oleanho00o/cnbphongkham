# ported from: src/zalo-bot/kenh-bot.ts, src/zalo-bot/zalo-bot-listener.ts, src/zalo-bot/bot-message-router.ts
"""One Zalo Bot account as a channel of the agent: it listens (long polling, or a webhook when the service has
a public address), filters who it answers, and sends the agent's replies as plain text.

What the Bot API cannot do, measured on the real API: no rich text (the reply is sent with ``parse_mode``
unset, markdown already stripped), no quoting, no reactions, no "seen" receipt, no files. ``getUpdates`` has
no ``offset``: a message taken off Zalo's queue is gone, so it goes to the agent (which stores it before it
runs) at once.

Polling, measured: an empty poll answers 408 and is not an error (poll again at once); hammering polls gets an
nginx 429, so every error retreats, doubling up to a minute; one update per call.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
from collections.abc import Awaitable, Callable, Mapping
from typing import Final

from agentcore.channels import ChannelCapabilities, ChannelSendError, OutboundMessage, Receive

from ..access import should_respond
from ..format.prepare_outgoing_text import lam_sach_theo_cau_hinh
from ..inbound import to_inbound
from ..models import AccountConfig
from .client import BotApiClient, LoiZaloBotApi
from .parser import parse_update
from .types import TRAN_KY_TU_MOT_TIN, ZaloBotUpdate

WEBHOOK_SECRET_HEADER: Final = "x-bot-api-secret-token"  # noqa: S105 - a header name, not a secret

logger = logging.getLogger(__name__)


def channel_name(account_id: str) -> str:
    return f"zalo-{account_id}"


class ZaloBotChannel:
    def __init__(
        self,
        account: AccountConfig,
        token: str,
        *,
        client_factory: Callable[[str], BotApiClient],
        webhook_url: str | None = None,
        poll_timeout_s: int = 30,
        backoff_s: tuple[float, float] = (2.0, 60.0),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.name = channel_name(account.id)
        self.account = account
        """Replaced by the plugin when the settings change; read on every message."""
        self.capabilities = ChannelCapabilities(max_text_chars=TRAN_KY_TU_MOT_TIN, markdown=False)
        self.bot_name = ""
        self.listening = False
        self._token = token
        self._client_factory = client_factory
        self._webhook_url = webhook_url
        self._poll_timeout_s = poll_timeout_s
        self._backoff_s = backoff_s
        self._sleep = sleep
        self._client: BotApiClient | None = None
        self._receive: Receive | None = None
        self._poller: asyncio.Task[None] | None = None
        self._webhook_secret: str | None = None

    @property
    def webhook_mode(self) -> bool:
        return self._webhook_url is not None

    async def start(self, receive: Receive) -> None:
        """Checks the token (``getMe``), then sets the webhook or starts polling. A refused token raises with
        the token masked; the hub shows the error and tries again later."""
        client = self._client_factory(self._token)
        try:
            me = await client.get_me()
            if self._webhook_url is not None:
                secret = secrets.token_urlsafe(32)
                await client.set_webhook(self._webhook_url, secret)
                self._webhook_secret = secret
            else:
                # Webhook and getUpdates exclude each other: a webhook left from webhook mode blocks polling.
                try:
                    await client.delete_webhook()
                except LoiZaloBotApi as err:
                    logger.info("bot %s: deleteWebhook refused (%s)", self.account.id, err.ma_loi)
        except BaseException:
            await client.aclose()
            raise
        self._client = client
        self._receive = receive
        self.bot_name = str(me.get("display_name") or me.get("account_name") or "")
        if self._webhook_url is None:
            self._poller = asyncio.create_task(self._poll(client), name=f"zalo bot poll {self.account.id}")
        self.listening = True

    async def stop(self) -> None:
        self.listening = False
        self._webhook_secret = None
        if self._poller is not None:
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
            self._poller = None
        client, self._client = self._client, None
        if client is None:
            return
        if self._webhook_url is not None:
            try:
                await client.delete_webhook()
            except LoiZaloBotApi as err:
                logger.warning("bot %s: deleteWebhook failed on stop (%s)", self.account.id, err.ma_loi)
        await client.aclose()

    def verify_webhook(self, headers: Mapping[str, str]) -> bool:
        """Constant-time check of the secret header; False when no webhook is set (fail closed)."""
        if not self._webhook_secret:
            return False
        received = next((v for k, v in headers.items() if k.lower() == WEBHOOK_SECRET_HEADER), "")
        return hmac.compare_digest(received.encode("utf-8"), self._webhook_secret.encode("utf-8"))

    async def handle(self, update: ZaloBotUpdate) -> None:
        """One update from polling or the webhook: filtered, then handed to the agent."""
        receive = self._receive
        if receive is None or not self.listening:
            return
        msg = parse_update(self.account.id, update)
        if msg is None:
            logger.debug("bot %s: update %s ignored", self.account.id, update.event_name)
            return
        decision = should_respond(self.account, msg)
        if not decision.respond:
            logger.debug("bot %s: not answered (%s)", self.account.id, decision.reason)
            return
        await receive(to_inbound(msg))

    def prepare(self, text: str) -> str | None:
        # No rich text on the Bot API: markdown is stripped. A reply that leaks the system prompt is refused.
        cleaned = lam_sach_theo_cau_hinh(text, rich_text=False)
        if cleaned.chan:
            logger.error(
                "bot %s: a reply that leaks the system prompt was not sent (%d chars)",
                self.account.id,
                len(text),
            )
            return None
        if cleaned.da_sua:
            logger.info(
                "bot %s: reply cleaned before sending: %s", self.account.id, ", ".join(cleaned.da_sua)
            )
        return cleaned.text

    async def send(self, message: OutboundMessage) -> None:
        client = self._client
        if client is None:
            raise ChannelSendError("the bot is not running")
        try:
            await client.send_message(message.conversation_id, message.text, None)
        except LoiZaloBotApi as err:
            raise ChannelSendError(str(err), retryable=send_error_is_retryable(err)) from None

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None:
        client = self._client
        if client is not None and self.account.typing_indicator_enabled:
            await client.send_chat_action(conversation_id)

    async def _poll(self, client: BotApiClient) -> None:
        first, longest = self._backoff_s
        pause = first
        while True:
            try:
                update = await client.get_updates(self._poll_timeout_s)
            except LoiZaloBotApi as err:
                logger.warning(
                    "bot %s: %s failed (HTTP %s, code %s); retrying in %.0f s",
                    self.account.id,
                    err.method,
                    err.http_status,
                    err.ma_loi,
                    pause,
                )
                await self._sleep(pause)
                pause = min(pause * 2, longest)
                continue
            pause = first
            if update is None:
                continue
            try:
                await self.handle(update)
            except Exception as err:  # the message is lost (no offset); polling goes on
                logger.error(
                    "bot %s: a message could not be handed over (%s)", self.account.id, type(err).__name__
                )


def send_error_is_retryable(err: LoiZaloBotApi) -> bool:
    """Network errors, rate limits and server errors are tried again; a refusal (a blocked user, a bad chat
    id, too long a text) is not."""
    if err.http_status is None:
        return True
    code = err.ma_loi
    return err.http_status == 429 or err.http_status >= 500 or code in (429, "429")

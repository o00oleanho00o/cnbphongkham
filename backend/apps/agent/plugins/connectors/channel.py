"""One chat channel of a connector, as the channel hub sees it.

The connector pushes what it hears (the hook routes call ``handle_inbound`` and ``handle_typing``); the hub's
replies go back as signed POSTs to the connector's ``callback_url``. The channel does not split a reply (its
capabilities say no limit): the connector does that for its platform (protocol section 4).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from agentcore.channels import (
    ChannelCapabilities,
    ChannelSendError,
    InboundMessage,
    OutboundMessage,
)

from .signing import signed_headers

SEND_TIMEOUT_S: Final = 60.0
TYPING_TIMEOUT_S: Final = 5.0
RETRYABLE_STATUSES: Final = frozenset({429, 503})
MAX_ERROR_CHARS: Final = 300

logger = logging.getLogger(__name__)

Key = Callable[[str], Awaitable[str | None]]
"""The connector's key by its name; None once it is revoked."""
Receiver = Callable[[InboundMessage], Awaitable[int | None]]
"""What the hub hands ``start``: stores the message and gives its ingress id (None when it is blank)."""


@dataclass(slots=True)
class ChannelSettings:
    """What the connector registered for a channel (the ``channel:<name>`` record, without ``seen_at``)."""

    connector: str
    callback_url: str
    max_text_chars: int | None = None
    markdown: bool = False
    rules: str = ""
    disabled_tools: list[str] = field(default_factory=list[str])


class ConnectorChannel:
    def __init__(self, name: str, settings: ChannelSettings, key: Key) -> None:
        self._name = name
        self.settings = settings
        self._key = key
        self._receive: Receiver | None = None
        self._notify: Callable[[str], None] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ChannelCapabilities:
        # None: the hub hands over the whole reply once; the connector splits it for its platform. The
        # registered ``max_text_chars`` is for whoever writes the replies, not for the hub.
        return ChannelCapabilities(max_text_chars=None, markdown=self.settings.markdown)

    @property
    def listening(self) -> bool:
        return self._receive is not None

    async def start(self, receive: Any) -> None:
        self._receive = receive

    async def stop(self) -> None:
        self._receive = None

    def on_typing(self, notify: Callable[[str], None]) -> None:
        self._notify = notify

    def listens_to(self, conversation_id: str, metadata: Mapping[str, str]) -> bool:
        return metadata.get("observe") == "1"

    # --- from the connector ---

    async def handle_inbound(self, inbound: InboundMessage) -> int | None:
        """Hands the message to the hub; its ingress id. Raises ``RuntimeError`` before the hub started the
        channel (the connector keeps the message and tries again)."""
        if self._receive is None:
            raise RuntimeError(f"channel {self._name} is not started yet")
        return await self._receive(inbound)

    def handle_typing(self, conversation_id: str) -> None:
        if self._notify is not None:
            self._notify(conversation_id)

    # --- to the connector ---

    async def send(self, message: OutboundMessage) -> None:
        key = await self._key(self.settings.connector)
        if key is None:
            raise ChannelSendError("the connector's key is revoked", retryable=False)
        body = _json(
            {
                "delivery_id": _delivery_id(self._name, message),
                "channel": self._name,
                "conversation_id": message.conversation_id,
                "user_id": message.user_id,
                "reply_to": message.reply_to,
                "text": message.text,
                "metadata": dict(message.metadata),
            }
        )
        response = await self._post("/send", key, body, SEND_TIMEOUT_S)
        if response.status_code == 200:
            return
        detail = _error_body(response)
        text = str(detail.get("error") or f"HTTP {response.status_code}")[:MAX_ERROR_CHARS]
        retryable = response.status_code in RETRYABLE_STATUSES or (
            response.status_code >= 500 and detail.get("retryable") is not False
        )
        after = detail.get("retry_after_s")
        raise ChannelSendError(
            text,
            retryable=retryable,
            retry_after_s=float(after) if retryable and isinstance(after, int | float) else None,
        )

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None:
        key = await self._key(self.settings.connector)
        if key is None:
            return
        body = _json({"channel": self._name, "conversation_id": conversation_id, "metadata": dict(metadata)})
        try:
            await self._post("/typing", key, body, TYPING_TIMEOUT_S)
        except ChannelSendError:  # typing is a courtesy
            logger.debug("connector %s did not take a typing signal", self.settings.connector)

    async def _post(self, route: str, key: str, body: bytes, timeout_s: float) -> httpx.Response:
        url = f"{self.settings.callback_url.rstrip('/')}{route}"
        path = httpx.URL(url).path
        headers = {
            "Content-Type": "application/json",
            **signed_headers(key, self.settings.connector, "POST", path, body),
        }
        # trust_env off: a connector lives in the stack's own network, never behind the egress proxy.
        try:
            async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
                return await client.post(url, content=body, headers=headers)
        except httpx.HTTPError as err:  # timeouts and network errors are retried
            raise ChannelSendError(f"{type(err).__name__} reaching the connector", retryable=True) from err


def _json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _error_body(response: httpx.Response) -> dict[str, Any]:
    try:
        found = response.json()
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _delivery_id(channel: str, message: OutboundMessage) -> str:
    """The same for every retry of one part of one reply (the hub resends the same ``reply_to`` and part)."""
    if message.reply_to:
        return f"{channel}:{message.reply_to}:{message.part}"
    digest = hashlib.sha256(f"{message.conversation_id}\n{message.text}".encode()).hexdigest()[:32]
    return f"{channel}:#{digest}:{message.part}"

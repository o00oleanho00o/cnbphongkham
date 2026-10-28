"""What the channels of this service pass around: the shapes of a message in and out, and ``split_reply``.

Copied from backend/packages/agent-core/src/agentcore/channels.py (dataclasses ``InboundMessage``,
``OutboundMessage``, ``ObservedMessage``, ``ChannelCapabilities``, ``ChannelSendError``, ``split_reply``); this
service imports nothing from the agent. ``InboundMessage`` and ``ObservedMessage`` are the bodies of
``POST .../inbound`` and ``.../observed`` of docs/CONNECTOR-PROTOCOL.md; ``OutboundMessage`` is one part of
the whole reply the agent sent to ``POST /send``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal

PROACTIVE: Final = "proactive"
"""The metadata key (value ``"1"``) of a message the agent starts on its own, not as an answer. A channel that
tells the two apart (a personal account has stricter limits on messages nobody asked for) reads it."""
OBSERVE: Final = "observe"
"""The metadata key (value ``"1"``) of an inbound message whose reply the agent tells the listening plugins of."""


@dataclass(frozen=True, slots=True)
class InboundMessage:
    channel: str
    conversation_id: str
    """Where the chat happens; for a one-to-one chat the channel may use the user id."""
    user_id: str
    message_id: str
    """The channel's own id of the message; a message seen twice is processed once."""
    text: str
    metadata: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    max_text_chars: int | None = None
    """Longest reply the channel accepts in one message; None for no limit."""
    markdown: bool = False
    streaming: bool = False


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """One message of a reply; a long reply is sent as several, ``part`` of ``parts``."""

    conversation_id: str
    text: str
    user_id: str | None = None
    reply_to: str | None = None
    """The channel's id of the message being answered."""
    part: int = 1
    parts: int = 1
    metadata: Mapping[str, str] = field(default_factory=dict[str, str])
    """What the inbound message carried (thread type and the like)."""


class ChannelSendError(Exception):
    """A send that did not go through. ``retryable`` False (a blocked user, a deleted chat) stops retries."""

    def __init__(self, message: str, *, retryable: bool = True, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_s = retry_after_s


Receive = Callable[[InboundMessage], Awaitable[None]]

Origin = Literal["inbound", "own", "agent"]
"""Who wrote a message the agent only watches: ``inbound`` someone else in the chat, ``own`` the person who
runs the account (from another device), ``agent`` the agent's own reply."""


@dataclass(frozen=True, slots=True)
class ObservedMessage:
    """A message of a chat the agent only watches, whether or not it runs a turn for it: a group message
    nobody asked the agent about, what the account's owner typed."""

    channel: str
    conversation_id: str
    sender_id: str
    message_id: str
    text: str
    origin: Origin
    is_group: bool = False
    sender_name: str = ""
    user_id: str = ""
    """The person of the chat: who wrote, or whom the agent's reply answers; "" when not known."""
    answered: bool = False
    """``inbound`` only: the agent takes the message up and will answer it."""
    at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, str] = field(default_factory=dict[str, str])


Observe = Callable[[ObservedMessage], Awaitable[None]]


def split_reply(text: str, max_chars: int | None) -> list[str]:
    """The reply in pieces of at most ``max_chars``, cut at a paragraph, a line or a space when one is
    near."""
    text = text.strip()
    if not text:
        return []
    if max_chars is None or len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    while len(text) > max_chars:
        window = text[: max_chars + 1]
        cut = max((window.rfind(sep) for sep in ("\n\n", "\n", " ")), default=-1)
        if cut < max_chars // 2:
            cut = max_chars
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return [part for part in parts if part]

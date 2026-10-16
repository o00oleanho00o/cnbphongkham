"""What every channel (CLI, HTTP, chat platforms from plugins) hands to the agent, and how a conversation maps
to a session id.

A session is one conversation (a chat thread, an HTTP ``conversation_id``) at one epoch; starting over bumps
the epoch, so the old session stays readable. ``user_id`` is the person speaking: it keys the notes about that
person and never picks the session, so in a group every speaker shares the conversation's session.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal, Protocol, runtime_checkable

MAX_SESSION_ID_CHARS: Final = 200
_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def valid_channel_name(name: str) -> bool:
    return bool(_NAME.match(name))


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
    """A message of a chat, told to the plugins that listen (``ctx.on_message``) whether or not the agent runs
    a turn for it: a group message nobody asked the agent about, what the account's owner typed, a reply.
    Channels tell of what they hear (``ctx.observe``); the channel hub tells of the agent's replies."""

    channel: str
    conversation_id: str
    sender_id: str
    message_id: str
    text: str
    origin: Origin
    is_group: bool = False
    sender_name: str = ""
    answered: bool = False
    """``inbound`` only: the agent takes the message up and will answer it."""
    at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, str] = field(default_factory=dict[str, str])


Observe = Callable[[ObservedMessage], Awaitable[None]]


class ChannelAdapter(Protocol):
    """A chat platform as the agent sees it. ``start`` begins listening (webhook, polling) and returns; each
    message heard goes to ``receive``, which stores it before it runs. ``send`` delivers one message and
    raises ``ChannelSendError`` when it cannot."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> ChannelCapabilities: ...

    async def start(self, receive: Receive) -> None: ...

    async def stop(self) -> None: ...

    async def send(self, message: OutboundMessage) -> None: ...


@runtime_checkable
class ShowsTyping(Protocol):
    """A channel that can show the person that a reply is being written; called every few seconds while the
    conversation's messages are answered. ``metadata`` is what the inbound message carried."""

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None: ...


@runtime_checkable
class FiltersListening(Protocol):
    """A channel that listens to only some of its chats. What it hears itself it filters on its own; the
    channel hub asks it before it tells the plugins that listen of the agent's reply in a chat. ``metadata``
    is what the inbound message carried."""

    def listens_to(self, conversation_id: str, metadata: Mapping[str, str]) -> bool: ...


@runtime_checkable
class PreparesText(Protocol):
    """A channel that turns the whole reply into what it can show (strips markup it cannot render) before it
    is split into parts; None means the reply must not go out at all (the channel's own safety check)."""

    def prepare(self, text: str) -> str | None: ...


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


def session_id_for(agent: str, channel: str, conversation_id: str, epoch: int) -> str:
    """``agent:channel:conversation:epoch``; a conversation id that would make it too long is hashed."""
    for kind, name in (("agent", agent), ("channel", channel)):
        if not _NAME.match(name):
            raise ValueError(f"invalid {kind} name {name!r}: use a-z, 0-9, '_' or '-'")
    if not conversation_id or epoch < 0:
        raise ValueError("a session needs a conversation id and an epoch of 0 or more")
    session_id = f"{agent}:{channel}:{conversation_id}:{epoch}"
    if len(session_id) <= MAX_SESSION_ID_CHARS:
        return session_id
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:40]
    return f"{agent}:{channel}:#{digest}:{epoch}"

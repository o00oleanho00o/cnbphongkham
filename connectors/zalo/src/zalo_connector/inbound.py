"""One message heard on a Zalo account, the same for every kind of account, and how it becomes the agent's
``InboundMessage``.

The agent sees the text; in a group the speaker's name goes in front, because everyone in a group shares one
conversation. ``metadata`` carries what the reply needs back (the thread type) and what the dashboard shows.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .channels import OBSERVE, InboundMessage, ObservedMessage, Origin

THREAD_USER = "user"
THREAD_GROUP = "group"


@dataclass(frozen=True, slots=True)
class ZaloInbound:
    account_id: str
    thread_id: str
    """The chat: the person's id in a one-to-one chat, the group's id in a group."""
    is_group: bool
    sender_id: str
    sender_name: str
    message_id: str
    text: str
    image_urls: tuple[str, ...] = ()
    mentions_me: bool = False
    is_self: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict[str, Any])
    """The platform's own data of the message (zca-js ``data``), for receipts and quotes."""


IMAGE_ONLY = "[gửi một ảnh]"

Heard = Callable[[ZaloInbound], Awaitable[None]]
"""Told of every message from someone else, answered or not, before the filter (the address book)."""


def to_inbound(
    msg: ZaloInbound, extra: Mapping[str, str] | None = None, *, observe: bool = False
) -> InboundMessage:
    """``observe``: the agent tells the listening plugins of its reply to this chat (the chat is one the
    account keeps conversations of); it travels in the metadata, where the old channel hub asked
    ``listens_to``."""
    text = msg.text.strip()
    if not text and msg.image_urls:
        text = IMAGE_ONLY
    if msg.is_group and msg.sender_name:
        text = f"{msg.sender_name}: {text}"
    metadata = {"thread_type": THREAD_GROUP if msg.is_group else THREAD_USER}
    if msg.sender_name:
        metadata["sender_name"] = msg.sender_name
    if msg.image_urls:
        metadata["image_url"] = msg.image_urls[0]
    if observe:
        metadata[OBSERVE] = "1"
    metadata.update(extra or {})
    return InboundMessage(
        channel="",  # the agent client sets the channel that heard it
        conversation_id=msg.thread_id,
        user_id=msg.sender_id,
        message_id=msg.message_id,
        text=text,
        metadata=metadata,
    )


def to_observed(channel: str, msg: ZaloInbound, *, answered: bool) -> ObservedMessage | None:
    """The message as the plugins that keep conversations see it: the words as written (a group message
    without the speaker's name in front), who wrote it, and whether the agent takes it up. None for one with
    nothing to keep (a sticker, a voice note)."""
    text = msg.text.strip() or (IMAGE_ONLY if msg.image_urls else "")
    if not text:
        return None
    origin: Origin = "own" if msg.is_self else "inbound"
    return ObservedMessage(
        channel=channel,
        conversation_id=msg.thread_id,
        sender_id=msg.sender_id,
        message_id=msg.message_id,
        text=text,
        origin=origin,
        is_group=msg.is_group,
        sender_name=msg.sender_name,
        answered=answered and not msg.is_self,
    )

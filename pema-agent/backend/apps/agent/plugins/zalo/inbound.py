"""One message heard on a Zalo account, the same for every kind of account, and how it becomes the agent's
``InboundMessage``.

The agent sees the text; in a group the speaker's name goes in front, because everyone in a group shares one
conversation. ``metadata`` carries what the reply needs back (the thread type) and what the dashboard shows.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentcore.channels import InboundMessage

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


def to_inbound(msg: ZaloInbound) -> InboundMessage:
    text = msg.text.strip()
    if not text and msg.image_urls:
        text = "[gửi một ảnh]"
    if msg.is_group and msg.sender_name:
        text = f"{msg.sender_name}: {text}"
    metadata = {"thread_type": THREAD_GROUP if msg.is_group else THREAD_USER}
    if msg.sender_name:
        metadata["sender_name"] = msg.sender_name
    if msg.image_urls:
        metadata["image_url"] = msg.image_urls[0]
    return InboundMessage(
        channel="",  # the hub sets the channel that heard it
        conversation_id=msg.thread_id,
        user_id=msg.sender_id,
        message_id=msg.message_id,
        text=text,
        metadata=metadata,
    )

"""What every channel (CLI, HTTP, later Zalo and others) hands to the agent, and how a conversation maps to a
session id.

A session is one conversation (a Zalo thread, an HTTP ``conversation_id``) at one epoch; starting over bumps
the epoch, so the old session stays readable. ``user_id`` is the person speaking: it keys the notes about that
person and never picks the session, so in a group every speaker shares the conversation's session.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

MAX_SESSION_ID_CHARS: Final = 200
_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


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

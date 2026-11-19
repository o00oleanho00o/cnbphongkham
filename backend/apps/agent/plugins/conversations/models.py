"""What the plugin keeps: conversations, their messages with the role of each writer, and the people seen."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal

Role = Literal["customer", "staff", "agent"]
Origin = Literal["inbound", "own", "agent"]

ROLES: Final = ("customer", "staff", "agent")


def conversation_id(channel: str, external_id: str) -> str:
    """The same chat always has the same id, so a message heard twice lands in one place."""
    digest = hashlib.sha1(f"{channel}\n{external_id}".encode(), usedforsecurity=False).hexdigest()
    return f"cv-{digest[:20]}"


@dataclass(frozen=True, slots=True)
class NewMessage:
    conversation_id: str
    channel: str
    external_id: str
    """The chat's id on the platform."""
    is_group: bool
    title_hint: str
    message_id: str
    sender_id: str
    sender_name: str
    role: Role
    origin: Origin
    at: datetime
    text: str
    answered: bool = False
    meta: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True)
class Message:
    seq: int
    conversation_id: str
    message_id: str
    sender_id: str
    sender_name: str
    role: Role
    origin: Origin
    at: datetime
    text: str
    answered: bool

    def shown(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "role": self.role,
            "at": self.at.isoformat(),
            "text": self.text,
            "answered": self.answered,
        }


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    channel: str
    external_id: str
    is_group: bool
    title: str
    excluded: bool
    message_count: int
    first_at: datetime
    last_at: datetime

    def shown(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "external_id": self.external_id,
            "is_group": self.is_group,
            "title": self.title,
            "excluded": self.excluded,
            "message_count": self.message_count,
            "first_at": self.first_at.isoformat(),
            "last_at": self.last_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Person:
    """Someone who wrote in a channel, for choosing who is staff."""

    sender_id: str
    name: str
    messages: int
    role: Role

    def shown(self) -> dict[str, Any]:
        return {"sender_id": self.sender_id, "name": self.name, "messages": self.messages, "role": self.role}

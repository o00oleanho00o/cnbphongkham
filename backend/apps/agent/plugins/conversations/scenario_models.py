"""What the scenario store keeps and what a search gives back."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

Scope = Literal["channel", "plugin", "agent"]
SCOPES: Final = ("channel", "plugin", "agent")

HitHow = Literal["meaning", "words"]


def episode_id(conversation_id: str, first_seq: int) -> str:
    """The same stretch of the same chat always has the same id, so cutting it again changes nothing."""
    digest = hashlib.sha1(f"{conversation_id}\n{first_seq}".encode(), usedforsecurity=False).hexdigest()
    return f"ep-{digest[:20]}"


@dataclass(frozen=True, slots=True)
class Episode:
    id: str
    channel: str
    plugin: str
    conversation_id: str
    started_at: datetime
    ended_at: datetime
    first_seq: int
    last_seq: int
    ask: str
    transcript: tuple[tuple[str, str], ...]
    fingerprint: str
    repeats: int
    enabled: bool
    updated_at: datetime

    def shown(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "ask": self.ask,
            "transcript": [{"role": role, "text": text} for role, text in self.transcript],
            "repeats": self.repeats,
            "enabled": self.enabled,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Hit:
    episode: Episode
    score: float
    how: HitHow

    def shown(self) -> dict[str, Any]:
        return {**self.episode.shown(), "score": round(self.score, 3), "how": self.how}


@dataclass(frozen=True, slots=True)
class Reach:
    """Which episodes a question may use: those of one channel, of every channel of a chat plugin, or all."""

    channel: str | None = None
    plugin: str | None = None


@dataclass(frozen=True, slots=True)
class Counts:
    episodes: int
    without_vector: int

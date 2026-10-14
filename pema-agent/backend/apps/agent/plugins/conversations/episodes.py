"""Cutting kept conversations into episodes: what a customer asked and how the staff reacted.

An episode starts at a customer's message and runs while the chat goes on (a pause of more than ``gap_s``
ends it; a long one is cut at a customer's message that follows a staff message). Only episodes with a
reaction of the staff are kept: the staff's way of answering is what is worth learning, and a customer's
words with no answer teach nothing. The agent's own replies are left out, and so is anything too short, any
greeting or thanks on its own, and any text that looks like an attack on the agent. Personal details are
hidden before an episode is made (``redact.mask``), so nothing here points at a person."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from agentcore.harness.guards.threats import scan_for_threats

from .models import Message, Role
from .redact import mask
from .words import meaningful

GAP_S: Final = 1800.0
"""A pause this long ends an episode."""
MAX_MESSAGES: Final = 12
MAX_CHARS: Final = 2500
MIN_ASK_WORDS: Final = 3
MIN_REACTION_CHARS: Final = 12
FINGERPRINT_WORDS: Final = 25


@dataclass(frozen=True, slots=True)
class Draft:
    """An episode as cut, before it is stored."""

    started_at: datetime
    ended_at: datetime
    first_seq: int
    last_seq: int
    transcript: tuple[tuple[str, str], ...]
    """(``customer`` or ``staff``, text) lines in order, neighbours of one role joined."""
    ask: str
    """What the customer said, joined: the text a search is matched against."""
    fingerprint: str

    @property
    def reaction(self) -> str:
        return " ".join(text for role, text in self.transcript if role == "staff")


def cut(messages: Sequence[Message], *, gap_s: float = GAP_S) -> list[Draft]:
    """The episodes of one conversation's messages (any order); the ones worth keeping."""
    ordered = sorted((m for m in messages if m.role != "agent"), key=lambda m: (m.at, m.seq))
    drafts = (_draft(chunk) for segment in _segments(ordered, gap_s) for chunk in _chunks(segment))
    return [draft for draft in drafts if draft is not None]


def _segments(ordered: Sequence[Message], gap_s: float) -> list[list[Message]]:
    segments: list[list[Message]] = []
    for message in ordered:
        if segments and (message.at - segments[-1][-1].at).total_seconds() <= gap_s:
            segments[-1].append(message)
        else:
            segments.append([message])
    return segments


def _chunks(segment: list[Message]) -> list[list[Message]]:
    """The segment from its first customer message, cut where it grows too long at a customer's message that
    follows a staff message."""
    first = next((i for i, m in enumerate(segment) if m.role == "customer"), None)
    if first is None:
        return []
    chunks: list[list[Message]] = [[]]
    size = 0
    for index, message in enumerate(segment[first:], start=first):
        previous = segment[index - 1] if index > first else None
        too_long = len(chunks[-1]) >= MAX_MESSAGES or size >= MAX_CHARS
        if too_long and message.role == "customer" and previous is not None and previous.role == "staff":
            chunks.append([])
            size = 0
        chunks[-1].append(message)
        size += len(message.text)
    return chunks


def _draft(chunk: list[Message]) -> Draft | None:
    names = {m.sender_name for m in chunk if m.sender_name}
    lines: list[tuple[Role, str]] = []
    for message in chunk:
        text = mask(message.text.strip(), names)
        if lines and lines[-1][0] == message.role:
            lines[-1] = (message.role, f"{lines[-1][1]} {text}")
        else:
            lines.append((message.role, text))
    ask = " ".join(text for role, text in lines if role == "customer")
    reaction = " ".join(text for role, text in lines if role == "staff")
    if len(meaningful(ask)) < MIN_ASK_WORDS or len(reaction) < MIN_REACTION_CHARS:
        return None
    if scan_for_threats(f"{ask}\n{reaction}", "strict"):
        return None
    return Draft(
        started_at=chunk[0].at,
        ended_at=chunk[-1].at,
        first_seq=min(m.seq for m in chunk),
        last_seq=max(m.seq for m in chunk),
        transcript=tuple((role, text) for role, text in lines),
        ask=ask,
        fingerprint=fingerprint_of(ask),
    )


def fingerprint_of(ask: str) -> str:
    """The same question asked again in the same words has the same fingerprint (case, marks and
    punctuation do not count)."""
    base = " ".join(meaningful(ask)[:FINGERPRINT_WORDS])
    return hashlib.sha1(base.encode(), usedforsecurity=False).hexdigest()[:16]

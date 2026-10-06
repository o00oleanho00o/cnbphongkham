"""The words of a notification (package O, step O3). New module.

One short text for the personal Zalo bell and the team group, one title and body for a push. They are composed
from the fields of ``NotificationPayload`` only (short code, identity label, urgency, a summary the action
wrote
from a template, the deep link). ``guard_text`` runs the free-text fields through the PII mask before anything
leaves: a row that reached the outbox through some path that skipped the serializer still cannot put a phone
number or an e-mail in a chat.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pema.policy.pii import mask_pii

URGENT_PREFIX = "[KHẨN] "
BELL_PREFIX = "[Pema] "
PUSH_TITLE = "Pema"
PUSH_TITLE_URGENT = "Pema - KHẨN"


class UnsafeTextError(ValueError):
    """The text carries personal data. The error never repeats the text."""


def guard_text(value: str) -> str:
    if mask_pii(value).changed:
        raise UnsafeTextError("the notification text carries personal data")
    return value


def _field(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def deep_link_url(payload: Mapping[str, Any], base_url: str | None) -> str:
    link = _field(payload, "deep_link")
    return f"{base_url.rstrip('/')}{link}" if base_url else link


def render_chat_text(payload: Mapping[str, Any], base_url: str | None) -> str:
    """The line the bell and the group get: ``[Pema] [KHẨN] summary · identity · #A1B2`` and the link."""
    summary = guard_text(_field(payload, "summary"))
    label = guard_text(_field(payload, "identity_label"))
    urgent = payload.get("urgency") == "urgent"
    parts = [summary]
    if label:
        parts.append(label)
    parts.append(_field(payload, "short_code"))
    head = BELL_PREFIX + (URGENT_PREFIX if urgent else "") + " · ".join(part for part in parts if part)
    return f"{head}\nMở: {deep_link_url(payload, base_url)}"


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    deep_link: str
    short_code: str
    urgent: bool


def render_push(payload: Mapping[str, Any]) -> PushMessage:
    urgent = payload.get("urgency") == "urgent"
    return PushMessage(
        title=PUSH_TITLE_URGENT if urgent else PUSH_TITLE,
        body=guard_text(_field(payload, "summary")),
        deep_link=_field(payload, "deep_link"),
        short_code=_field(payload, "short_code"),
        urgent=urgent,
    )

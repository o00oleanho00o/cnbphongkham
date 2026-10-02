"""Live updates and presence (package ST-R): the payload of ``GET /api/v1/events`` and the presence DTOs.

New module (not a port). An event only says "something changed, refetch": it never carries a message text, a
patient name, a phone number or any other PII, and ``id`` is the id of the changed object (conversation, task,
review item) or ``None`` for "some". The screens reload their own list through the normal API, so permissions
and filters stay the backend's.

Presence is a WARNING shown to colleagues ("Lan is replying"), never a lock: nothing here stops anybody from
sending.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel


class LiveEventType(StrEnum):
    INBOX_CHANGED = "inbox.changed"
    """A conversation or a message changed (inbound, reply, assignment, status, read marker)."""
    TASKS_CHANGED = "tasks.changed"
    """A CSKH task was created, resolved or superseded."""
    REVIEW_CHANGED = "review.changed"
    """A review item was created or decided."""
    PRESENCE_CHANGED = "presence.changed"
    """Somebody started or stopped looking at a conversation (``id`` is the conversation)."""
    HANDOFF_CHANGED = "handoff.changed"
    """A care agent asked for a person, the chain moved on, or somebody accepted or declined (``id`` is the
    patient). Package M, step M5."""
    CARE_CHANGED = "care.changed"
    """The care state of a patient changed: control state, autonomy level, a paused reminder, a note for the
    agent, an alert (``id`` is the patient). Package M, step M5."""


class LiveEvent(ApiModel):
    """The ``data`` of one server-sent event (default ``message`` event type)."""

    type: LiveEventType
    id: UUID | None = Field(default=None, description="The changed object, or null for 'some of them'.")


class PresenceState(StrEnum):
    VIEWING = "viewing"
    REPLYING = "replying"


class PresenceBeat(ApiModel):
    """Body of the heartbeat the browser sends every 15 seconds while a conversation is open."""

    state: PresenceState


class PresenceViewer(ApiModel):
    """A colleague who has the conversation open now (the caller is never in the list)."""

    user_id: UUID
    name: str = Field(max_length=200, description="Display name of the staff member; staff-only information.")
    state: PresenceState


__all__ = ["LiveEvent", "LiveEventType", "PresenceBeat", "PresenceState", "PresenceViewer"]

"""Live updates (package ST-R): the payload of ``GET /api/v1/events``.

New module (not a port). An event only says "something changed, refetch": it never carries a patient name, a
phone number or any other PII, and ``id`` is the id of the changed object (task, appointment) or ``None`` for
"some". The screens reload their own list through the normal API, so permissions and filters stay the
backend's.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel


class LiveEventType(StrEnum):
    TASKS_CHANGED = "tasks.changed"
    """A CSKH task was created, resolved or superseded."""
    APPOINTMENTS_CHANGED = "appointments.changed"
    """An appointment was booked, moved or went through a reception transition (``id`` is the appointment).
    Package U, step U2: the schedule and the dashboard reload."""


class LiveEvent(ApiModel):
    """The ``data`` of one server-sent event (default ``message`` event type)."""

    type: LiveEventType
    id: UUID | None = Field(default=None, description="The changed object, or null for 'some of them'.")


__all__ = ["LiveEvent", "LiveEventType"]

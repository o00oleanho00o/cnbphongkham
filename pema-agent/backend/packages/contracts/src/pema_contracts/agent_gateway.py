"""DTOs of the agent gateway (``/agent-gateway``, docs/PLAN-crm-plugin.md).

What the clinic's agent may send and get back. Every answer is about the person of one chat link or is free
of persons (start times); none carries a name, a phone, a doctor or a patient id.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field

from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import ApiModel, VnDatetime


class FreeDay(ApiModel):
    day: date
    starts: list[VnDatetime] = Field(description="Free start times of the day, earliest first.")


class FreeSlotsOut(ApiModel):
    duration_min: int
    days: list[FreeDay]


class ContactSave(ApiModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=32, description="Any Vietnamese way of writing it.")
    messages_consent: bool | None = Field(
        default=None,
        description="The person agreed (true) or refused (false) reminders by message; null leaves it as is.",
    )


class ContactOut(ApiModel):
    created: bool = Field(description="True when this saved a new patient; an existing one is never changed.")
    messages_consent: bool | None


class AgentBooking(ApiModel):
    starts_at: VnDatetime
    duration_min: int = Field(default=30, ge=5, le=480)
    note: str | None = Field(default=None, max_length=500, description="The service the person asked for.")


class AgentReschedule(ApiModel):
    starts_at: VnDatetime
    duration_min: int | None = Field(default=None, ge=5, le=480)


class AgentCancel(ApiModel):
    reason: str = Field(min_length=1, max_length=200)


class AgentAppointmentOut(ApiModel):
    """No note: staff write internal remarks there."""

    id: UUID
    starts_at: VnDatetime
    duration_min: int
    status: AppointmentStatus


class ReminderOut(ApiModel):
    appointment_id: UUID
    channel: str
    external_id: str
    starts_at: VnDatetime
    duration_min: int
    status: AppointmentStatus
    updated_at: VnDatetime = Field(
        description="Last change of the appointment (booking, move, confirmation)."
    )

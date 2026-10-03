"""Appointment DTOs (table ``clinic.appointment``; JS source: PemaOps appointments)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"


class AppointmentOut(ApiModel):
    id: UUID
    patient_id: UUID
    patient_code: str
    doctor_id: UUID | None
    starts_at: VnDatetime
    duration_min: int
    status: AppointmentStatus
    note: str | None = None
    cancel_reason: str | None = None
    cancelled_at: VnDatetime | None = None
    missed_at: VnDatetime | None = None
    created_by: UUID | None = None
    version: int = Field(description="Optimistic lock counter; send it back on PATCH/transitions.")


class AppointmentCreate(ApiModel):
    patient_id: UUID
    doctor_id: UUID | None = None
    starts_at: VnDatetime
    duration_min: int = Field(default=30, ge=5, le=480)
    note: str | None = Field(default=None, max_length=1000)
    crm_task_id: UUID | None = Field(
        default=None,
        description="When booking from a CRM task, task + activity + appointment commit together.",
    )


class AppointmentUpdate(ApiModel):
    version: int
    doctor_id: UUID | None = None
    starts_at: VnDatetime | None = None
    duration_min: int | None = Field(default=None, ge=5, le=480)
    note: str | None = Field(default=None, max_length=1000)


class AppointmentTransition(ApiModel):
    """Body for check-in / cancel / miss style transitions."""

    version: int
    reason: str | None = Field(default=None, max_length=500)


class ScheduleView(StrEnum):
    DAY = "day"
    WEEK = "week"


class ScheduleItem(AppointmentOut):
    """One row of the schedule: the appointment plus the two names a reception desk reads on the board.
    ``patient_name`` is filled only for a caller that holds ``patient.read``."""

    patient_name: str | None = None
    doctor_name: str | None = None


class ScheduleDoctor(ApiModel):
    """A doctor the schedule can be filtered by (active doctor or owner of the clinic)."""

    id: UUID
    name: str


class ScheduleOut(ApiModel):
    """The day (or the 7 days from ``from_day``) of the clinic board, oldest first. A doctor's own call lists
    only that doctor's appointments."""

    view: ScheduleView
    from_day: date
    to_day: date = Field(description="Last day, inclusive (same as ``from_day`` for the day view).")
    doctor_id: UUID | None = None
    items: list[ScheduleItem]
    doctors: list[ScheduleDoctor]


class FreeSlotOut(ApiModel):
    """First start the validator accepts for the given patient, doctor, day and duration; ``None`` when the
    day has none (prototype: ``Khong co gio trong``)."""

    starts_at: VnDatetime | None = None

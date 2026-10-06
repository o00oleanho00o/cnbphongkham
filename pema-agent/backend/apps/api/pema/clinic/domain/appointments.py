# ported from: prototype/shared/operations-data.js (validate, saveAppointment, setStatus, cancel) and
# prototype/shared/crm-automation.js (reception)
"""Scheduling rules: working hours, double-booking check and the status machine of an appointment.

Forced deviations from the JS prototype (which kept everything in ``localStorage``):

* the schema has no services or buffers on an appointment, so the per-service buffer is gone: a slot is
  occupied from ``starts_at`` for ``duration_min`` minutes (``buffer`` is 0, so the room "chuẩn bị phòng" time
  is not modelled). The doctor-versus-doctor and patient-versus-patient overlap rules of ``validate`` are kept
  exactly. Package U step U10 adds the room ``room_id`` and the two room rules of ``validate``: a room blocked
  in the window (``Trùng thời gian khóa``) and a room already busy in the window (``Phòng đang bận``); the
  service-room list (``Phòng không phù hợp với dịch vụ``) stays out because an appointment has no service;
* working hours (08:00 to 18:00, break 12:00 to 13:00) are the constants of the prototype's doctors; there
  is no per-doctor shift table yet (open item);
* times are aware datetimes (stored ``timestamptz``); the day and the clock time are read in the clinic's
  +07:00 zone (``pema_contracts.common.VN_TZ``).

This module is pure: it imports no database code, so the same validator serves the REST routes and the
agent proposal (``AgentFacingClinicActions``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode

WORK_START = time(8, 0)
WORK_END = time(18, 0)
BREAK_START = time(12, 0)
BREAK_END = time(13, 0)

FREE_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.CANCELLED, AppointmentStatus.MISSED}
)
"""JS ``active``: a cancelled or missed appointment no longer occupies its slot."""

CONFIRM_FROM: frozenset[AppointmentStatus] = frozenset({AppointmentStatus.BOOKED})
"""JS ``setStatus(id, 'confirmed')``: the desk phoned the patient and they said yes."""
CHECK_IN_FROM: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED}
)
START_FROM: frozenset[AppointmentStatus] = frozenset({AppointmentStatus.ARRIVED})
COMPLETE_FROM: frozenset[AppointmentStatus] = frozenset({AppointmentStatus.IN_PROGRESS})
MISS_FROM: frozenset[AppointmentStatus] = frozenset({AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED})
CANCEL_FROM: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED, AppointmentStatus.ARRIVED}
)
EDIT_FROM: frozenset[AppointmentStatus] = frozenset({AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED})
"""JS: ``Lich da huy/vang hen; hay tao lich moi``. A started or finished visit is not rescheduled."""


@dataclass(frozen=True)
class Slot:
    """What the double-booking check needs about one appointment."""

    patient_id: UUID
    doctor_id: UUID | None
    starts_at: datetime
    duration_min: int
    appointment_id: UUID | None = None
    status: AppointmentStatus = AppointmentStatus.BOOKED

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_min)


@dataclass(frozen=True)
class Conflict:
    """Which rule the candidate broke (``doctor`` or ``patient``) and the slot it collides with. The
    message never contains a name."""

    kind: str
    with_appointment_id: UUID | None
    with_starts_at: datetime


def _local(value: datetime) -> datetime:
    return value.astimezone(VN_TZ)


def validate_slot(
    starts_at: datetime, duration_min: int, now: datetime, *, require_future: bool = False
) -> None:
    """JS ``validate``: valid date and time, not before today, inside the doctor's shift and out of the
    break. ``require_future`` is for proposals made by the agent: a slot already in the past is never
    useful there (the UI keeps the prototype's behaviour of accepting earlier times of today)."""
    if starts_at.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thời điểm hẹn phải có múi giờ.")
    start = _local(starts_at)
    end = start + timedelta(minutes=duration_min)
    if duration_min < 5 or duration_min > 480:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thời lượng không hợp lệ.")
    if start.date() < _local(now).date() or (require_future and starts_at <= now):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Ngày giờ hẹn phải từ hiện tại trở đi.")
    if end.date() != start.date():
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Lịch hẹn không được kéo dài sang ngày khác.")
    if start.time() < WORK_START or end.time() > WORK_END:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Ngoài ca làm việc 08:00–18:00 của phòng khám.")
    if start.time() < BREAK_END and end.time() > BREAK_START:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Trùng giờ nghỉ 12:00–13:00.")


def overlaps(a: Slot, b: Slot) -> bool:
    return a.starts_at < b.ends_at and a.ends_at > b.starts_at


def find_conflict(candidate: Slot, existing: Iterable[Slot]) -> Conflict | None:
    """JS ``validate``: ``Trung benh nhan`` / ``Trung bac si`` against every active appointment of the
    same time. The candidate's own row (reschedule) is skipped."""
    for other in existing:
        if other.status in FREE_STATUSES:
            continue
        if candidate.appointment_id is not None and other.appointment_id == candidate.appointment_id:
            continue
        if not overlaps(candidate, other):
            continue
        if other.patient_id == candidate.patient_id:
            return Conflict("patient", other.appointment_id, other.starts_at)
        if candidate.doctor_id is not None and other.doctor_id == candidate.doctor_id:
            return Conflict("doctor", other.appointment_id, other.starts_at)
    return None


def raise_for_conflict(conflict: Conflict) -> None:
    who = "bệnh nhân" if conflict.kind == "patient" else "bác sĩ"
    local = _local(conflict.with_starts_at).strftime("%d/%m %H:%M")
    raise DomainError(
        ErrorCode.APPOINTMENT_CONFLICT,
        f"Trùng lịch của {who} lúc {local}.",
        details={"conflict": conflict.kind, "with_appointment_id": str(conflict.with_appointment_id)},
    )


@dataclass(frozen=True)
class RoomSlot:
    """What the room check needs about one appointment that holds a room."""

    starts_at: datetime
    duration_min: int
    appointment_id: UUID | None = None
    status: AppointmentStatus = AppointmentStatus.BOOKED

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_min)


@dataclass(frozen=True)
class BlockWindow:
    """A ``clinic.room_block`` row: the day and the clock window (clinic zone) with its reason."""

    day: date
    start: time
    end: time
    reason: str


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def find_block(starts_at: datetime, duration_min: int, blocks: Iterable[BlockWindow]) -> BlockWindow | None:
    """JS ``validate``: ``Trung thoi gian khoa``: the first block of the same day whose window overlaps
    ``[start, start + duration)`` (``start < b.end and occupied > b.start``). Appointments never cross
    midnight (``validate_slot``), so the clock minutes of the clinic zone are enough."""
    begin = _local(starts_at)
    first = begin.hour * 60 + begin.minute
    last = first + duration_min
    for block in blocks:
        if block.day != begin.date():
            continue
        if first < _minutes(block.end) and last > _minutes(block.start):
            return block
    return None


def find_room_busy(
    starts_at: datetime,
    duration_min: int,
    others: Iterable[RoomSlot],
    *,
    exclude: UUID | None = None,
) -> RoomSlot | None:
    """JS ``validate``: ``Phong dang ban``: the first active appointment of the same room that overlaps the
    window. The visit being moved (``exclude``) is skipped."""
    end = starts_at + timedelta(minutes=duration_min)
    for other in others:
        if other.status in FREE_STATUSES:
            continue
        if exclude is not None and other.appointment_id == exclude:
            continue
        if starts_at < other.ends_at and end > other.starts_at:
            return other
    return None


def raise_for_block(block: BlockWindow) -> None:
    raise DomainError(
        ErrorCode.APPOINTMENT_CONFLICT,
        f"Trùng thời gian khóa: {block.reason}",
        details={"conflict": "room_block"},
    )


def raise_for_room_busy(other: RoomSlot) -> None:
    local = _local(other.starts_at).strftime("%H:%M")
    raise DomainError(
        ErrorCode.APPOINTMENT_CONFLICT,
        f"Phòng đang bận hoặc đang chuẩn bị sau lịch {local}.",
        details={"conflict": "room", "with_appointment_id": str(other.appointment_id)},
    )

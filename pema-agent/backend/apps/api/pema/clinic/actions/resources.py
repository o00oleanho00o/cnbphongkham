# ported from: prototype/shared/operations-ui.js (resources) and prototype/shared/operations-data.js (rooms,
# block)
"""Doctors, rooms and room blocks ("Bác sĩ & phòng").

What the prototype screen showed and where it comes from here:

* a card per doctor with the shift (``08:00-18:00``, break ``12:00-13:00``) and the load of the day
  ("N lịch · M phút điều trị / 540 phút ca"). The prototype stored the shift on the doctor; here a doctor is a
  ``clinic.user_account`` of role ``doctor`` and the shift is the weekly one of ``clinic.staff_profiles``
  (package M; the break is the gap between two intervals). Nothing is copied: this action only READS both, and
  the shift is edited where it already is (``/admin/care/staff``). The load counts the doctor's appointments
  that are not cancelled or missed, like ``O.active``.
* the rooms (name, active) and the room blocks ("Khóa phòng" with a reason, "Gỡ khóa").

Block rule of ``block()``: the window must lie inside 08:00-18:00, start before end, and carry a reason. The
prototype also refuses a block that overlaps an active appointment of the room ("Có lịch hẹn trong khoảng
này. Hãy dời lịch trước khi khóa phòng."); since U10 an appointment carries its room, so ``add_block`` (the
"block_room" action of the room grid) checks it too.

Permissions: reading needs ``appointment.read`` (everybody who sees the schedule) or ``admin.rules``; every
change needs ``admin.rules`` (ARCH-PB01 "Quản trị catalog/role": manager, owner).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.domain.appointments import FREE_STATUSES
from pema.clinic.models import Appointment, Room, RoomBlock, UserAccount
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.care import ShiftIntervalOut
from pema_contracts.catalog import (
    DoctorResourceOut,
    ResourcesOut,
    RoomBlockCreate,
    RoomBlockOut,
    RoomCreate,
    RoomOut,
    RoomUpdate,
)
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

READ_PERMISSIONS = (Permission.APPOINTMENT_READ, Permission.ADMIN_RULES)
BLOCK_FROM = time(8, 0)
BLOCK_TO = time(18, 0)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_FREE = [s.value for s in FREE_STATUSES]


def room_out(row: Room) -> RoomOut:
    return RoomOut(id=row.id, name=row.name, capacity=row.capacity, active=row.active, version=row.version)


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def block_out(row: RoomBlock) -> RoomBlockOut:
    return RoomBlockOut(
        id=row.id,
        room_id=row.room_id,
        day=row.day,
        start=_hhmm(row.starts_at),
        end=_hhmm(row.ends_at),
        reason=row.reason,
        created_by=row.created_by,
    )


def _minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:])


def shift_for(shift: object, day: date) -> list[ShiftIntervalOut]:
    """The intervals of the weekday of ``day`` from the weekly shift jsonb of ``clinic.staff_profiles``."""
    days = cast(dict[str, Any], shift) if isinstance(shift, dict) else {}
    out: list[ShiftIntervalOut] = []
    for item in cast(list[Any], days.get(WEEKDAYS[day.weekday()]) or []):
        interval = cast(dict[str, Any], item) if isinstance(item, dict) else {}
        start, end = interval.get("start"), interval.get("end")
        if isinstance(start, str) and isinstance(end, str):
            out.append(ShiftIntervalOut(start=start, end=end))
    return out


def shift_minutes(intervals: list[ShiftIntervalOut]) -> int:
    """Length of the shift; an end earlier than the start means it ends the next morning."""
    return sum((_minutes(i.end) - _minutes(i.start)) % (24 * 60) for i in intervals)


async def list_resources(db: ClinicDatabase, ctx: ActionContext, *, day: date | None = None) -> ResourcesOut:
    require_any(ctx, READ_PERMISSIONS)
    chosen = day or now().astimezone(VN_TZ).date()
    start = datetime.combine(chosen, time.min, tzinfo=VN_TZ)
    async with db.session() as session:
        doctors = (
            await session.scalars(
                select(UserAccount)
                .where(UserAccount.clinic_id == ctx.clinic_id, UserAccount.role == "doctor")
                .order_by(UserAccount.display_name, UserAccount.id)
            )
        ).all()
        ids = [d.id for d in doctors]
        shifts: dict[UUID, object] = {}
        load: dict[UUID, tuple[int, int]] = defaultdict(lambda: (0, 0))
        if ids:
            rows = await session.execute(
                text(
                    "SELECT user_id, shift FROM clinic.staff_profiles "
                    "WHERE clinic_id = :c AND user_id = ANY(:ids)"
                ),
                {"c": ctx.clinic_id, "ids": ids},
            )
            shifts = {r.user_id: r.shift for r in rows}
            totals = await session.execute(
                select(
                    Appointment.doctor_id, func.count(), func.coalesce(func.sum(Appointment.duration_min), 0)
                )
                .where(
                    Appointment.clinic_id == ctx.clinic_id,
                    Appointment.doctor_id.in_(ids),
                    Appointment.starts_at >= start,
                    Appointment.starts_at < start + timedelta(days=1),
                    Appointment.status.notin_(_FREE),
                )
                .group_by(Appointment.doctor_id)
            )
            for doctor_id, count, minutes in totals:
                if doctor_id is not None:
                    load[doctor_id] = (int(count), int(minutes))
        rooms = (
            await session.scalars(
                select(Room).where(Room.clinic_id == ctx.clinic_id).order_by(Room.name, Room.id)
            )
        ).all()
        blocks = (
            await session.scalars(
                select(RoomBlock)
                .where(RoomBlock.clinic_id == ctx.clinic_id, RoomBlock.day >= chosen)
                .order_by(RoomBlock.day, RoomBlock.starts_at, RoomBlock.id)
            )
        ).all()

        doctor_rows: list[DoctorResourceOut] = []
        for d in doctors:
            intervals = shift_for(shifts.get(d.id), chosen)
            count, minutes = load[d.id]
            doctor_rows.append(
                DoctorResourceOut(
                    user_id=d.id,
                    name=d.display_name,
                    active=d.active,
                    has_shift=d.id in shifts,
                    shift=intervals,
                    shift_minutes=shift_minutes(intervals),
                    booked_count=count,
                    booked_minutes=minutes,
                )
            )
        return ResourcesOut(
            day=chosen,
            doctors=doctor_rows,
            rooms=[room_out(r) for r in rooms],
            blocks=[block_out(b) for b in blocks],
        )


async def _load_room(session: AsyncSession, ctx: ActionContext, room_id: UUID) -> Room:
    row = await session.scalar(select(Room).where(Room.id == room_id, Room.clinic_id == ctx.clinic_id))
    if row is None:
        raise not_found("phòng")
    return row


async def create_room(db: ClinicDatabase, ctx: ActionContext, payload: RoomCreate) -> RoomOut:
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        row = Room(clinic_id=ctx.clinic_id, name=payload.name, capacity=payload.capacity)
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Tên phòng đã tồn tại.") from exc
        await audit.record(session, ctx, "room.create", "room", row.id, {"capacity": row.capacity})
        return room_out(row)


async def update_room(db: ClinicDatabase, ctx: ActionContext, room_id: UUID, payload: RoomUpdate) -> RoomOut:
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        row = await _load_room(session, ctx, room_id)
        check_version(row.version, payload.version)
        changed: list[str] = []
        if payload.name is not None and payload.name != row.name:
            row.name = payload.name
            changed.append("name")
        if payload.capacity is not None and payload.capacity != row.capacity:
            row.capacity = payload.capacity
            changed.append("capacity")
        if payload.active is not None and payload.active != row.active:
            row.active = payload.active
            changed.append("active")
        if not changed:
            return room_out(row)
        try:
            with lost_race_is_conflict():
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Tên phòng đã tồn tại.") from exc
        await audit.record(session, ctx, "room.update", "room", row.id, {"changed_fields": changed})
        return room_out(row)


async def add_block(db: ClinicDatabase, ctx: ActionContext, payload: RoomBlockCreate) -> RoomBlockOut:
    """ "Khóa phòng": a window the room cannot be booked: inside 08:00-18:00, start before end, a reason."""
    require(ctx, Permission.ADMIN_RULES)
    start = time.fromisoformat(payload.start)
    end = time.fromisoformat(payload.end)
    if not (BLOCK_FROM <= start < end <= BLOCK_TO):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do."
        )
    async with db.session() as session:
        await _load_room(session, ctx, payload.room_id)
        day_start = datetime.combine(payload.day, time.min, tzinfo=VN_TZ)
        held = await session.scalars(
            select(Appointment).where(
                Appointment.clinic_id == ctx.clinic_id,
                Appointment.room_id == payload.room_id,
                Appointment.status.notin_(_FREE),
                Appointment.starts_at >= day_start,
                Appointment.starts_at < day_start + timedelta(days=1),
            )
        )
        for held_row in held:
            begin = held_row.starts_at.astimezone(VN_TZ)
            first = begin.hour * 60 + begin.minute
            if first < _minutes(payload.end) and first + held_row.duration_min > _minutes(payload.start):
                raise DomainError(
                    ErrorCode.APPOINTMENT_CONFLICT,
                    "Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.",
                    details={"conflict": "room", "with_appointment_id": str(held_row.id)},
                )
        row = RoomBlock(
            clinic_id=ctx.clinic_id,
            room_id=payload.room_id,
            day=payload.day,
            starts_at=start,
            ends_at=end,
            reason=payload.reason,
            created_by=ctx.actor_user_id,
        )
        session.add(row)
        await session.flush()
        await audit.record(
            session,
            ctx,
            "room_block.create",
            "room_block",
            row.id,
            {
                "room_id": str(row.room_id),
                "day": row.day.isoformat(),
                "start": payload.start,
                "end": payload.end,
            },
        )
        return block_out(row)


async def remove_block(db: ClinicDatabase, ctx: ActionContext, block_id: UUID) -> None:
    """ "Gỡ khóa". The row is deleted; the audit row keeps who removed which window of which room."""
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        row = await session.scalar(
            select(RoomBlock).where(RoomBlock.id == block_id, RoomBlock.clinic_id == ctx.clinic_id)
        )
        if row is None:
            raise not_found("khoảng khóa phòng")
        details = {"room_id": str(row.room_id), "day": row.day.isoformat()}
        await session.delete(row)
        await session.flush()
        await audit.record(session, ctx, "room_block.delete", "room_block", block_id, details)

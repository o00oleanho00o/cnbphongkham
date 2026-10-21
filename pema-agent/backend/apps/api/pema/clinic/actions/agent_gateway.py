"""What the clinic's agent may do: the actions behind ``/agent-gateway`` (docs/PLAN-crm-plugin.md).

New module. The agent acts for ONE person: the one of a chat link (``channel`` + ``external_id``, set by the
agent's code from the chat, never by its model). The link names the patient on the server
(``clinic.patient_channel``); the agent never holds a patient id and every appointment it names must be of
that patient, or it is "not found". Nothing returned names anyone.

* free start times: steps of 15 minutes in the opening hours, at least ``MIN_LEAD`` ahead; a time is free
  while fewer active visits overlap it than there are active doctors (a booking of the agent has no doctor
  yet: the desk assigns one). Rooms and shifts are not read (the desk's validator does not read shifts);
* a contact is saved once: the first time makes a patient (``source = agent:<channel>``) and the link; later
  saves never change the patient, only the person's consent to reminders (``consent`` of kind
  ``messaging``). Phones are never matched against existing patients: that would let anyone stand for a
  patient by giving their number;
* booking and moving reuse the desk's validator (``validate_and_check``) under one more advisory lock, the
  capacity lock, so two bookings of the agent cannot both take the last free place; both need an
  ``Idempotency-Key``. At most ``MAX_UPCOMING`` coming visits per person and ``MAX_MOVES`` moves per visit;
* confirming and cancelling go through the desk's ``transition``, gated by the agent's permission;
* the reminder list is for the agent's reminder job: coming visits of linked people whose current
  ``messaging`` consent is granted, with ids, channel and times only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions import agent_events
from pema.clinic.actions._common import lost_race_is_conflict, not_found, now
from pema.clinic.actions.appointments import (
    DOCTOR_ROLES,
    announce,
    book_in_session,
    transition,
    validate_and_check,
)
from pema.clinic.actions.patients import CODE_RETRIES, next_patient_code
from pema.clinic.domain import appointments as rules
from pema.clinic.domain.phone import normalize_vn_phone
from pema.clinic.models import Appointment, AuditLog, Consent, Patient, PatientChannel, UserAccount
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.agent_gateway import (
    AgentAppointmentOut,
    AgentBooking,
    AgentCancel,
    AgentReschedule,
    ContactOut,
    ContactSave,
    FreeDay,
    FreeSlotsOut,
    ReminderOut,
)
from pema_contracts.appointments import AppointmentCreate, AppointmentStatus, AppointmentTransition
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

P = Permission
SLOT_STEP = timedelta(minutes=15)
MIN_LEAD = timedelta(minutes=30)
MAX_DAYS = 14
MAX_UPCOMING = 2
MAX_MOVES = 3
MAX_LISTED = 10
MAX_REMINDERS = 500
ACTIVE = (AppointmentStatus.BOOKED.value, AppointmentStatus.CONFIRMED.value)
MAX_RECENT = 3
RECENT_WINDOW = timedelta(days=7)
MESSAGING = "messaging"
_FREE = [s.value for s in rules.FREE_STATUSES]
_LONGEST = timedelta(minutes=480)


def _out(row: Appointment) -> AgentAppointmentOut:
    return AgentAppointmentOut(
        id=row.id,
        starts_at=row.starts_at,
        duration_min=row.duration_min,
        status=AppointmentStatus(row.status),
    )


def _need_key(ctx: ActionContext) -> None:
    if not ctx.idempotency_key:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thiếu Idempotency-Key.")


async def _lock(session: AsyncSession, key: str) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


async def _link(
    session: AsyncSession, ctx: ActionContext, channel: str, external_id: str
) -> PatientChannel | None:
    return await session.scalar(
        select(PatientChannel).where(
            PatientChannel.clinic_id == ctx.clinic_id,
            PatientChannel.channel == channel,
            PatientChannel.external_id == external_id,
        )
    )


async def _require_link(
    session: AsyncSession, ctx: ActionContext, channel: str, external_id: str
) -> PatientChannel:
    link = await _link(session, ctx, channel, external_id)
    if link is None:
        raise DomainError(
            ErrorCode.INVALID_STATE, "Chưa lưu liên hệ của người này: lưu tên và số điện thoại trước."
        )
    return link


async def _own(
    session: AsyncSession, ctx: ActionContext, link: PatientChannel, appointment_id: UUID
) -> Appointment:
    row = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.clinic_id == ctx.clinic_id,
            Appointment.patient_id == link.patient_id,
        )
    )
    if row is None:
        raise not_found("lịch hẹn")
    return row


def _changeable(row: Appointment) -> None:
    if row.status not in ACTIVE or row.starts_at <= now():
        raise DomainError(
            ErrorCode.INVALID_STATE, "Lịch này đã qua, đã hủy hoặc đã bắt đầu; không đổi được nữa."
        )


def _check_time(starts_at: datetime, duration_min: int) -> None:
    clock = now()
    rules.validate_slot(starts_at, duration_min, clock, require_future=True)
    if starts_at < clock + MIN_LEAD:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Giờ hẹn phải cách bây giờ ít nhất 30 phút.")


async def _doctors(session: AsyncSession, ctx: ActionContext) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(UserAccount)
        .where(
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.active.is_(True),
            UserAccount.role.in_(DOCTOR_ROLES),
        )
    )
    return int(count or 0)


async def _visits(
    session: AsyncSession, ctx: ActionContext, start: datetime, end: datetime, exclude: UUID | None = None
) -> list[tuple[datetime, datetime]]:
    """Active visits that overlap ``[start, end)``, as (start, end)."""
    query = select(Appointment.starts_at, Appointment.duration_min).where(
        Appointment.clinic_id == ctx.clinic_id,
        Appointment.status.notin_(_FREE),
        Appointment.starts_at < end,
        Appointment.starts_at > start - _LONGEST,
    )
    if exclude is not None:
        query = query.where(Appointment.id != exclude)
    rows = (await session.execute(query)).all()
    return [(s, s + timedelta(minutes=d)) for s, d in rows if s + timedelta(minutes=d) > start]


def _overlapping(visits: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> int:
    return sum(1 for s, e in visits if s < end and e > start)


async def _check_place(
    session: AsyncSession,
    ctx: ActionContext,
    starts_at: datetime,
    duration_min: int,
    exclude: UUID | None = None,
) -> None:
    """Under the capacity lock: one more visit at this time still leaves a doctor for each."""
    await _lock(session, f"appt:{ctx.clinic_id}:agent-capacity")
    end = starts_at + timedelta(minutes=duration_min)
    taken = _overlapping(await _visits(session, ctx, starts_at, end, exclude), starts_at, end)
    if taken >= await _doctors(session, ctx):
        raise DomainError(
            ErrorCode.APPOINTMENT_CONFLICT,
            "Giờ này vừa hết chỗ; hãy chọn giờ khác.",
            details={"conflict": "capacity"},
        )


async def free_slots(
    db: ClinicDatabase, ctx: ActionContext, *, day_from: date, days: int = 1, duration_min: int = 30
) -> FreeSlotsOut:
    require(ctx, P.AGENT_SLOTS_READ)
    if not 1 <= days <= MAX_DAYS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"Chỉ xem được từ 1 đến {MAX_DAYS} ngày.")
    if not 5 <= duration_min <= 480:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thời lượng không hợp lệ.")
    clock = now()
    first = max(day_from, clock.astimezone(VN_TZ).date())
    opens = datetime.combine(first, rules.WORK_START, tzinfo=VN_TZ)
    closes = datetime.combine(first + timedelta(days=days - 1), rules.WORK_END, tzinfo=VN_TZ)
    async with db.session() as session:
        doctors = await _doctors(session, ctx)
        visits = await _visits(session, ctx, opens, closes)
    out: list[FreeDay] = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        start = datetime.combine(day, rules.WORK_START, tzinfo=VN_TZ)
        starts: list[datetime] = []
        length = timedelta(minutes=duration_min)
        while start + length <= datetime.combine(day, rules.WORK_END, tzinfo=VN_TZ):
            try:
                rules.validate_slot(start, duration_min, clock, require_future=True)
                free = start >= clock + MIN_LEAD and _overlapping(visits, start, start + length) < doctors
            except DomainError:
                free = False
            if free:
                starts.append(start)
            start += SLOT_STEP
        out.append(FreeDay(day=day, starts=starts))
    return FreeSlotsOut(duration_min=duration_min, days=out)


async def _new_patient(
    session: AsyncSession, ctx: ActionContext, full_name: str, phone: str, channel: str
) -> Patient:
    for _ in range(CODE_RETRIES):
        candidate = Patient(
            clinic_id=ctx.clinic_id,
            code=await next_patient_code(session, ctx),
            full_name=full_name,
            phone=phone,
            first_contact_at=now().astimezone(VN_TZ).date(),
            source=f"agent:{channel}",
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError:  # a desk booking took the same code meanwhile
            continue
        return candidate
    raise DomainError(ErrorCode.INTERNAL, "Không tạo được mã bệnh nhân. Vui lòng thử lại.")


async def save_contact(
    db: ClinicDatabase, ctx: ActionContext, channel: str, external_id: str, payload: ContactSave
) -> ContactOut:
    require(ctx, P.AGENT_CONTACT_WRITE)
    phone = normalize_vn_phone(payload.phone)
    if phone is None:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "Số điện thoại không hợp lệ: cần số di động hoặc số bàn Việt Nam."
        )
    async with db.session() as session:
        await _lock(session, f"agent-gw:{ctx.clinic_id}:{channel}:{external_id}")
        link = await _link(session, ctx, channel, external_id)
        created = link is None
        if link is None:
            patient = await _new_patient(session, ctx, payload.full_name, phone, channel)
            await audit.record(session, ctx, "patient.create", "patient", patient.id, {"code": patient.code})
            link = PatientChannel(
                clinic_id=ctx.clinic_id, channel=channel, external_id=external_id, patient_id=patient.id
            )
            session.add(link)
            await session.flush()
            await audit.record(
                session,
                ctx,
                "patient_channel.create",
                "patient_channel",
                link.id,
                {"patient_id": str(patient.id), "channel": channel},
            )
        consent = await agent_events.current_messages_consent(session, ctx.clinic_id, link.patient_id)
        wanted = payload.messages_consent
        if wanted is not None and wanted != consent:
            stamp = now()
            row = Consent(
                clinic_id=ctx.clinic_id,
                patient_id=link.patient_id,
                kind=MESSAGING,
                granted=wanted,
                granted_at=stamp if wanted else None,
                revoked_at=None if wanted else stamp,
                source=f"agent:{channel}",
            )
            session.add(row)
            await session.flush()
            await audit.record(
                session,
                ctx,
                "consent.record",
                "consent",
                row.id,
                {"patient_id": str(link.patient_id), "kind": MESSAGING, "granted": wanted},
            )
            await agent_events.record_person_changed(session, ctx, link.patient_id, messages_consent=wanted)
            consent = wanted
    return ContactOut(created=created, messages_consent=consent)


async def _upcoming(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> list[Appointment]:
    return list(
        (
            await session.scalars(
                select(Appointment)
                .where(
                    Appointment.clinic_id == ctx.clinic_id,
                    Appointment.patient_id == patient_id,
                    Appointment.status.in_(ACTIVE),
                    Appointment.starts_at > now(),
                )
                .order_by(Appointment.starts_at, Appointment.id)
                .limit(MAX_LISTED)
            )
        ).all()
    )


async def _recent_others(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> list[Appointment]:
    """The person's visits changed in the last days that are not coming any more (arrived, being seen, done,
    cancelled, missed), so the agent tells the status, not a guess that a visit was never saved. The status is
    all it learns: the reason of a cancellation and the note stay with staff."""
    return list(
        (
            await session.scalars(
                select(Appointment)
                .where(
                    Appointment.clinic_id == ctx.clinic_id,
                    Appointment.patient_id == patient_id,
                    Appointment.status.notin_(ACTIVE),
                    Appointment.updated_at > now() - RECENT_WINDOW,
                )
                .order_by(Appointment.updated_at.desc(), Appointment.id)
                .limit(MAX_RECENT)
            )
        ).all()
    )


async def book(
    db: ClinicDatabase, ctx: ActionContext, channel: str, external_id: str, payload: AgentBooking
) -> AgentAppointmentOut:
    require(ctx, P.AGENT_BOOKING_WRITE)
    _need_key(ctx)
    async with db.session() as session:
        link = await _require_link(session, ctx, channel, external_id)
        replayed = await audit.find_replayed_entity(session, ctx, "appointment.create")
        if replayed is not None:
            return _out(await _own(session, ctx, link, UUID(replayed)))
        _check_time(payload.starts_at, payload.duration_min)
        await _check_place(session, ctx, payload.starts_at, payload.duration_min)
        if len(await _upcoming(session, ctx, link.patient_id)) >= MAX_UPCOMING:
            raise DomainError(
                ErrorCode.INVALID_STATE,
                f"Người này đã có {MAX_UPCOMING} lịch sắp tới; hãy dời hoặc hủy một lịch trước.",
            )
        row, _ = await book_in_session(
            session,
            ctx,
            AppointmentCreate(
                patient_id=link.patient_id,
                starts_at=payload.starts_at,
                duration_min=payload.duration_min,
                note=payload.note,
            ),
        )
        created = _out(row)
        patient_id = row.patient_id
    announce(created.id, patient_id, "create", created.status)
    return created


async def my_appointments(
    db: ClinicDatabase, ctx: ActionContext, channel: str, external_id: str
) -> list[AgentAppointmentOut]:
    require(ctx, P.AGENT_APPOINTMENT_READ)
    async with db.session() as session:
        link = await _link(session, ctx, channel, external_id)
        if link is None:
            return []
        recent = await _recent_others(session, ctx, link.patient_id)
        return [_out(row) for row in [*await _upcoming(session, ctx, link.patient_id), *recent]]


async def reschedule(
    db: ClinicDatabase,
    ctx: ActionContext,
    channel: str,
    external_id: str,
    appointment_id: UUID,
    payload: AgentReschedule,
) -> AgentAppointmentOut:
    require(ctx, P.AGENT_APPOINTMENT_CHANGE)
    _need_key(ctx)
    async with db.session() as session:
        link = await _require_link(session, ctx, channel, external_id)
        row = await _own(session, ctx, link, appointment_id)
        if await audit.find_replay(session, ctx, "appointment.update", row.id):
            return _out(row)
        _changeable(row)
        moves = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.clinic_id == ctx.clinic_id,
                AuditLog.action == "appointment.update",
                AuditLog.entity_id == str(row.id),
                AuditLog.actor_type == ctx.actor_type.value,
            )
        )
        if (moves or 0) >= MAX_MOVES:
            raise DomainError(
                ErrorCode.INVALID_STATE, f"Lịch này đã dời {MAX_MOVES} lần; nhân viên sẽ liên hệ để xếp lại."
            )
        duration = payload.duration_min or row.duration_min
        _check_time(payload.starts_at, duration)
        await _check_place(session, ctx, payload.starts_at, duration, exclude=row.id)
        await validate_and_check(
            session,
            ctx,
            patient_id=row.patient_id,
            doctor_id=row.doctor_id,
            starts_at=payload.starts_at,
            duration_min=duration,
            exclude=row.id,
            require_future=True,
            room_id=row.room_id,
        )
        row.starts_at = payload.starts_at
        row.duration_min = duration
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "appointment.update",
            "appointment",
            row.id,
            {"changed_fields": ["starts_at", "duration_min"]},
        )
        await agent_events.record_appointment_changed(session, ctx, row)
        moved = _out(row)
        patient_id = row.patient_id
    announce(moved.id, patient_id, "update", moved.status)
    return moved


async def _current_version(
    db: ClinicDatabase, ctx: ActionContext, channel: str, external_id: str, appointment_id: UUID
) -> Appointment:
    async with db.session() as session:
        link = await _require_link(session, ctx, channel, external_id)
        row = await _own(session, ctx, link, appointment_id)
        _changeable(row)
        return row


async def confirm(
    db: ClinicDatabase, ctx: ActionContext, channel: str, external_id: str, appointment_id: UUID
) -> AgentAppointmentOut:
    require(ctx, P.AGENT_APPOINTMENT_CHANGE)
    row = await _current_version(db, ctx, channel, external_id, appointment_id)
    if row.status == AppointmentStatus.CONFIRMED.value:
        return _out(row)
    done = await transition(
        db,
        ctx,
        appointment_id,
        AppointmentTransition(version=row.version),
        verb="confirm",
        permission=P.AGENT_APPOINTMENT_CHANGE,
        allowed_from=rules.CONFIRM_FROM,
        target=AppointmentStatus.CONFIRMED,
    )
    return AgentAppointmentOut(
        id=done.id, starts_at=done.starts_at, duration_min=done.duration_min, status=done.status
    )


async def cancel(
    db: ClinicDatabase,
    ctx: ActionContext,
    channel: str,
    external_id: str,
    appointment_id: UUID,
    payload: AgentCancel,
) -> AgentAppointmentOut:
    require(ctx, P.AGENT_APPOINTMENT_CHANGE)
    row = await _current_version(db, ctx, channel, external_id, appointment_id)
    done = await transition(
        db,
        ctx,
        appointment_id,
        AppointmentTransition(version=row.version, reason=f"Khách hủy qua chat: {payload.reason}"),
        verb="cancel",
        permission=P.AGENT_APPOINTMENT_CHANGE,
        allowed_from=frozenset({AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED}),
        target=AppointmentStatus.CANCELLED,
        reason_required=True,
    )
    return AgentAppointmentOut(
        id=done.id, starts_at=done.starts_at, duration_min=done.duration_min, status=done.status
    )


async def reminders(db: ClinicDatabase, ctx: ActionContext, *, hours: int = 26) -> list[ReminderOut]:
    require(ctx, P.AGENT_REMINDERS_READ)
    if not 1 <= hours <= 48:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Chỉ xem được từ 1 đến 48 giờ tới.")
    clock = now()
    consent = (
        select(Consent.patient_id, Consent.granted)
        .where(Consent.clinic_id == ctx.clinic_id, Consent.kind == MESSAGING)
        .ext(distinct_on(Consent.patient_id))
        .order_by(Consent.patient_id, Consent.created_at.desc(), Consent.id.desc())
        .subquery()
    )
    async with db.session() as session:
        rows = await session.execute(
            select(Appointment, PatientChannel.channel, PatientChannel.external_id)
            .join(
                PatientChannel,
                (PatientChannel.patient_id == Appointment.patient_id)
                & (PatientChannel.clinic_id == Appointment.clinic_id),
            )
            .join(consent, consent.c.patient_id == Appointment.patient_id)
            .where(
                Appointment.clinic_id == ctx.clinic_id,
                Appointment.status.in_(ACTIVE),
                Appointment.starts_at > clock,
                Appointment.starts_at <= clock + timedelta(hours=hours),
                consent.c.granted.is_(True),
            )
            .order_by(Appointment.starts_at, Appointment.id)
            .limit(MAX_REMINDERS)
        )
        return [
            ReminderOut(
                appointment_id=a.id,
                channel=channel,
                external_id=external_id,
                starts_at=a.starts_at,
                duration_min=a.duration_min,
                status=AppointmentStatus(a.status),
                updated_at=a.updated_at,
            )
            for a, channel, external_id in rows.all()
        ]


__all__ = [
    "book",
    "cancel",
    "confirm",
    "free_slots",
    "my_appointments",
    "reminders",
    "reschedule",
    "save_contact",
]

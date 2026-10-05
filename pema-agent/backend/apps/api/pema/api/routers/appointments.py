"""Appointments (package B1). Conflict checks are server-side, in ``pema.clinic.actions.appointments``."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, Limit, Offset, cookie_scheme
from pema.clinic.actions import appointments
from pema_contracts.appointments import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatus,
    AppointmentTransition,
    AppointmentUpdate,
    FreeSlotOut,
    ScheduleOut,
    ScheduleView,
)
from pema_contracts.common import Page, VnDatetime

router = APIRouter(
    tags=["appointments"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get("/appointments", response_model=Page[AppointmentOut], summary="List appointments")
async def list_appointments(
    db: Database,
    ctx: Ctx,
    starts_from: VnDatetime | None = None,
    starts_to: VnDatetime | None = None,
    patient_id: UUID | None = None,
    doctor_id: UUID | None = None,
    appointment_status: AppointmentStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[AppointmentOut]:
    return await appointments.list_appointments(
        db,
        ctx,
        starts_from=starts_from,
        starts_to=starts_to,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=appointment_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/appointments/schedule",
    response_model=ScheduleOut,
    summary="The clinic board: one day or seven days, optionally one doctor",
    description=(
        "Every status is returned; the screen hides cancelled and missed by default. A doctor gets only "
        "their own appointments. Declared before `/appointments/{appointment_id}` so `schedule` is not "
        "read as an id."
    ),
)
async def get_schedule(
    db: Database,
    ctx: Ctx,
    day: date,
    view: ScheduleView = ScheduleView.DAY,
    doctor_id: UUID | None = None,
) -> ScheduleOut:
    return await appointments.list_schedule(db, ctx, day=day, view=view, doctor_id=doctor_id)


@router.get(
    "/appointments/free-slot",
    response_model=FreeSlotOut,
    summary="First free start of a day for a patient and a doctor",
)
async def get_free_slot(
    db: Database,
    ctx: Ctx,
    patient_id: UUID,
    day: date,
    doctor_id: UUID | None = None,
    duration_min: int = Query(default=30, ge=5, le=480),
) -> FreeSlotOut:
    return await appointments.find_free_slot(
        db, ctx, patient_id=patient_id, doctor_id=doctor_id, day=day, duration_min=duration_min
    )


@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment (validated; optional CRM task link)",
)
async def create_appointment(body: AppointmentCreate, db: Database, ctx: Ctx) -> AppointmentOut:
    return await appointments.create_appointment(db, ctx, body)


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut, summary="One appointment")
async def get_appointment(appointment_id: UUID, db: Database, ctx: Ctx) -> AppointmentOut:
    return await appointments.get_appointment(db, ctx, appointment_id)


@router.patch(
    "/appointments/{appointment_id}",
    response_model=AppointmentOut,
    summary="Reschedule or edit (optimistic lock on version)",
)
async def update_appointment(
    appointment_id: UUID, body: AppointmentUpdate, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.update_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/confirm",
    response_model=AppointmentOut,
    summary="Confirmed with the patient (booked to confirmed)",
)
async def confirm_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.confirm_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/check-in",
    response_model=AppointmentOut,
    summary="Patient arrived",
)
async def check_in_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.check_in_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/start",
    response_model=AppointmentOut,
    summary="Treatment started (arrived to in_progress)",
)
async def start_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.start_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/complete",
    response_model=AppointmentOut,
    summary="Treatment finished (in_progress to completed)",
)
async def complete_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.complete_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentOut,
    summary="Cancel with a reason",
)
async def cancel_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.cancel_appointment(db, ctx, appointment_id, body)


@router.post(
    "/appointments/{appointment_id}/miss",
    response_model=AppointmentOut,
    summary="Mark as no-show",
)
async def miss_appointment(
    appointment_id: UUID, body: AppointmentTransition, db: Database, ctx: Ctx
) -> AppointmentOut:
    return await appointments.miss_appointment(db, ctx, appointment_id, body)

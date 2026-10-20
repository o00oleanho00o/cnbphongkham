"""The agent gateway: what the clinic's agent may do, for the person of one chat (docs/PLAN-crm-plugin.md).

Only the agent's machine key opens these routes (``agent_gateway_auth``); no staff cookie does. A person is
``{channel}/{external_id}``, set by the agent's code from the chat it serves; the server finds the patient.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Security, status

from pema.api.agent_gateway_auth import agent_gateway, agent_gateway_scheme, count_person_write
from pema.api.dashboard_auth import Database
from pema.api.deps import ERROR_RESPONSES, IdempotencyKey
from pema.clinic.actions import agent_gateway as actions
from pema_contracts.actions import ActionContext
from pema_contracts.agent_gateway import (
    AgentAppointmentOut,
    AgentBooking,
    AgentCancel,
    AgentReschedule,
    ContactOut,
    ContactSave,
    FreeSlotsOut,
    ReminderOut,
)
from pema_contracts.roles import Permission

P = Permission
SlotsCtx = Annotated[ActionContext, agent_gateway(P.AGENT_SLOTS_READ)]
ContactCtx = Annotated[ActionContext, agent_gateway(P.AGENT_CONTACT_WRITE)]
BookingCtx = Annotated[ActionContext, agent_gateway(P.AGENT_BOOKING_WRITE)]
ReadCtx = Annotated[ActionContext, agent_gateway(P.AGENT_APPOINTMENT_READ)]
ChangeCtx = Annotated[ActionContext, agent_gateway(P.AGENT_APPOINTMENT_CHANGE)]
RemindersCtx = Annotated[ActionContext, agent_gateway(P.AGENT_REMINDERS_READ)]

router = APIRouter(
    prefix="/agent-gateway",
    tags=["agent-gateway"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(agent_gateway_scheme)],
)

Channel = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:-]{1,64}$", description="The chat channel.")]
ExternalId = Annotated[
    str, Path(pattern=r"^[A-Za-z0-9_.:@=-]{1,128}$", description="The person's id in that channel.")
]
PERSON = "/contacts/{channel}/{external_id}"


@router.get("/free-slots", response_model=FreeSlotsOut, summary="Free start times of the coming days")
async def get_free_slots(
    db: Database,
    ctx: SlotsCtx,
    day_from: date,
    days: int = Query(default=1, ge=1, le=14),
    duration_min: int = Query(default=30, ge=5, le=480),
) -> FreeSlotsOut:
    return await actions.free_slots(db, ctx, day_from=day_from, days=days, duration_min=duration_min)


@router.put(PERSON, response_model=ContactOut, summary="Save the person's name and phone (once)")
async def save_contact(
    channel: Channel, external_id: ExternalId, body: ContactSave, db: Database, ctx: ContactCtx
) -> ContactOut:
    count_person_write(channel, external_id)
    return await actions.save_contact(db, ctx, channel, external_id, body)


@router.get(
    f"{PERSON}/appointments", response_model=list[AgentAppointmentOut], summary="The person's coming visits"
)
async def list_my_appointments(
    channel: Channel, external_id: ExternalId, db: Database, ctx: ReadCtx
) -> list[AgentAppointmentOut]:
    return await actions.my_appointments(db, ctx, channel, external_id)


@router.post(
    f"{PERSON}/appointments",
    response_model=AgentAppointmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book a visit for the person",
)
async def book_appointment(
    channel: Channel,
    external_id: ExternalId,
    body: AgentBooking,
    db: Database,
    ctx: BookingCtx,
    idempotency_key: IdempotencyKey = None,
) -> AgentAppointmentOut:
    count_person_write(channel, external_id)
    return await actions.book(db, ctx, channel, external_id, body)


@router.post(
    f"{PERSON}/appointments/{{appointment_id}}/confirm",
    response_model=AgentAppointmentOut,
    summary="The person confirms a coming visit",
)
async def confirm_appointment(
    channel: Channel, external_id: ExternalId, appointment_id: UUID, db: Database, ctx: ChangeCtx
) -> AgentAppointmentOut:
    count_person_write(channel, external_id)
    return await actions.confirm(db, ctx, channel, external_id, appointment_id)


@router.post(
    f"{PERSON}/appointments/{{appointment_id}}/reschedule",
    response_model=AgentAppointmentOut,
    summary="Move a coming visit of the person",
)
async def reschedule_appointment(
    channel: Channel,
    external_id: ExternalId,
    appointment_id: UUID,
    body: AgentReschedule,
    db: Database,
    ctx: ChangeCtx,
    idempotency_key: IdempotencyKey = None,
) -> AgentAppointmentOut:
    count_person_write(channel, external_id)
    return await actions.reschedule(db, ctx, channel, external_id, appointment_id, body)


@router.post(
    f"{PERSON}/appointments/{{appointment_id}}/cancel",
    response_model=AgentAppointmentOut,
    summary="Cancel a coming visit of the person",
)
async def cancel_appointment(
    channel: Channel,
    external_id: ExternalId,
    appointment_id: UUID,
    body: AgentCancel,
    db: Database,
    ctx: ChangeCtx,
) -> AgentAppointmentOut:
    count_person_write(channel, external_id)
    return await actions.cancel(db, ctx, channel, external_id, appointment_id, body)


@router.get(
    "/reminders",
    response_model=list[ReminderOut],
    summary="Coming visits of linked people who agreed to messages",
)
async def list_reminders(
    db: Database, ctx: RemindersCtx, hours: int = Query(default=26, ge=1, le=48)
) -> list[ReminderOut]:
    return await actions.reminders(db, ctx, hours=hours)

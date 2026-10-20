"""What the agent must hear, written beside the change it tells about (docs/PLAN-crm-plugin.md 3.4).

New module. Two events, both ids, times and statuses only (no name, no phone), both a STATE not a delta so
that a duplicate, a late or a missed one cannot leave the agent wrong (it keeps the highest version):

* ``appointment.changed``: a visit of a person linked to a chat (``clinic.patient_channel``) was booked,
  moved, confirmed, cancelled, missed, completed... One event per link of the patient (normally one);
* ``person.changed``: the consent of a linked person to messages (consent kind ``messaging``) changed.

``record_*`` add the row to the CALLER's session, so it commits or rolls back with the change, and after the
commit wake the worker (``set_waker``). With no ``PEMA_AGENT_EVENTS_URL`` they do nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.actions._common import now
from pema.clinic.models import Appointment, Consent, PatientChannel
from pema.clinic.models.agent_event import AgentEvent
from pema.config.env import get_settings
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext

log = create_logger("agent.events")

APPOINTMENT_CHANGED = "appointment.changed"
PERSON_CHANGED = "person.changed"
MESSAGING = "messaging"

_waker: Callable[[], None] | None = None


def set_waker(waker: Callable[[], None] | None) -> None:
    """Install (or remove, with ``None``) what runs after a commit that wrote events: it wakes the worker."""
    global _waker
    _waker = waker


def enabled() -> bool:
    url = get_settings().agent_events_url
    return bool(url and url.strip())


def _wake_after_commit(session: AsyncSession) -> None:
    def wake(_session: Any) -> None:
        waker = _waker
        if waker is None:
            return
        try:
            waker()
        except Exception as err:  # a broken waker must never fail the clinic operation
            log.error("agent event waker failed", err=err)

    event.listen(session.sync_session, "after_commit", wake, once=True)


async def current_messages_consent(session: AsyncSession, clinic_id: UUID, patient_id: UUID) -> bool | None:
    """The current consent of kind ``messaging``: the newest row (``consent`` is an append-only history)."""
    return await session.scalar(
        select(Consent.granted)
        .where(Consent.clinic_id == clinic_id, Consent.patient_id == patient_id, Consent.kind == MESSAGING)
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .limit(1)
    )


async def _links(session: AsyncSession, clinic_id: UUID, patient_id: UUID) -> list[PatientChannel]:
    rows = await session.scalars(
        select(PatientChannel)
        .where(PatientChannel.clinic_id == clinic_id, PatientChannel.patient_id == patient_id)
        .order_by(PatientChannel.created_at, PatientChannel.id)
    )
    return list(rows)


def _add(session: AsyncSession, clinic_id: UUID, kind: str, payload: dict[str, Any]) -> None:
    session.add(AgentEvent(clinic_id=clinic_id, kind=kind, payload=payload))
    _wake_after_commit(session)


async def record_appointment_changed(session: AsyncSession, ctx: ActionContext, row: Appointment) -> None:
    """Call after the flush that changed ``row`` (its ``version`` is the new one)."""
    if not enabled():
        return
    links = await _links(session, ctx.clinic_id, row.patient_id)
    if not links:
        return
    consent = await current_messages_consent(session, ctx.clinic_id, row.patient_id)
    for link in links:
        _add(
            session,
            ctx.clinic_id,
            APPOINTMENT_CHANGED,
            {
                "appointment_id": str(row.id),
                "channel": link.channel,
                "external_id": link.external_id,
                "starts_at": row.starts_at.isoformat(),
                "duration_min": row.duration_min,
                "status": row.status,
                "version": row.version,
                "messages_consent": consent,
                "actor_type": ctx.actor_type.value,
                "occurred_at": now().isoformat(),
            },
        )


async def record_person_changed(
    session: AsyncSession, ctx: ActionContext, patient_id: UUID, *, messages_consent: bool | None
) -> None:
    """Call after the consent row of kind ``messaging`` of ``patient_id`` was added."""
    if not enabled():
        return
    for link in await _links(session, ctx.clinic_id, patient_id):
        _add(
            session,
            ctx.clinic_id,
            PERSON_CHANGED,
            {
                "channel": link.channel,
                "external_id": link.external_id,
                "messages_consent": messages_consent,
                "actor_type": ctx.actor_type.value,
                "occurred_at": now().isoformat(),
            },
        )

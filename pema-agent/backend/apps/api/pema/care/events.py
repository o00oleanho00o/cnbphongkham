"""``CareEvent``: what wakes a care agent (PLAN-AI01-M section 3). New module (not a port).

Every source (the Zalo webhook of C1/C2, the CRM rule engine of B2, the scheduler of S, the dashboard) turns
what happened into one ``CareEvent`` and publishes it; they all enter the same pipeline and differ only in
``initiator``. ``patient_ref`` is the pseudonym patient code, never a name or a phone number, and ``payload``
carries ids and codes only (the text of a patient message stays in the history store, the harness reads it
from there).

``priority_of`` is the 3-level order of the one sequential worker (one GPU, PLAN-M section 2): a patient
who is writing now, before an event that came due, before the daily tick.

``event_kind_for_rule`` maps the rule keys of the CRM engine (B2, ``pema_contracts.crm.RuleKey``) to event
kinds: d1/d3/d7/due -> ``milestone_due``, overdue -> ``visit_overdue``, no_show -> ``no_show``,
dormant90/dormant180/abandoned -> ``dormant`` (assumption for ``abandoned``: a plan the patient let go is a
patient gone quiet), birthday -> ``birthday``. ``manual`` tasks are written by staff for staff and wake
nobody.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import Field

from pema_contracts.common import ApiModel, JsonObject
from pema_contracts.crm import RuleKey


class EventKind(StrEnum):
    PATIENT_MESSAGE = "patient_message"
    SESSION_COMPLETED = "session_completed"
    MILESTONE_DUE = "milestone_due"
    VISIT_OVERDUE = "visit_overdue"
    NO_SHOW = "no_show"
    DORMANT = "dormant"
    BIRTHDAY = "birthday"
    STAFF_COMMAND = "staff_command"
    DOCTOR_EDIT = "doctor_edit"
    DAILY_TICK = "daily_tick"


class Initiator(StrEnum):
    PATIENT = "patient"
    SYSTEM = "system"
    STAFF = "staff"
    DOCTOR = "doctor"


class Priority(IntEnum):
    """Smaller runs first."""

    PATIENT_MESSAGE = 0
    DUE_EVENT = 1
    TICK = 2


class CareEvent(ApiModel):
    kind: EventKind
    initiator: Initiator
    patient_ref: str = Field(min_length=1, description="Pseudonym patient code; never a name or a phone.")
    payload: JsonObject = Field(default_factory=dict[str, Any])
    occurred_at: datetime


def priority_of(event: CareEvent) -> Priority:
    """patient message > due event (system events, staff commands, doctor edits) > tick."""
    if event.kind is EventKind.PATIENT_MESSAGE:
        return Priority.PATIENT_MESSAGE
    if event.kind is EventKind.DAILY_TICK:
        return Priority.TICK
    return Priority.DUE_EVENT


def is_proactive(event: CareEvent) -> bool:
    """A message the agent writes because of this event is proactive (counts against the daily cap) unless
    the patient is the one who just wrote."""
    return event.initiator is not Initiator.PATIENT


_RULE_KINDS: dict[RuleKey, EventKind] = {
    RuleKey.D1: EventKind.MILESTONE_DUE,
    RuleKey.D3: EventKind.MILESTONE_DUE,
    RuleKey.D7: EventKind.MILESTONE_DUE,
    RuleKey.DUE: EventKind.MILESTONE_DUE,
    RuleKey.OVERDUE: EventKind.VISIT_OVERDUE,
    RuleKey.NO_SHOW: EventKind.NO_SHOW,
    RuleKey.ABANDONED: EventKind.DORMANT,
    RuleKey.DORMANT90: EventKind.DORMANT,
    RuleKey.DORMANT180: EventKind.DORMANT,
    RuleKey.BIRTHDAY: EventKind.BIRTHDAY,
}


def event_kind_for_rule(rule: RuleKey) -> EventKind | None:
    """``None`` for ``manual`` (a staff task, not a care event)."""
    return _RULE_KINDS.get(rule)


def event_from_rule(rule: RuleKey, patient_ref: str, occurred_at: datetime) -> CareEvent | None:
    """The event a CRM rule task of the engine (B2) turns into; ``None`` when the rule wakes no agent."""
    kind = event_kind_for_rule(rule)
    if kind is None:
        return None
    return CareEvent(
        kind=kind,
        initiator=Initiator.SYSTEM,
        patient_ref=patient_ref,
        payload={"rule": rule.value},
        occurred_at=occurred_at,
    )

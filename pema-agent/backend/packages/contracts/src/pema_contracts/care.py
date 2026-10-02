"""Supervision DTOs of the per-patient care agent (package M, step M5). New module (not a port).

What staff see and do around a care agent: who is waiting for them (``GET /care/handoffs``), the
timeline of one
patient's agent, "return to the agent" (with an optional, time-boxed LOWER level), "tell the agent", and the
administration of skills, shifts, the 24/7 on-call contact, the depth/autonomy matrix, SLA and alerts.

Rules this contract keeps (PLAN-AI01-M sections 11 and 12):

* The FE holds no business rule. Every decision it shows comes in a field of these DTOs: ``can_accept``,
  ``can_release``, ``release_levels`` (the levels a release may use: it only lowers), ``consequence`` (the
  sentence of the preview), ``can_edit`` / ``can_approve`` of the matrix.
* No clinical record data. ``summary`` is the PII-masked context line written when the round opened; memory
  facts are short preferences; codes (``reason``, ``code``) are machine strings the FE words in Vietnamese.
* Staff-only information (patient and staff display names) is returned to the staff routes only, like the
  inbox does; the live events (``handoff.changed``, ``care.changed``) carry ids, never names.
* The thresholds of the matrix are TEMPORARY until the doctor confirms them: ``pending_doctor_approval``
  is the
  badge, and only a role that holds ``care.approve`` may clear it. Any edit of a cell sets it again.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.review import ReviewKind


class CareControlState(StrEnum):
    AUTO = "AUTO"
    HANDOFF_ROUTING = "HANDOFF_ROUTING"
    STAFF = "STAFF"


class CareDepth(StrEnum):
    """How deep a question goes: D1 administrative ... D5 red flag (PLAN-AI01-M section 6)."""

    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"
    D5 = "D5"


class CareUrgency(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"


class CareLevel(StrEnum):
    """Autonomy level of the agent: L0 drafts only, L1 approved templates, L2 plus KB answers."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class MemorySourceOut(StrEnum):
    PATIENT = "patient"
    STAFF = "staff"
    DOCTOR_EDIT = "doctor_edit"


# ==================================================================================== handoffs
class HandoffWaitingOut(ApiModel):
    """One routing round that is waiting for a person."""

    patient_id: UUID
    patient_name: str = Field(max_length=200, description="Display name; staff-only information.")
    reason: str = Field(max_length=200, description="Code of the signal that decided (never patient text).")
    summary: str = Field(
        max_length=1000, description="PII-masked summary of the context, written by the agent."
    )
    depth: CareDepth
    urgency: CareUrgency
    confidence: float = Field(ge=0.0, le=1.0)
    required_skill: str | None = None
    opened_at: VnDatetime
    sla_due_at: VnDatetime | None = Field(
        default=None, description="When the person asked now must answer by."
    )
    position: int = Field(ge=1, description="1-based place of the asked person in the chain.")
    chain_length: int = Field(ge=1)
    on_call_step: bool = Field(description="The chain reached the 24/7 on-call contact.")
    suggested_by_name: str | None = Field(
        default=None, max_length=200, description="A colleague who suggested the person asked."
    )
    mine: bool = Field(description="The caller is the person being asked now.")
    can_accept: bool
    can_decline: bool


class HandoffListOut(ApiModel):
    items: list[HandoffWaitingOut]


class HandoffDeclineIn(ApiModel):
    reason: str = Field(
        min_length=1, max_length=500, description="Free text, kept for the routing, not for the patient."
    )
    suggest_user_id: UUID | None = Field(default=None, description="Another colleague who should take it.")


class HandoffResultOut(ApiModel):
    patient_id: UUID
    state: CareControlState
    outcome: str | None = Field(default=None, description="``accepted`` once somebody took it, else null.")


# ===================================================================================== timeline
class TimelineEntryKind(StrEnum):
    SENT = "sent"
    """The agent sent a message on its own (autonomy level allowed it)."""
    REVIEWED = "reviewed"
    """A person reviewed a draft (``detail`` says approved, edited or rejected)."""
    PAUSED = "paused"
    """The agent held something for a person (a draft, a reminder, a state change)."""
    CONTROL = "control"
    """The conversation changed state (AUTO, HANDOFF_ROUTING, STAFF)."""
    AUTONOMY = "autonomy"
    """The autonomy level changed (demotion, promotion, override)."""


class TimelineEntryOut(ApiModel):
    id: str
    at: VnDatetime
    kind: TimelineEntryKind
    code: str = Field(max_length=200, description="Machine code of the action; the FE words it.")
    depth: CareDepth | None = None
    actor_name: str | None = Field(default=None, max_length=200)
    detail: str | None = Field(default=None, max_length=500)


class PendingDraftOut(ApiModel):
    review_item_id: UUID
    kind: ReviewKind
    created_at: VnDatetime
    requires_doctor: bool


class PausedReminderOut(ApiModel):
    id: UUID
    event_kind: str
    due_at: VnDatetime
    paused_at: VnDatetime
    prepared_text: str | None = Field(default=None, max_length=1000)


class MemoryFactOut(ApiModel):
    id: UUID
    fact: str = Field(max_length=500)
    source: MemorySourceOut
    created_at: VnDatetime
    valid_until: VnDatetime | None = None


class OpenHandoffOut(ApiModel):
    reason: str
    summary: str
    depth: CareDepth
    urgency: CareUrgency
    confidence: float = Field(ge=0.0, le=1.0)
    required_skill: str | None = None
    opened_at: VnDatetime
    current_candidate_name: str | None = None
    sla_due_at: VnDatetime | None = None


class CareControlOut(ApiModel):
    state: CareControlState
    since: VnDatetime
    staff_owner_id: UUID | None = None
    staff_owner_name: str | None = Field(default=None, max_length=200)
    release_note: str | None = Field(default=None, max_length=500)


class CareAutonomyOut(ApiModel):
    effective_level: CareLevel
    base_level: CareLevel
    override_level: CareLevel | None = None
    override_until: VnDatetime | None = None
    paused: bool


class PatientCareTimelineOut(ApiModel):
    patient_id: UUID
    patient_name: str = Field(max_length=200)
    control: CareControlOut
    autonomy: CareAutonomyOut
    open_handoff: OpenHandoffOut | None = None
    pending_drafts: list[PendingDraftOut]
    paused_reminders: list[PausedReminderOut]
    entries: list[TimelineEntryOut]
    memory: list[MemoryFactOut]
    can_release: bool = Field(description="The conversation is in STAFF and the caller may return it.")
    can_tell_agent: bool
    release_levels: list[CareLevel] = Field(
        description="Levels a release may set: a release only LOWERS the level, never raises it."
    )
    max_override_days: int = Field(ge=1, description="Longest time-boxed override a release may set.")


class ReleaseIn(ApiModel):
    """Return the conversation to the agent. ``level`` null keeps the agent's own level; a level needs
    ``days`` (how long it applies) and must not be above the agent's own."""

    note: str = Field(
        default="", max_length=500, description="Handover note; PII is masked before it is stored."
    )
    level: CareLevel | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class ReleasePreviewOut(ApiModel):
    allowed: bool
    consequence: str = Field(
        max_length=500, description="What the agent will do after the release (Vietnamese)."
    )


class ReleaseResultOut(ApiModel):
    patient_id: UUID
    state: CareControlState
    override_level: CareLevel | None = None
    override_until: VnDatetime | None = None


class TellAgentIn(ApiModel):
    instruction: str = Field(
        min_length=1, max_length=500, description="Free text; PII is masked before it is stored."
    )


class TellAgentOut(ApiModel):
    memory_id: UUID
    source: MemorySourceOut = MemorySourceOut.STAFF


# ======================================================================================= admin
Hhmm = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class ShiftIntervalOut(ApiModel):
    start: Hhmm
    end: Hhmm = Field(description="An end earlier than the start means the shift ends the next morning.")


class ShiftOut(ApiModel):
    """Weekly shift of a person: a list of intervals per weekday (local clinic time)."""

    mon: list[ShiftIntervalOut]
    tue: list[ShiftIntervalOut]
    wed: list[ShiftIntervalOut]
    thu: list[ShiftIntervalOut]
    fri: list[ShiftIntervalOut]
    sat: list[ShiftIntervalOut]
    sun: list[ShiftIntervalOut]


SkillName = Annotated[str, StringConstraints(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")]


class StaffCareProfileOut(ApiModel):
    user_id: UUID
    name: str = Field(max_length=200)
    role: str
    skills: list[str]
    shift: ShiftOut
    capacity: int = Field(ge=1)
    languages: list[str]
    load: int = Field(ge=0, description="Conversations in STAFF state that the person owns now.")
    version: int


class StaffCareProfileIn(ApiModel):
    skills: list[SkillName] = Field(max_length=30)
    shift: ShiftOut
    capacity: int = Field(ge=1, le=50)
    languages: list[Annotated[str, StringConstraints(min_length=2, max_length=8)]] = Field(max_length=5)
    version: int = Field(description="Optimistic lock: the version that was read.")


class StaffCareProfileListOut(ApiModel):
    items: list[StaffCareProfileOut]
    known_skills: list[str] = Field(description="Skills the routing knows (suggestions for the editor).")


class OnCallContactOut(ApiModel):
    id: UUID
    zalo_number: str = Field(description="Staff-only (care.admin). Never logged and never sent to the model.")
    owner: str = Field(max_length=200)
    valid_from: VnDatetime
    valid_to: VnDatetime | None = None
    active: bool
    is_fixture: bool = Field(description="A test number; the screen flags it as not a real contact.")
    version: int


OnCallNumber = Annotated[str, StringConstraints(pattern=r"^\+?\d{8,15}$")]


class OnCallContactIn(ApiModel):
    zalo_number: OnCallNumber
    owner: str = Field(min_length=1, max_length=200)
    valid_from: VnDatetime | None = None
    valid_to: VnDatetime | None = None
    active: bool = True
    version: int | None = Field(default=None, description="Required to change an existing contact.")


class OnCallListOut(ApiModel):
    items: list[OnCallContactOut]
    chain_ends_with_on_call: bool = Field(
        description="True while an active contact exists: the chain always ends at the 24/7 number."
    )


class DepthSignal(StrEnum):
    """Signals of the handoff skill that have their own "hand off from depth X" cell."""

    DEFAULT = "default"
    VIP = "vip"
    COMPLEX_HISTORY = "complex_history"
    PAST_COMPLAINT = "past_complaint"
    PENDING_DOCTOR_WORK = "pending_doctor_work"
    POST_PROCEDURE = "post_procedure"
    OUT_OF_HOURS = "out_of_hours"
    ASKS_FOR_HUMAN = "asks_for_human"
    NEGATIVE_SENTIMENT = "negative_sentiment"
    REPEATED_QUESTION = "repeated_question"
    ANSWER_REJECTED = "answer_rejected"
    URGENT = "urgent"


class DepthRowOut(ApiModel):
    signal: DepthSignal
    from_depth: CareDepth


class HandoffMatrixOut(ApiModel):
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    unverified_max_depth: CareDepth
    post_procedure_window_hours: int = Field(ge=0, le=720)
    repeat_question_threshold: int = Field(ge=2, le=10)
    rows: list[DepthRowOut]


class AutonomyRuleOut(ApiModel):
    action_type: str = Field(max_length=100)
    hard_human: bool = Field(description="Always a person; the cell cannot be edited.")
    n_to_l2: int | None = Field(
        default=None, ge=1, le=1000, description="Unchanged approvals before L2; null: none."
    )
    d3_enabled: bool


class AutonomyMatrixOut(ApiModel):
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    appointment_confirm_l1: bool
    rules: list[AutonomyRuleOut]


class CareMatrixOut(ApiModel):
    pending_doctor_approval: bool = Field(
        description="The badge: the numbers are defaults until a doctor approves."
    )
    can_edit: bool
    can_approve: bool
    handoff: HandoffMatrixOut
    autonomy: AutonomyMatrixOut
    version: int


class CareMatrixIn(ApiModel):
    """Cells of the matrix. Saving sets ``pending_doctor_approval`` again (whoever edits)."""

    handoff: HandoffMatrixOut
    autonomy: AutonomyMatrixOut
    version: int


class CareApprovalIn(ApiModel):
    approved: bool = Field(description="True clears the badge, false puts it back.")
    version: int


class CareTimingOut(ApiModel):
    sla_urgent_minutes: int = Field(ge=1, le=240)
    sla_normal_minutes: int = Field(ge=1, le=1440)
    max_candidates: int = Field(ge=2, le=10, description="Chain length including the on-call contact.")
    oncall_direct_from_depth: CareDepth
    send_window_start: Hhmm | None = Field(
        default=None, description="Read only here: edited in the channel settings."
    )
    send_window_end: Hhmm | None = None
    time_zone: str
    pending_doctor_approval: bool
    can_edit: bool
    version: int


class CareTimingIn(ApiModel):
    sla_urgent_minutes: int = Field(ge=1, le=240)
    sla_normal_minutes: int = Field(ge=1, le=1440)
    max_candidates: int = Field(ge=2, le=10)
    oncall_direct_from_depth: CareDepth
    version: int


class CareAlertKind(StrEnum):
    DEMOTION = "demotion"
    UNRESPONSIVE = "unresponsive"
    RED_FLAG = "red_flag"
    ON_CALL_USED = "on_call_used"


class CareAlertOut(ApiModel):
    id: str
    kind: CareAlertKind
    at: VnDatetime
    patient_id: UUID | None = None
    patient_name: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=200)


class CareAlertListOut(ApiModel):
    items: list[CareAlertOut]


__all__ = [
    "AutonomyMatrixOut",
    "AutonomyRuleOut",
    "CareAlertKind",
    "CareAlertListOut",
    "CareAlertOut",
    "CareApprovalIn",
    "CareAutonomyOut",
    "CareControlOut",
    "CareControlState",
    "CareDepth",
    "CareLevel",
    "CareMatrixIn",
    "CareMatrixOut",
    "CareTimingIn",
    "CareTimingOut",
    "CareUrgency",
    "DepthRowOut",
    "DepthSignal",
    "HandoffDeclineIn",
    "HandoffListOut",
    "HandoffMatrixOut",
    "HandoffResultOut",
    "HandoffWaitingOut",
    "MemoryFactOut",
    "MemorySourceOut",
    "OnCallContactIn",
    "OnCallContactOut",
    "OnCallListOut",
    "OpenHandoffOut",
    "PatientCareTimelineOut",
    "PausedReminderOut",
    "PendingDraftOut",
    "ReleaseIn",
    "ReleasePreviewOut",
    "ReleaseResultOut",
    "ShiftIntervalOut",
    "ShiftOut",
    "StaffCareProfileIn",
    "StaffCareProfileListOut",
    "StaffCareProfileOut",
    "TellAgentIn",
    "TellAgentOut",
    "TimelineEntryKind",
    "TimelineEntryOut",
]

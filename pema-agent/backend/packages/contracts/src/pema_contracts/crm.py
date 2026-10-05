"""CRM DTOs: rules, tasks, activities (tables ``clinic.crm_rule/crm_task/crm_activity``).

Ported from ``prototype/shared/crm-data.js`` and ``crm-automation.js``. The rule engine itself lives
in ``pema.clinic.crm_rules`` (package B2); these DTOs are only the wire shape.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from pema_contracts.appointments import AppointmentCreate
from pema_contracts.common import ApiModel, VnDatetime


class RuleKey(StrEnum):
    """The 10 automation rules (JS ids). ``manual`` tasks are created by staff."""

    D1 = "d1"
    D3 = "d3"
    D7 = "d7"
    DUE = "due"
    OVERDUE = "overdue"
    NO_SHOW = "no_show"
    ABANDONED = "abandoned"
    DORMANT90 = "dormant90"
    DORMANT180 = "dormant180"
    BIRTHDAY = "birthday"
    MANUAL = "manual"


class TaskPriority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TaskStatus(StrEnum):
    OPEN = "open"
    RESCHEDULED = "rescheduled"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class RuleSendMode(StrEnum):
    """What the system may do beyond creating the staff task. Birthday is never auto-sent."""

    STAFF_TASK = "staff_task"
    """Task only; staff contact the patient (default, JS ``actionType``)."""
    AUTO_REMINDER = "auto_reminder"
    """Simple appointment reminder that may self-approve and go out on a proactive channel."""
    DRAFT_FOR_REVIEW = "draft_for_review"
    """AI drafts the message; a human approves before it is sent."""


class CrmChannel(StrEnum):
    """JS labels: Goi dien, Zalo, SMS, Ghi chu noi bo."""

    CALL = "call"
    ZALO = "zalo"
    SMS = "sms"
    INTERNAL_NOTE = "internal_note"


class CrmOutcome(StrEnum):
    """The 10 contact outcomes (JS ``outcomes``)."""

    UNANSWERED = "unanswered"
    CALLBACK = "callback"
    NO_NEED = "no_need"
    BUSY = "busy"
    BOOKED = "booked"
    DOCTOR = "doctor"
    REACTION = "reaction"
    COMPLAINT = "complaint"
    OPTOUT = "optout"
    INVALID = "invalid"


class CrmRuleOut(ApiModel):
    id: UUID
    rule_key: RuleKey
    name: str
    trigger: str
    delay_days: int
    suggested_action: str
    priority: TaskPriority
    active: bool
    send_mode: RuleSendMode = RuleSendMode.STAFF_TASK
    conditions: dict[str, Any] = Field(default_factory=dict)
    version: int


class CrmRuleUpdate(ApiModel):
    version: int
    active: bool | None = None
    delay_days: int | None = Field(default=None, ge=0, le=730)
    priority: TaskPriority | None = None
    suggested_action: str | None = Field(default=None, max_length=500)
    send_mode: RuleSendMode | None = None


class CrmTaskOut(ApiModel):
    id: UUID
    patient_id: UUID
    patient_code: str
    rule_key: RuleKey
    task_key: str = Field(description="Idempotency key: rule + patient + source event.")
    reason: str
    priority: TaskPriority
    status: TaskStatus
    owner_user_id: UUID | None = None
    owner_name: str | None = None
    due_at: VnDatetime
    created_at: VnDatetime
    suggested_action: str
    source_event_id: str | None = None
    related_appointment_id: UUID | None = None
    resolution: str | None = None
    resolved_at: VnDatetime | None = None
    version: int


class CrmTaskResolve(ApiModel):
    """Finish a task by logging one contact attempt (JS ``resolve`` / ``finish``)."""

    version: int
    outcome: CrmOutcome
    channel: CrmChannel
    note: str = Field(min_length=1, max_length=2000)
    owner_user_id: UUID
    next_action_at: VnDatetime | None = Field(
        default=None, description="Required for unanswered, callback and busy."
    )
    priority: TaskPriority | None = None
    booking: AppointmentCreate | None = Field(
        default=None, description="Required when outcome is booked; saved in the same transaction."
    )


class CrmActivityOut(ApiModel):
    id: UUID
    patient_id: UUID
    task_id: UUID | None
    kind: str = Field(description="'cskh' or 'complaint'.")
    channel: CrmChannel
    outcome: CrmOutcome | None
    note: str
    actor_user_id: UUID | None
    actor_name: str | None = None
    occurred_at: VnDatetime
    next_action_at: VnDatetime | None = None
    related_appointment_id: UUID | None = None


class CrmActivityCreate(ApiModel):
    """Manual internal note / contact log not tied to closing a task."""

    patient_id: UUID
    task_id: UUID | None = None
    channel: CrmChannel
    outcome: CrmOutcome | None = None
    note: str = Field(min_length=1, max_length=2000)
    next_action_at: VnDatetime | None = None


class CrmProfile(ApiModel):
    """Read model computed from visits, plans and appointments (JS ``profile``)."""

    lifecycle_stage: str
    last_visit_at: date | None = None
    expected_next_visit_at: date | None = None
    expected_visit_source: str | None = None
    overdue_days: int = 0
    remaining_sessions: int = 0
    risk_level: str = "normal"
    marketing_opt_out: bool = False


class MessageTemplateOut(ApiModel):
    """An approved text a ``kind: message`` job may send in ``patient_channel`` (table
    ``clinic.message_template``). Only a doctor approves; an unapproved template is never active."""

    id: UUID
    template_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$", max_length=64)
    title: str
    body: str = Field(max_length=2000)
    marketing: bool = Field(
        default=False, description="Obeys marketing_opt_out. Birthday is never auto-sent."
    )
    active: bool
    approved_by: UUID | None = None
    approved_at: VnDatetime | None = None
    version: int


class MessageTemplateCreate(ApiModel):
    template_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$", max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    marketing: bool = False


class MessageTemplateUpdate(ApiModel):
    version: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    marketing: bool | None = None
    active: bool | None = None


class MessageTemplateApprove(ApiModel):
    """Doctor sign-off. Editing the body afterwards clears the approval (version bump)."""

    version: int


class CrmSegmentKey(StrEnum):
    """Customer groups of the old CRM01 ``segment`` card: the five lifecycle stages (``stageLabels`` of
    ``crm-automation.js``) and ``at_risk``, which cuts across them (no new booking and overdue by more than
    7 days, or sessions left and more than 45 days idle)."""

    NEW = "new"
    RETURNING = "returning"
    TREATING = "treating"
    DORMANT = "dormant"
    REACTIVATED = "reactivated"
    AT_RISK = "at_risk"


class CrmSegmentCount(ApiModel):
    key: CrmSegmentKey
    count: int = Field(ge=0)


class CrmSegmentsOut(ApiModel):
    """One number per group, computed from the same read model as Patient 360 (``compute_profile``)."""

    total_patients: int = Field(ge=0)
    segments: list[CrmSegmentCount]
    marketing_opt_out: int = Field(ge=0, description="Patients who asked not to receive marketing.")


class CrmSegmentPatientOut(ApiModel):
    """A row of the list behind one segment card. ``version`` is the lock of ``PATCH /patients/{id}``, which
    the opt-out switch uses (audited there)."""

    patient_id: UUID
    patient_code: str
    full_name: str
    version: int
    lifecycle_stage: CrmSegmentKey
    last_visit_at: date | None = None
    expected_next_visit_at: date | None = None
    overdue_days: int = Field(ge=0)
    remaining_sessions: int = Field(ge=0)
    risk_level: str
    marketing_opt_out: bool
    cs_owner_name: str | None = None

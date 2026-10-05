# ported from: prototype/shared/crm-automation.js (the shapes of patient, appointment, session, task)
"""Plain immutable inputs and outputs of the rule engine.

The engine is pure: no I/O and no clock. The caller (``runner``) loads these snapshots from Postgres (or a
fixture) and passes ``now``. Ids that come from the source system are opaque strings (``source_event_id``,
appointment and session ids): they end up inside the task key ``CRM:<rule>:<patient code>:<source>``
exactly as
in the JavaScript, which is what makes the task set comparable with the original run for run.

Mapping of the JavaScript ``patient`` to ``PatientSnapshot``:

====================================  ===========================================================
JavaScript                            Python
====================================  ===========================================================
``p.id`` (``'P025'``)                 ``code`` (the key uses the code); ``id`` is the uuid
``p.doctor`` / ``p.crm.owner``        ``doctor_id`` / ``cs_owner_id`` (user ids)
``p.lastVisit``                       ``last_visit`` (latest completed session day)
``p.total`` / ``p.completed``         ``total_sessions`` / ``completed_sessions`` of open plans
``p.crm.birthday``                    ``birth_date``
``p.crm.recommendationAt`` & co       ``recommendation_at``, ``expected_visit_*``
``p.crm.lastProtocolSession``         ``last_protocol_session_id`` (clinic.patient column, migration b2_0001)
``p.servicePlans[0].id``              ``first_plan_id``
====================================  ===========================================================
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pema.clinic.crm_rules.protocols import ProtocolConfig
from pema.clinic.crm_rules.rules import RuleConfig
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey, TaskPriority, TaskStatus
from pema_contracts.policy import PolicyProfileKey

OPEN_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.OPEN, TaskStatus.RESCHEDULED})
"""``open(t)`` of the JavaScript: ``['open', 'rescheduled'].includes(t.status)``."""


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"


INACTIVE_APPOINTMENT_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.CANCELLED, AppointmentStatus.MISSED}
)
"""``!O.active(a)``: cancelled and missed appointments no longer count as a booking."""


class LifecycleStage(StrEnum):
    NEW = "new"
    RETURNING = "returning"
    TREATING = "treating"
    DORMANT = "dormant"
    REACTIVATED = "reactivated"


class RiskLevel(StrEnum):
    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    id: str
    day: date
    protocol_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppointmentSnapshot:
    id: str
    starts_at: datetime
    status: AppointmentStatus
    cancelled_at: datetime | None = None
    missed_at: datetime | None = None

    @property
    def day(self) -> date:
        """Clinic-local day of the appointment (``a.date``)."""
        return self.starts_at.astimezone(VN_TZ).date()

    @property
    def active(self) -> bool:
        return self.status not in INACTIVE_APPOINTMENT_STATUSES


@dataclass(frozen=True, slots=True)
class ChannelTarget:
    """Where an automatic message to this patient would go: a verified identity on an enabled account."""

    account_id: str
    thread_id: str
    thread_type: int = 0
    policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL
    """Effective profile of the account and its agent (the restrictive one wins). Fail safe by default."""


@dataclass(frozen=True, slots=True)
class PatientSnapshot:
    id: UUID
    code: str
    doctor_id: UUID | None = None
    cs_owner_id: UUID | None = None
    last_visit: date | None = None
    total_sessions: int = 0
    completed_sessions: int = 0
    sessions: tuple[SessionSnapshot, ...] = ()
    appointments: tuple[AppointmentSnapshot, ...] = ()
    birth_date: date | None = None
    marketing_opt_out: bool = False
    recommendation_at: date | None = None
    expected_visit_source: str | None = None
    expected_visit_reason: str | None = None
    last_protocol_session_id: str | None = None
    reactivated_at: datetime | None = None
    first_plan_id: str | None = None
    channel_target: ChannelTarget | None = None
    messaging_consent: bool = False
    """Latest ``messaging`` consent is granted and not revoked. An addition: automatic messages only."""


@dataclass(frozen=True, slots=True)
class TemplateRef:
    """An approved, active ``clinic.message_template``. Unapproved templates are not passed in at all."""

    key: str
    marketing: bool = False


@dataclass(frozen=True, slots=True)
class ExistingTask:
    task_key: str
    rule_key: RuleKey
    status: TaskStatus


@dataclass(frozen=True, slots=True)
class TaskCandidate:
    """A task the rules say should exist (the ``candidates`` of ``run()``)."""

    task_key: str
    patient_id: UUID
    patient_code: str
    rule_key: RuleKey
    reason: str
    priority: TaskPriority
    created_at: datetime
    due_at: datetime
    owner_user_id: UUID | None
    suggested_action: str
    source_event_id: str
    related_appointment_id: str | None = None
    related_plan_id: str | None = None


@dataclass(frozen=True, slots=True)
class PatientCrmUpdate:
    """What ``refresh()`` writes back when a Laser CO2 session sets the D+30 recommendation."""

    patient_id: UUID
    recommendation_at: date
    expected_visit_source: str
    expected_visit_reason: str
    last_protocol_session_id: str


@dataclass(frozen=True, slots=True)
class ProfileView:
    """Read model of ``profile(p)``: derived from visits, plans and appointments, never stored."""

    last_visit_at: date | None
    expected_next_visit_at: date | None
    expected_visit_source: str | None
    expected_visit_reason: str | None
    overdue_days: int
    lifecycle_stage: LifecycleStage
    remaining: int
    risk_level: RiskLevel
    age: int
    marketing_opt_out: bool


@dataclass(frozen=True, slots=True)
class Reconciliation:
    new_tasks: tuple[TaskCandidate, ...]
    superseded_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RulesOutcome:
    """Everything one pure run decides."""

    today: date
    candidates: tuple[TaskCandidate, ...]
    new_tasks: tuple[TaskCandidate, ...]
    superseded_keys: tuple[str, ...]
    patient_updates: tuple[PatientCrmUpdate, ...]
    refreshed: tuple[PatientSnapshot, ...]
    profiles: Mapping[UUID, ProfileView] = field(default_factory=dict[UUID, ProfileView])


@dataclass(frozen=True, slots=True)
class ClinicCrmData:
    """What the runner loads for one clinic (``CrmRuleStore.load``)."""

    rules: tuple[RuleConfig, ...]
    patients: tuple[PatientSnapshot, ...]
    existing_tasks: tuple[ExistingTask, ...]
    templates: Mapping[str, TemplateRef] = field(default_factory=dict[str, TemplateRef])
    protocols: Mapping[str, ProtocolConfig] = field(default_factory=dict[str, ProtocolConfig])
    """``clinic.protocol`` by code (package U4). Empty: the engine uses the built-in laser-co2 defaults."""

"""ORM mapping of the package-M tables (migration ``m_0001_care_tables``).

New module (not a port). Source of the columns: ``docs/PLAN-AI01-M.md`` section 10 and
``recipes/M/01-M1-schema.md``. Same style as ``pema.clinic.models``: columns only, no ``relationship`` and no
``ForeignKey`` (the database owns the composite ``(clinic_id, id)`` keys), ``version`` as ``version_id_col``
(a lost race raises ``StaleDataError``), single tenant (no row level security; ``clinic_id`` is the
installation id).

Two schemas live in one ``CareBase``: ``agent.*`` (care agents and their working tables; both runtime roles
read and write them) and ``clinic.*`` (``staff_profiles``, ``patient_ownership``, ``on_call_contacts``; only
``be_app`` writes them, the worker reads them through the views ``clinic_agent.staff_profile``,
``patient_ownership`` and ``on_call_contact``). The module imports nothing from ``pema.clinic``.

Rule for ``CareMemory``: no column may hold clinical record data (diagnosis, prescription, photo, lab value).
``fact`` is a short, PII-masked statement about the patient's preferences or habits; a test pins the column
set.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Double,
    FetchedValue,
    Identity,
    Integer,
    Interval,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column

AGENT_SCHEMA = "agent"
CLINIC_SCHEMA = "clinic"

PATIENT_CHANNEL_PROFILE = "patient_channel"


class MemorySource(StrEnum):
    PATIENT = "patient"
    STAFF = "staff"
    DOCTOR_EDIT = "doctor_edit"


class ControlState(StrEnum):
    AUTO = "AUTO"
    HANDOFF_ROUTING = "HANDOFF_ROUTING"
    STAFF = "STAFF"


class HandoffOutcome(StrEnum):
    ACCEPTED = "accepted"
    EXHAUSTED_TO_ONCALL = "exhausted_to_oncall"
    CANCELLED = "cancelled"


class ActionDisposition(StrEnum):
    AUTO_SENT = "auto_sent"
    REVIEWED = "reviewed"
    PAUSED = "paused"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"
    CANCELLED = "cancelled"


class CareBase(DeclarativeBase):
    pass


def _created_at() -> MappedColumn[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> MappedColumn[datetime]:
    """Maintained by the ``touch_updated_at`` trigger; ``FetchedValue`` makes the ORM read it back."""
    return mapped_column(DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue())


# ====================================================================================== agent.*
class CareAgent(CareBase):
    """One care agent per patient (``UNIQUE (patient_id)``)."""

    __tablename__ = "care_agents"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    profile: Mapped[str] = mapped_column(Text, default=PATIENT_CHANNEL_PROFILE)
    autonomy_levels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    autonomy_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    trust_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class CareMemory(CareBase):
    """A short fact about one patient. NO clinical record data in any column (PLAN-M section 10)."""

    __tablename__ = "care_memory"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    care_agent_id: Mapped[UUID]
    fact: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class ConversationControl(CareBase):
    """State machine row of one patient: AUTO, HANDOFF_ROUTING or STAFF (only staff return it to AUTO)."""

    __tablename__ = "conversation_control"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    state: Mapped[str] = mapped_column(Text, default=ControlState.AUTO.value)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    staff_owner: Mapped[UUID | None] = mapped_column(default=None)
    release_note: Mapped[str | None] = mapped_column(Text, default=None)
    auto_release_after: Mapped[timedelta | None] = mapped_column(Interval, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class HandoffRequest(CareBase):
    """One routing round (``outcome`` is NULL while open; at most one open request per patient)."""

    __tablename__ = "handoff_requests"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    reason: Mapped[str] = mapped_column(Text)
    depth: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Double)
    required_skill: Mapped[str | None] = mapped_column(Text, default=None)
    urgency: Mapped[str] = mapped_column(Text, default="normal")
    candidates: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    current_idx: Mapped[int] = mapped_column(Integer, default=0)
    current_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_by: Mapped[UUID | None] = mapped_column(default=None)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class AgentTask(CareBase):
    """Work given to a specialist agent by a care agent (delegation depth 1)."""

    __tablename__ = "tasks"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    parent_id: Mapped[UUID | None] = mapped_column(default=None)
    care_agent_id: Mapped[UUID]
    agent_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default=TaskStatus.QUEUED.value)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class ActionLog(CareBase):
    """What a care agent did: auto_sent, reviewed (with the doctor's edit diff) or paused."""

    __tablename__ = "actions_log"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    clinic_id: Mapped[UUID]
    care_agent_id: Mapped[UUID]
    action_type: Mapped[str] = mapped_column(Text)
    depth: Mapped[str | None] = mapped_column(Text, default=None)
    disposition: Mapped[str] = mapped_column(Text)
    reviewer_edit_diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class Skill(CareBase):
    """A named skill: instruction text + classifier configuration (``handoff`` is the first one)."""

    __tablename__ = "skills"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(Text)
    instruction: Mapped[str] = mapped_column(Text)
    classifier_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    enabled_for_profiles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


# ===================================================================================== clinic.*
class StaffProfile(CareBase):
    """Skills, shift, capacity and languages of one staff user (routing input, PLAN-M section 7)."""

    __tablename__ = "staff_profiles"
    __table_args__ = {"schema": CLINIC_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    user_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    shift: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    capacity: Mapped[int] = mapped_column(Integer, default=5)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["vi"])
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class PatientOwnership(CareBase):
    """CS owner and treating doctor of one patient."""

    __tablename__ = "patient_ownership"
    __table_args__ = {"schema": CLINIC_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    cs_owner: Mapped[UUID | None] = mapped_column(default=None)
    doctor: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class OnCallContact(CareBase):
    """The 24/7 Zalo contact. Lives in the database only (never in code or the repository)."""

    __tablename__ = "on_call_contacts"
    __table_args__ = {"schema": CLINIC_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    zalo_number: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012


class PausedReminderRow(CareBase):
    """A reminder that came due while a person had the conversation (``m_0002_paused_reminders``)."""

    __tablename__ = "paused_reminders"
    __table_args__ = {"schema": AGENT_SCHEMA}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    care_agent_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    patient_ref: Mapped[str] = mapped_column(Text)
    event_kind: Mapped[str] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(Text, default=None)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(Text)
    prepared_text: Mapped[str | None] = mapped_column(Text, default=None)
    owner_user_id: Mapped[UUID | None] = mapped_column(default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="paused")
    resolution: Mapped[str | None] = mapped_column(Text, default=None)
    paused_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}  # noqa: RUF012

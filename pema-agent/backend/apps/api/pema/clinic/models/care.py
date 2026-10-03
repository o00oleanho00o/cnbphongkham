"""``clinic.patient``, ``episode``, ``treatment_plan``, ``treatment_session``, ``consent``."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    code: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text, default=None)
    birth_date: Mapped[date | None] = mapped_column(Date, default=None)
    gender: Mapped[str] = mapped_column(Text, default="unknown")
    doctor_id: Mapped[UUID | None] = mapped_column(default=None)
    cs_owner_id: Mapped[UUID | None] = mapped_column(default=None)
    marketing_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    first_contact_at: Mapped[date | None] = mapped_column(Date, default=None)
    source: Mapped[str | None] = mapped_column(Text, default=None)
    recommendation_at: Mapped[date | None] = mapped_column(Date, default=None)
    expected_visit_source: Mapped[str | None] = mapped_column(Text, default=None)
    expected_visit_reason: Mapped[str | None] = mapped_column(Text, default=None)
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    latest_outcome: Mapped[str | None] = mapped_column(Text, default=None)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_action_type: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Episode(Base):
    __tablename__ = "episode"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active")
    started_on: Mapped[date] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class TreatmentPlan(Base):
    __tablename__ = "treatment_plan"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    episode_id: Mapped[UUID | None] = mapped_column(default=None)
    doctor_id: Mapped[UUID | None] = mapped_column(default=None)
    service_code: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    goal: Mapped[str | None] = mapped_column(Text, default=None)
    total_sessions: Mapped[int] = mapped_column(Integer, default=1)
    completed_sessions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class TreatmentSession(Base):
    __tablename__ = "treatment_session"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    plan_id: Mapped[UUID | None] = mapped_column(default=None)
    doctor_id: Mapped[UUID | None] = mapped_column(default=None)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    protocol_id: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="completed")
    session_type: Mapped[str | None] = mapped_column(Text, default=None)
    region: Mapped[str | None] = mapped_column(Text, default=None)
    view: Mapped[str | None] = mapped_column(Text, default=None)
    next_visit_on: Mapped[date | None] = mapped_column(Date, default=None)
    aftercare: Mapped[str | None] = mapped_column(Text, default=None)
    consent_id: Mapped[UUID | None] = mapped_column(default=None)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Consent(Base):
    """Append-only history: the CURRENT consent of a kind is the newest row of that kind."""

    __tablename__ = "consent"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column(Boolean)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    source: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

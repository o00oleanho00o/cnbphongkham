"""``clinic.crm_rule``, ``crm_task``, ``crm_activity``, ``message_template`` (rules: package B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class CrmRule(Base):
    __tablename__ = "crm_rule"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    rule_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    suggested_action: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, default="normal")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    send_mode: Mapped[str] = mapped_column(Text, default="staff_task")
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class CrmTask(Base):
    __tablename__ = "crm_task"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    task_key: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[UUID]
    rule_key: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, default="normal")
    status: Mapped[str] = mapped_column(Text, default="open")
    owner_user_id: Mapped[UUID | None] = mapped_column(default=None)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suggested_action: Mapped[str] = mapped_column(Text)
    source_event_id: Mapped[str | None] = mapped_column(Text, default=None)
    related_appointment_id: Mapped[UUID | None] = mapped_column(default=None)
    related_plan_id: Mapped[UUID | None] = mapped_column(default=None)
    resolution: Mapped[str | None] = mapped_column(Text, default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class CrmActivity(Base):
    __tablename__ = "crm_activity"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    task_id: Mapped[UUID | None] = mapped_column(default=None)
    kind: Mapped[str] = mapped_column(Text, default="cskh")
    channel: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    note: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[UUID | None] = mapped_column(default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_action_type: Mapped[str | None] = mapped_column(Text, default=None)
    related_appointment_id: Mapped[UUID | None] = mapped_column(default=None)


class MessageTemplate(Base):
    __tablename__ = "message_template"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    template_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

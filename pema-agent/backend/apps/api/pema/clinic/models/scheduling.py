"""``clinic.appointment``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class Appointment(Base):
    __tablename__ = "appointment"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    doctor_id: Mapped[UUID | None] = mapped_column(default=None)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(Text, default="booked")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(Text, default=None)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    missed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

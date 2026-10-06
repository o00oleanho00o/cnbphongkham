"""``clinic.service``, ``clinic.service_version``, ``clinic.protocol``, ``clinic.room``, ``clinic.room_block``
(migration u4_0010_services_resources). Package U, step U4."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, BigInteger, Boolean, Date, DateTime, Integer, Text, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class Service(Base):
    __tablename__ = "service"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    protocol_code: Mapped[str | None] = mapped_column(Text, default=None)
    room_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), default=list)
    terms_version: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class ServiceVersion(Base):
    """Append-only snapshot of the terms of a service (the database refuses UPDATE and DELETE)."""

    __tablename__ = "service_version"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    service_id: Mapped[UUID]
    version_no: Mapped[int] = mapped_column(Integer)
    price_vnd: Mapped[int] = mapped_column(BigInteger)
    rate_bp: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(Integer)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)
    changed_by: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Protocol(Base):
    __tablename__ = "protocol"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    milestones: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    followup_days: Mapped[int | None] = mapped_column(Integer, default=None)
    window_days: Mapped[int] = mapped_column(Integer, default=45)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Room(Base):
    __tablename__ = "room"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class RoomBlock(Base):
    __tablename__ = "room_block"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    room_id: Mapped[UUID]
    day: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(default=None)

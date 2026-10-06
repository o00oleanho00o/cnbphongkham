"""Package O tables: ``clinic.account_roster`` (O1), ``clinic.conversation_assignment`` and
``clinic.notification_outbox`` (O2).

Later steps add the notification log and the push tokens to this module. Columns only, like the rest of
``pema.clinic.models``; the database owns the foreign keys and the CHECKs (exactly one of ``weekdays`` and
``on_date``, ``start_time <> end_time``, the kinds and states of the O2 tables).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Date, DateTime, Integer, Text, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class AccountRoster(Base):
    __tablename__ = "account_roster"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    account_id: Mapped[str] = mapped_column(Text)
    user_id: Mapped[UUID]
    weekdays: Mapped[list[str] | None] = mapped_column(ARRAY(Text), default=None)
    """``mon`` .. ``sun`` (the keys of ``clinic.staff_profiles.shift``); ``None`` when the entry is for one
    date."""
    on_date: Mapped[date | None] = mapped_column(Date, default=None)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    """Earlier than ``start_time``: the slot ends the next morning (a night shift)."""
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class ConversationAssignment(Base):
    """History of who held a conversation (append only; the current holder stays
    ``clinic.conversation.assigned_user_id``)."""

    __tablename__ = "conversation_assignment"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    user_id: Mapped[UUID | None] = mapped_column(default=None)
    """Holder after the change; ``None``: back in the queue."""
    kind: Mapped[str] = mapped_column(Text)
    """``claim`` | ``takeover`` | ``release`` | ``shift_end`` | ``assign``."""
    previous_user_id: Mapped[UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    by: Mapped[UUID | None] = mapped_column(default=None)
    """The staff member who made the change; ``None``: the system."""


class NotificationOutbox(Base):
    """What must be told to whom (package O3 delivers). The payload never carries PII."""

    __tablename__ = "notification_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(Text)
    recipient_kind: Mapped[str] = mapped_column(Text)
    """``user`` (``recipient_user_id`` is set) or ``team_group``."""
    recipient_user_id: Mapped[UUID | None] = mapped_column(default=None)
    conversation_id: Mapped[UUID | None] = mapped_column(default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

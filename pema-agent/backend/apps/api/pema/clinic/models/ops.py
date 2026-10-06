"""Package O tables: ``clinic.account_roster`` (O1), ``clinic.conversation_assignment`` and
``clinic.notification_outbox`` (O2).

O3 adds the delivery bookkeeping of the outbox, ``notification_log``, ``push_token``, ``notify_setting``,
``notify_preference``, ``notify_link_code`` and ``sla_check``. Columns only, like the rest of
``pema.clinic.models``; the database owns the foreign keys and the CHECKs (exactly one of ``weekdays`` and
``on_date``, ``start_time <> end_time``, the kinds and states of the O2 tables).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Boolean, Date, DateTime, Integer, Text, Time, func
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
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chain_step: Mapped[str | None] = mapped_column(Text, default=None)
    """``None``: the first step of the recipient kind; ``bell``: waiting for the personal Zalo; ``done``."""
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acked_by: Mapped[UUID | None] = mapped_column(default=None)


class NotificationLog(Base):
    """One attempt of one step of the delivery chain (append only). No text, no recipient detail."""

    __tablename__ = "notification_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    outbox_id: Mapped[UUID]
    provider: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    error_code: Mapped[str | None] = mapped_column(Text, default=None)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushToken(Base):
    """A device of an operator. ``token_hash`` is the key, ``token_enc`` what the provider needs (AES-GCM)."""

    __tablename__ = "push_token"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    user_id: Mapped[UUID]
    platform: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    token_enc: Mapped[str] = mapped_column(Text)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotifySetting(Base):
    """The clinic's notification settings (one row; the defaults apply while it does not exist)."""

    __tablename__ = "notify_setting"

    clinic_id: Mapped[UUID] = mapped_column(primary_key=True)
    ack_timeout_s: Mapped[int] = mapped_column(Integer, default=180)
    team_group_id: Mapped[str | None] = mapped_column(Text, default=None)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    bell_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    group_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    public_base_url: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[UUID | None] = mapped_column(default=None)


class NotifyPreference(Base):
    """Quiet hours of one operator (clinic clock); ``urgent`` notices still ring."""

    __tablename__ = "notify_preference"

    clinic_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    quiet_start: Mapped[time | None] = mapped_column(Time, default=None)
    quiet_end: Mapped[time | None] = mapped_column(Time, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotifyLinkCode(Base):
    """The one-time code that links a personal Zalo id to an operator (only its hash is stored)."""

    __tablename__ = "notify_link_code"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    user_id: Mapped[UUID]
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SlaCheck(Base):
    """ "Look at routing request ``request_id`` again at ``due_at``" (package M's ``SlaScheduler``)."""

    __tablename__ = "sla_check"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    request_id: Mapped[UUID]
    idx: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

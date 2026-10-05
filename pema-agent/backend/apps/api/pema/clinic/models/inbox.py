"""``clinic.channel_identity``, ``conversation``, ``message``, ``review_item``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class ChannelIdentity(Base):
    __tablename__ = "channel_identity"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(Text)
    external_user_id: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[UUID | None] = mapped_column(default=None)
    display_name: Mapped[str | None] = mapped_column(Text, default=None)
    friend_status: Mapped[str] = mapped_column(Text, default="unknown")
    verification_status: Mapped[str] = mapped_column(Text, default="unlinked")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by: Mapped[UUID | None] = mapped_column(default=None)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(Text)
    external_ref: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[UUID | None] = mapped_column(default=None)
    identity_id: Mapped[UUID | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(Text, default="open")
    assigned_user_id: Mapped[UUID | None] = mapped_column(default=None)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Message(Base):
    __tablename__ = "message"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    sender_type: Mapped[str] = mapped_column(Text)
    sender_user_id: Mapped[UUID | None] = mapped_column(default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    masked_body: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="received")
    proactive: Mapped[bool] = mapped_column(Boolean, default=False)
    update_id: Mapped[str | None] = mapped_column(Text, default=None)
    external_message_id: Mapped[str | None] = mapped_column(Text, default=None)
    review_item_id: Mapped[UUID | None] = mapped_column(default=None)
    error_code: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ReviewItem(Base):
    __tablename__ = "review_item"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, default="agent_turn")
    status: Mapped[str] = mapped_column(Text, default="pending")
    conversation_id: Mapped[UUID | None] = mapped_column(default=None)
    patient_id: Mapped[UUID | None] = mapped_column(default=None)
    job_id: Mapped[str | None] = mapped_column(Text, default=None)
    draft_text: Mapped[str | None] = mapped_column(Text, default=None)
    final_text: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    risk_level: Mapped[str] = mapped_column(Text, default="normal")
    red_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    requires_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_version: Mapped[str | None] = mapped_column(Text, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by: Mapped[UUID | None] = mapped_column(default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

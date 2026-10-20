"""``clinic.agent_event``: the outbox the API's worker sends to the agent (docs/PLAN-crm-plugin.md 3.4).

On a base of its own on purpose: ``clinic.audit`` guards the clinic's own data (a change of it needs its audit
row). The delivery bookkeeping of this table (attempts, delivered) is not a clinic change, so the worker may
update it without one; a row is only ever INSERTED beside the change it tells about, in that change's
transaction, which carries the audit row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pema.clinic.models.base import CLINIC_SCHEMA


class OutboxBase(DeclarativeBase):
    metadata = MetaData(schema=CLINIC_SCHEMA)


class AgentEvent(OutboxBase):
    __tablename__ = "agent_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    clinic_id: Mapped[UUID]
    event_id: Mapped[UUID] = mapped_column(default=uuid4)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

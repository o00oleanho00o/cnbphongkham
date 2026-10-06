"""``clinic.invoice``, ``clinic.payment``, ``clinic.procedure_entry``, ``clinic.procedure_entry_person``,
``clinic.finance_period``, ``clinic.finance_notification`` (migration u6_0010_finance). Package U, step U6."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    number: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(Text)
    order_id: Mapped[UUID | None] = mapped_column(default=None)
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    received_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    invoice_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Payment(Base):
    """One receipt. Append-only for the application role (INSERT and SELECT only)."""

    __tablename__ = "payment"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    idempotency_key: Mapped[str] = mapped_column(Text)
    invoice_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(Text)
    paid_on: Mapped[date] = mapped_column(Date)
    received_by: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcedureEntry(Base):
    __tablename__ = "procedure_entry"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    service_id: Mapped[UUID]
    service_name: Mapped[str] = mapped_column(Text)
    terms_version: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(Text)
    entry_date: Mapped[date] = mapped_column(Date)
    invoice_id: Mapped[UUID]
    owns_invoice: Mapped[bool] = mapped_column(Boolean, default=True)
    list_vnd: Mapped[int] = mapped_column(BigInteger)
    discount_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    net_vnd: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, default="pending")
    note: Mapped[str] = mapped_column(Text)
    void_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class ProcedureEntryPerson(Base):
    """Who performed the procedure, with the revenue share and the commission rate that applied (snapshot)."""

    __tablename__ = "procedure_entry_person"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    entry_id: Mapped[UUID]
    position: Mapped[int] = mapped_column(Integer)
    doctor_id: Mapped[UUID]
    share_bp: Mapped[int] = mapped_column(Integer)
    rate_bp: Mapped[int] = mapped_column(Integer)


class FinancePeriod(Base):
    """A closed month (``closed``) and, once the payout is confirmed, a paid one (``paid``). No row: open."""

    __tablename__ = "finance_period"

    clinic_id: Mapped[UUID] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, default="closed")
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_by: Mapped[UUID | None] = mapped_column(default=None)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    paid_by: Mapped[UUID | None] = mapped_column(default=None)
    reference: Mapped[str | None] = mapped_column(Text, default=None)
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class FinanceNotification(Base):
    """What the owner sees when a receipt is recorded (one per payment)."""

    __tablename__ = "finance_notification"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    payment_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    invoice_id: Mapped[UUID]
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

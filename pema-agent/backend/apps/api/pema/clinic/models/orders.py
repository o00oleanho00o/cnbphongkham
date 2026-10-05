"""``clinic.catalog_import``, ``clinic.product``, ``clinic.order``, ``clinic.order_item`` (migration
u5_0010_orders_catalog). Package U, step U5."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class CatalogImport(Base):
    """Provenance of the catalog: one row per run of ``pema catalog import``."""

    __tablename__ = "catalog_import"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    source_name: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(Text, default=None)
    total_rows: Mapped[int] = mapped_column(Integer)
    prescription_rows: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """One row of the clinic's price list. The key is the Excel code (``H002``)."""

    __tablename__ = "product"

    clinic_id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(Text, default="")
    route: Mapped[str] = mapped_column(Text)
    price_vnd: Mapped[int] = mapped_column(BigInteger)
    vat: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal(0))
    price_before_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    batch: Mapped[str] = mapped_column(Text, default="")
    serial: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    catalog_hash: Mapped[str] = mapped_column(Text)


class Order(Base):
    __tablename__ = "order"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    doctor_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(Text, default="draft")
    order_date: Mapped[date] = mapped_column(Date)
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    total_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    catalog_hash: Mapped[str | None] = mapped_column(Text, default=None)
    reviewed_by: Mapped[UUID | None] = mapped_column(default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    invoice_id: Mapped[UUID | None] = mapped_column(default=None)
    received_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class OrderItem(Base):
    """A line of an order with the snapshot of the product at the time it was saved."""

    __tablename__ = "order_item"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    order_id: Mapped[UUID]
    line_no: Mapped[int] = mapped_column(Integer)
    product_code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(Text, default="")
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    catalog_route: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(Text)
    route_reason: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_vnd: Mapped[int] = mapped_column(BigInteger)
    usage: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")

"""Product catalog and quick orders (package U, step U5).

Tables ``clinic.product``, ``clinic.catalog_import``, ``clinic.order``, ``clinic.order_item``. JS source:
``prototype/shared/order-data.js`` (``saveOrder``, ``approveOrder``, ``orderPrintData``), ``order-ui.js``,
``order-review.js``, ``product-catalog-runtime.js``; the catalog itself is ``product-catalog.json`` (the
clinic's real price list, 115 rows, product id = the Excel code).

Rules the DTOs keep:

* Money is an integer number of VND. A price of 0 in the catalog stays 0.
* A line has a ``route``: ``PRESCRIPTION`` (Đơn thuốc), ``CONSULTATION`` (Phiếu tư vấn), ``NONE`` ("Không in":
  left off the sheets, still part of the total) or ``UNRESOLVED`` ("Cần phân loại": blocks approval and
  printing). The catalog proposes ``catalog_route``; any other ``route`` needs a ``route_reason``.
* A draft is edited with the ``version`` it was read at (409 when stale). An approved order never changes;
  a draft with money received (``received_vnd`` > 0 or ``paid``) cannot be edited either.
* Approval needs a usage text on every printed line and a diagnosis; the approver is the responsible doctor.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.patients import Gender

PRODUCT_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$"


class OrderRoute(StrEnum):
    PRESCRIPTION = "PRESCRIPTION"
    CONSULTATION = "CONSULTATION"
    NONE = "NONE"
    UNRESOLVED = "UNRESOLVED"


class OrderStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


# ---------------------------------------------------------------------------------------------- catalog
class ProductOut(ApiModel):
    code: str = Field(description="The Excel code, e.g. 'H002'. It is the product id.")
    name: str
    unit: str
    source_type: str = Field(description="The Excel type: Thuốc, Mỹ Phẩm, TPCN or empty.")
    route: OrderRoute = Field(description="Where the catalog sends the product (the prototype's outputType).")
    price_vnd: int = Field(ge=0, description="Price after tax.")
    vat: float
    row_number: int
    active: bool


class CatalogSummaryOut(ApiModel):
    """The line above the product list ("115 sản phẩm · 30 thuốc · 78 sản phẩm tư vấn · 7 cần phân loại")
    and the provenance of the data."""

    total: int
    prescription: int
    consultation: int
    unresolved: int
    source_name: str | None = Field(description="File the catalog was imported from.")
    sha256: str | None = Field(description="SHA-256 of the canonical rows that were imported.")
    imported_at: VnDatetime | None = None


class CatalogImportOut(ApiModel):
    """Result of ``pema catalog import``."""

    total: int
    created: int
    updated: int
    unchanged: int
    deactivated: int
    sha256: str
    unchanged_run: bool = Field(
        description="True when the same rows had already been imported: nothing changed."
    )


# ----------------------------------------------------------------------------------------------- orders
class OrderItemIn(ApiModel):
    """One line the cashier chose. Name, unit and price are NOT sent: they come from the catalog (or from the
    snapshot the draft already holds)."""

    product_code: str = Field(pattern=PRODUCT_CODE_PATTERN)
    quantity: int = Field(ge=1, le=9999)
    route: OrderRoute | None = Field(default=None, description="Omitted: the catalog route.")
    route_reason: str = Field(default="", max_length=500)
    usage: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=1000)


class OrderItemOut(ApiModel):
    line_no: int
    product_code: str
    name: str
    source_type: str
    unit: str
    catalog_route: OrderRoute
    route: OrderRoute
    route_reason: str
    quantity: int
    unit_price_vnd: int
    usage: str
    note: str


class OrderCreate(ApiModel):
    patient_id: UUID
    doctor_id: UUID | None = Field(default=None, description="Omitted: the doctor of the patient.")
    diagnosis: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=2000)
    items: list[OrderItemIn] = Field(min_length=1, max_length=200)


class OrderUpdate(ApiModel):
    """A draft is saved as a whole: the lines replace the previous ones."""

    version: int
    doctor_id: UUID | None = None
    diagnosis: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=2000)
    items: list[OrderItemIn] = Field(min_length=1, max_length=200)


class OrderApprove(ApiModel):
    version: int = Field(description="The version the doctor reviewed; a newer one answers 409.")


class OrderSummaryOut(ApiModel):
    id: UUID
    patient_id: UUID
    patient_code: str
    patient_name: str
    doctor_id: UUID
    doctor_name: str
    status: OrderStatus
    order_date: date
    item_count: int
    total_vnd: int
    reviewed_by_name: str | None = None
    reviewed_at: VnDatetime | None = None
    created_at: VnDatetime
    version: int


class OrderOut(OrderSummaryOut):
    diagnosis: str
    note: str
    items: list[OrderItemOut]
    received_vnd: int
    paid: bool
    invoice_id: UUID | None = None
    editable: bool = Field(description="A draft with nothing received: it may still be edited.")
    unresolved_count: int = Field(ge=0)
    ready_to_approve: bool = Field(
        description="Every line is classified with its usage, the diagnosis is there and something prints."
    )


class OrderPatientOut(ApiModel):
    code: str
    full_name: str
    age: int | None = None
    gender: Gender = Gender.UNKNOWN


class OrderPrintOut(ApiModel):
    """What the review page and the A5 sheets draw: the order and its lines split by route."""

    order: OrderOut
    patient: OrderPatientOut
    prescription: list[OrderItemOut]
    consultation: list[OrderItemOut]
    excluded: list[OrderItemOut]
    unresolved: list[OrderItemOut]
    printable: bool = Field(
        description="Approved, every line classified and complete: the sheets may be printed."
    )


class ApprovedOrderGroupOut(ApiModel):
    """One approved order as the patient app shows it (staff preview): lines grouped by sheet."""

    order_id: UUID
    order_date: date
    doctor_name: str
    diagnosis: str
    note: str
    prescription: list[OrderItemOut]
    consultation: list[OrderItemOut]
    approved_at: VnDatetime | None = None

"""Finance PB02 (package U, step U6): performed procedures, commission rows, invoices, receipts, monthly
periods.

Tables ``clinic.invoice``, ``clinic.payment``, ``clinic.procedure_entry``, ``clinic.procedure_entry_person``,
``clinic.finance_period``, ``clinic.finance_notification``. JS/Python source: ``prototype/finance_server.py``
(``Finance.view``, ``command``, ``mutate``), ``prototype/finance/finance.js`` (the four tabs),
``docs/24_FINANCE_AND_PROCEDURE_FEES.md``.

Rules the DTOs keep:

* Money is an integer number of VND (``*_vnd``); a commission rate and a revenue share are integer basis
  points (``*_bp``, 10000 = 100 %).
* Performed revenue and collected cash are different numbers and never added together: ``revenue_vnd`` is
  the net price of the procedures done in the month, ``collected_vnd`` the receipts of the month.
* The API returns a projection per role: ``own`` (a doctor, or the owner looking at their own rows) carries no
  ``collected_vnd``, no ``debt_vnd`` and no clinic-wide row; ``clinic`` (owner, accountant) carries all of
  them.
* A month without a period row is ``open``; ``closed`` freezes its table (a snapshot) and its entries;
  ``paid`` is the accounting confirmation of the payout with a voucher reference.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from pema_contracts.catalog import ServiceBasis
from pema_contracts.common import ApiModel, VnDatetime

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
Month = Annotated[str, StringConstraints(pattern=MONTH_PATTERN)]


class FinanceScope(StrEnum):
    """Which projection the caller asks for. ``clinic``: the whole clinic (owner, accountant). ``own``: only
    the rows where the caller performed (doctor; the owner may ask for it too)."""

    CLINIC = "clinic"
    OWN = "own"


class EntryStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    VOID = "void"


class PeriodStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    PAID = "paid"


class PaymentMethod(StrEnum):
    CASH = "cash"
    TRANSFER = "transfer"


class InvoiceSource(StrEnum):
    FINANCE = "finance"
    ORDER = "order"


# ----------------------------------------------------------------------------------------------- overview
class FinanceSummaryOut(ApiModel):
    revenue_vnd: int = Field(
        description="Performed revenue: the net price of the procedures done in the month "
        "(own: the caller's share)."
    )
    fee_vnd: int = Field(
        description="Approved procedure fee (commission) of the month. Not the clinic's profit."
    )
    pending_vnd: int = Field(description="Procedure fee still waiting for approval. Not part of ``fee_vnd``.")
    collected_vnd: int | None = Field(
        default=None, description="Receipts of the month. Null in the personal projection."
    )
    debt_vnd: int | None = Field(
        default=None,
        description="Open balance of every invoice at this moment (not only the month's). "
        "Null in the personal projection.",
    )


class FinancePeriodOut(ApiModel):
    month: Month
    status: PeriodStatus
    closed_at: VnDatetime | None = None
    paid_at: VnDatetime | None = None
    reference: str | None = Field(
        default=None, description="Voucher of the payout; set when ``status`` is paid."
    )


class FinanceTeamOut(ApiModel):
    doctor_id: UUID
    doctor_name: str
    entry_count: int = Field(ge=0)
    revenue_vnd: int
    fee_vnd: int = Field(description="Approved fee of this doctor.")


class FinanceOverviewOut(ApiModel):
    month: Month
    today: date
    scope: FinanceScope
    summary: FinanceSummaryOut
    period: FinancePeriodOut
    team: list[FinanceTeamOut] = Field(description="One row per doctor (own: the caller only).")
    pending_entries: int = Field(ge=0, description="Entries waiting for the accountant's approval.")


# ------------------------------------------------------------------------------------------------- entries
class FinanceRowOut(ApiModel):
    """One commission row: one performer of one procedure. ``revenue_vnd`` is the performer's share of the net
    price (the last performer takes the remainder, so the rows add up to the net price); ``fee_vnd`` is
    ``base_vnd`` x ``rate_bp``, rounded to the dong."""

    entry_id: UUID
    date: date
    patient_code: str
    service_name: str
    doctor_id: UUID
    doctor_name: str
    status: EntryStatus
    basis: ServiceBasis
    base_vnd: int
    rate_bp: int
    share_bp: int
    revenue_vnd: int
    fee_vnd: int
    note: str = ""


class FinanceDoctorOut(ApiModel):
    id: UUID
    name: str


class FinanceEntriesOut(ApiModel):
    month: Month
    today: date
    scope: FinanceScope
    period: FinancePeriodOut
    rows: list[FinanceRowOut]
    doctors: list[FinanceDoctorOut] = Field(description="Who can be a performer (own: the caller only).")
    can_write: bool = Field(description="True when the caller may record, approve or void entries.")


class EntryPersonIn(ApiModel):
    doctor_id: UUID
    share_bp: int = Field(
        ge=1, le=10000, description="Share of the revenue; the shares of an entry add up to 10000."
    )
    rate_bp: int = Field(
        ge=0, le=10000, description="Commission rate of this person; the rates add up to at most 10000."
    )


class EntryCreate(ApiModel):
    patient_id: UUID
    service_id: UUID
    entry_date: date = Field(
        description="The day the procedure was done; not in the future, not in a closed month."
    )
    list_vnd: int = Field(ge=1, le=10**12)
    discount_vnd: int = Field(ge=0, le=10**12, default=0)
    invoice_id: UUID | None = Field(
        default=None,
        description="Attach the procedure to an invoice that already exists (same patient, not "
        "over-allocated). "
        "Omit to raise a new invoice for it.",
    )
    note: str = Field(min_length=1, max_length=500, description="Confirmation that the procedure was done.")
    people: list[EntryPersonIn] = Field(
        min_length=1,
        max_length=4,
        description="Who performed it. Never filled in from the doctor in charge of the patient.",
    )


class EntryPersonOut(ApiModel):
    doctor_id: UUID
    doctor_name: str
    share_bp: int
    rate_bp: int
    revenue_vnd: int
    fee_vnd: int


class EntryOut(ApiModel):
    id: UUID
    entry_date: date
    patient_id: UUID
    patient_code: str
    service_id: UUID
    service_name: str
    terms_version: int
    basis: ServiceBasis
    invoice_id: UUID
    invoice_number: str
    owns_invoice: bool
    list_vnd: int
    discount_vnd: int
    net_vnd: int
    status: EntryStatus
    note: str
    void_reason: str | None = None
    people: list[EntryPersonOut]
    version: int


class EntryVoid(ApiModel):
    reason: str = Field(
        min_length=1, max_length=500, description="Why the entry is cancelled; kept on the entry."
    )


# ------------------------------------------------------------------------------------- invoices and receipts
class InvoiceOut(ApiModel):
    id: UUID
    number: str
    patient_id: UUID
    patient_code: str
    patient_name: str
    source: InvoiceSource
    order_id: UUID | None = None
    invoice_date: date
    amount_vnd: int
    received_vnd: int
    due_vnd: int = Field(description="``amount_vnd`` minus ``received_vnd``; what a receipt may still take.")


class InvoiceFromOrder(ApiModel):
    order_id: UUID


class BillableOrderOut(ApiModel):
    """A quick order (U5) that has no invoice yet."""

    order_id: UUID
    patient_id: UUID
    patient_code: str
    patient_name: str
    status: str
    order_date: date
    total_vnd: int


class PaymentCreate(ApiModel):
    id: str = Field(
        min_length=3,
        max_length=160,
        description="Idempotency key of the receipt: a retry with the same key and content returns the first "
        "receipt, the same key with other content is refused.",
    )
    invoice_id: UUID
    amount_vnd: int = Field(ge=1, le=10**12)
    method: PaymentMethod


class PaymentOut(ApiModel):
    id: UUID
    key: str
    invoice_id: UUID
    invoice_number: str
    patient_code: str
    amount_vnd: int
    method: PaymentMethod
    paid_on: date
    created_at: VnDatetime
    replayed: bool = Field(
        default=False, description="True when this call found the receipt of an earlier call."
    )


class NotificationOut(ApiModel):
    id: UUID
    payment_id: UUID
    invoice_id: UUID
    title: str
    body: str
    amount_vnd: int
    created_at: VnDatetime
    read: bool


# ---------------------------------------------------------------------------------------------- periods
class PeriodRowOut(ApiModel):
    month: Month
    status: PeriodStatus
    entry_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    closable: bool
    blocker: str | None = Field(default=None, description="Why the month cannot be closed yet (Vietnamese).")
    closed_at: VnDatetime | None = None
    paid_at: VnDatetime | None = None
    reference: str | None = None


class PeriodListOut(ApiModel):
    today: date
    items: list[PeriodRowOut] = Field(description="The last 12 months, newest first.")


class PeriodPay(ApiModel):
    reference: str = Field(min_length=1, max_length=120, description="Voucher of the payout.")

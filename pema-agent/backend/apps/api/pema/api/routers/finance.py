"""Finance PB02 (package U, step U6). Each route calls one action of ``pema.clinic.actions``; the rules (role
projection, rate snapshots, duplicate and over-collection guards, closed months) live in
``actions.finance``, ``actions.finance_cash`` and ``pema.clinic.finance.domain``.

The projection comes from the signed-in user. There is no role or doctor header:
``prototype/finance_server.py`` trusted ``X-Pema-Role`` and ``X-Pema-Doctor``; this API trusts the session
only.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Response, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, Limit, Offset, cookie_scheme
from pema.clinic.actions import finance, finance_cash
from pema_contracts.common import Page
from pema_contracts.finance import (
    MONTH_PATTERN,
    BillableOrderOut,
    EntryCreate,
    EntryOut,
    EntryVoid,
    FinanceDoctorOut,
    FinanceEntriesOut,
    FinanceOverviewOut,
    FinancePeriodOut,
    FinanceScope,
    InvoiceFromOrder,
    InvoiceOut,
    NotificationOut,
    PaymentCreate,
    PaymentOut,
    PeriodListOut,
    PeriodPay,
)

router = APIRouter(tags=["finance"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])

MonthQuery = Annotated[str, Query(pattern=MONTH_PATTERN, description="Accounting month, YYYY-MM.")]
ScopeQuery = Annotated[
    FinanceScope | None,
    Query(
        description="The projection: clinic (owner, accountant) or own (doctor, owner). "
        "Default: the widest one allowed."
    ),
]
MonthPath = Annotated[str, Path(pattern=MONTH_PATTERN, description="Accounting month, YYYY-MM.")]


@router.get("/finance/overview", response_model=FinanceOverviewOut, summary="The overview of a month")
async def overview(db: Database, ctx: Ctx, month: MonthQuery, scope: ScopeQuery = None) -> FinanceOverviewOut:
    return await finance.overview(db, ctx, month, scope)


@router.get(
    "/finance/entries",
    response_model=FinanceEntriesOut,
    summary="The commission table of a month: one row per performer of every procedure",
)
async def list_entries(
    db: Database, ctx: Ctx, month: MonthQuery, scope: ScopeQuery = None
) -> FinanceEntriesOut:
    return await finance.list_entries(db, ctx, month, scope)


@router.post(
    "/finance/entries",
    response_model=EntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a completed procedure and who performed it (pending approval)",
)
async def create_entry(body: EntryCreate, db: Database, ctx: Ctx) -> EntryOut:
    return await finance.create_entry(db, ctx, body)


@router.post(
    "/finance/entries/{entry_id}/approve",
    response_model=EntryOut,
    summary="Approve a pending entry (before the month is closed)",
)
async def approve_entry(entry_id: UUID, db: Database, ctx: Ctx) -> EntryOut:
    return await finance.approve_entry(db, ctx, entry_id)


@router.post(
    "/finance/entries/{entry_id}/void",
    response_model=EntryOut,
    summary="Cancel an entry with a reason (before the month is closed, nothing received)",
)
async def void_entry(entry_id: UUID, body: EntryVoid, db: Database, ctx: Ctx) -> EntryOut:
    return await finance.void_entry(db, ctx, entry_id, body)


@router.get(
    "/finance/performers",
    response_model=list[FinanceDoctorOut],
    summary="Who can be named as a performer of a procedure",
)
async def list_performers(db: Database, ctx: Ctx) -> list[FinanceDoctorOut]:
    return await finance.list_performers(db, ctx)


@router.get(
    "/finance/periods",
    response_model=PeriodListOut,
    summary="The last 12 months with their status and what blocks closing them",
)
async def list_periods(db: Database, ctx: Ctx) -> PeriodListOut:
    return await finance.list_periods(db, ctx)


@router.post(
    "/finance/periods/{month}/close",
    response_model=FinancePeriodOut,
    summary="Close a month that ended: freeze its commission table",
)
async def close_period(month: MonthPath, db: Database, ctx: Ctx) -> FinancePeriodOut:
    return await finance.close_period(db, ctx, month)


@router.post(
    "/finance/periods/{month}/pay",
    response_model=FinancePeriodOut,
    summary="Confirm the payout of a closed month with its voucher",
)
async def pay_period(month: MonthPath, body: PeriodPay, db: Database, ctx: Ctx) -> FinancePeriodOut:
    return await finance.pay_period(db, ctx, month, body)


@router.get(
    "/finance/export",
    summary="The commission table of a month as CSV for Excel",
    responses={200: {"content": {"text/csv": {}}, "description": "UTF-8 CSV with a byte order mark."}},
)
async def export_csv(db: Database, ctx: Ctx, month: MonthQuery, scope: ScopeQuery = None) -> Response:
    text = await finance.export_csv(db, ctx, month, scope)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="Pema-tien-thu-thuat-{month}.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/finance/invoices", response_model=Page[InvoiceOut], summary="Invoices, newest first")
async def list_invoices(
    db: Database,
    ctx: Ctx,
    due_only: Annotated[bool, Query(description="Only invoices with an open balance.")] = False,
    patient_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[InvoiceOut]:
    return await finance_cash.list_invoices(
        db, ctx, due_only=due_only, patient_id=patient_id, limit=limit, offset=offset
    )


@router.get(
    "/finance/billable-orders",
    response_model=list[BillableOrderOut],
    summary="Quick orders that have something to pay and no invoice yet",
)
async def list_billable_orders(db: Database, ctx: Ctx) -> list[BillableOrderOut]:
    return await finance_cash.list_billable_orders(db, ctx)


@router.post(
    "/finance/invoices/from-order",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Raise the invoice of a quick order (the same invoice when asked again)",
)
async def create_invoice_for_order(body: InvoiceFromOrder, db: Database, ctx: Ctx) -> InvoiceOut:
    return await finance_cash.create_for_order(db, ctx, body)


@router.get("/finance/payments", response_model=Page[PaymentOut], summary="The receipts of a month")
async def list_payments(
    db: Database, ctx: Ctx, month: MonthQuery, limit: Limit = 50, offset: Offset = 0
) -> Page[PaymentOut]:
    return await finance_cash.list_payments(db, ctx, month, limit=limit, offset=offset)


@router.post(
    "/finance/payments",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a receipt on an invoice (idempotent on its key)",
)
async def record_payment(body: PaymentCreate, response: Response, db: Database, ctx: Ctx) -> PaymentOut:
    receipt = await finance_cash.record_payment(db, ctx, body)
    if receipt.replayed:
        response.status_code = status.HTTP_200_OK  # a retry: the first receipt, nothing written
    return receipt


@router.get(
    "/finance/notifications",
    response_model=list[NotificationOut],
    summary="The owner's payment notifications",
)
async def list_notifications(db: Database, ctx: Ctx) -> list[NotificationOut]:
    return await finance_cash.list_notifications(db, ctx)


@router.post(
    "/finance/notifications/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark a notification as read",
)
async def read_notification(notification_id: UUID, db: Database, ctx: Ctx) -> NotificationOut:
    return await finance_cash.mark_notification_read(db, ctx, notification_id)

# ported from: prototype/finance_server.py (mutate 'payment', 'read', notify) and
# prototype/shared/order-data.js (saveOrder: the invoice of a quick order)
"""PB02 finance, the cash side: the invoice of an order, receipts with an idempotency key, and the owner's
payment notifications.

Forced deviations from the Python/JavaScript prototype:

* the prototype mirrored the invoices and receipts of the old ``localStorage`` cashier into its SQLite
  document (``mutate('sync')``) and refused to collect an invoice of that origin ("Hóa đơn web cũ phải thu
  tại Thu ngân web"). The cashier is the U5 orders flow now, so there is nothing to mirror and every invoice
  is collected here: ``sync`` is not ported;
* an invoice of an order is raised explicitly by the cashier (``create_for_order``), once per order; the draft
  order keeps it up to date while nothing is received (``_invoices.sync_order_invoice``). The prototype
  rewrote the invoice with every save;
* ``finance.collect`` (owner, accountant, reception) records receipts and sees the open invoices; the receipts
  list and every total need ``finance.read``; the notifications are the owner's (``finance.notifications``);
* the receipt, the invoice balance, the order mirror (``received_vnd`` / ``paid`` of the order, which stops
  further edits of the order) and the owner's notification commit in one transaction.

Rules kept as they were: a receipt carries a key (3 to 160 characters); a retry with the same key and content
returns the first receipt and writes nothing; the same key with other content is refused ("Mã giao dịch đã
dùng cho nội dung khác"); a receipt over the open balance is refused ("Số thu vượt công nợ"); a failure
writes no notification.

Audit actions: ``finance.invoice.create``, ``finance.payment.record``, ``finance.notification.read``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions import orders
from pema.clinic.actions._common import lost_race_is_conflict, not_found, now
from pema.clinic.actions._invoices import invoice_number
from pema.clinic.actions.finance import today
from pema.clinic.finance import domain
from pema.clinic.models import FinanceNotification, Invoice, Order, Patient, Payment
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.finance import (
    BillableOrderOut,
    InvoiceFromOrder,
    InvoiceOut,
    InvoiceSource,
    NotificationOut,
    PaymentCreate,
    PaymentMethod,
    PaymentOut,
)
from pema_contracts.roles import Permission

INVOICE_PERMISSIONS = (Permission.FINANCE_READ, Permission.FINANCE_COLLECT)
METHOD_LABELS = {PaymentMethod.CASH.value: "Tiền mặt", PaymentMethod.TRANSFER.value: "Chuyển khoản"}
NOTIFICATION_TITLE = "Đã nhận thanh toán"
ORDER_WITHOUT_VALUE_MESSAGE = "Đơn có giá trị 0 ₫, không cần hóa đơn."


def _invoice_out(invoice: Invoice, patient: Patient) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        number=invoice.number,
        patient_id=invoice.patient_id,
        patient_code=patient.code,
        patient_name=patient.full_name,
        source=InvoiceSource(invoice.source),
        order_id=invoice.order_id,
        invoice_date=invoice.invoice_date,
        amount_vnd=invoice.amount_vnd,
        received_vnd=invoice.received_vnd,
        due_vnd=invoice.amount_vnd - invoice.received_vnd,
    )


# ------------------------------------------------------------------------------------------------ invoices
async def list_invoices(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    due_only: bool = False,
    patient_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[InvoiceOut]:
    """Invoices, newest first. ``due_only`` keeps the ones with an open balance ("Hóa đơn còn nợ")."""
    require_any(ctx, INVOICE_PERMISSIONS)
    async with db.session() as session:
        base = (
            select(Invoice, Patient)
            .join(Patient, (Patient.clinic_id == Invoice.clinic_id) & (Patient.id == Invoice.patient_id))
            .where(Invoice.clinic_id == ctx.clinic_id)
        )
        if due_only:
            base = base.where(Invoice.received_vnd < Invoice.amount_vnd)
        if patient_id is not None:
            base = base.where(Invoice.patient_id == patient_id)
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = (
            await session.execute(
                base.order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc(), Invoice.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return Page[InvoiceOut](
            items=[_invoice_out(invoice, patient) for invoice, patient in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


async def list_billable_orders(
    db: ClinicDatabase, ctx: ActionContext, *, limit: int = 50
) -> list[BillableOrderOut]:
    """Quick orders (U5) with something to pay and no invoice yet, newest first."""
    require_any(ctx, INVOICE_PERMISSIONS)
    async with db.session() as session:
        rows = (
            await session.execute(
                select(Order, Patient)
                .join(Patient, (Patient.clinic_id == Order.clinic_id) & (Patient.id == Order.patient_id))
                .where(Order.clinic_id == ctx.clinic_id, Order.invoice_id.is_(None), Order.total_vnd > 0)
                .order_by(Order.created_at.desc(), Order.id)
                .limit(limit)
            )
        ).all()
        return [
            BillableOrderOut(
                order_id=order.id,
                patient_id=order.patient_id,
                patient_code=patient.code,
                patient_name=patient.full_name,
                status=order.status,
                order_date=order.order_date,
                total_vnd=order.total_vnd,
            )
            for order, patient in rows
        ]


async def create_for_order(db: ClinicDatabase, ctx: ActionContext, payload: InvoiceFromOrder) -> InvoiceOut:
    """Raise the invoice of a quick order: its total, once. Asking again returns the same invoice."""
    require(ctx, Permission.FINANCE_COLLECT)
    async with db.session() as session:
        order = await session.scalar(
            select(Order)
            .where(Order.id == payload.order_id, Order.clinic_id == ctx.clinic_id)
            .with_for_update()
        )
        if order is None:
            raise not_found("đơn")
        patient = await session.scalar(
            select(Patient).where(Patient.id == order.patient_id, Patient.clinic_id == ctx.clinic_id)
        )
        if patient is None:  # unreachable: foreign key
            raise not_found("bệnh nhân")
        existing = await session.scalar(
            select(Invoice).where(Invoice.order_id == order.id, Invoice.clinic_id == ctx.clinic_id)
        )
        if existing is not None:
            return _invoice_out(existing, patient)
        if order.total_vnd <= 0:
            raise domain.fail(ORDER_WITHOUT_VALUE_MESSAGE)
        invoice = Invoice(
            clinic_id=ctx.clinic_id,
            number=invoice_number(order.order_date),
            patient_id=order.patient_id,
            source=InvoiceSource.ORDER.value,
            order_id=order.id,
            amount_vnd=order.total_vnd,
            received_vnd=0,
            invoice_date=order.order_date,
            created_by=ctx.actor_user_id,
        )
        session.add(invoice)
        await session.flush()
        # A Core UPDATE: the link must not bump the order's ``version``, or the draft the cashier has open
        # would turn stale for a change that touches none of its content.
        await session.execute(
            update(Order)
            .where(Order.id == order.id, Order.clinic_id == ctx.clinic_id)
            .values(invoice_id=invoice.id)
        )
        await audit.record(
            session,
            ctx,
            "finance.invoice.create",
            "invoice",
            invoice.id,
            {"order_id": str(order.id), "amount_vnd": invoice.amount_vnd},
        )
        return _invoice_out(invoice, patient)


# ------------------------------------------------------------------------------------------------ receipts
def _payment_out(payment: Payment, invoice: Invoice, patient: Patient, *, replayed: bool) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        key=payment.idempotency_key,
        invoice_id=payment.invoice_id,
        invoice_number=invoice.number,
        patient_code=patient.code,
        amount_vnd=payment.amount_vnd,
        method=PaymentMethod(payment.method),
        paid_on=payment.paid_on,
        created_at=payment.created_at,
        replayed=replayed,
    )


async def _same_receipt(
    session: AsyncSession, ctx: ActionContext, payload: PaymentCreate
) -> PaymentOut | None:
    """The receipt this key already made, when the retry carries the same content; refuse a different one."""
    found = await session.execute(
        select(Payment, Invoice, Patient)
        .join(Invoice, (Invoice.clinic_id == Payment.clinic_id) & (Invoice.id == Payment.invoice_id))
        .join(Patient, (Patient.clinic_id == Payment.clinic_id) & (Patient.id == Payment.patient_id))
        .where(Payment.clinic_id == ctx.clinic_id, Payment.idempotency_key == payload.id)
    )
    row = found.first()
    if row is None:
        return None
    payment, invoice, patient = row
    if (
        payment.invoice_id != payload.invoice_id
        or payment.amount_vnd != payload.amount_vnd
        or payment.method != payload.method.value
    ):
        raise DomainError(ErrorCode.DUPLICATE_REQUEST, domain.KEY_REUSED_MESSAGE)
    return _payment_out(payment, invoice, patient, replayed=True)


async def record_payment(db: ClinicDatabase, ctx: ActionContext, payload: PaymentCreate) -> PaymentOut:
    """``mutate('payment')``: take money on an invoice. Idempotent on ``payload.id``; never more than the open
    balance; the invoice, the receipt, the order mirror and the notification are one transaction."""
    require(ctx, Permission.FINANCE_COLLECT)
    async with db.session() as session:
        replay = await _same_receipt(session, ctx, payload)
        if replay is not None:
            return replay
        invoice = await session.scalar(
            select(Invoice)
            .where(Invoice.id == payload.invoice_id, Invoice.clinic_id == ctx.clinic_id)
            .with_for_update()
        )
        if invoice is None:
            raise not_found("hóa đơn")
        replay = await _same_receipt(session, ctx, payload)  # a concurrent retry committed while we waited
        if replay is not None:
            return replay
        if payload.amount_vnd > invoice.amount_vnd - invoice.received_vnd:
            raise domain.fail(domain.OVERPAYMENT_MESSAGE)
        patient = await session.scalar(
            select(Patient).where(Patient.id == invoice.patient_id, Patient.clinic_id == ctx.clinic_id)
        )
        if patient is None:  # unreachable: foreign key
            raise not_found("bệnh nhân")
        invoice.received_vnd += payload.amount_vnd
        payment = Payment(
            clinic_id=ctx.clinic_id,
            idempotency_key=payload.id,
            invoice_id=invoice.id,
            patient_id=invoice.patient_id,
            amount_vnd=payload.amount_vnd,
            method=payload.method.value,
            paid_on=today(),
            received_by=ctx.actor_user_id,
        )
        try:
            async with session.begin_nested():
                session.add(payment)
                with lost_race_is_conflict():
                    await session.flush()
        except IntegrityError as exc:  # the same key raced in for another invoice
            raise DomainError(ErrorCode.DUPLICATE_REQUEST, domain.KEY_REUSED_MESSAGE) from exc
        session.add(
            FinanceNotification(
                clinic_id=ctx.clinic_id,
                payment_id=payment.id,
                title=NOTIFICATION_TITLE,
                body=(
                    f"{patient.code} · {domain.format_vnd(payment.amount_vnd)} đ · "
                    f"{METHOD_LABELS[payment.method]}"
                ),
                amount_vnd=payment.amount_vnd,
                invoice_id=invoice.id,
            )
        )
        if invoice.order_id is not None:
            await orders.set_payment_state(
                session,
                ctx,
                invoice.order_id,
                received_vnd=invoice.received_vnd,
                paid=invoice.received_vnd >= invoice.amount_vnd,
            )
        await session.flush()
        await audit.record(
            session,
            ctx,
            "finance.payment.record",
            "payment",
            payment.id,
            {
                "invoice_id": str(invoice.id),
                "amount_vnd": payment.amount_vnd,
                "method": payment.method,
                "received_vnd": invoice.received_vnd,
            },
        )
        await session.refresh(payment)
        return _payment_out(payment, invoice, patient, replayed=False)


async def list_payments(
    db: ClinicDatabase, ctx: ActionContext, month: str, *, limit: int = 50, offset: int = 0
) -> Page[PaymentOut]:
    """The receipts of a month by the day they were taken, newest first ("Giao dịch trong kỳ")."""
    require(ctx, Permission.FINANCE_READ)
    first = domain.parse_month(month)
    after = domain.next_month_start(first)
    async with db.session() as session:
        base = (
            select(Payment, Invoice, Patient)
            .join(Invoice, (Invoice.clinic_id == Payment.clinic_id) & (Invoice.id == Payment.invoice_id))
            .join(Patient, (Patient.clinic_id == Payment.clinic_id) & (Patient.id == Payment.patient_id))
            .where(Payment.clinic_id == ctx.clinic_id, Payment.paid_on >= first, Payment.paid_on < after)
        )
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = (
            await session.execute(
                base.order_by(Payment.paid_on.desc(), Payment.created_at.desc(), Payment.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return Page[PaymentOut](
            items=[_payment_out(p, i, pt, replayed=False) for p, i, pt in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


# ------------------------------------------------------------------------------------------- notifications
def _notification_out(row: FinanceNotification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        payment_id=row.payment_id,
        invoice_id=row.invoice_id,
        title=row.title,
        body=row.body,
        amount_vnd=row.amount_vnd,
        created_at=row.created_at,
        read=row.is_read,
    )


async def list_notifications(
    db: ClinicDatabase, ctx: ActionContext, *, limit: int = 100
) -> list[NotificationOut]:
    """The owner's payment notifications, newest first (the prototype showed the latest 100)."""
    require(ctx, Permission.FINANCE_NOTIFICATIONS)
    async with db.session() as session:
        rows = await session.scalars(
            select(FinanceNotification)
            .where(FinanceNotification.clinic_id == ctx.clinic_id)
            .order_by(FinanceNotification.created_at.desc(), FinanceNotification.id)
            .limit(limit)
        )
        return [_notification_out(row) for row in rows]


async def mark_notification_read(
    db: ClinicDatabase, ctx: ActionContext, notification_id: UUID
) -> NotificationOut:
    """``mutate('read')``: mark one notification as read. Reading a read one changes nothing."""
    require(ctx, Permission.FINANCE_NOTIFICATIONS)
    async with db.session() as session:
        row = await session.scalar(
            select(FinanceNotification).where(
                FinanceNotification.id == notification_id, FinanceNotification.clinic_id == ctx.clinic_id
            )
        )
        if row is None:
            raise not_found("thông báo")
        if not row.is_read:
            row.is_read = True
            row.read_at = now()
            await session.flush()
            await audit.record(
                session,
                ctx,
                "finance.notification.read",
                "finance_notification",
                row.id,
                {"payment_id": str(row.payment_id)},
            )
        return _notification_out(row)

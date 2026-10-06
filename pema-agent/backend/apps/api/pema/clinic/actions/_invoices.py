"""Where an order and its invoice meet (package U, step U6).

The orders actions call ``sync_order_invoice`` after a draft is saved; the finance actions create the
invoice and record receipts. This module only reads and writes the models, so the two sides do not import
each other.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.models import Invoice, Order
from pema_contracts.actions import ActionContext


async def sync_order_invoice(session: AsyncSession, ctx: ActionContext, order: Order) -> bool:
    """After a draft is saved, the invoice raised for it follows the new total, as the prototype's
    ``saveOrder`` rewrote the invoice with every save. Only while nothing is received: a draft with money
    received cannot be edited at all (``orders._editable``). True when the amount of an invoice changed."""
    if order.invoice_id is None:
        return False
    invoice = await session.scalar(
        select(Invoice)
        .where(Invoice.id == order.invoice_id, Invoice.clinic_id == ctx.clinic_id)
        .with_for_update()
    )
    if invoice is None or invoice.received_vnd > 0 or invoice.amount_vnd == order.total_vnd:
        return False
    invoice.amount_vnd = order.total_vnd
    return True


def invoice_number(day: date) -> str:
    """``HD-260920-3F9A1C``: the day of the invoice and six random hex digits (unique per clinic in the
    database)."""
    return f"HD-{day:%y%m%d}-{uuid4().hex[:6].upper()}"

"""Product catalog and quick orders (package U, step U5). Each route calls one action of
``pema.clinic.actions``; the rules (version, classification, approval, immutability) are in
``pema.clinic.actions.orders`` and ``pema.clinic.domain.orders``.

The catalog is loaded by the CLI ``pema catalog import``, never through a route.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, Limit, Offset, cookie_scheme
from pema.clinic.actions import catalog, orders
from pema_contracts.common import Page
from pema_contracts.orders import (
    ApprovedOrderGroupOut,
    CatalogSummaryOut,
    OrderApprove,
    OrderCreate,
    OrderOut,
    OrderPrintOut,
    OrderStatus,
    OrderSummaryOut,
    OrderUpdate,
    ProductOut,
)

router = APIRouter(tags=["orders"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])
catalog_router = APIRouter(
    tags=["catalog"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)]
)


@catalog_router.get(
    "/catalog/products", response_model=Page[ProductOut], summary="Search the product catalog"
)
async def list_products(
    db: Database,
    ctx: Ctx,
    q: Annotated[str, Query(max_length=120, description="Code, name or type; accents are ignored.")] = "",
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[ProductOut]:
    return await catalog.list_products(db, ctx, q=q, limit=limit, offset=offset)


@catalog_router.get(
    "/catalog/summary", response_model=CatalogSummaryOut, summary="Counts and provenance of the catalog"
)
async def catalog_summary(db: Database, ctx: Ctx) -> CatalogSummaryOut:
    return await catalog.catalog_summary(db, ctx)


@router.get("/orders", response_model=Page[OrderSummaryOut], summary="Orders, newest first")
async def list_orders(
    db: Database,
    ctx: Ctx,
    patient_id: UUID | None = None,
    status: OrderStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[OrderSummaryOut]:
    return await orders.list_orders(db, ctx, patient_id=patient_id, status=status, limit=limit, offset=offset)


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft order from catalog products",
)
async def create_draft(body: OrderCreate, db: Database, ctx: Ctx) -> OrderOut:
    return await orders.create_draft(db, ctx, body)


@router.get(
    "/patients/{patient_id}/approved-orders",
    response_model=list[ApprovedOrderGroupOut],
    summary="Approved orders as the patient app groups them (staff preview)",
)
async def approved_orders(patient_id: UUID, db: Database, ctx: Ctx) -> list[ApprovedOrderGroupOut]:
    return await orders.approved_for_patient(db, ctx, patient_id)


@router.get("/orders/{order_id}", response_model=OrderOut, summary="One order with its lines")
async def get_order(order_id: UUID, db: Database, ctx: Ctx) -> OrderOut:
    return await orders.get_order(db, ctx, order_id)


@router.put(
    "/orders/{order_id}",
    response_model=OrderOut,
    summary="Save a draft (the lines replace the previous ones); an approved order is immutable",
)
async def update_draft(order_id: UUID, body: OrderUpdate, db: Database, ctx: Ctx) -> OrderOut:
    return await orders.update_draft(db, ctx, order_id, body)


@router.post(
    "/orders/{order_id}/approve",
    response_model=OrderOut,
    summary="The responsible doctor approves the order so it can be printed",
)
async def approve_order(order_id: UUID, body: OrderApprove, db: Database, ctx: Ctx) -> OrderOut:
    return await orders.approve(db, ctx, order_id, body)


@router.get(
    "/orders/{order_id}/print-data",
    response_model=OrderPrintOut,
    summary="The order and its lines split into Đơn thuốc and Phiếu tư vấn",
)
async def print_data(
    order_id: UUID,
    db: Database,
    ctx: Ctx,
    require_approved: Annotated[
        bool, Query(description="Refuse a draft or an incomplete order (the strict print check).")
    ] = False,
) -> OrderPrintOut:
    return await orders.print_data(db, ctx, order_id, require_approved=require_approved)

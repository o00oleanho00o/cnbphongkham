"""Review queue (B1). A human decision always precedes a send."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security

from pema.api.dashboard_auth import Ctx, Database, Delivery
from pema.api.deps import ERROR_RESPONSES, IdempotencyKey, Limit, Offset, cookie_scheme
from pema.clinic.actions import review_items
from pema_contracts.common import Page
from pema_contracts.review import (
    ReviewApprove,
    ReviewEscalate,
    ReviewItemOut,
    ReviewKind,
    ReviewReject,
    ReviewStatus,
)

router = APIRouter(
    tags=["review-items"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get("/review-items", response_model=Page[ReviewItemOut], summary="Review queue")
async def list_review_items(
    db: Database,
    ctx: Ctx,
    review_status: ReviewStatus | None = None,
    kind: ReviewKind | None = None,
    requires_doctor: bool | None = None,
    patient_id: UUID | None = None,
    conversation_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ReviewItemOut]:
    return await review_items.list_review_items(
        db,
        ctx,
        status=review_status,
        kind=kind,
        requires_doctor=requires_doctor,
        patient_id=patient_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )


@router.get("/review-items/{item_id}", response_model=ReviewItemOut, summary="One review item")
async def get_review_item(item_id: UUID, db: Database, ctx: Ctx) -> ReviewItemOut:
    return await review_items.get_review_item(db, ctx, item_id)


@router.post(
    "/review-items/{item_id}/approve",
    response_model=ReviewItemOut,
    summary="Approve (optionally edited) and send. Clinical items need a doctor.",
)
async def approve_review_item(
    item_id: UUID,
    body: ReviewApprove,
    db: Database,
    ctx: Ctx,
    delivery: Delivery,
    idempotency_key: IdempotencyKey = None,
) -> ReviewItemOut:
    return await review_items.approve_review_item(db, ctx, item_id, body, delivery=delivery)


@router.post(
    "/review-items/{item_id}/reject",
    response_model=ReviewItemOut,
    summary="Reject the draft",
)
async def reject_review_item(item_id: UUID, body: ReviewReject, db: Database, ctx: Ctx) -> ReviewItemOut:
    return await review_items.reject_review_item(db, ctx, item_id, body)


@router.post(
    "/review-items/{item_id}/escalate",
    response_model=ReviewItemOut,
    summary="Hand over to a doctor",
)
async def escalate_review_item(item_id: UUID, body: ReviewEscalate, db: Database, ctx: Ctx) -> ReviewItemOut:
    return await review_items.escalate_review_item(db, ctx, item_id, body)

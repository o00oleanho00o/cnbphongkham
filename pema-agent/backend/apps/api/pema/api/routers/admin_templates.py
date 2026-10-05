"""Approved message templates (package B1).

Doctor approval (permission ``review.decide_clinical``) activates one.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import admin_router
from pema.clinic.actions import templates
from pema_contracts.crm import (
    MessageTemplateApprove,
    MessageTemplateCreate,
    MessageTemplateOut,
    MessageTemplateUpdate,
)

router = admin_router("templates", "admin-templates")


@router.get("", response_model=list[MessageTemplateOut], summary="Message templates")
async def list_templates(db: Database, ctx: Ctx) -> list[MessageTemplateOut]:
    return await templates.list_templates(db, ctx)


@router.post(
    "",
    response_model=MessageTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft template (inactive until a doctor approves)",
)
async def create_template(body: MessageTemplateCreate, db: Database, ctx: Ctx) -> MessageTemplateOut:
    return await templates.create_template(db, ctx, body)


@router.patch("/{template_id}", response_model=MessageTemplateOut, summary="Edit (clears the approval)")
async def update_template(
    template_id: UUID, body: MessageTemplateUpdate, db: Database, ctx: Ctx
) -> MessageTemplateOut:
    return await templates.update_template(db, ctx, template_id, body)


@router.post(
    "/{template_id}/approve",
    response_model=MessageTemplateOut,
    summary="Doctor sign-off: activates the template (audited)",
)
async def approve_template(
    template_id: UUID, body: MessageTemplateApprove, db: Database, ctx: Ctx
) -> MessageTemplateOut:
    return await templates.approve_template(db, ctx, template_id, body)

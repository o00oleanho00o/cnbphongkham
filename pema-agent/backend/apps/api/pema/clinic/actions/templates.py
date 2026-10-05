"""Doctor-approved message templates (actions behind ``routers/admin_templates.py``).

New module. In ``patient_channel`` a scheduled ``kind: message`` job may only send a template that a doctor
approved (PLAN-AI01 sections 5 and 8; ``clinic_agent.message_template_approved`` exposes exactly the active
and approved ones to the worker). Rules:

* a new template is a DRAFT: ``active = false``, no approval;
* ``review.decide_clinical`` (doctor, owner) approves it: it becomes active and records who and when;
* editing the BODY or the ``marketing`` flag clears the approval and deactivates it (a doctor signed the old
  words, not the new ones); title edits keep it;
* a template cannot be activated without an approval; it can always be deactivated;
* ``admin.rules`` (owner, manager) writes drafts; the list is visible to those who write or approve.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.actions._mappers import template_out
from pema.clinic.models import MessageTemplate
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.crm import (
    MessageTemplateApprove,
    MessageTemplateCreate,
    MessageTemplateOut,
    MessageTemplateUpdate,
)
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission


async def _load(session: AsyncSession, ctx: ActionContext, template_id: UUID) -> MessageTemplate:
    row = await session.scalar(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id, MessageTemplate.clinic_id == ctx.clinic_id
        )
    )
    if row is None:
        raise not_found("mẫu tin nhắn")
    return row


async def list_templates(db: ClinicDatabase, ctx: ActionContext) -> list[MessageTemplateOut]:
    require_any(ctx, (Permission.ADMIN_RULES, Permission.REVIEW_DECIDE_CLINICAL))
    async with db.session() as session:
        rows = (
            await session.scalars(
                select(MessageTemplate)
                .where(MessageTemplate.clinic_id == ctx.clinic_id)
                .order_by(MessageTemplate.template_key)
            )
        ).all()
        return [template_out(r) for r in rows]


async def create_template(
    db: ClinicDatabase, ctx: ActionContext, payload: MessageTemplateCreate
) -> MessageTemplateOut:
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        row = MessageTemplate(
            clinic_id=ctx.clinic_id,
            template_key=payload.template_key,
            title=payload.title,
            body=payload.body,
            marketing=payload.marketing,
            active=False,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Mã mẫu tin nhắn đã tồn tại.") from exc
        await audit.record(
            session,
            ctx,
            "message_template.create",
            "message_template",
            row.id,
            {"template_key": row.template_key, "marketing": row.marketing},
        )
        return template_out(row)


async def update_template(
    db: ClinicDatabase, ctx: ActionContext, template_id: UUID, payload: MessageTemplateUpdate
) -> MessageTemplateOut:
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        row = await _load(session, ctx, template_id)
        check_version(row.version, payload.version)
        changed: list[str] = []
        content_changed = False
        if payload.title is not None and payload.title != row.title:
            row.title = payload.title
            changed.append("title")
        if payload.body is not None and payload.body != row.body:
            row.body = payload.body
            changed.append("body")
            content_changed = True
        if payload.marketing is not None and payload.marketing != row.marketing:
            row.marketing = payload.marketing
            changed.append("marketing")
            content_changed = True
        cleared_approval = False
        if content_changed and row.approved_at is not None:
            row.approved_at = None
            row.approved_by = None
            row.active = False
            cleared_approval = True
        if payload.active is not None and payload.active != row.active:
            if payload.active and row.approved_at is None:
                raise DomainError(
                    ErrorCode.REVIEW_REQUIRED, "Mẫu chưa được bác sĩ duyệt nên chưa thể kích hoạt."
                )
            row.active = payload.active
            changed.append("active")
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "message_template.update",
            "message_template",
            row.id,
            {"changed_fields": changed, "approval_cleared": cleared_approval},
        )
        return template_out(row)


async def approve_template(
    db: ClinicDatabase, ctx: ActionContext, template_id: UUID, payload: MessageTemplateApprove
) -> MessageTemplateOut:
    """Doctor sign-off (``review.decide_clinical``): activates the template and records who and when."""
    require(ctx, Permission.REVIEW_DECIDE_CLINICAL)
    async with db.session() as session:
        row = await _load(session, ctx, template_id)
        if await audit.find_replay(session, ctx, "message_template.approve", row.id):
            return template_out(row)
        check_version(row.version, payload.version)
        row.approved_by = ctx.actor_user_id
        row.approved_at = now()
        row.active = True
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "message_template.approve",
            "message_template",
            row.id,
            {"template_key": row.template_key, "marketing": row.marketing},
        )
        return template_out(row)

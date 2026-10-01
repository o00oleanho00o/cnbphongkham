"""Audit log reader (action behind ``routers/admin_audit.py``). Append-only: there is no write path here;
rows are written only by ``pema.clinic.audit.record`` and the SECURITY DEFINER functions of ``clinic_agent``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from pema.clinic.actions._mappers import audit_out
from pema.clinic.models import AuditLog
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.admin import AuditLogOut
from pema_contracts.common import Page
from pema_contracts.roles import Permission


async def list_audit_logs(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    actor_user_id: UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[AuditLogOut]:
    require(ctx, Permission.ADMIN_LOGS)
    conditions: list[Any] = [AuditLog.clinic_id == ctx.clinic_id]
    if actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if action:
        conditions.append(AuditLog.action == action)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if occurred_from is not None:
        conditions.append(AuditLog.occurred_at >= occurred_from)
    if occurred_to is not None:
        conditions.append(AuditLog.occurred_at < occurred_to)
    async with db.session(ctx.clinic_id) as session:
        total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
        rows = (
            await session.scalars(
                select(AuditLog)
                .where(*conditions)
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items = [audit_out(r) for r in rows]
    return Page[AuditLogOut](items=items, total=total, limit=limit, offset=offset)

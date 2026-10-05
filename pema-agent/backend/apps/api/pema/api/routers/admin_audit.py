"""Audit log reader (package B1). Append-only; there is no write or delete endpoint."""

from __future__ import annotations

from uuid import UUID

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import Limit, Offset, admin_router
from pema.clinic.actions import audit_logs
from pema_contracts.admin import AuditLogOut
from pema_contracts.common import Page, VnDatetime

router = admin_router("logs", "admin-audit")


@router.get("/audit", response_model=Page[AuditLogOut], summary="Audit log (append-only)")
async def list_audit_logs(
    db: Database,
    ctx: Ctx,
    actor_user_id: UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    occurred_from: VnDatetime | None = None,
    occurred_to: VnDatetime | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[AuditLogOut]:
    return await audit_logs.list_audit_logs(
        db,
        ctx,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )

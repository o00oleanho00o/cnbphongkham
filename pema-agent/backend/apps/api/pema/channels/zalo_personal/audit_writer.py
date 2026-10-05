"""Append-only audit rows for the C2 mutations (accounts, channel settings, kill switch, bridge reports).

New module. ``clinic.audit_log`` is insert/select only for role ``be_app`` (migration 0001). The C2 admin
routes and
the bridge webhook run as ``be_app`` and write the row in the SAME transaction as the change it
describes, so a
mutation without an audit row cannot commit. ``details`` carries field names, ids and codes only: never
message
text, never a credential, never a name or a phone number (AGENT.md).
"""

from __future__ import annotations

import json
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType


class AuditSink(Protocol):
    async def record(
        self,
        ctx: ActionContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict[str, object] | None = None,
    ) -> None: ...


async def write_audit(
    session: AsyncSession,
    ctx: ActionContext,
    action: str,
    entity_type: str,
    entity_id: str | None,
    details: dict[str, object] | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO clinic.audit_log (clinic_id, actor_type, actor_user_id, actor_role, action, "
            "entity_type, entity_id, request_id, details) VALUES (:clinic_id, :actor_type, :actor_user_id, "
            ":actor_role, :action, :entity_type, :entity_id, :request_id, CAST(:details AS jsonb))"
        ),
        {
            "clinic_id": ctx.clinic_id,
            "actor_type": (ctx.actor_type or ActorType.SYSTEM).value,
            "actor_user_id": ctx.actor_user_id,
            "actor_role": ctx.actor_role.value if ctx.actor_role else None,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "request_id": ctx.request_id,
            "details": json.dumps(details) if details is not None else None,
        },
    )


class SqlAuditSink:
    """Own transaction; for the account routes whose change lives in ``agent.*`` (another store's
    transaction)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def record(
        self,
        ctx: ActionContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict[str, object] | None = None,
    ) -> None:
        async with self._db.session() as session:
            await write_audit(session, ctx, action, entity_type, entity_id, details)

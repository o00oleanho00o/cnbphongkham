"""Writer and readers of the append-only ``clinic.audit_log``.

New module (the original had no clinic audit). Rules of ``pema_contracts.actions.AuditRecord``:

* ``details`` carries field NAMES and ids only, never message text or PII values. ``record`` refuses a
  details object that uses a known PII key, as a safety net against a careless caller;
* the row is written in the SAME transaction as the mutation it describes (the caller's session), so a
  rolled back mutation leaves no audit row and a committed one always has one (``guard`` enforces it);
* ``find_replay`` is the idempotency lookup: a repeated ``Idempotency-Key`` finds the audit row of the
  first execution and the action returns the current state instead of acting twice.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.models import AuditLog
from pema_contracts.actions import ActionContext

FORBIDDEN_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "body",
        "content",
        "message",
        "draft_text",
        "final_text",
        "note",
        "reason_text",
        "full_name",
        "name",
        "display_name",
        "phone",
        "email",
        "address",
        "birth_date",
        "password",
        "token",
    }
)
"""Keys that must never appear in ``details``: they would put PII or clinical text into the audit log."""


def _check_details(details: Mapping[str, Any] | None) -> None:
    if not details:
        return
    bad = FORBIDDEN_DETAIL_KEYS & {key.lower() for key in details}
    if bad:
        raise ValueError(f"audit details must not carry PII keys: {sorted(bad)}")


async def record(
    session: AsyncSession,
    ctx: ActionContext,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Add one audit row in the caller's transaction and flush it (so ``id`` is known)."""
    _check_details(details)
    merged: dict[str, Any] = dict(details or {})
    if ctx.idempotency_key and "idempotency_key" not in merged:
        merged["idempotency_key"] = ctx.idempotency_key
    if ctx.source.value != "ui" and "source" not in merged:
        merged["source"] = ctx.source.value
    row = AuditLog(
        clinic_id=ctx.clinic_id,
        actor_type=ctx.actor_type.value,
        actor_user_id=ctx.actor_user_id,
        actor_role=ctx.actor_role.value if ctx.actor_role else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        request_id=ctx.request_id,
        details=merged or None,
    )
    session.add(row)
    await session.flush()
    return row


async def find_replay(session: AsyncSession, ctx: ActionContext, action: str, entity_id: object) -> bool:
    """``True`` when this ``Idempotency-Key`` already executed ``action`` on ``entity_id``."""
    if not ctx.idempotency_key:
        return False
    found = await session.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.clinic_id == ctx.clinic_id,
            AuditLog.action == action,
            AuditLog.entity_id == str(entity_id),
            AuditLog.details["idempotency_key"].astext == ctx.idempotency_key,
        )
        .limit(1)
    )
    return found is not None

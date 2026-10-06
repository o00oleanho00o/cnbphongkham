"""Channel accounts as clinic identities (package O, step O1). New module, no zalo-agent original.

A channel account of ``agent.accounts`` is what the customer sees ("Long" on Zalo). O1 adds to it:

* ``purpose``: ``customer`` (faces customers) or ``internal`` (the clinic's own notifier; it never sends to a
  customer and can never be the identity of a conversation);
* its own send limits (``send_gap_min_s``, ``send_gap_max_s``, ``daily_cap``) that override the one row per
  channel of ``clinic.channel_setting``. ``effective_limits`` is the one function that answers "which limit
  applies to this identity"; the send path of step O4 calls it.

What this module never does: read, return or log a credential. ``agent.accounts`` is read with an explicit
column list that has no ``*_enc`` column, and the DTOs of ``pema_contracts.ops`` have no field for one. The
accounts screen and QR login stay in ``admin_accounts`` (permission ``admin.accounts``); this module only
manages what O adds (permission ``identity.manage``, owner and manager).

Permissions: reading the identities needs ``roster.read`` or ``identity.manage`` (every operator reads them,
the Inbox filters by identity); every change needs ``identity.manage``. Every change writes an audit row
with field names and the new purpose/limit values (numbers and a code, never a label or any free text).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import (
    EffectiveLimits,
    IdentityOut,
    IdentityPurpose,
    IdentityUpdate,
    LimitOverrides,
)
from pema_contracts.roles import Permission

READ_PERMISSIONS = (Permission.ROSTER_READ, Permission.IDENTITY_MANAGE)
"""The columns below are the whole read surface: no ``bot_token_enc``, ``credential_enc`` or
``webhook_secret_enc`` is ever selected."""

_IDENTITY_SQL = """
    SELECT a.id, a.label, a.channel, a.purpose, a.enabled, a.send_gap_min_s, a.send_gap_max_s, a.daily_cap,
    s.enabled AS channel_enabled, s.kill_switch_on, s.bridge_state, s.min_gap_seconds AS channel_gap_min,
    s.max_gap_seconds AS channel_gap_max, s.daily_cap AS channel_daily_cap FROM agent.accounts a LEFT JOIN
    clinic.channel_setting s ON s.clinic_id = a.clinic_id AND s.channel = a.channel
     WHERE a.clinic_id = :clinic_id"""
_LIST_SQL = text(_IDENTITY_SQL + " ORDER BY a.purpose, a.label, a.id")
_GET_SQL = text(_IDENTITY_SQL + " AND a.id = :account_id")

_PURPOSE_IN_USE = "Không đổi được: còn hội thoại đang gắn với danh tính này."
_ROSTER_IN_USE = "Không đổi được: hãy xóa lịch trực của danh tính này trước."
_LIMIT_ORDER = "Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa."


def _limits(row: Any) -> tuple[LimitOverrides, EffectiveLimits]:
    overrides = LimitOverrides(
        send_gap_min_s=row.send_gap_min_s, send_gap_max_s=row.send_gap_max_s, daily_cap=row.daily_cap
    )
    effective = EffectiveLimits(
        send_gap_min_s=row.send_gap_min_s if row.send_gap_min_s is not None else (row.channel_gap_min or 0),
        send_gap_max_s=row.send_gap_max_s if row.send_gap_max_s is not None else (row.channel_gap_max or 0),
        daily_cap=row.daily_cap if row.daily_cap is not None else row.channel_daily_cap,
    )
    return overrides, effective


def _identity_out(row: Any) -> IdentityOut:
    overrides, effective = _limits(row)
    return IdentityOut(
        id=row.id,
        label=row.label,
        channel=ChannelKind(row.channel),
        purpose=IdentityPurpose(row.purpose),
        enabled=bool(row.enabled),
        channel_enabled=bool(row.channel_enabled) if row.channel_enabled is not None else False,
        kill_switch_on=bool(row.kill_switch_on) if row.kill_switch_on is not None else False,
        bridge_state=row.bridge_state,
        overrides=overrides,
        effective=effective,
    )


async def effective_limits(db: ClinicDatabase, clinic_id: UUID, account_id: str) -> EffectiveLimits | None:
    """The limits that apply to one identity: its override, else the row of its channel, else no limit
    (gap 0, no cap). ``None`` when the account does not exist. No permission: an internal lookup for the send
    path, it returns numbers only."""
    async with db.session() as session:
        row = (await session.execute(_GET_SQL, {"clinic_id": clinic_id, "account_id": account_id})).first()
    return None if row is None else _limits(row)[1]


async def list_identities(db: ClinicDatabase, ctx: ActionContext) -> list[IdentityOut]:
    """Every channel account with its purpose, state and limits. Customer-facing first, then internal."""
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        rows = (await session.execute(_LIST_SQL, {"clinic_id": ctx.clinic_id})).all()
    return [_identity_out(row) for row in rows]


async def get_identity(db: ClinicDatabase, ctx: ActionContext, account_id: str) -> IdentityOut:
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        return _identity_out(await _load(session, ctx, account_id))


async def _load(session: AsyncSession, ctx: ActionContext, account_id: str) -> Any:
    row = (await session.execute(_GET_SQL, {"clinic_id": ctx.clinic_id, "account_id": account_id})).first()
    if row is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Danh tính không tồn tại.")
    return row


async def update_identity_settings(
    db: ClinicDatabase, ctx: ActionContext, account_id: str, body: IdentityUpdate
) -> IdentityOut:
    """Purpose, label and the send-limit overrides of one identity (owner and manager).

    A limit sent as ``None`` clears its override. The effective gap must stay ordered (min <= max) after the
    change. Moving an account to ``internal`` is refused while a conversation or a roster entry still points
    at it (the database has the same guard as a trigger)."""
    require(ctx, Permission.IDENTITY_MANAGE)
    fields = body.model_fields_set
    if not fields:
        return await get_identity(db, ctx, account_id)
    async with db.session() as session:
        row = await _load(session, ctx, account_id)
        overrides, _ = _limits(row)
        merged = {
            "send_gap_min_s": overrides.send_gap_min_s,
            "send_gap_max_s": overrides.send_gap_max_s,
            "daily_cap": overrides.daily_cap,
        }
        for key in merged:
            if key in fields:
                merged[key] = getattr(body, key)
        gap_min = (
            merged["send_gap_min_s"] if merged["send_gap_min_s"] is not None else (row.channel_gap_min or 0)
        )
        gap_max = (
            merged["send_gap_max_s"] if merged["send_gap_max_s"] is not None else (row.channel_gap_max or 0)
        )
        if gap_min > gap_max:
            raise DomainError(ErrorCode.VALIDATION_FAILED, _LIMIT_ORDER)

        purpose = body.purpose.value if body.purpose is not None else row.purpose
        if purpose == IdentityPurpose.INTERNAL.value and row.purpose != purpose:
            await _refuse_if_in_use(session, ctx, account_id)

        label = body.label if body.label is not None else row.label
        try:
            await session.execute(
                text(
                    "UPDATE agent.accounts SET purpose = :purpose, label = :label, "
                    "send_gap_min_s = :gap_min, send_gap_max_s = :gap_max, daily_cap = :cap, "
                    "updated_at = now() WHERE clinic_id = :clinic_id AND id = :account_id"
                ),
                {
                    "purpose": purpose,
                    "label": label,
                    "gap_min": merged["send_gap_min_s"],
                    "gap_max": merged["send_gap_max_s"],
                    "cap": merged["daily_cap"],
                    "clinic_id": ctx.clinic_id,
                    "account_id": account_id,
                },
            )
        except IntegrityError as exc:
            # the database trigger refused: a conversation was attached between our check and the update
            raise DomainError(ErrorCode.INVALID_STATE, _PURPOSE_IN_USE) from exc
        details: dict[str, Any] = {"changed_fields": sorted(fields)}
        if "purpose" in fields:
            details["purpose"] = purpose
        for key in merged:
            if key in fields:
                details[key] = merged[key]
        await audit.record(session, ctx, "identity.update", "account", account_id, details)
        return _identity_out(await _load(session, ctx, account_id))


async def _refuse_if_in_use(session: AsyncSession, ctx: ActionContext, account_id: str) -> None:
    conversations = await session.scalar(
        text(
            "SELECT count(*) FROM clinic.conversation "
            "WHERE clinic_id = :clinic_id AND account_id = :account_id"
        ),
        {"clinic_id": ctx.clinic_id, "account_id": account_id},
    )
    if conversations:
        raise DomainError(ErrorCode.INVALID_STATE, _PURPOSE_IN_USE)
    roster = await session.scalar(
        text(
            "SELECT count(*) FROM clinic.account_roster "
            "WHERE clinic_id = :clinic_id AND account_id = :account_id"
        ),
        {"clinic_id": ctx.clinic_id, "account_id": account_id},
    )
    if roster:
        raise DomainError(ErrorCode.INVALID_STATE, _ROSTER_IN_USE)

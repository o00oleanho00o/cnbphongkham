# ported from: prototype/shared/crm-automation.js (the laser-co2 chain: D+1, D+3, D+7 and the D+30 review)
"""Treatment protocols as data: the follow-up milestones the CRM rule engine (package B2) reads.

In the JavaScript the chain was hard-coded (``'laser-co2'``, delays 1, 3, 7, a 45 day window and a D+30
recommendation). Here it is a row of ``clinic.protocol``; ``pema.clinic.crm_rules.protocols`` turns the rows
into ``ProtocolConfig`` for the engine, which falls back to the constants it always had when a protocol has no
row, so a clinic that never edits one sees no change.

A protocol's ``milestones`` are the day offsets of the three protocol rules ``d1``, ``d3`` and ``d7``:
a milestone day wins over ``clinic.crm_rule.delay_days`` of the same rule for sessions of this protocol.
``followup_days`` is the review recommendation (D+30 for laser-co2), ``window_days`` how old a session may be
for the chain to apply (45). A protocol is never deleted (services and sessions refer to its ``code``); an
inactive one stops creating tasks and recommendations for new runs.

Read: ``admin.rules`` (owner, manager) and ``session.write`` (the doctor who records the session picks the
protocol). Write: ``admin.rules``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found
from pema.clinic.crm_rules.rules import PROTOCOL_RULE_KEYS
from pema.clinic.models import Protocol
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.catalog import ProtocolCreate, ProtocolMilestone, ProtocolOut, ProtocolUpdate
from pema_contracts.crm import RuleKey
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

READ_PERMISSIONS = (Permission.ADMIN_RULES, Permission.SESSION_WRITE)


def protocol_out(row: Protocol) -> ProtocolOut:
    return ProtocolOut(
        id=row.id,
        code=row.code,
        name=row.name,
        milestones=[
            ProtocolMilestone(rule_key=RuleKey(str(m["rule_key"])), day=int(m["day"])) for m in row.milestones
        ],
        followup_days=row.followup_days,
        window_days=row.window_days,
        active=row.active,
        version=row.version,
    )


def milestones_json(milestones: list[ProtocolMilestone]) -> list[dict[str, object]]:
    return [{"rule_key": m.rule_key.value, "day": m.day} for m in milestones]


def check_milestones(milestones: list[ProtocolMilestone], window_days: int) -> None:
    """Only ``d1``/``d3``/``d7``, each at most once, and none beyond the window (it could never fire)."""
    keys = [m.rule_key for m in milestones]
    if any(k not in PROTOCOL_RULE_KEYS for k in keys):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Mốc theo dõi chỉ gồm D+1, D+3 và D+7.")
    if len(set(keys)) != len(keys):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Mỗi mốc theo dõi chỉ khai báo một lần.")
    late = [m for m in milestones if m.day > window_days]
    if late:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            f"Mốc ngày {late[0].day} vượt quá cửa sổ áp dụng {window_days} ngày.",
        )


async def _load(session: AsyncSession, ctx: ActionContext, protocol_id: UUID) -> Protocol:
    row = await session.scalar(
        select(Protocol).where(Protocol.id == protocol_id, Protocol.clinic_id == ctx.clinic_id)
    )
    if row is None:
        raise not_found("giao thức")
    return row


async def list_protocols(db: ClinicDatabase, ctx: ActionContext) -> list[ProtocolOut]:
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        rows = (
            await session.scalars(
                select(Protocol).where(Protocol.clinic_id == ctx.clinic_id).order_by(Protocol.code)
            )
        ).all()
        return [protocol_out(r) for r in rows]


async def create_protocol(db: ClinicDatabase, ctx: ActionContext, payload: ProtocolCreate) -> ProtocolOut:
    require(ctx, Permission.ADMIN_RULES)
    check_milestones(payload.milestones, payload.window_days)
    async with db.session() as session:
        row = Protocol(
            clinic_id=ctx.clinic_id,
            code=payload.code,
            name=payload.name,
            milestones=milestones_json(payload.milestones),
            followup_days=payload.followup_days,
            window_days=payload.window_days,
            active=payload.active,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Mã giao thức đã tồn tại.") from exc
        await audit.record(
            session,
            ctx,
            "protocol.create",
            "protocol",
            row.id,
            {"code": row.code, "milestones": len(payload.milestones), "followup_days": row.followup_days},
        )
        return protocol_out(row)


async def update_protocol(
    db: ClinicDatabase, ctx: ActionContext, protocol_id: UUID, payload: ProtocolUpdate
) -> ProtocolOut:
    require(ctx, Permission.ADMIN_RULES)
    sent = payload.model_fields_set
    async with db.session() as session:
        row = await _load(session, ctx, protocol_id)
        check_version(row.version, payload.version)
        window = payload.window_days if payload.window_days is not None else row.window_days
        milestones = (
            payload.milestones
            if payload.milestones is not None
            else [
                ProtocolMilestone(rule_key=RuleKey(str(m["rule_key"])), day=int(m["day"]))
                for m in row.milestones
            ]
        )
        check_milestones(milestones, window)

        changed: list[str] = []
        if payload.name is not None and payload.name != row.name:
            row.name = payload.name
            changed.append("name")
        if payload.milestones is not None and milestones_json(milestones) != row.milestones:
            row.milestones = milestones_json(milestones)
            changed.append("milestones")
        if "followup_days" in sent and payload.followup_days != row.followup_days:
            row.followup_days = payload.followup_days
            changed.append("followup_days")
        if payload.window_days is not None and payload.window_days != row.window_days:
            row.window_days = payload.window_days
            changed.append("window_days")
        if payload.active is not None and payload.active != row.active:
            row.active = payload.active
            changed.append("active")
        if not changed:
            return protocol_out(row)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(session, ctx, "protocol.update", "protocol", row.id, {"changed_fields": changed})
        return protocol_out(row)

# new module (not a port): in the prototype the rule table was edited in localStorage, with no roles
"""Admin of the ten automation rules: list and tune (``/admin/rules``).

Authorization is enforced here, in the action, never in the FE (``pema_contracts.roles``): only a signed-in
staff user with the owner or manager role may read or tune the rules (``Permission.ADMIN_RULES``). Package B1
publishes the role-to-permission matrix in ``pema.clinic.rbac``; until it lands this module holds the one
row it
needs (``RULES_ADMIN_ROLES``) and G replaces it with the matrix call (open item).

A tune is an optimistic update: ``version`` must match the stored one or the call fails with
``VERSION_CONFLICT``. Every successful tune writes ONE audit row (field names and the rule key, never
values of
patient data; there are none here). A birthday rule can never leave ``staff_task`` (AGENT.md; the database has
the same CHECK), so the engine and the table agree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from sqlalchemy import text

from pema.clinic.crm_rules.rules import DEFAULT_RULES, json_object, validate_send_mode
from pema.clinic.crm_rules.sql_store import seed_default_rules
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.crm import CrmRuleOut, CrmRuleUpdate, RuleKey, RuleSendMode, TaskPriority
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

RULES_ADMIN_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.MANAGER})
"""Who may read and tune the automation rules (``Permission.ADMIN_RULES``)."""


class CrmRuleAdminService(Protocol):
    async def list_rules(self, ctx: ActionContext) -> list[CrmRuleOut]: ...

    async def update_rule(self, ctx: ActionContext, rule_key: RuleKey, body: CrmRuleUpdate) -> CrmRuleOut: ...


def require_rules_admin(ctx: ActionContext) -> None:
    """Deny by default: a staff user with an allowed role."""
    if ctx.actor_type is not ActorType.USER or ctx.actor_role not in RULES_ADMIN_ROLES:
        raise DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền xem hoặc chỉnh quy tắc chăm sóc.")


def _to_out(row: Mapping[str, Any]) -> CrmRuleOut:
    return CrmRuleOut(
        id=row["id"],
        rule_key=RuleKey(str(row["rule_key"])),
        name=str(row["name"]),
        trigger=str(row["trigger"]),
        delay_days=int(row["delay_days"]),
        suggested_action=str(row["suggested_action"]),
        priority=TaskPriority(str(row["priority"])),
        active=bool(row["active"]),
        send_mode=RuleSendMode(str(row["send_mode"])),
        conditions=json_object(row["conditions"]),
        version=int(row["version"]),
    )


def changed_fields(body: CrmRuleUpdate) -> list[str]:
    """Names of the fields a tune sets (``version`` is the lock, not a change)."""
    return [name for name in body.model_fields_set if name != "version" and getattr(body, name) is not None]


class SqlCrmRuleAdminService:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def list_rules(self, ctx: ActionContext) -> list[CrmRuleOut]:
        require_rules_admin(ctx)
        async with self._db.session() as session:
            await seed_default_rules(session, ctx.clinic_id)
            result = await session.execute(
                text(
                    "SELECT id, rule_key, name, trigger, delay_days, suggested_action, priority, active, "
                    "send_mode, conditions, version FROM clinic.crm_rule WHERE clinic_id = :c"
                ),
                {"c": ctx.clinic_id},
            )
            by_key = {RuleKey(str(r["rule_key"])): _to_out(dict(r)) for r in result.mappings().all()}
        return [by_key[d.key] for d in DEFAULT_RULES if d.key in by_key]

    async def update_rule(self, ctx: ActionContext, rule_key: RuleKey, body: CrmRuleUpdate) -> CrmRuleOut:
        require_rules_admin(ctx)
        if rule_key is RuleKey.MANUAL:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy quy tắc.")
        if body.send_mode is not None and not validate_send_mode(rule_key, body.send_mode):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                "Quy tắc sinh nhật chỉ tạo việc cho nhân viên, không gửi tự động.",
            )
        fields = changed_fields(body)
        async with self._db.session() as session:
            await seed_default_rules(session, ctx.clinic_id)
            result = await session.execute(
                text(
                    "UPDATE clinic.crm_rule SET "
                    "active = COALESCE(:active, active), delay_days = COALESCE(:delay_days, delay_days), "
                    "priority = COALESCE(:priority, priority), "
                    "suggested_action = COALESCE(:suggested_action, suggested_action), "
                    "send_mode = COALESCE(:send_mode, send_mode), version = version + 1 "
                    "WHERE clinic_id = :c AND rule_key = :key AND version = :version "
                    "RETURNING id, rule_key, name, trigger, delay_days, suggested_action, priority, active, "
                    "send_mode, conditions, version"
                ),
                {
                    "c": ctx.clinic_id,
                    "key": rule_key.value,
                    "version": body.version,
                    "active": body.active,
                    "delay_days": body.delay_days,
                    "priority": body.priority.value if body.priority is not None else None,
                    "suggested_action": body.suggested_action,
                    "send_mode": body.send_mode.value if body.send_mode is not None else None,
                },
            )
            row = result.mappings().first()
            if row is None:
                exists = await session.execute(
                    text("SELECT 1 FROM clinic.crm_rule WHERE clinic_id = :c AND rule_key = :key"),
                    {"c": ctx.clinic_id, "key": rule_key.value},
                )
                if exists.first() is None:
                    raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy quy tắc.")
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT, "Quy tắc đã được người khác sửa. Hãy tải lại rồi thử lại."
                )
            await session.execute(
                text(
                    "INSERT INTO clinic.audit_log (clinic_id, actor_type, actor_user_id, actor_role, action, "
                    "entity_type, entity_id, request_id, details) "
                    "VALUES (:c, 'user', :user, :role, 'crm_rule.update', 'crm_rule', :key, :request, "
                    "CAST(:details AS jsonb))"
                ),
                {
                    "c": ctx.clinic_id,
                    "user": ctx.actor_user_id,
                    "role": ctx.actor_role.value if ctx.actor_role is not None else None,
                    "key": rule_key.value,
                    "request": ctx.request_id,
                    "details": json.dumps({"fields": sorted(fields), "version": int(row["version"])}),
                },
            )
            return _to_out(dict(row))

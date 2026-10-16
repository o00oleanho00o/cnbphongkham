"""Admin DTOs for clinic-level operations: the audit log.

CRM rule admin DTOs live in ``pema_contracts.crm`` (``CrmRuleOut`` / ``CrmRuleUpdate``).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, JsonObject, VnDatetime
from pema_contracts.roles import ActorType, Role

__all__ = ["AuditLogOut"]


class AuditLogOut(ApiModel):
    id: int
    occurred_at: VnDatetime
    actor_type: ActorType
    actor_user_id: UUID | None
    actor_role: Role | None
    action: str = Field(description="Dotted verb, e.g. 'patient.update'.")
    entity_type: str
    entity_id: str | None
    request_id: str | None = None
    details: JsonObject | None = Field(
        default=None, description="Field names and ids only; no message text, no PII values."
    )

"""Action layer contract.

Every business operation is an ``action``: an async callable ``(ActionContext, input) -> output``
in ``pema.clinic.actions``. REST routes, the scheduler and the agent tools all call the same
action; there is no separate path for AI (PLAN-AI01 principle 2). Actions:

* authorise from ``ctx.actor_role`` / ``ctx.actor_type`` (deny by default),
* filter by ``ctx.clinic_id`` (RLS is defence in depth),
* write one ``audit_log`` row for every mutation,
* are idempotent when given an ``idempotency_key``,
* raise ``DomainError`` with an ``ErrorCode`` on failure.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import ConfigDict, Field

from pema_contracts.common import ApiModel, JsonObject, VnDatetime
from pema_contracts.roles import ActorType, Role


class ActionSource(StrEnum):
    UI = "ui"
    AGENT = "agent"
    SCHEDULER = "scheduler"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class ActionContext(ApiModel):
    """Who is calling, for which clinic. Built by the API layer from the JWT or service token."""

    model_config = ConfigDict(frozen=True)

    clinic_id: UUID
    actor_type: ActorType
    actor_user_id: UUID | None = None
    actor_role: Role | None = None
    source: ActionSource = ActionSource.UI
    request_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class AuditRecord(ApiModel):
    """What an action writes to ``clinic.audit_log`` (append-only)."""

    action: str = Field(description="Dotted verb: 'patient.create', 'review_item.approve', ...")
    entity_type: str
    entity_id: str | None = None
    details: JsonObject | None = Field(
        default=None, description="Field names and ids only. Never message text or PII values."
    )
    occurred_at: VnDatetime | None = None


class ActionResult[T](ApiModel):
    data: T
    audit_id: int | None = None
    idempotent_replay: bool = False


class Action[InT: ApiModel, OutT](Protocol):
    """Shape of an action callable (documentation and typing aid)."""

    async def __call__(self, ctx: ActionContext, payload: InT, /) -> OutT: ...

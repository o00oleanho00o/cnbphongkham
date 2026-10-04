"""Plumbing shared by the two D2 admin routers (``admin_agents`` and ``admin_threads``). No zalo-agent source.

Not a router: no route lives here, so the OpenAPI document does not change.

How a request gets what it needs, until package B1's auth and package G's composition root land. Everything is
DENY BY DEFAULT: a missing piece answers 401/403/501, never "allowed".

* the signed-in staff member: B1's auth layer sets ``request.state.clinic_id`` (``UUID``) and
  ``request.state.permissions`` (a collection of ``pema_contracts.roles.Permission`` values); this module
  reads only those two attributes. No clinic id -> 401 ``unauthenticated`` (and nothing is touched: the
  guard runs before the handler body). A missing permission -> 403 ``forbidden``;
* the stores: package G sets ``app.state.admin_stores = AdminStores(...)`` at start-up. Without it -> 501
  ``not_implemented`` (the skeleton behaviour);
* the pending-batch cancel and the audit sink are optional hooks, see ``AdminStores``.

Every history message, memory fact and contact is patient data: these routes are staff-only
(``admin.agents``) and never log message text.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from pema.config.account_store import AccountStoreImpl
from pema.config.agent_store import AgentStoreImpl
from pema.conversation.store import PostgresConversationStore
from pema_contracts.common import JsonObject
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

CancelPendingBatch = Callable[[UUID, str, str], Awaitable[int]]
"""``huyBatchCuaThread``: drop the messages the batcher (package C1, Redis) still holds for a thread and
return how many. The destructive routes call it BEFORE touching the database: a parked batch that runs in
between would write the old messages back into the history that was just cleaned."""

AuditSink = Callable[[UUID, str, str, str, JsonObject], Awaitable[None]]
"""``(clinic_id, action, entity_type, entity_id, details)``: writes one audit row (package B1's audit log).
The details carry ids and counts only, never message text."""


@dataclass
class AdminStores:
    agents: AgentStoreImpl
    accounts: AccountStoreImpl
    conversation: PostgresConversationStore
    cancel_pending_batch: CancelPendingBatch | None = None
    audit: AuditSink | None = None


def get_admin_stores(request: Request) -> AdminStores:
    stores = getattr(request.app.state, "admin_stores", None)
    if not isinstance(stores, AdminStores):
        raise DomainError(ErrorCode.NOT_IMPLEMENTED, "Chức năng chưa được triển khai.")
    return stores


def get_clinic_id(request: Request) -> UUID:
    clinic_id: object = getattr(request.state, "clinic_id", None)
    if not isinstance(clinic_id, UUID):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
    return clinic_id


def has_permission(request: Request, permission: Permission) -> bool:
    granted: object = getattr(request.state, "permissions", None)
    if not isinstance(granted, Collection):
        return False
    held: Collection[object] = granted  # pyright: ignore[reportUnknownVariableType]
    return permission in held or permission.value in held


def require_permission(request: Request, permission: Permission) -> None:
    if not has_permission(request, permission):
        raise DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.")


def require_admin_agents(request: Request, clinic_id: Annotated[UUID, Depends(get_clinic_id)]) -> UUID:
    """Dependency of every route of both routers: signed in (-> the clinic) AND holding ``admin.agents``. The
    clinic id is resolved FIRST so an anonymous caller gets 401, not 403."""
    require_permission(request, Permission.ADMIN_AGENTS)
    return clinic_id


ClinicId = Annotated[UUID, Depends(require_admin_agents)]
Stores = Annotated[AdminStores, Depends(get_admin_stores)]


async def record_audit(
    stores: AdminStores, clinic_id: UUID, action: str, entity_type: str, entity_id: str, details: JsonObject
) -> None:
    """Audit one mutation when a sink is wired (see ``AuditSink``)."""
    if stores.audit is not None:
        await stores.audit(clinic_id, action, entity_type, entity_id, details)

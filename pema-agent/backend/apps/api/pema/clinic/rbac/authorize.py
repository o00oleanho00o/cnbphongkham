"""Authorization checks used by every action: deny by default, raise ``DomainError(FORBIDDEN)``.

New module. The check is on the ``ActionContext`` (who), never on a request, so REST routes, the scheduler
and the agent tools all authorise the same way (PLAN-AI01 principle 3).
"""

from __future__ import annotations

from collections.abc import Iterable

from pema.clinic.rbac.matrix import CLINICAL_ROLES, permissions_for
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission, Role

FORBIDDEN_MESSAGE = "Bạn không có quyền thực hiện thao tác này."


def has_permission(ctx: ActionContext, permission: Permission) -> bool:
    return permission in permissions_for(ctx.actor_type, ctx.actor_role)


def require(ctx: ActionContext, permission: Permission) -> None:
    if not has_permission(ctx, permission):
        raise DomainError(ErrorCode.FORBIDDEN, FORBIDDEN_MESSAGE, details={"permission": permission.value})


def require_any(ctx: ActionContext, permissions: Iterable[Permission]) -> None:
    wanted = tuple(permissions)
    if not any(has_permission(ctx, p) for p in wanted):
        raise DomainError(
            ErrorCode.FORBIDDEN, FORBIDDEN_MESSAGE, details={"permission": [p.value for p in wanted]}
        )


def is_role(ctx: ActionContext, *roles: Role) -> bool:
    return ctx.actor_type is ActorType.USER and ctx.actor_role in roles


def is_clinical(ctx: ActionContext) -> bool:
    """Owner and doctor may see and decide clinical review items. Everything else is non-clinical."""
    return ctx.actor_type is ActorType.USER and ctx.actor_role in CLINICAL_ROLES


def is_doctor_scoped(ctx: ActionContext) -> bool:
    """A doctor only opens records they own or are scheduled for (docs/ARCH-PB01.md, AGENT.md CRM01)."""
    return is_role(ctx, Role.DOCTOR)

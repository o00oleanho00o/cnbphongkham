"""The seam between B1's session and the admin routers of the other packages (package G, no TS source).

Every admin router was written against a small seam of its own (``request.state.clinic_id`` and
``request.state.permissions`` for D2/D3, ``request.state.action_context`` for P, ``request.state.actor`` for
S, a ``staff_context_resolver`` for C1/C2, ``dependency_overrides`` for B2/D1/D5 ...). This module is the
ONE place that fills all of them from B1's authentication, so the rules stay in B1:

* ``StaffSessionMiddleware`` verifies the session cookie of a request under ``/api/v1/admin`` with
  ``dashboard_auth.verify_session_token`` (signature, expiry, the session row, the password fingerprint, the
  user and clinic still being active) and, when it is valid, fills ``request.state`` and the settings
  clinic of the task. A missing or bad session fills NOTHING: every router then answers 401 (deny by
  default);
* the permission of the router family is checked HERE for the routers that have no permission check of
  their own (model, usage, tools, schedules, MCP): a role without it gets 403 before the route runs. The
  routers that check their own permission (accounts, channels, agents, KB, policy, rules, B1's) keep doing
  so;
* ``resolve_staff_context`` is the ``staff_context_resolver`` of C1 and the ``authorize`` of C2.

Permissions come from ``pema.clinic.rbac.matrix`` (the matrix of ARCH-PB01): nothing here widens a role.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from pema.api import dashboard_auth
from pema.clinic.rbac.matrix import permissions_for
from pema.config.env import get_settings
from pema.config.runtime_settings_store import use_settings_clinic
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission

log = create_logger("composition.auth")

ADMIN_PREFIX = "/api/v1/admin/"

ROUTER_PERMISSION: dict[str, Permission] = {
    "model": Permission.ADMIN_MODEL,
    "usage": Permission.ADMIN_USAGE,
    "traces": Permission.ADMIN_USAGE,
    "logs": Permission.ADMIN_LOGS,
    "tools": Permission.ADMIN_TOOLS,
    "schedules": Permission.ADMIN_SCHEDULES,
    "mcp": Permission.ADMIN_MCP,
}
"""Router families WITHOUT a permission check of their own: the middleware enforces it. The others check in
their service (B1 actions, D2 ``require_admin_agents``, D3 ``cap_quyen``, C1/C2 ``authorize``, P ``can``)."""


_current_staff: ContextVar[ActionContext | None] = ContextVar("pema_staff_context", default=None)


def current_staff_context() -> ActionContext | None:
    """The ``ActionContext`` of the signed-in staff member of the request being served, if any (audit sinks
    of the packages that have no context argument read it)."""
    return _current_staff.get()


def _family(path: str) -> str | None:
    if not path.startswith(ADMIN_PREFIX):
        return None
    return path[len(ADMIN_PREFIX) :].split("/", 1)[0] or None


def _state_of(scope: Scope) -> dict[str, Any]:
    state: dict[str, Any] = scope.setdefault("state", {})
    return state


def _cookie_of(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                cookie_name, _, cookie_value = part.strip().partition("=")
                if cookie_name == name:
                    return cookie_value
    return None


def _request_id_of(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"x-request-id":
            return value.decode("latin-1")
    return None


class StaffSessionMiddleware:
    """Pure ASGI middleware (not ``BaseHTTPMiddleware``): the downstream app runs in the SAME task, so the
    settings clinic set here is visible to the route and to the synchronous readers it calls."""

    def __init__(self, app: ASGIApp, db: Callable[[], ClinicDatabase]) -> None:
        self.app = app
        self._db = db

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        family = _family(scope["path"]) if scope["type"] == "http" else None
        if family is None:
            await self.app(scope, receive, send)
            return
        token = _cookie_of(scope, get_settings().session_cookie_name)
        user = await dashboard_auth.verify_session_token(self._db(), token) if token else None
        if user is None:
            await self.app(scope, receive, send)
            return
        permissions = permissions_for(ActorType.USER, user.role)
        required = ROUTER_PERMISSION.get(family)
        if required is not None and required not in permissions:
            error = DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.")
            response = JSONResponse(
                status_code=error.http_status,
                content=error.to_response(_request_id_of(scope)).model_dump(mode="json"),
            )
            await response(scope, receive, send)
            return
        state = _state_of(scope)
        state["clinic_id"] = user.clinic_id
        state["user_id"] = user.user_id
        state["role"] = user.role.value
        state["permissions"] = frozenset(p.value for p in permissions)
        state["action_context"] = user.action_context(request_id=_request_id_of(scope))
        state["actor"] = str(user.user_id)
        token_ctx = _current_staff.set(state["action_context"])
        try:
            with use_settings_clinic(user.clinic_id):
                await self.app(scope, receive, send)
        finally:
            _current_staff.reset(token_ctx)


def clinic_of(request: Request) -> UUID:
    clinic_id: object = getattr(request.state, "clinic_id", None)
    if not isinstance(clinic_id, UUID):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
    return clinic_id


def require_permission(request: Request, permission: Permission) -> ActionContext:
    """The ``ActionContext`` of the signed-in staff member, once the permission is checked."""
    context: object = getattr(request.state, "action_context", None)
    granted: object = getattr(request.state, "permissions", None)
    if not isinstance(context, ActionContext) or not isinstance(granted, Collection):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
    held: Collection[object] = granted  # pyright: ignore[reportUnknownVariableType]
    if permission.value not in held:
        raise DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.")
    return context


async def resolve_staff_context(request: Request, permission: Permission) -> ActionContext:
    """``staff_context_resolver`` (C1) and ``authorize`` (C2): ``(request, permission) -> ActionContext``."""
    return require_permission(request, permission)


type Resolver = Callable[[Request, Permission], Awaitable[ActionContext]]

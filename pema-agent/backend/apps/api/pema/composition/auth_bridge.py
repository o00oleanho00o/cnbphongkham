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
  their own (model, usage, tools, schedules, MCP, policy): a role without it gets 403 before the route runs.
  The
  routers that check their own permission (accounts, channels, agents, KB, rules, B1's) keep doing
  so;
* ``resolve_staff_context`` is the ``staff_context_resolver`` of C1 and the ``authorize`` of C2.

Permissions come from ``pema.clinic.rbac.matrix`` (the matrix of ARCH-PB01): nothing here widens a role.

Default deny (package G, SECURITY-REVIEW-AI01 SEC-13): once the application is wired, EVERY route under
``/api/v1`` refuses a call without a session cookie (401) except the ones that authenticate in another way
(``PUBLIC_API_PREFIXES``: the login and the two signed webhooks). A route added later with a forgotten
guard is therefore closed, not open. Admin routes also verify the cookie here; the other staff routes verify
it in their own dependency (``dashboard_auth.current_user``), so a valid cookie costs one lookup, not two.

Audit (same review, SEC-23): a successful change made through the families of ``AUDITED_FAMILIES`` (knowledge
base, MCP servers, schedules, tool settings) writes one ``clinic.audit_log`` row of its own, with the method
and the path only (never a body: it may hold a key or a text). The other admin families audit in their
services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pema.api import dashboard_auth
from pema.api.request_id import clean_request_id
from pema.clinic import audit
from pema.clinic.rbac.matrix import permissions_for
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission

log = create_logger("composition.auth")

API_PREFIX = "/api/v1/"
ADMIN_PREFIX = "/api/v1/admin/"
PUBLIC_API_PREFIXES: tuple[str, ...] = ("/api/v1/auth/login", "/api/v1/webhooks/", "/api/v1/.well-known/")
"""Routes that authenticate in another way: the login itself and the webhooks (secret token / HMAC); and the
public key set of the agent tokens."""
AUDITED_FAMILIES: frozenset[str] = frozenset({"kb", "mcp", "schedules", "tools"})
"""Admin families whose services write no audit row of their own."""
UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ROUTER_PERMISSION: dict[str, Permission] = {
    "model": Permission.ADMIN_MODEL,
    "usage": Permission.ADMIN_USAGE,
    "traces": Permission.ADMIN_USAGE,
    "logs": Permission.ADMIN_LOGS,
    "tools": Permission.ADMIN_TOOLS,
    "schedules": Permission.ADMIN_SCHEDULES,
    "mcp": Permission.ADMIN_MCP,
    "policy": Permission.ADMIN_POLICY,
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
            return clean_request_id(value.decode("latin-1"))
    return None


async def _refuse(scope: Scope, receive: Receive, send: Send, error: DomainError) -> None:
    response = JSONResponse(
        status_code=error.http_status,
        content=error.to_response(_request_id_of(scope)).model_dump(mode="json"),
    )
    await response(scope, receive, send)


class StaffSessionMiddleware:
    """Pure ASGI middleware (not ``BaseHTTPMiddleware``): the downstream app runs in the SAME task, so the
    settings clinic set here is visible to the route and to the synchronous readers it calls."""

    def __init__(
        self, app: ASGIApp, db: Callable[[], ClinicDatabase], enforce: Callable[[], bool] = lambda: True
    ) -> None:
        self.app = app
        self._db = db
        self._enforce = enforce
        """Whether an anonymous call to a guarded family is refused here. ``False`` only for a bare
        ``create_app()`` with no composition root (the route tests that replace the dependencies by hand)."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope["path"] if scope["type"] == "http" else ""
        if not path.startswith(API_PREFIX) or path.startswith(PUBLIC_API_PREFIXES):
            await self.app(scope, receive, send)
            return
        token = _cookie_of(scope, get_settings().session_cookie_name)
        family = _family(path)
        if family is None:
            # A staff route outside /admin: its own dependency verifies the session. Default deny only here.
            if token is None and self._enforce():
                await _refuse(
                    scope, receive, send, DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
                )
                return
            await self.app(scope, receive, send)
            return
        user = await dashboard_auth.verify_session_token(self._db(), token) if token else None
        required = ROUTER_PERMISSION.get(family)
        if user is None:
            if self._enforce():
                # Whether or not the router checks the session itself, an anonymous call stops here: some of
                # them (the application log) need no clinic at all, and a route that forgot its guard stays
                # shut.
                await _refuse(
                    scope, receive, send, DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
                )
                return
            await self.app(scope, receive, send)
            return
        permissions = permissions_for(ActorType.USER, user.role)
        if required is not None and required not in permissions:
            await _refuse(
                scope,
                receive,
                send,
                DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này."),
            )
            return
        state = _state_of(scope)
        state["clinic_id"] = user.clinic_id
        state["user_id"] = user.user_id
        state["role"] = user.role.value
        state["permissions"] = frozenset(p.value for p in permissions)
        state["action_context"] = user.action_context(request_id=_request_id_of(scope))
        state["actor"] = str(user.user_id)
        token_ctx = _current_staff.set(state["action_context"])
        status_seen: list[int] = []

        async def watch_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_seen.append(int(message["status"]))
            await send(message)

        try:
            await self.app(scope, receive, watch_status)
        finally:
            _current_staff.reset(token_ctx)
        method = str(scope.get("method", "")).upper()
        if family in AUDITED_FAMILIES and method in UNSAFE_METHODS and status_seen and status_seen[0] < 400:
            await self._audit(state["action_context"], family, method, path, status_seen[0])

    async def _audit(self, ctx: ActionContext, family: str, method: str, path: str, status: int) -> None:
        """One row per successful change (the response is already on its way: a failure here is logged, it
        cannot undo the change)."""
        try:
            async with self._db().session() as session:
                await audit.record(
                    session,
                    ctx,
                    f"admin.{family}.{method.lower()}",
                    "admin_route",
                    path[:200],
                    {"status": status},
                )
        except Exception as err:
            log.error("audit of an admin change failed", err=err, family=family)


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

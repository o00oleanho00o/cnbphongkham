"""Identity and RBAC (package B1). Session = HttpOnly JWT cookie; see ``pema.api.dashboard_auth``."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, Security, status

from pema.api import dashboard_auth as auth
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.rbac import permissions_for
from pema_contracts.auth import LoginRequest, MeResponse, PermissionsResponse, SessionInfo
from pema_contracts.roles import ActorType, Permission

router = APIRouter(tags=["auth"], responses=ERROR_RESPONSES)


def _ordered(permissions: frozenset[Permission]) -> list[Permission]:
    return sorted(permissions, key=lambda p: p.value)


@router.post("/auth/login", response_model=SessionInfo, summary="Sign in and set the session cookie")
async def login(body: LoginRequest, request: Request, response: Response, db: auth.Database) -> SessionInfo:
    result = await auth.login(
        db,
        body,
        client_ip=auth.client_ip(request),
        request_id=request.headers.get("x-request-id"),
    )
    auth.set_session_cookie(response, result)
    return result.user.session_info()


@router.post(
    "/auth/refresh",
    response_model=SessionInfo,
    dependencies=[Security(cookie_scheme)],
    summary="Extend the current session",
)
async def refresh(
    request: Request, response: Response, db: auth.Database, user: auth.CurrentUser
) -> SessionInfo:
    result = await auth.refresh(db, user, request.headers.get("x-request-id"))
    auth.set_session_cookie(response, result)
    return result.user.session_info()


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(cookie_scheme)],
    summary="Clear the session cookie",
)
async def logout(request: Request, response: Response, db: auth.Database, user: auth.CurrentUser) -> None:
    await auth.revoke_session(db, user, request.headers.get("x-request-id"))
    auth.clear_session_cookie(response)


@router.get(
    "/me",
    response_model=MeResponse,
    dependencies=[Security(cookie_scheme)],
    summary="Current user, clinic and permission list",
)
async def me(user: auth.CurrentUser) -> MeResponse:
    return MeResponse(user=user.summary(), permissions=_ordered(permissions_for(ActorType.USER, user.role)))


@router.get(
    "/permissions",
    response_model=PermissionsResponse,
    dependencies=[Security(cookie_scheme)],
    summary="Permission codes of the current role (deny by default)",
)
async def permissions(user: auth.CurrentUser) -> PermissionsResponse:
    return PermissionsResponse(
        role=user.role, permissions=_ordered(permissions_for(ActorType.USER, user.role))
    )

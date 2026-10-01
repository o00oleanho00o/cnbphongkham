"""Identity and RBAC (package B1). Session = HttpOnly JWT cookie; see ``pema.api.dashboard_auth``."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, Security, status

from pema.api import dashboard_auth as auth
from pema.api import dashboard_password_store as password_store
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.api.request_id import clean_request_id
from pema.clinic.rbac import permissions_for
from pema_contracts.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    PermissionsResponse,
    SessionInfo,
)
from pema_contracts.errors import DomainError, ErrorCode
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
        request_id=clean_request_id(request.headers.get("x-request-id")),
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
    result = await auth.refresh(db, user, clean_request_id(request.headers.get("x-request-id")))
    auth.set_session_cookie(response, result)
    return result.user.session_info()


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(cookie_scheme)],
    summary="Clear the session cookie",
)
async def logout(request: Request, response: Response, db: auth.Database, user: auth.CurrentUser) -> None:
    await auth.revoke_session(db, user, clean_request_id(request.headers.get("x-request-id")))
    auth.clear_session_cookie(response)


@router.post(
    "/auth/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(cookie_scheme)],
    summary="Change the signed-in user's own password",
    description=(
        "Needs the current password, so a borrowed cookie cannot take the account over. Every OTHER "
        "session of the user ends at once; the session that made the change keeps working. Wrong attempts "
        "count against the login rate limit (5 per minute per user)."
    ),
)
async def change_password(
    body: ChangePasswordRequest, request: Request, db: auth.Database, user: auth.CurrentUser
) -> None:
    # ``dashboard-password-route.ts`` shared the login attempt counter: a stolen cookie must not be able to
    # guess the current password at machine speed. Keyed by user, cleared by a success.
    bucket = f"password:{user.user_id}"
    if not auth.allow_login_attempt(bucket):
        raise DomainError(ErrorCode.RATE_LIMITED, "Thử đổi mật khẩu quá nhiều lần. Vui lòng đợi một phút.")
    await password_store.change_password(
        db,
        user.action_context(clean_request_id(request.headers.get("x-request-id"))),
        current_password=body.current_password.get_secret_value(),
        new_password=body.new_password.get_secret_value(),
        keep_session_id=user.session_id,
    )
    auth.clear_login_attempts(bucket)


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

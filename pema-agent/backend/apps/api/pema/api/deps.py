"""Shared route plumbing for the OpenAPI skeleton: security schemes, common parameters, 501 helper."""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Header, Query, Security
from fastapi.security import APIKeyCookie

from pema_contracts.errors import DomainError, ErrorCode, ErrorResponse

API_PREFIX = "/api/v1"

cookie_scheme = APIKeyCookie(
    name="pema_session",
    auto_error=False,
    scheme_name="SessionCookie",
    description="HttpOnly JWT cookie set by POST /auth/login (staff).",
)

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=128,
        description="Repeats with the same key and body return the first result.",
    ),
]
Limit = Annotated[int, Query(ge=1, le=200, description="Page size.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not authenticated."},
    403: {"model": ErrorResponse, "description": "Role lacks the permission."},
    404: {"model": ErrorResponse, "description": "Not found in this clinic."},
    409: {"model": ErrorResponse, "description": "Version conflict or invalid state."},
    422: {"model": ErrorResponse, "description": "Validation failed."},
    429: {"model": ErrorResponse, "description": "Rate limited or channel cap reached."},
    501: {"model": ErrorResponse, "description": "Skeleton: not implemented yet."},
}


def not_implemented() -> NoReturn:
    """Every skeleton endpoint ends here until its owning package implements it."""
    raise DomainError(ErrorCode.NOT_IMPLEMENTED, "Chức năng chưa được triển khai.")


def admin_router(segment: str, tag: str) -> APIRouter:
    """Router mounted at ``/admin/<segment>`` for staff with a session cookie. Each admin router file is
    owned by ONE package (docs/CONTRACTS-AI01.md); that package replaces the 501 bodies in its file only."""
    return APIRouter(
        prefix=f"/admin/{segment}",
        tags=[tag],
        responses=ERROR_RESPONSES,
        dependencies=[Security(cookie_scheme)],
    )

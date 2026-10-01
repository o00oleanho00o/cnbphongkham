"""Staff accounts of the clinic (package B1): the owner resets another user's password (SEC-24).

There is no route to list or create users yet (accounts come from the seed script); this router only holds
the reset, so a forgotten password no longer needs the operator to touch the database.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Request, status

from pema.api import dashboard_auth as auth
from pema.api import dashboard_password_store as password_store
from pema.api.deps import admin_router
from pema.api.request_id import clean_request_id
from pema.clinic.rbac import require
from pema_contracts.auth import ResetPasswordRequest
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

router = admin_router("users", "admin-users")


@router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Owner resets another staff member's password",
    description=(
        "Owner only (`admin.users`). Sets a new password for a user of the SAME clinic (another clinic's id "
        "is a 404) and ends EVERY session of that user at once. Not for the caller's own account: use "
        "`POST /auth/password`. The new password has the same 8-character floor as a password change. "
        "Limited to 5 resets per minute per owner. The audit entry records who reset whose account, never "
        "the password."
    ),
)
async def reset_user_password(
    user_id: UUID, body: ResetPasswordRequest, request: Request, db: auth.Database, user: auth.CurrentUser
) -> None:
    ctx = user.action_context(clean_request_id(request.headers.get("x-request-id")))
    # Permission first, so a non-owner is told 403 and never spends (or is told about) the owner's budget.
    require(ctx, Permission.ADMIN_USERS)
    if not auth.allow_login_attempt(f"reset-password:{user.user_id}"):
        raise DomainError(ErrorCode.RATE_LIMITED, "Đặt lại mật khẩu quá nhiều lần. Vui lòng đợi một phút.")
    await password_store.set_password(db, ctx, user_id, body.new_password.get_secret_value())

"""Staff accounts of the clinic (package B1, H4): list, create, edit and lock, and the owner's password reset.

``GET`` is ``admin.users.read`` (owner and manager); every change is ``admin.users`` (owner only). The rules
(self-lock, last owner, session revocation, audit) live in ``dashboard_staff_store`` and
``dashboard_password_store``, never here. A staff member is never deleted: the way out is to lock them.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Query, Request, status

from pema.api import dashboard_auth as auth
from pema.api import dashboard_password_store as password_store
from pema.api import dashboard_staff_store as staff_store
from pema.api.deps import Limit, Offset, admin_router
from pema.api.request_id import clean_request_id
from pema.clinic.rbac import require
from pema_contracts.actions import ActionContext
from pema_contracts.auth import ResetPasswordRequest, StaffUserCreate, StaffUserOut, StaffUserUpdate
from pema_contracts.common import Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission, Role

router = admin_router("users", "admin-users")


def _spend(ctx: ActionContext, bucket: str, message: str) -> None:
    """Permission first, so a caller without it is told 403 and never spends (or learns about) the owner's
    budget; then 5 attempts per minute per owner and kind of action."""
    require(ctx, Permission.ADMIN_USERS)
    if not auth.allow_login_attempt(f"{bucket}:{ctx.actor_user_id}"):
        raise DomainError(ErrorCode.RATE_LIMITED, message)


@router.get(
    "",
    response_model=Page[StaffUserOut],
    summary="Staff accounts of the clinic",
    description=(
        "Owner and manager (`admin.users.read`). Staff of the caller's clinic only, A to Z by name, never a "
        "password or a hash. Filters: `q` (name or e-mail, any case), `role`, `active` (false = locked)."
    ),
)
async def list_users(
    db: auth.Database,
    ctx: auth.Ctx,
    q: Annotated[str | None, Query(max_length=100, description="Name or e-mail contains this text.")] = None,
    role: Role | None = None,
    active: bool | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[StaffUserOut]:
    return await staff_store.list_staff(db, ctx, q=q, role=role, active=active, limit=limit, offset=offset)


@router.post(
    "",
    response_model=StaffUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Owner creates a staff account",
    description=(
        "Owner only (`admin.users`). Role is one of owner, manager, doctor, cs_staff, reception, "
        "accountant (never `patient`). The e-mail is the sign-in name, unique per clinic (409 when taken). "
        "The initial password has the same 8-character floor as a password change. Limited to 5 creations "
        "per minute per owner. The audit entry never holds the password, the name or the e-mail."
    ),
)
async def create_user(body: StaffUserCreate, db: auth.Database, ctx: auth.Ctx) -> StaffUserOut:
    _spend(ctx, "create-user", "Tạo tài khoản quá nhiều lần. Vui lòng đợi một phút.")
    return await staff_store.create_staff(db, ctx, body)


@router.patch(
    "/{user_id}",
    response_model=StaffUserOut,
    summary="Owner renames, re-roles, locks or unlocks a staff member",
    description=(
        "Owner only (`admin.users`), same clinic (another clinic's id is a 404). Send the `version` you "
        "read. Locking (`active: false`) or changing the role ends EVERY session of that user at once; a "
        "locked account cannot sign in. Refused with 422: locking or re-roling your own account, and "
        "anything that would leave the clinic without an active owner. Staff are never deleted, only "
        "locked."
    ),
)
async def update_user(user_id: UUID, body: StaffUserUpdate, db: auth.Database, ctx: auth.Ctx) -> StaffUserOut:
    return await staff_store.update_staff(db, ctx, user_id, body)


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
    _spend(ctx, "reset-password", "Đặt lại mật khẩu quá nhiều lần. Vui lòng đợi một phút.")
    await password_store.set_password(db, ctx, user_id, body.new_password.get_secret_value())

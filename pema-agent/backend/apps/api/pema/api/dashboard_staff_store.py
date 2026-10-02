"""Staff accounts of the clinic: list, create, edit and lock (package H4, ``routers/admin_users.py``).

New module, no zalo-agent original: the original had ONE dashboard password and no accounts. It sits next to
``dashboard_password_store`` (which resets a password) and uses ``dashboard_session_store`` to end
sessions, so it lives in ``pema.api`` like them (the action layer may not import the API layer).

Rules, all enforced here and never by the screen:

* reading the list is ``admin.users.read`` (owner and manager); every change is ``admin.users`` (owner only);
* rows of another clinic are a 404 (row level security leaves nothing to find; the ``clinic_id`` filter is the
  second lock); a user that is not a staff role (``patient``) is never listed and never editable here;
* a staff member is never deleted (audit rows and foreign keys point at them): the only way out is to LOCK
  (``active = false``). A locked account cannot sign in and every session it had is deleted at once;
* a role change also deletes every session of that user, so no access granted by the old role lives on;
* the owner cannot lock or re-role their OWN account (422), and the clinic always keeps at least one ACTIVE
  owner (422): the active owners are locked ``FOR UPDATE`` before the check, so two owners demoting each other
  at the same moment cannot leave the clinic without one;
* the e-mail (the sign-in name) is unique per clinic (409 on a duplicate);
* optimistic concurrency by ``version`` (409 ``version_conflict``);
* the audit row carries field NAMES, roles and ids, never a name, an e-mail or a password.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.api import dashboard_session_store as sessions
from pema.clinic import audit
from pema.clinic.actions._common import check_version, escape_like, lost_race_is_conflict
from pema.clinic.models import UserAccount
from pema.clinic.rbac import passwords, require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.auth import StaffUserCreate, StaffUserOut, StaffUserUpdate
from pema_contracts.common import Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import STAFF_ROLES, Permission, Role

USER_NOT_FOUND_MESSAGE = "Không tìm thấy tài khoản."
DUPLICATE_EMAIL_MESSAGE = "Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác."
NOT_A_STAFF_ROLE_MESSAGE = "Vai trò này không dành cho nhân viên."
CANNOT_CHANGE_OWN_ACCESS_MESSAGE = "Bạn không thể tự khóa hoặc tự đổi vai trò của chính mình."
LAST_OWNER_MESSAGE = "Phòng khám phải luôn có ít nhất một chủ phòng khám đang hoạt động."
NOTHING_TO_CHANGE_MESSAGE = "Không có thay đổi nào để lưu."
TOO_SHORT_MESSAGE = f"Mật khẩu cần ít nhất {passwords.MIN_PASSWORD_LENGTH} ký tự."

_STAFF_ROLE_VALUES = tuple(sorted(role.value for role in STAFF_ROLES))


def staff_out(row: UserAccount) -> StaffUserOut:
    return StaffUserOut(
        id=row.id,
        display_name=row.display_name,
        email=row.email,
        role=Role(row.role),
        active=row.active,
        last_login_at=row.last_login_at,
        created_at=row.created_at,
        version=row.version,
    )


def _require_staff_role(role: Role) -> None:
    if role not in STAFF_ROLES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, NOT_A_STAFF_ROLE_MESSAGE)


async def list_staff(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    q: str | None = None,
    role: Role | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[StaffUserOut]:
    """Staff of the caller's clinic, A to Z by name. ``q`` matches the name or the e-mail, any case."""
    require(ctx, Permission.ADMIN_USERS_READ)
    conditions: list[Any] = [UserAccount.clinic_id == ctx.clinic_id, UserAccount.role.in_(_STAFF_ROLE_VALUES)]
    if role is not None:
        conditions.append(UserAccount.role == role.value)
    if active is not None:
        conditions.append(UserAccount.active.is_(active))
    needle = (q or "").strip()
    if needle:
        pattern = f"%{escape_like(needle)}%"
        conditions.append(
            or_(
                UserAccount.display_name.ilike(pattern, escape="\\"),
                UserAccount.email.ilike(pattern, escape="\\"),
            )
        )
    async with db.session(ctx.clinic_id) as session:
        total = await session.scalar(select(func.count()).select_from(UserAccount).where(*conditions)) or 0
        rows = (
            await session.scalars(
                select(UserAccount)
                .where(*conditions)
                .order_by(func.lower(UserAccount.display_name), UserAccount.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items = [staff_out(r) for r in rows]
    return Page[StaffUserOut](items=items, total=total, limit=limit, offset=offset)


async def create_staff(db: ClinicDatabase, ctx: ActionContext, payload: StaffUserCreate) -> StaffUserOut:
    """The owner creates a staff account with an initial password they choose (8-character floor)."""
    require(ctx, Permission.ADMIN_USERS)
    _require_staff_role(payload.role)
    plain = payload.password.get_secret_value()
    if len(plain) < passwords.MIN_PASSWORD_LENGTH:
        raise DomainError(ErrorCode.VALIDATION_FAILED, TOO_SHORT_MESSAGE)
    async with db.session(ctx.clinic_id) as session:
        row = UserAccount(
            clinic_id=ctx.clinic_id,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role.value,
            password_hash=passwords.hash_password(plain),
            active=True,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.INVALID_STATE, DUPLICATE_EMAIL_MESSAGE) from exc
        await session.refresh(row, ["created_at"])
        await audit.record(session, ctx, "user.create", "user_account", row.id, {"role": row.role})
        return staff_out(row)


async def _lock_active_owners(session: AsyncSession, clinic_id: UUID) -> list[UUID]:
    """Lock every ACTIVE owner of the clinic (a fixed order, so two callers cannot deadlock)."""
    return list(
        (
            await session.scalars(
                select(UserAccount.id)
                .where(
                    UserAccount.clinic_id == clinic_id,
                    UserAccount.role == Role.OWNER.value,
                    UserAccount.active.is_(True),
                )
                .order_by(UserAccount.id)
                .with_for_update()
            )
        ).all()
    )


async def update_staff(
    db: ClinicDatabase, ctx: ActionContext, user_id: UUID, payload: StaffUserUpdate
) -> StaffUserOut:
    """The owner renames, re-roles, locks or unlocks a staff member."""
    require(ctx, Permission.ADMIN_USERS)
    if payload.display_name is None and payload.role is None and payload.active is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, NOTHING_TO_CHANGE_MESSAGE)
    if payload.role is not None:
        _require_staff_role(payload.role)
    async with db.session(ctx.clinic_id) as session:
        owners: list[UUID] = []
        if payload.role is not None or payload.active is not None:
            # Before anything is read: the count of active owners must not change under our feet.
            owners = await _lock_active_owners(session, ctx.clinic_id)
        row = await session.scalar(
            select(UserAccount)
            .where(
                UserAccount.id == user_id,
                UserAccount.clinic_id == ctx.clinic_id,
                UserAccount.role.in_(_STAFF_ROLE_VALUES),
            )
            .with_for_update()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, USER_NOT_FOUND_MESSAGE)
        check_version(row.version, payload.version)

        changed: list[str] = []
        details: dict[str, Any] = {}
        revoke = False
        if payload.display_name is not None and payload.display_name != row.display_name:
            row.display_name = payload.display_name
            changed.append("display_name")
        if payload.role is not None and payload.role.value != row.role:
            if row.id == ctx.actor_user_id:
                raise DomainError(ErrorCode.VALIDATION_FAILED, CANNOT_CHANGE_OWN_ACCESS_MESSAGE)
            details["role_from"] = row.role
            details["role_to"] = payload.role.value
            row.role = payload.role.value
            changed.append("role")
            revoke = True
        if payload.active is not None and payload.active != row.active:
            if row.id == ctx.actor_user_id and not payload.active:
                raise DomainError(ErrorCode.VALIDATION_FAILED, CANNOT_CHANGE_OWN_ACCESS_MESSAGE)
            row.active = payload.active
            details["active"] = payload.active
            changed.append("active")
            if not payload.active:
                revoke = True
        if not changed:
            return staff_out(row)

        stays_owner = row.role == Role.OWNER.value and row.active
        if row.id in owners and not stays_owner and not any(other != row.id for other in owners):
            raise DomainError(ErrorCode.VALIDATION_FAILED, LAST_OWNER_MESSAGE)
        with lost_race_is_conflict():
            await session.flush()
        if revoke:
            await sessions.delete_other_sessions(session, row.id, None)
        details["changed_fields"] = changed
        details["sessions_revoked"] = revoke
        await audit.record(session, ctx, "user.update", "user_account", row.id, details)
        return staff_out(row)

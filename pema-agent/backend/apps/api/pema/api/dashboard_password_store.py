# ported from: src/server/dashboard-password-store.ts
"""Per-user passwords of the dashboard, stored as argon2id hashes in ``clinic.user_account.password_hash``.

Forced deviations: the original had ONE dashboard password in ``runtime_settings`` (scrypt, "DB beats env",
the env var as an on/off switch). The clinic has accounts: the hash lives on the user row and there is no
environment password and no "forgotten password: delete one row" recovery. Recovery is an owner resetting the
account (``set_password``) or the operator running the seed script; that is a deliberate product choice.

Kept from the original (tests ``test_dashboard_password_store.py``):

* the clear text is never stored; every hash has its own salt;
* a corrupt stored value never matches and never falls back to anything weaker;
* changing a password invalidates every other session of that user at once (the fingerprint stored in each
  session no longer matches), and the session that made the change keeps working;
* the new password has the same floor as before (8 characters) and must differ from the old one.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from pema.api import dashboard_session_store as sessions
from pema.clinic import audit
from pema.clinic.models import UserAccount
from pema.clinic.rbac import passwords, require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission

WRONG_CURRENT_MESSAGE = "Mật khẩu hiện tại không đúng."
TOO_SHORT_MESSAGE = f"Mật khẩu mới cần ít nhất {passwords.MIN_PASSWORD_LENGTH} ký tự."
SAME_AS_OLD_MESSAGE = "Mật khẩu mới phải khác mật khẩu hiện tại."


def verify_user_password(user: UserAccount | None, plain: str) -> bool:
    """Constant-work check: an unknown user costs one throw-away verification, like a wrong password."""
    if user is None:
        passwords.burn_verification_time(plain)
        return False
    return passwords.verify_password(user.password_hash, plain)


def current_password_material(user: UserAccount) -> str:
    """Fingerprint of the password in force (``currentPasswordMaterial`` of the original)."""
    return passwords.fingerprint(user.password_hash)


def _check_new_password(new_password: str) -> None:
    if len(new_password) < passwords.MIN_PASSWORD_LENGTH:
        raise DomainError(ErrorCode.VALIDATION_FAILED, TOO_SHORT_MESSAGE)


async def change_password(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    current_password: str,
    new_password: str,
    keep_session_id: UUID | None,
) -> None:
    """A user changes their OWN password. A borrowed cookie cannot do it without the current password."""
    if ctx.actor_type is not ActorType.USER or ctx.actor_user_id is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Cần đăng nhập.")
    async with db.session(ctx.clinic_id) as session:
        user = await session.scalar(
            select(UserAccount).where(
                UserAccount.id == ctx.actor_user_id, UserAccount.clinic_id == ctx.clinic_id
            )
        )
        if not verify_user_password(user, current_password) or user is None:
            raise DomainError(ErrorCode.UNAUTHENTICATED, WRONG_CURRENT_MESSAGE)
        _check_new_password(new_password)
        if passwords.verify_password(user.password_hash, new_password):
            raise DomainError(ErrorCode.VALIDATION_FAILED, SAME_AS_OLD_MESSAGE)
        user.password_hash = passwords.hash_password(new_password)
        await session.flush()
        await sessions.delete_other_sessions(session, user.id, keep_session_id)
        if keep_session_id is not None:
            await sessions.rebind_fingerprint(
                session, keep_session_id, passwords.fingerprint(user.password_hash)
            )
        await audit.record(session, ctx, "auth.change_password", "user_account", user.id)


async def set_password(db: ClinicDatabase, ctx: ActionContext, user_id: UUID, new_password: str) -> None:
    """An owner resets another account's password (``admin.accounts``). Every session of that user ends."""
    require(ctx, Permission.ADMIN_ACCOUNTS)
    _check_new_password(new_password)
    async with db.session(ctx.clinic_id) as session:
        user = await session.scalar(
            select(UserAccount).where(UserAccount.id == user_id, UserAccount.clinic_id == ctx.clinic_id)
        )
        if user is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản.")
        user.password_hash = passwords.hash_password(new_password)
        await session.flush()
        await sessions.delete_other_sessions(session, user.id, None)
        await audit.record(session, ctx, "auth.reset_password", "user_account", user.id)

# ported from: src/server/dashboard-session-store.ts
"""Server-side record of a dashboard login in ``clinic.auth_session``.

Forced deviations: SQLite ``dashboard_sessions`` becomes ``clinic.auth_session`` (Postgres, RLS by
``clinic_id``, one row per login, tied to a user). The original stored ``sha256(secret)`` because its token
was ``<id>.<secret>``; here the token is a signed JWT that carries only the session id, so no secret needs
hashing: the signature authenticates the cookie and the ROW is what can be revoked. Same properties:

* logout deletes the row, so a leaked cookie stops working at once (a self-contained token would not);
* every row stores the fingerprint of the password in force when it was created, so changing the password
  invalidates every older session (``prune_stale_fingerprint``);
* an expired row is never accepted.

These are Core statements, not ORM objects, on purpose: housekeeping (pruning, revocation) must not trip
the "every ORM mutation is audited" guard. The callers audit the business event (login, logout, refresh,
password change).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.models import AuthSession, Clinic, UserAccount


@dataclass(frozen=True)
class SessionPrincipal:
    """What a valid session resolves to. ``role`` and ``active`` come from the user row at request time, so
    a role change or a deactivation applies at once."""

    session_id: UUID
    user_id: UUID
    clinic_id: UUID
    role: str
    display_name: str
    clinic_name: str
    expires_at: datetime
    password_fingerprint: str
    password_hash: str | None


async def insert_session(
    session: AsyncSession,
    *,
    session_id: UUID,
    clinic_id: UUID,
    user_id: UUID,
    password_fingerprint: str,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    await session.execute(
        insert(AuthSession).values(
            id=session_id,
            clinic_id=clinic_id,
            user_id=user_id,
            password_fingerprint=password_fingerprint,
            created_at=created_at,
            expires_at=expires_at,
        )
    )


async def find_principal(session: AsyncSession, session_id: UUID, now: datetime) -> SessionPrincipal | None:
    """The live session, its active user and active clinic; ``None`` when any link is missing or expired."""
    row = (
        await session.execute(
            select(
                AuthSession.id,
                AuthSession.user_id,
                AuthSession.clinic_id,
                AuthSession.expires_at,
                AuthSession.password_fingerprint,
                UserAccount.role,
                UserAccount.display_name,
                UserAccount.password_hash,
                Clinic.name,
            )
            .join(
                UserAccount,
                (UserAccount.id == AuthSession.user_id) & (UserAccount.clinic_id == AuthSession.clinic_id),
            )
            .join(Clinic, Clinic.id == AuthSession.clinic_id)
            .where(
                AuthSession.id == session_id,
                AuthSession.expires_at > now,
                UserAccount.active.is_(True),
                Clinic.active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    return SessionPrincipal(
        session_id=row.id,
        user_id=row.user_id,
        clinic_id=row.clinic_id,
        role=row.role,
        display_name=row.display_name,
        clinic_name=row.name,
        expires_at=row.expires_at,
        password_fingerprint=row.password_fingerprint,
        password_hash=row.password_hash,
    )


async def extend_session(session: AsyncSession, session_id: UUID, expires_at: datetime) -> None:
    await session.execute(
        update(AuthSession).where(AuthSession.id == session_id).values(expires_at=expires_at)
    )


async def rebind_fingerprint(session: AsyncSession, session_id: UUID, password_fingerprint: str) -> None:
    """The session that changed the password keeps working: it adopts the new fingerprint (the original
    issued the user a fresh cookie for the same reason)."""
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(password_fingerprint=password_fingerprint)
    )


async def delete_session(session: AsyncSession, session_id: UUID) -> None:
    """Logout: the cookie can no longer be used."""
    await session.execute(delete(AuthSession).where(AuthSession.id == session_id))


async def delete_other_sessions(session: AsyncSession, user_id: UUID, keep: UUID | None) -> None:
    """Password change: every session of the user except the one that made the change."""
    stmt = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep is not None:
        stmt = stmt.where(AuthSession.id != keep)
    await session.execute(stmt)


async def prune_sessions(
    session: AsyncSession, now: datetime, user_id: UUID, current_fingerprint: str
) -> None:
    """Login is the cheapest moment to clean: expired rows, and rows signed with an older password of this
    user (changing the password evicts every old session)."""
    await session.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user_id,
            (AuthSession.expires_at <= now) | (AuthSession.password_fingerprint != current_fingerprint),
        )
    )


async def count_sessions(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(AuthSession)) or 0

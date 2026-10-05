# ported from: src/server/dashboard-auth.ts
"""Authentication of the staff dashboard: login with email and password, session as an HttpOnly JWT cookie.

Forced deviations from the original (one password in ``.env``, a random ``<id>.<secret>`` cookie, SQLite
session table):

* accounts: ``email`` + argon2id password of ``clinic.user_account`` (``dashboard_password_store``). One
  installation is one clinic (single tenant), so login takes no clinic slug and the clinic is the installation
  clinic (``get_installation_clinic_id``);
* the cookie is a signed JWT (HS256, ``PEMA_JWT_SECRET``) carrying only ``sub`` (user) and ``sid`` (session
  id); a ``cid`` claim of a cookie issued before single tenant is ignored when read. Every request ALSO loads
  the session row (``dashboard_session_store``), so logout
  revokes for real, a password change evicts older sessions, and a role change or a deactivation applies at
  once (the role is read from the user row, never from the token);
* (SEC-24) a session has two clocks: ``expires_at`` slides (``Settings.session_ttl_minutes`` after the last
  login or refresh) and ``absolute_expires_at`` does not (``PEMA_SESSION_ABSOLUTE_DAYS`` after the login, 7 by
  default, 1 to 30 allowed). ``refresh`` never pushes the sliding expiry past the ceiling, a request past
  it is a 401, and the cookie ``Max-Age`` and the JWT ``exp`` are capped by it, so a stolen cookie cannot
  be kept alive by refreshing it;
* the rate limit is kept as is (5 attempts per minute per key, buckets pruned past 500) and keyed twice:
  by client IP and by ``email``, so one account cannot be ground down from many addresses.

Session transport: cookie ``pema_session`` (``Settings.session_cookie_name``), ``HttpOnly``, ``SameSite=Lax``,
``Secure`` outside the ``dev`` environment. There is no service-token path here: the agent worker does not
call the REST API, it uses the action layer in process.

FastAPI dependencies live here too (``get_db``, ``current_user``, ``action_context``, ``get_delivery``) so the
routers stay thin and tests replace them with ``app.state`` or ``dependency_overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, Request, Response
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pema.api import dashboard_password_store as password_store
from pema.api import dashboard_session_store as session_store
from pema.api.client_ip import ProxyNetwork, parse_trusted_proxies, resolve_client_ip
from pema.api.request_id import clean_request_id
from pema.clinic import audit
from pema.clinic.actions._common import now
from pema.clinic.actions.outbound import OutboundDelivery
from pema.clinic.models import Clinic, UserAccount
from pema.clinic.rbac import passwords
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.auth import LoginRequest, SessionInfo, UserSummary
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import STAFF_ROLES, ActorType, Role

_log = create_logger("api.auth")

JWT_ALGORITHM = "HS256"
MIN_JWT_SECRET_CHARS = 32
BAD_CREDENTIALS_MESSAGE = "Email hoặc mật khẩu không đúng."
NOT_SIGNED_IN_MESSAGE = "Cần đăng nhập."
SESSION_ENDED_MESSAGE = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
DEFAULT_SESSION_ABSOLUTE_DAYS = 7
MIN_SESSION_ABSOLUTE_DAYS = 1
MAX_SESSION_ABSOLUTE_DAYS = 30

# ===== Login rate limit: stops password brute force (ported unchanged) =====

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_MS = 60_000
PRUNE_THRESHOLD = 500
"""Only sweep past this many buckets: sweeping on every call is O(n) for nothing."""

_attempts: dict[str, tuple[int, float]] = {}


def _now_ms() -> float:
    return now().timestamp() * 1000


def _prune_expired_attempts(now_ms: float) -> None:
    """The map lives as long as the process: drop buckets whose window passed so it cannot grow forever."""
    for key in [k for k, (_, reset_at) in _attempts.items() if now_ms >= reset_at]:
        del _attempts[key]


def allow_login_attempt(key: str, now_ms: float | None = None) -> bool:
    """``True`` = may still try to log in; ``False`` = more than 5 attempts per minute for this key."""
    at = _now_ms() if now_ms is None else now_ms
    if len(_attempts) > PRUNE_THRESHOLD:
        _prune_expired_attempts(at)
    entry = _attempts.get(key)
    if entry is None or at >= entry[1]:
        _attempts[key] = (1, at + LOGIN_WINDOW_MS)
        return True
    count = entry[0] + 1
    _attempts[key] = (count, entry[1])
    return count <= LOGIN_MAX_ATTEMPTS


def clear_login_attempts(key: str) -> None:
    """A successful login clears the count so the next legitimate login is not locked out."""
    _attempts.pop(key, None)


def login_attempt_bucket_count() -> int:
    """Number of rate-limit buckets held (memory-leak test)."""
    return len(_attempts)


def reset_login_rate_limit() -> None:
    """Drop every bucket (tests: many logins share one frozen minute and one address)."""
    _attempts.clear()


# ===== Settings of this module =====


class DashboardAuthSettings(BaseSettings):
    """Auth knobs that ``pema.config.env.Settings`` does not carry (that file belongs to package A)."""

    model_config = SettingsConfigDict(env_prefix="PEMA_", env_file=".env", extra="ignore")

    dashboard_behind_proxy: bool = False
    """``DASHBOARD_BEHIND_PROXY``: trust the rightmost ``X-Forwarded-For`` entry (a proxy appends it)."""
    trusted_proxies: str = ""
    """``PEMA_TRUSTED_PROXIES``: IPs or CIDRs (comma separated) of the proxies whose ``X-Forwarded-For`` is
    believed. Empty = nobody, even with ``dashboard_behind_proxy`` on (see ``client_ip.py``)."""
    session_cookie_secure: bool | None = None
    """``None`` = secure unless ``PEMA_ENVIRONMENT`` is ``dev``."""
    session_absolute_days: int = Field(
        default=DEFAULT_SESSION_ABSOLUTE_DAYS, ge=MIN_SESSION_ABSOLUTE_DAYS, le=MAX_SESSION_ABSOLUTE_DAYS
    )
    """``SESSION_ABSOLUTE_DAYS``: hard lifetime of a session counted from the login. Out of range refuses
    to start (fail closed) instead of silently running with a session that never ends or ends at once."""


@lru_cache
def get_auth_settings() -> DashboardAuthSettings:
    return DashboardAuthSettings()


@lru_cache
def get_trusted_proxies() -> tuple[ProxyNetwork, ...]:
    """Parsed once; a malformed ``PEMA_TRUSTED_PROXIES`` raises at the first login, it is never ignored."""
    return parse_trusted_proxies(get_auth_settings().trusted_proxies)


def _cookie_secure() -> bool:
    explicit = get_auth_settings().session_cookie_secure
    return explicit if explicit is not None else get_settings().environment != "dev"


# ===== Token =====


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    session_id: UUID


def _secret() -> str:
    secret = get_settings().jwt_secret
    value = secret.get_secret_value() if secret else ""
    if len(value) < MIN_JWT_SECRET_CHARS:
        # Fail closed: no secret, no login. Never a default key.
        _log.error("PEMA_JWT_SECRET is missing or shorter than the minimum")
        raise DomainError(ErrorCode.INTERNAL, "Hệ thống chưa cấu hình khóa phiên đăng nhập.")
    return value


def create_session_token(claims: TokenClaims, issued_at: datetime, expires_at: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(claims.user_id),
            "sid": str(claims.session_id),
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        _secret(),
        algorithm=JWT_ALGORITHM,
    )


def parse_session_token(token: str | None, at: datetime | None = None) -> TokenClaims | None:
    """Signature, expiry and shape. ``None`` for anything wrong (tampered, expired, other algorithm)."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "sid"], "verify_exp": False},
        )
        if int(claims["exp"]) <= int((at or now()).timestamp()):
            return None
        return TokenClaims(UUID(claims["sub"]), UUID(claims["sid"]))
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None


# ===== Authenticated user =====


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    clinic_id: UUID
    role: Role
    display_name: str
    clinic_name: str
    session_id: UUID
    expires_at: datetime
    absolute_expires_at: datetime
    """The ceiling of this session (SEC-24): ``expires_at`` never goes past it."""

    def summary(self) -> UserSummary:
        return UserSummary(
            id=self.user_id,
            display_name=self.display_name,
            role=self.role,
            clinic_id=self.clinic_id,
            clinic_name=self.clinic_name,
        )

    def session_info(self) -> SessionInfo:
        return SessionInfo(user=self.summary(), expires_at=self.expires_at)

    def action_context(
        self, request_id: str | None = None, idempotency_key: str | None = None
    ) -> ActionContext:
        return ActionContext(
            clinic_id=self.clinic_id,
            actor_type=ActorType.USER,
            actor_user_id=self.user_id,
            actor_role=self.role,
            source=ActionSource.UI,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )


def _session_ttl() -> timedelta:
    return timedelta(minutes=get_settings().session_ttl_minutes)


def _session_absolute_lifetime() -> timedelta:
    return timedelta(days=get_auth_settings().session_absolute_days)


def _max_age_seconds(stamp: datetime, expires_at: datetime) -> int:
    """Cookie ``Max-Age``: until the (capped) expiry, so the browser drops the cookie with the session."""
    return max(0, int((expires_at - stamp).total_seconds()))


def _unauthenticated() -> DomainError:
    return DomainError(ErrorCode.UNAUTHENTICATED, NOT_SIGNED_IN_MESSAGE)


async def verify_session_token(db: ClinicDatabase, token: str | None) -> AuthenticatedUser | None:
    """``verifySessionToken``: signature and expiry, then the session row, the password fingerprint and the
    user and clinic still being active."""
    at = now()
    claims = parse_session_token(token, at)
    if claims is None:
        return None
    async with db.session() as session:
        principal = await session_store.find_principal(session, claims.session_id, at)
    if principal is None or principal.user_id != claims.user_id:
        return None
    # The password changed after this session was created.
    if passwords.fingerprint(principal.password_hash) != principal.password_fingerprint:
        return None
    try:
        role = Role(principal.role)
    except ValueError:
        return None
    if role not in STAFF_ROLES:
        return None
    return AuthenticatedUser(
        user_id=principal.user_id,
        clinic_id=principal.clinic_id,
        role=role,
        display_name=principal.display_name,
        clinic_name=principal.clinic_name,
        session_id=principal.session_id,
        expires_at=min(principal.expires_at, principal.absolute_expires_at),
        absolute_expires_at=principal.absolute_expires_at,
    )


@dataclass(frozen=True)
class LoginResult:
    token: str
    user: AuthenticatedUser
    max_age_seconds: int


def _system_context(clinic_id: UUID, request_id: str | None) -> ActionContext:
    return ActionContext(
        clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.UI, request_id=request_id
    )


async def login(
    db: ClinicDatabase,
    body: LoginRequest,
    *,
    client_ip: str,
    request_id: str | None = None,
) -> LoginResult:
    """Email + password. Every failure is the same 401 (no account enumeration); every success and every
    failure is audited."""
    email = body.email.strip().lower()
    account_key = f"acct:{email}"
    if not allow_login_attempt(f"ip:{client_ip}") or not allow_login_attempt(account_key):
        raise DomainError(ErrorCode.RATE_LIMITED, "Thử đăng nhập quá nhiều lần. Vui lòng đợi một phút.")

    clinic_id = await get_installation_clinic_id(db)
    plain = body.password.get_secret_value()
    stamp = now()
    absolute_expires_at = stamp + _session_absolute_lifetime()
    expires_at = min(stamp + _session_ttl(), absolute_expires_at)
    async with db.session() as session:
        user = await session.scalar(
            select(UserAccount).where(
                UserAccount.clinic_id == clinic_id, UserAccount.email == email, UserAccount.active.is_(True)
            )
        )
        valid = password_store.verify_user_password(user, plain)
        role = Role(user.role) if user is not None and user.role in {r.value for r in Role} else None
        if user is not None and valid and role is not None and role in STAFF_ROLES:
            clinic_name = await _clinic_name(session)
            if passwords.needs_rehash(user.password_hash or ""):
                user.password_hash = passwords.hash_password(plain)
                await session.flush()
            session_id = uuid4()
            await session_store.prune_sessions(
                session, stamp, user.id, passwords.fingerprint(user.password_hash)
            )
            await session_store.insert_session(
                session,
                session_id=session_id,
                clinic_id=clinic_id,
                user_id=user.id,
                password_fingerprint=passwords.fingerprint(user.password_hash),
                created_at=stamp,
                expires_at=expires_at,
                absolute_expires_at=absolute_expires_at,
            )
            # A Core UPDATE, not ``user.last_login_at = ...``: the ORM would bump ``version`` on every
            # login, and an owner editing this account in the staff screen would get a spurious 409 because
            # the person signed in meanwhile. ``version`` guards edits of the account, not its sign-ins.
            await session.execute(
                update(UserAccount).where(UserAccount.id == user.id).values(last_login_at=stamp)
            )
            await session.flush()
            ctx = ActionContext(
                clinic_id=clinic_id,
                actor_type=ActorType.USER,
                actor_user_id=user.id,
                actor_role=role,
                source=ActionSource.UI,
                request_id=request_id,
            )
            await audit.record(
                session, ctx, "auth.login", "user_account", user.id, {"session_id": str(session_id)}
            )
            authed = AuthenticatedUser(
                user_id=user.id,
                clinic_id=clinic_id,
                role=role,
                display_name=user.display_name,
                clinic_name=clinic_name,
                session_id=session_id,
                expires_at=expires_at,
                absolute_expires_at=absolute_expires_at,
            )
        else:
            authed = None
    if authed is None:
        # The failing transaction above rolled back nothing worth keeping; the failure gets its own audit row.
        async with db.session() as session:
            await audit.record(
                session, _system_context(clinic_id, request_id), "auth.login_failed", "user_account", None
            )
        raise DomainError(ErrorCode.UNAUTHENTICATED, BAD_CREDENTIALS_MESSAGE)
    clear_login_attempts(account_key)
    token = create_session_token(TokenClaims(authed.user_id, authed.session_id), stamp, expires_at)
    return LoginResult(token=token, user=authed, max_age_seconds=_max_age_seconds(stamp, expires_at))


async def _clinic_name(session: AsyncSession) -> str:
    """Name of the clinic (``clinic.clinic`` holds exactly one row)."""
    return await session.scalar(select(Clinic.name)) or ""


async def refresh(db: ClinicDatabase, user: AuthenticatedUser, request_id: str | None = None) -> LoginResult:
    """Slide the current session forward and issue a new cookie, but never past the absolute ceiling fixed at
    login (SEC-24). Past the ceiling the answer is 401: the user signs in again."""
    stamp = now()
    if user.absolute_expires_at <= stamp:
        raise DomainError(ErrorCode.UNAUTHENTICATED, SESSION_ENDED_MESSAGE)
    wanted = min(stamp + _session_ttl(), user.absolute_expires_at)
    async with db.session() as session:
        expires_at = await session_store.extend_session(session, user.session_id, wanted, stamp)
        if expires_at is None:
            # The row went away or crossed its ceiling between the request check and now.
            raise DomainError(ErrorCode.UNAUTHENTICATED, SESSION_ENDED_MESSAGE)
        await audit.record(
            session, user.action_context(request_id), "auth.refresh", "user_account", user.user_id
        )
    renewed = AuthenticatedUser(
        user_id=user.user_id,
        clinic_id=user.clinic_id,
        role=user.role,
        display_name=user.display_name,
        clinic_name=user.clinic_name,
        session_id=user.session_id,
        expires_at=expires_at,
        absolute_expires_at=user.absolute_expires_at,
    )
    token = create_session_token(TokenClaims(user.user_id, user.session_id), stamp, expires_at)
    return LoginResult(token=token, user=renewed, max_age_seconds=_max_age_seconds(stamp, expires_at))


async def revoke_session(db: ClinicDatabase, user: AuthenticatedUser, request_id: str | None = None) -> None:
    """Logout: delete the row; the old cookie never works again."""
    async with db.session() as session:
        await session_store.delete_session(session, user.session_id)
        await audit.record(
            session, user.action_context(request_id), "auth.logout", "user_account", user.user_id
        )


def set_session_cookie(response: Response, result: LoginResult) -> None:
    response.set_cookie(
        key=get_settings().session_cookie_name,
        value=result.token,
        max_age=result.max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=get_settings().session_cookie_name,
        path="/",
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )


# ===== FastAPI dependencies =====

_default_db: ClinicDatabase | None = None


def get_db(request: Request) -> ClinicDatabase:
    """The database of the API process (role ``be_app``). Package G sets ``app.state.clinic_db`` in the
    composition root; until then a process-wide instance is built from ``Settings.database_url``."""
    configured: object = getattr(request.app.state, "clinic_db", None)
    if isinstance(configured, ClinicDatabase):
        return configured
    global _default_db
    if _default_db is None:
        _default_db = ClinicDatabase(get_settings().database_url)
    return _default_db


def get_delivery(request: Request) -> OutboundDelivery | None:
    """The channel sender (``app.state.outbound_delivery``, wired by package G). ``None`` leaves manual
    replies and approved review items ``queued`` in the Inbox."""
    delivery: object = getattr(request.app.state, "outbound_delivery", None)
    return delivery if isinstance(delivery, OutboundDelivery) else None


Database = Annotated[ClinicDatabase, Depends(get_db)]
Delivery = Annotated[OutboundDelivery | None, Depends(get_delivery)]


def client_ip(request: Request) -> str:
    return resolve_client_ip(
        request,
        behind_proxy=get_auth_settings().dashboard_behind_proxy,
        trusted_proxies=get_trusted_proxies(),
    )


async def current_user(request: Request, db: Database) -> AuthenticatedUser:
    token = request.cookies.get(get_settings().session_cookie_name)
    user = await verify_session_token(db, token)
    if user is None:
        raise _unauthenticated()
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]


def action_context(request: Request, user: CurrentUser) -> ActionContext:
    """``ActionContext`` of the signed-in staff member. ``Idempotency-Key`` is read from the header (the
    routes that accept it declare it in OpenAPI; reading it here keeps every route's signature unchanged)."""
    return user.action_context(
        request_id=clean_request_id(request.headers.get("x-request-id")),
        idempotency_key=(request.headers.get("idempotency-key") or None),
    )


Ctx = Annotated[ActionContext, Depends(action_context)]

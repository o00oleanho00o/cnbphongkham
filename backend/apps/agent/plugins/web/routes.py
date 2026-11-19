"""Routes of the ``web`` plugin.

Open (``/v1/hooks/web``): ``GET /state`` (does the dashboard still need its first account?), ``POST /setup``
(that first account; refused once one exists) and ``POST /login``. Failed logins are limited per address and
per account.

Admin (``/v1/plugins/web``): ``GET /me``, ``POST /password`` (ends every other login), and the API keys of
the chat API (``GET``/``POST /api-keys``, ``DELETE /api-keys/{id}``; a new key is shown once).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from agent_app.auth import Principal
from agent_app.gateway import WindowLimiter

from . import tokens
from .users import ApiKey, Directory, User, normal_email

PASSWORD_MIN: Final = 10
PASSWORD_MAX: Final = 200
LOGIN_FAILURES: Final = 5
LOGIN_WINDOW_S: Final = 300.0

logger = logging.getLogger(__name__)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(_Body):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class NewAccount(Credentials):
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class PasswordChange(_Body):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class NewApiKey(_Body):
    name: str = Field(min_length=1, max_length=100)


class Session(BaseModel):
    token: str
    expires_at: datetime
    email: str


class State(BaseModel):
    needs_setup: bool


class Me(BaseModel):
    email: str
    created_at: datetime


class CreatedApiKey(ApiKey):
    key: str
    """Shown this once."""


Clock = Callable[[], datetime]


def public_routes(directory: Directory, lifetime: timedelta, clock: Clock) -> APIRouter:
    router = APIRouter()
    failures = WindowLimiter(LOGIN_FAILURES, LOGIN_WINDOW_S)

    async def session(user: User) -> Session:
        token, expires = tokens.issue(
            await directory.signing_key(), user.email, user.token_version, clock(), lifetime
        )
        return Session(token=token, expires_at=expires, email=user.email)

    @router.get("/state")
    async def state() -> State:
        return State(needs_setup=not await directory.has_users())

    @router.post("/setup", status_code=status.HTTP_201_CREATED)
    async def setup(body: NewAccount) -> Session:
        user = await directory.create_owner(body.email, body.password, clock())
        if user is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Đã có tài khoản quản trị - hãy đăng nhập")
        logger.info("the dashboard's first account was created")
        return await session(user)

    @router.post("/login")
    async def login(body: Credentials, request: Request) -> Session:
        keys = (
            f"ip:{request.client.host if request.client else 'unknown'}",
            f"user:{normal_email(body.email)}",
        )
        now = time.monotonic()
        if any(failures.blocked(key, now) for key in keys):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Sai quá nhiều lần - thử lại sau ít phút")
        user = await directory.check_login(body.email, body.password)
        if user is None:
            for key in keys:
                failures.count(key, now)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
        return await session(user)

    return router


def admin_routes(directory: Directory, lifetime: timedelta, clock: Clock) -> APIRouter:
    router = APIRouter()

    async def account(request: Request) -> User:
        principal = getattr(request.state, "principal", None)
        user = await directory.user(principal.subject) if isinstance(principal, Principal) else None
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không phải tài khoản dashboard")
        return user

    @router.get("/me")
    async def me(request: Request) -> Me:
        user = await account(request)
        return Me(email=user.email, created_at=user.created_at)

    @router.post("/password")
    async def change_password(body: PasswordChange, request: Request) -> Session:
        user = await account(request)
        if await directory.check_login(user.email, body.current_password) is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Mật khẩu hiện tại không đúng")
        user = await directory.set_password(user, body.new_password)
        logger.info("the password of a dashboard account was changed; older logins ended")
        token, expires = tokens.issue(
            await directory.signing_key(), user.email, user.token_version, clock(), lifetime
        )
        return Session(token=token, expires_at=expires, email=user.email)

    @router.get("/api-keys")
    async def list_api_keys() -> list[ApiKey]:
        return await directory.api_keys()

    @router.post("/api-keys", status_code=status.HTTP_201_CREATED)
    async def create_api_key(body: NewApiKey) -> CreatedApiKey:
        key, text = await directory.create_api_key(body.name, clock())
        logger.info("API key %s made", key.id)
        return CreatedApiKey(**key.model_dump(), key=text)

    @router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_api_key(key_id: Annotated[str, Path(pattern=r"^[0-9a-f]{1,32}$")]) -> Response:
        if not await directory.delete_api_key(key_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có API key này")
        logger.info("API key %s revoked", key_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router

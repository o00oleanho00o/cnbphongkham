"""The accounts that may use the dashboard and the API keys that may use the chat API, kept in the plugin's
``ctx.storage``: ``user:<email>`` (the password as a salted scrypt hash), ``api-key:<id>`` (a SHA-256 digest
of the key; the key itself is shown once, when it is made) and ``signing-key`` (the JWT key, sealed with the
service's secret key).

A change of password bumps the account's ``token_version``: every login token issued before stops working.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Final

from pydantic import BaseModel

from agent_app.auth import CHAT, Principal
from agent_app.plugins import PluginStorage

USER: Final = "user:"
API_KEY: Final = "api-key:"
SIGNING_KEY: Final = "signing-key"
API_KEY_PREFIX: Final = "pak_"
SCRYPT_N: Final = 2**14
SCRYPT_R: Final = 8
SCRYPT_P: Final = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    encoded = (base64.b64encode(part).decode("ascii") for part in (salt, digest))
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${'$'.join(encoded)}"


def password_matches(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        given = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except ValueError:
        return False
    return kind == "scrypt" and hmac.compare_digest(given, expected)


@functools.cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


class User(BaseModel):
    email: str
    password: str
    created_at: datetime
    token_version: int = 1


class ApiKey(BaseModel):
    id: str
    name: str
    created_at: datetime


class _StoredApiKey(ApiKey):
    digest: str


def normal_email(email: str) -> str:
    return email.strip().lower()


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class Directory:
    def __init__(
        self, storage: PluginStorage, *, encrypt: Callable[[str], str], decrypt: Callable[[str], str]
    ) -> None:
        self._storage = storage
        self._encrypt = encrypt
        self._decrypt = decrypt
        self._signing_key: str | None = None
        self._setup = asyncio.Lock()

    async def has_users(self) -> bool:
        return bool(await self._storage.list(USER, limit=1))

    async def create_owner(self, email: str, password: str, now: datetime) -> User | None:
        """The first account; None once any account exists (the setup screen is gone)."""
        async with self._setup:
            if await self.has_users():
                return None
            user = User(email=normal_email(email), password=await _hashed(password), created_at=now)
            await self._save(user)
            return user

    async def user(self, email: str) -> User | None:
        found = await self._storage.get(USER + normal_email(email))
        return None if found is None else User.model_validate(found)

    async def check_login(self, email: str, password: str) -> User | None:
        user = await self.user(email)
        stored = user.password if user is not None else _dummy_hash()
        # An unknown email costs the same hash as a known one, so timing does not tell which exist.
        matched = await asyncio.to_thread(password_matches, password, stored)
        return user if user is not None and matched else None

    async def set_password(self, user: User, password: str) -> User:
        changed = user.model_copy(
            update={"password": await _hashed(password), "token_version": user.token_version + 1}
        )
        await self._save(changed)
        return changed

    async def api_keys(self) -> list[ApiKey]:
        found = [_StoredApiKey.model_validate(value) for _, value in await self._storage.list(API_KEY)]
        return [ApiKey(id=k.id, name=k.name, created_at=k.created_at) for k in found]

    async def create_api_key(self, name: str, now: datetime) -> tuple[ApiKey, str]:
        """The key and its text, which is never stored nor shown again."""
        key_id, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
        stored = _StoredApiKey(id=key_id, name=name, created_at=now, digest=_digest(secret))
        await self._storage.put(API_KEY + key_id, stored.model_dump(mode="json"))
        return ApiKey(id=key_id, name=name, created_at=now), f"{API_KEY_PREFIX}{key_id}_{secret}"

    async def delete_api_key(self, key_id: str) -> bool:
        return await self._storage.delete(API_KEY + key_id)

    async def api_key_principal(self, token: str) -> Principal | None:
        key_id, _, secret = token.removeprefix(API_KEY_PREFIX).partition("_")
        if not key_id or not secret or len(key_id) > 32:
            return None
        found = await self._storage.get(API_KEY + key_id)
        if found is None:
            return None
        stored = _StoredApiKey.model_validate(found)
        if not hmac.compare_digest(_digest(secret), stored.digest):
            return None
        return Principal(f"apikey:{key_id}", frozenset({CHAT}))

    async def signing_key(self) -> str:
        """Made on first use and kept sealed; every process of the service signs with the same one."""
        if self._signing_key is None:
            sealed = await self._storage.get(SIGNING_KEY)
            if not isinstance(sealed, str):
                sealed = self._encrypt(secrets.token_urlsafe(48))
                await self._storage.put(SIGNING_KEY, sealed)
            self._signing_key = self._decrypt(sealed)
        return self._signing_key

    async def _save(self, user: User) -> None:
        await self._storage.put(USER + user.email, user.model_dump(mode="json"))


async def _hashed(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)

"""The ``sso`` plugin: callers signed in on another service (the issuer) reach the agent with a short JWT that
service signed; the agent checks it with the issuer's public keys (``keys.KeySet``), so the two share no
secret. The token's ``scope`` (space separated) decides the routes: ``admin`` opens the admin and the chat
routes, ``chat`` the chat routes only; a valid token with neither gets 403.

Only asymmetric signatures are accepted, and a token of another issuer is left to the other sign-ins before
any key is fetched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import jwt

from agent_app.auth import ADMIN, CHAT, Authenticator, Principal
from agent_app.plugins import PluginContext

from .keys import KeySet

ALGORITHMS: Final = frozenset({"EdDSA", "ES256", "RS256"})
LEEWAY_S: Final = 30
"""Clock difference allowed between the issuer and this machine."""
SUBJECT_PREFIX: Final = "sso:"


@dataclass(frozen=True, slots=True)
class Settings:
    issuer: str
    audience: str
    jwks_url: str

    @classmethod
    def of(cls, config: Mapping[str, Any]) -> Settings:
        values = {key: str(config.get(key) or "").strip() for key in ("issuer", "audience", "jwks_url")}
        empty = [key for key, value in values.items() if not value]
        if empty:
            raise ValueError(f"set {', '.join(empty)}")
        if not values["jwks_url"].startswith(("http://", "https://")):
            raise ValueError("jwks_url must be an http:// or https:// URL")
        return cls(**values)


def register(ctx: PluginContext) -> None:
    settings = Settings.of(ctx.config)
    ctx.register_authenticator(authenticator(settings, KeySet(settings.jwks_url)))


def authenticator(settings: Settings, keys: KeySet) -> Authenticator:
    async def authenticate(token: str) -> Principal | None:
        if token.count(".") != 2:
            return None
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        algorithm, kid = header.get("alg"), header.get("kid")
        if unverified.get("iss") != settings.issuer or algorithm not in ALGORITHMS:
            return None
        if not isinstance(kid, str):
            return None
        key = await keys.key(kid)
        if key is None or key.algorithm_name != algorithm:
            return None
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                audience=settings.audience,
                issuer=settings.issuer,
                leeway=LEEWAY_S,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.PyJWTError:
            return None
        subject, scope = claims.get("sub"), claims.get("scope")
        if not isinstance(subject, str) or not subject:
            return None
        return Principal(SUBJECT_PREFIX + subject, scopes_of(scope if isinstance(scope, str) else ""))

    return authenticate


def scopes_of(scope: str) -> frozenset[str]:
    granted = set(scope.split())
    if ADMIN in granted:
        return frozenset({ADMIN, CHAT})
    return frozenset({CHAT}) if CHAT in granted else frozenset()

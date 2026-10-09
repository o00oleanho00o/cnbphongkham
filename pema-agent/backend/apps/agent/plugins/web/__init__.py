"""The ``web`` plugin: the dashboard's sign-in. One admin account, created on the first visit (email and
password), signs in for a JWT the gateway accepts as an ``admin`` caller; API keys made on the dashboard reach
the chat API only. Nothing comes from the environment: the accounts and the signing key live in the plugin's
storage.

Forgot the password: ``agent plugins forget web --prefix user:`` removes the account, and the next visit
creates one again (do it with the dashboard closed to others).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_app.auth import ADMIN, CHAT, Authenticator, Principal
from agent_app.plugins import PluginContext

from . import tokens
from .routes import admin_routes, public_routes
from .users import API_KEY_PREFIX, Directory


def register(ctx: PluginContext) -> None:
    directory = Directory(ctx.storage, encrypt=ctx.encrypt, decrypt=ctx.decrypt)
    lifetime = timedelta(hours=max(1, min(720, int(ctx.config.get("token_hours") or 12))))
    ctx.register_authenticator(authenticator(directory))
    ctx.register_routes(admin_routes(directory, lifetime, _now))
    ctx.register_routes(public_routes(directory, lifetime, _now), kind="hooks")


def authenticator(directory: Directory) -> Authenticator:
    async def authenticate(token: str) -> Principal | None:
        if token.startswith(API_KEY_PREFIX):
            return await directory.api_key_principal(token)
        if token.count(".") != 2:
            return None
        found = tokens.read(await directory.signing_key(), token)
        if found is None:
            return None
        email, version = found
        user = await directory.user(email)
        if user is None or user.token_version != version:
            return None
        return Principal(user.email, frozenset({ADMIN, CHAT}))

    return authenticate


def _now() -> datetime:
    return datetime.now(UTC)

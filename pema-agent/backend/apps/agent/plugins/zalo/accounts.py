# ported from: src/config/account-store.ts
"""The plugin's Zalo accounts, kept in ``ctx.storage``: ``account:<id>`` holds the settings, ``secret:<id>``
the sealed credential (bot token, personal login cookie or OA keys), so listing accounts never reads a secret.

The secret is sealed with the service's key (``ctx.encrypt``) and opened through one path only
(``secret``), easy to audit; the account settings that go out through the admin routes carry
``has_credentials`` at most.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

from pydantic import ValidationError

from agent_app.plugins import PluginStorage

from .models import AccountConfig, AccountCreate, AccountUpdate, Allowlist, AllowlistMode, ChannelKind

ACCOUNT: Final = "account:"
SECRET: Final = "secret:"  # noqa: S105 - a key prefix, not a secret

logger = logging.getLogger(__name__)


class AccountExistsError(ValueError):
    pass


class AccountStore:
    def __init__(
        self,
        storage: PluginStorage,
        *,
        encrypt: Callable[[str], str],
        decrypt: Callable[[str], str],
    ) -> None:
        self._storage = storage
        self._encrypt = encrypt
        self._decrypt = decrypt

    async def list(self) -> list[AccountConfig]:
        return [AccountConfig.model_validate(value) for _, value in await self._storage.list(ACCOUNT)]

    async def get(self, account_id: str) -> AccountConfig | None:
        value = await self._storage.get(ACCOUNT + account_id)
        return None if value is None else AccountConfig.model_validate(value)

    async def create(self, body: AccountCreate) -> AccountConfig:
        if await self.get(body.id) is not None:
            raise AccountExistsError(f"account {body.id} already exists")
        # Tài khoản bot mặc định ĐÓNG danh sách cho phép: ai có link cũng nhắn được bot, mở sẵn là mời người
        # lạ đốt token và thử prompt injection. Nick cá nhân thì phải là bạn bè mới nhắn được.
        allowlist = (
            Allowlist(mode=AllowlistMode.LIST) if body.channel is ChannelKind.ZALO_BOT else Allowlist()
        )
        account = AccountConfig(id=body.id, label=body.label, channel=body.channel, allowlist=allowlist)
        await self._save(account)
        return account

    async def update(self, account_id: str, patch: AccountUpdate) -> AccountConfig | None:
        """``ValueError`` when the result is not a valid account."""
        current = await self.get(account_id)
        if current is None:
            return None
        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        try:
            merged = AccountConfig.model_validate(current.model_dump() | changes)
        except ValidationError as err:
            raise ValueError(str(err)) from err
        await self._save(merged)
        return merged

    async def delete(self, account_id: str) -> bool:
        """The account and its credential; what it said and heard stays in the agent's sessions."""
        await self._storage.delete(SECRET + account_id)
        return await self._storage.delete(ACCOUNT + account_id)

    async def has_secret(self, account_id: str) -> bool:
        return await self._storage.get(SECRET + account_id) is not None

    async def set_secret(self, account_id: str, secret: str | None) -> None:
        """Seals and stores the credential; None or blank removes it."""
        if secret is None or not secret.strip():
            await self._storage.delete(SECRET + account_id)
            return
        await self._storage.put(SECRET + account_id, self._encrypt(secret.strip()))

    async def secret(self, account_id: str) -> str | None:
        """The credential in clear, or None when none is stored or it no longer opens (the service key
        changed: logged, so the operator looks in the right place)."""
        sealed = await self._storage.get(SECRET + account_id)
        if not isinstance(sealed, str):
            return None
        try:
            return self._decrypt(sealed)
        except ValueError:
            logger.error(
                "the stored credential of account %s does not open; was the key changed?", account_id
            )
            return None

    async def _save(self, account: AccountConfig) -> None:
        await self._storage.put(ACCOUNT + account.id, account.model_dump(mode="json"))

# ported from: src/server/routes/account-routes.ts (``PUT /api/accounts/:id/bot-token`` only)
"""Admin operation behind ``PUT /admin/accounts/{account_id}/bot-token``: validate, store, restart.

The two invariants that matter most here are about SECRETS and about FAILING CLOSED:

* The token must never leak into any response. ``AccountOut`` carries only ``has_bot_token``; the token is
  write-only.
* A wrong token must NOT be stored: stored, the account looks configured but never runs, and the only symptom
  is a silent bot.

Forced deviations:

* Express route -> a service the FastAPI router calls; the clinic comes from the authenticated
  ``ActionContext``.
* The token format is validated by ``BotTokenSet`` (422 before this runs); "not a bot account" and "Zalo
  rejected the token" are ``DomainError(VALIDATION_FAILED)``; unknown account is ``NOT_FOUND``.
* ``botName`` and ``warning`` of the original response do not fit ``AccountOut`` (a contract DTO); a failed
  restart is logged and shows as ``running: false``. Open item for package G (add an optional ``warning``
  field).
* The probe client factory is injected, so tests never reach the real Bot API.
"""

from __future__ import annotations

from uuid import UUID

from pema.channels.zalo_bot.bot_account_manager import BotAccountManager
from pema.channels.zalo_bot.bot_account_runner import ClientFactory
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi, tao_zalo_bot_client
from pema.shared.logger import create_logger
from pema_contracts.admin_agent import AccountOut
from pema_contracts.agents import AccountStore
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode

_log = create_logger("bot-account-admin")


def _default_client(token: str) -> BotApiClient:
    return tao_zalo_bot_client(token)


class BotAccountAdminService:
    def __init__(
        self,
        *,
        accounts: AccountStore,
        manager: BotAccountManager,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._accounts = accounts
        self._manager = manager
        self._client_factory = client_factory or _default_client

    async def set_bot_token(self, clinic_id: UUID, account_id: str, token: str) -> AccountOut:
        account = await self._accounts.get_account(clinic_id, account_id)
        if account is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản.")
        if account.channel is not ChannelKind.ZALO_BOT:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Chỉ tài khoản loại bot mới nhận token.")

        # Ask Zalo BEFORE storing. Zalo refusing and the network dropping are different causes with the same
        # outcome: fail closed, store nothing.
        client = self._client_factory(token)
        try:
            await client.get_me()
        except LoiZaloBotApi:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, "Zalo không chấp nhận token này hoặc không kiểm tra được."
            ) from None
        finally:
            await client.aclose()

        await self._accounts.set_bot_token(clinic_id, account_id, token)
        stored = await self._accounts.get_account(clinic_id, account_id) or account

        running = False
        warning: str | None = None
        try:
            running = await self._manager.restart(stored)
        except Exception as err:
            _log.warning("Lưu token xong nhưng khởi động lại thất bại", err=err, account_id=account_id)
            warning = "Đã lưu token nhưng chưa khởi động lại được tài khoản bot."

        return AccountOut.model_validate(
            stored.model_dump()
            | {"has_bot_token": True, "running": running, "has_credentials": True, "warning": warning}
        )

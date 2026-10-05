"""Zalo Bot API account token (package C1 implements). Port of ``PUT /api/accounts/:id/bot-token``.

The token is validated against the Bot API before it is stored (a wrong token must not be saved) and is stored
encrypted; it is never returned.

Wiring seams (set on ``app.state`` by the composition root, package G; a missing one fails closed):

* ``staff_context_resolver``: ``async (Request, Permission) -> ActionContext``. Package B1's session/JWT check
  and the RBAC matrix; here it must enforce ``Permission.ADMIN_ACCOUNTS``.
* ``bot_account_admin``: a ``BotAccountAdminService``.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import Request

from pema.api.deps import admin_router
from pema.channels.zalo_bot.bot_account_admin import BotAccountAdminService
from pema_contracts.actions import ActionContext
from pema_contracts.admin_agent import AccountOut, BotTokenSet
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

router = admin_router("accounts", "admin-bot-accounts")


class StaffContextResolver(Protocol):
    async def __call__(self, request: Request, permission: Permission) -> ActionContext: ...


async def _require_staff(request: Request, permission: Permission) -> ActionContext:
    resolver: StaffContextResolver | None = getattr(request.app.state, "staff_context_resolver", None)
    if resolver is None:
        # Fail closed: without the auth seam nobody is authenticated.
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập.")
    return await resolver(request, permission)


def _service(request: Request) -> BotAccountAdminService:
    service: BotAccountAdminService | None = getattr(request.app.state, "bot_account_admin", None)
    if service is None:
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Dịch vụ tài khoản bot chưa sẵn sàng.")
    return service


@router.put(
    "/{account_id}/bot-token",
    response_model=AccountOut,
    summary="Set (validate, encrypt, store) the Zalo Bot API token",
)
async def set_bot_token(account_id: str, body: BotTokenSet, request: Request) -> AccountOut:
    ctx = await _require_staff(request, Permission.ADMIN_ACCOUNTS)
    return await _service(request).set_bot_token(ctx.clinic_id, account_id, body.token)

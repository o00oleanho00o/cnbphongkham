"""Zalo Bot API account token (package C1 implements). Port of ``PUT /api/accounts/:id/bot-token``.

The token is validated against the Bot API before it is stored (a wrong token must not be saved) and is
stored encrypted; it is never returned.
"""

from __future__ import annotations

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import AccountOut, BotTokenSet

router = admin_router("accounts", "admin-bot-accounts")


@router.put(
    "/{account_id}/bot-token",
    response_model=AccountOut,
    summary="Set (validate, encrypt, store) the Zalo Bot API token",
)
async def set_bot_token(account_id: str, body: BotTokenSet) -> AccountOut:
    not_implemented()

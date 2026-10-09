# ported from: src/server/routes/account-routes.ts
"""Admin routes of the Zalo plugin, under ``/v1/plugins/zalo`` (admin token): list, create, change and delete
accounts, set a bot's token, and the reaction icons the dashboard offers for auto-react. The webhook of bot
accounts is under ``/v1/hooks/zalo`` (open; the secret header is the only check).

The kind of an account is fixed at creation (delete and create again to change it). Request and response
shapes follow the earlier admin API so the dashboard pages carry over. Every change is followed by a ``sync``
so a channel starts or stops with it.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from .accounts import AccountExistsError
from .bot.client import LoiZaloBotApi
from .bot.types import ZaloBotUpdate, unwrap_webhook_payload
from .models import (
    AccountConfig,
    AccountCreate,
    AccountOut,
    AccountUpdate,
    BotTokenSet,
    ChannelKind,
    ReactionIconOut,
)
from .plugin import ZaloPlugin
from .reaction_icons import REACTION_ICONS

logger = logging.getLogger(__name__)


def account_routes(plugin: ZaloPlugin) -> APIRouter:
    router = APIRouter()
    store = plugin.store

    async def out(account: AccountConfig, warning: str | None = None) -> AccountOut:
        return AccountOut.model_validate(
            {
                **account.model_dump(),
                "running": plugin.running(account.id),
                "has_credentials": await store.has_secret(account.id),
                "warning": warning,
            }
        )

    @router.get("/accounts")
    async def list_accounts() -> list[AccountOut]:
        return [await out(account) for account in await store.list()]

    # Before ``/accounts/{account_id}``-style routes so the path is not read as an account id.
    @router.get("/accounts/reaction-icons")
    async def list_reaction_icons() -> list[ReactionIconOut]:
        return [
            ReactionIconOut(key=key, emoji=icon.emoji, label=icon.label)
            for key, icon in REACTION_ICONS.items()
        ]

    @router.post("/accounts", status_code=status.HTTP_201_CREATED)
    async def create_account(body: AccountCreate) -> AccountOut:
        try:
            created = await store.create(body)
        except AccountExistsError as err:
            raise HTTPException(status.HTTP_409_CONFLICT, "Account id đã tồn tại") from err
        await plugin.sync()
        return await out(created)

    @router.patch("/accounts/{account_id}")
    async def update_account(account_id: str, body: AccountUpdate) -> AccountOut:
        if body.auto_react_icon is not None and body.auto_react_icon not in REACTION_ICONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Icon reaction không hợp lệ")
        try:
            updated = await store.update(account_id, body)
        except ValueError as err:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Cấu hình tài khoản không hợp lệ"
            ) from err
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        await plugin.sync()
        return await out(updated)

    @router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_account(account_id: str) -> Response:
        if not await store.delete(account_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        await plugin.sync()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.put("/accounts/{account_id}/bot-token")
    async def set_bot_token(account_id: str, body: BotTokenSet) -> AccountOut:
        """Asks Zalo (``getMe``) BEFORE storing: a wrong token stored looks configured and never runs. The
        token never comes back in any answer."""
        account = await store.get(account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        if account.channel is not ChannelKind.ZALO_BOT:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Chỉ tài khoản loại bot mới nhận token"
            )
        client = plugin.bot_client(body.token)
        try:
            await client.get_me()
        except LoiZaloBotApi as err:
            logger.info("bot token of %s refused (%s, HTTP %s)", account_id, err.ma_loi, err.http_status)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Zalo không chấp nhận token này hoặc không kiểm tra được",
            ) from None
        finally:
            await client.aclose()
        await store.set_secret(account_id, body.token)
        await plugin.sync()
        return await out(account)

    return router


def hook_routes(plugin: ZaloPlugin) -> APIRouter:
    router = APIRouter()
    refused = "Webhook bị từ chối."

    @router.post("/bot/{account_id}")
    async def bot_webhook(account_id: str, request: Request) -> dict[str, bool]:
        """A delivery from Zalo for a bot in webhook mode. An unknown account and a wrong secret get the same
        401, so the open route does not tell which accounts exist; the secret is checked before parsing.
        A failure to hand the message over answers 500 so Zalo delivers it again."""
        channel = plugin.bot_channel(account_id)
        if channel is None or not channel.verify_webhook(request.headers):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, refused)
        try:
            payload = json.loads(await request.body())
            if not isinstance(payload, dict):
                raise TypeError("not an object")
            update = ZaloBotUpdate.model_validate(unwrap_webhook_payload(cast(dict[str, Any], payload)))
        except (ValueError, TypeError, ValidationError) as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nội dung webhook không hợp lệ") from err
        await channel.handle(update)
        return {"ok": True}

    return router

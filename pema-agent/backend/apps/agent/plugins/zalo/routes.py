# ported from: src/server/routes/account-routes.ts
"""Admin routes of the Zalo plugin, under ``/v1/plugins/zalo`` (admin token): accounts (list, create, change,
delete), a bot's token, the QR login of a personal account, the Node bridge (status, install, uninstall) and
the reaction icons the dashboard offers. Under ``/v1/hooks/zalo`` (open): the webhook of bot accounts (secret
header) and the events of the plugin's own bridge (HMAC signature).

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
    QrLoginState,
    QrLoginStatus,
    ReactionIconOut,
)
from .personal.client import BridgeClient, BridgeQrStatus, ZaloBridgeError
from .personal.signing import verify_signature
from .plugin import LOCKED_OUT, ZaloPlugin
from .reaction_icons import REACTION_ICONS

logger = logging.getLogger(__name__)


def account_routes(plugin: ZaloPlugin) -> APIRouter:
    router = APIRouter()
    store = plugin.store

    async def out(account: AccountConfig, warning: str | None = None) -> AccountOut:
        if warning is None and plugin.state(account.id) in LOCKED_OUT:
            warning = "Zalo đã đăng xuất hoặc khóa tài khoản này - quét lại mã QR."
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

    @router.post("/accounts/{account_id}/login", status_code=status.HTTP_202_ACCEPTED)
    async def start_qr_login(account_id: str) -> QrLoginStatus:
        """Starts a QR login on the bridge (a running session is returned as it is); personal accounts."""
        account = await store.get(account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        if account.channel is not ChannelKind.ZALO_PERSONAL:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Chỉ tài khoản cá nhân đăng nhập bằng mã QR"
            )
        client = _bridge_client(plugin)
        try:
            return _qr_out(await client.start_qr_login(account_id))
        except ZaloBridgeError as err:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Cầu nối Zalo từ chối ({err.kind})") from None

    @router.get("/accounts/{account_id}/login/status")
    async def qr_login_status(account_id: str) -> QrLoginStatus:
        """Polled by the dashboard. The QR image is the key to the account: only here, never logged."""
        client = _bridge_client(plugin)
        try:
            return _qr_out(await client.get_qr_login(account_id))
        except ZaloBridgeError as err:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Cầu nối Zalo từ chối ({err.kind})") from None

    @router.get("/bridge")
    async def bridge_status() -> dict[str, Any]:
        return plugin.bridge.status().to_json()

    @router.post("/bridge/install", status_code=status.HTTP_202_ACCEPTED)
    async def install_bridge() -> dict[str, Any]:
        """Installs the bridge in the background (several minutes); the dashboard polls ``GET /bridge``."""
        if plugin.bridge.status().version == "external":
            raise HTTPException(status.HTTP_409_CONFLICT, "Cầu nối chạy ngoài plugin, không cài ở đây")
        if not plugin.start_install():
            raise HTTPException(status.HTTP_409_CONFLICT, "Đang cài cầu nối")
        return plugin.bridge.status().to_json() | {"installing": True}

    @router.delete("/bridge")
    async def uninstall_bridge() -> dict[str, Any]:
        try:
            status_after = await plugin.bridge.uninstall()
        except ValueError as err:
            raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from None
        await plugin.sync()
        return status_after.to_json()

    return router


def _bridge_client(plugin: ZaloPlugin) -> BridgeClient:
    client = plugin.bridge.client
    if client is not None:
        return client
    if not plugin.bridge.installed():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cài cầu nối Zalo cá nhân trước (mục Cầu nối)")
    raise HTTPException(status.HTTP_409_CONFLICT, "Cầu nối Zalo đang khởi động - thử lại sau vài giây")


def _qr_out(found: BridgeQrStatus) -> QrLoginStatus:
    """The bridge's QR states mapped onto the dashboard's (``declined`` and ``timeout`` included)."""
    states = {
        "idle": QrLoginState.IDLE,
        "starting": QrLoginState.WAITING_SCAN,
        "waiting_scan": QrLoginState.WAITING_SCAN,
        "scanned": QrLoginState.SCANNED,
        "success": QrLoginState.SUCCESS,
        "declined": QrLoginState.ERROR,
        "error": QrLoginState.ERROR,
        "timeout": QrLoginState.EXPIRED,
    }
    detail = "Đã từ chối trên điện thoại" if found.state == "declined" else found.error
    return QrLoginStatus(
        state=states.get(found.state, QrLoginState.ERROR), qr_png_base64=found.qr_png_base64, detail=detail
    )


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

    @router.post("/webhooks/zalo-bridge/{account_id}")
    async def bridge_events(account_id: str, request: Request) -> dict[str, bool]:
        """An event of the plugin's own bridge, signed with the secret of its current run; checked before
        parsing. A failure answers 500 so the bridge sends it again."""
        body = await request.body()
        secret = plugin.bridge.secret
        if secret is None or not verify_signature(secret, request.headers, body):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, refused)
        try:
            payload = json.loads(body)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nội dung sự kiện không hợp lệ") from err
        if not isinstance(payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nội dung sự kiện không hợp lệ")
        await plugin.bridge_event(account_id, cast(dict[str, Any], payload))
        return {"ok": True}

    return router

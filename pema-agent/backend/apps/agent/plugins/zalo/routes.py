# ported from: src/server/routes/account-routes.ts
"""Admin routes of the Zalo plugin, under ``/v1/plugins/zalo`` (admin token): accounts (list, create, change,
delete), a bot's token, an OA's keys, the QR login of a personal account, the Node bridge (status, install,
uninstall), the reaction icons the dashboard offers, the address book, group names and the friends of personal
accounts.
Under ``/v1/hooks/zalo`` (open): the webhook of bot accounts (secret header) and the events of the plugin's
own bridge (HMAC signature).

The kind of an account is fixed at creation (delete and create again to change it). Request and response
shapes follow the earlier admin API so the dashboard pages carry over. Every change is followed by a ``sync``
so a channel starts or stops with it.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from pydantic import ValidationError

from .accounts import AccountExistsError
from .bot.client import LoiZaloBotApi
from .bot.types import ZaloBotUpdate, unwrap_webhook_payload
from .models import (
    MAX_ACCOUNT_ID_CHARS,
    ZALO_ID_PATTERN,
    AccountConfig,
    AccountCreate,
    AccountOut,
    AccountUpdate,
    BotTokenSet,
    ChannelKind,
    ContactOut,
    FriendDecision,
    FriendOut,
    FriendRequestOut,
    GroupOut,
    OaKeysSet,
    QrLoginState,
    QrLoginStatus,
    ReactionIconOut,
)
from .oa import NOT_AVAILABLE as OA_NOT_AVAILABLE
from .personal.client import BridgeAccountApi, BridgeClient, BridgeQrStatus, ZaloBridgeError
from .personal.signing import verify_signature
from .plugin import LOCKED_OUT, ZaloPlugin
from .reaction_icons import REACTION_ICONS

logger = logging.getLogger(__name__)

ACCOUNT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
AccountId = Annotated[str, Path(pattern=ACCOUNT_ID_PATTERN, max_length=MAX_ACCOUNT_ID_CHARS)]
AccountFilter = Annotated[str | None, Query(pattern=ACCOUNT_ID_PATTERN, max_length=MAX_ACCOUNT_ID_CHARS)]
ZaloId = Annotated[str, Path(pattern=ZALO_ID_PATTERN)]
ZALO_ID_RULE = re.compile(ZALO_ID_PATTERN)
MAX_NAMES = 60


def account_routes(plugin: ZaloPlugin) -> APIRouter:
    router = APIRouter()
    store = plugin.store

    async def out(account: AccountConfig, warning: str | None = None) -> AccountOut:
        if warning is None and plugin.state(account.id) in LOCKED_OUT:
            warning = "Zalo đã đăng xuất hoặc khóa tài khoản này - quét lại mã QR."
        if warning is None and account.channel is ChannelKind.ZALO_OA:
            warning = OA_NOT_AVAILABLE
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

    @router.put("/accounts/{account_id}/oa-keys")
    async def set_oa_keys(account_id: str, body: OaKeysSet) -> AccountOut:
        """Stores an Official Account's keys sealed; nothing checks them yet (no OA channel)."""
        account = await store.get(account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        if account.channel is not ChannelKind.ZALO_OA:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Chỉ tài khoản Zalo OA mới nhận khóa OA"
            )
        await store.set_secret(account_id, body.model_dump_json())
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
        now = plugin.bridge.status()
        if now.version == "external":
            raise HTTPException(status.HTTP_409_CONFLICT, "Cầu nối chạy ngoài plugin, không cài ở đây")
        if now.bundled:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cầu nối có sẵn trong bản cài agent, không cần cài")
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

    router.include_router(directory_routes(plugin))
    return router


def directory_routes(plugin: ZaloPlugin) -> APIRouter:
    """The address book and the friends of personal accounts. A friend list never carries more than the id
    and the name: Zalo gives phone numbers and birth dates too, which the dashboard has no use for."""
    router = APIRouter()

    def running_api(account_id: str) -> BridgeAccountApi:
        api = plugin.personal_api(account_id)
        if api is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Tài khoản chưa chạy hoặc là kênh bot")
        return api

    @router.get("/friends/{account_id}/requests")
    async def list_friend_requests(account_id: AccountId) -> list[FriendRequestOut]:
        return await plugin.friend_requests.list(account_id)

    @router.get("/friends/{account_id}/list")
    async def list_friends(account_id: AccountId) -> list[FriendOut]:
        api = running_api(account_id)
        try:
            friends = await api.get_all_friends()
        except ZaloBridgeError as err:
            logger.warning("friends of %s not listed (%s)", account_id, err.kind)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Không lấy được danh sách bạn") from None
        return [
            FriendOut(user_id=user_id, display_name=str(f.get("displayName") or f.get("zaloName") or ""))
            for f in friends
            if isinstance(user_id := f.get("userId"), str) and user_id
        ]

    async def decide(account_id: str, uid: str, *, accept: bool) -> Response:
        api = running_api(account_id)
        try:
            if accept:
                await api.accept_friend_request(uid)
            else:
                await api.reject_friend_request(uid)
        except ZaloBridgeError as err:
            logger.warning("friend request of %s not decided (%s)", account_id, err.kind)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Thao tác thất bại, thử lại sau"
            ) from None
        await plugin.friend_requests.delete(account_id, uid)  # only once Zalo took it: a failure is retried
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/friends/{account_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
    async def accept_friend(account_id: AccountId, body: FriendDecision) -> Response:
        return await decide(account_id, body.uid, accept=True)

    @router.post("/friends/{account_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
    async def reject_friend(account_id: AccountId, body: FriendDecision) -> Response:
        return await decide(account_id, body.uid, accept=False)

    @router.get("/contacts")
    async def list_contacts(
        account_id: AccountFilter = None,
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[ContactOut]:
        return await plugin.contacts.list(account_id=account_id, query=q, limit=limit, offset=offset)

    @router.get("/contacts/names")
    async def contact_names(
        account_id: Annotated[str, Query(pattern=ACCOUNT_ID_PATTERN, max_length=MAX_ACCOUNT_ID_CHARS)],
        ids: str = Query(default="", max_length=3000),
    ) -> dict[str, str]:
        """Display names of the given people (``ids``: Zalo ids separated by commas, at most 60), for the
        dashboard's chat list."""
        wanted = [uid for uid in ids.split(",") if ZALO_ID_RULE.fullmatch(uid)][:MAX_NAMES]
        return await plugin.contacts.names(account_id, wanted)

    @router.delete("/contacts/{account_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_contact(account_id: AccountId, user_id: ZaloId) -> Response:
        """Only the address-book row; deleting one that is not there is not an error."""
        await plugin.contacts.delete(account_id, user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/groups")
    async def list_groups(account_id: AccountFilter = None) -> list[GroupOut]:
        return await plugin.groups.list(account_id)

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

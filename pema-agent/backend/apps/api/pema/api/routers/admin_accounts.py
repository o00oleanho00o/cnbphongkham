# ported from: src/server/routes/account-routes.ts
"""Zalo accounts: list, create, update, delete, QR login (package C2 implements).

The bot-token endpoint lives in ``admin_bot_accounts.py`` (package C1). The channel kind is fixed at creation:
changing it would change the meaning of the stored credential (zca-js cookie versus bot token). Delete
the account
and create it again instead. QR login is for ``zalo_personal`` only and goes through the Node bridge; the
README of
the bridge states the account-lock risk.

Deviations from the original:

* Hono + zod became FastAPI + the DTOs of ``pema_contracts.admin_agent`` (clinic scoped, session cookie,
RBAC through
  ``C2Services.authorize``; permission ``admin.accounts``);
* ``datLoaiKenh``/``loai`` is ``channel``; every new account gets a ``policy_profile`` (default
``patient_channel``,
  fail safe); a new Bot account starts with a CLOSED allowlist (anyone with the link could otherwise burn
  tokens and
  try prompt injection) while a personal account does not need it (it must be a friend to message);
* ``hasCredentials`` reads the encrypted credential through the vault (the credential never leaves the
server);
* the credential is deleted together with the account (the original removed ``data/accounts/<id>``);
* PATCH starts/stops the listener like the original, but the answer is the plain ``AccountOut``: a failed
start is
  logged and visible as ``running=false`` (the contract has no ``warning`` field; open item for package G);
* every mutation writes an audit row.
"""

from __future__ import annotations

from fastapi import Request, Response, status

from pema.api.deps import admin_router
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.reaction_icons import REACTION_ICON_KEYS, REACTION_ICONS
from pema.channels.zalo_personal.services import C2Services, get_c2
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.admin_agent import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    QrLoginState,
    QrLoginStatus,
    ReactionIcon,
)
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission
from pema_contracts.tools import BUILTIN_TOOL_KEYS, CLINIC_TOOL_KEYS

router = admin_router("accounts", "admin-accounts")

log = create_logger("account-routes")

KNOWN_TOOL_KEYS = frozenset(BUILTIN_TOOL_KEYS) | frozenset(CLINIC_TOOL_KEYS)


async def _with_status(services: C2Services, config: AccountConfig) -> AccountOut:
    running = services.registry.get_running(config.clinic_id, config.id) is not None
    if config.channel is ChannelKind.ZALO_PERSONAL:
        has_credentials = await services.vault.has_credentials(config.clinic_id, config.id)
    else:
        has_credentials = config.has_bot_token
    return AccountOut.model_validate(
        {**config.model_dump(), "running": running, "has_credentials": has_credentials}
    )


async def _require_account(services: C2Services, ctx: ActionContext, account_id: str) -> AccountConfig:
    config = await services.accounts.get_account(ctx.clinic_id, account_id)
    if config is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Account không tồn tại")
    return config


async def _check_agent(services: C2Services, ctx: ActionContext, agent_id: str | None) -> None:
    if agent_id and await services.agents.get_agent(ctx.clinic_id, agent_id) is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Agent không tồn tại")


async def _stop(services: C2Services, config: AccountConfig) -> None:
    if config.channel is ChannelKind.ZALO_PERSONAL:
        await services.manager.stop_account(config.clinic_id, config.id)
    elif services.bot_lifecycle is not None:
        await services.bot_lifecycle.stop(config.clinic_id, config.id)


@router.get("", response_model=list[AccountOut], summary="Accounts with running state")
async def list_accounts(request: Request) -> list[AccountOut]:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    return [await _with_status(services, a) for a in await services.accounts.list_accounts(ctx.clinic_id)]


@router.get("/reaction-icons", response_model=list[ReactionIcon], summary="Reaction icons for auto-react")
async def list_reaction_icons(request: Request) -> list[ReactionIcon]:
    # Danh sách reaction cho UI chọn - giữ 1 nguồn duy nhất ở server, tránh frontend chép lại rồi lệch.
    # (a comment, not a docstring: a docstring would change the OpenAPI description, a contract file.)
    services = get_c2(request)
    await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    return [ReactionIcon(key=key, emoji=REACTION_ICONS[key].emoji) for key in REACTION_ICON_KEYS]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, summary="Create an account")
async def create_account(body: AccountCreate, request: Request) -> AccountOut:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    if await services.accounts.get_account(ctx.clinic_id, body.id) is not None:
        raise DomainError(ErrorCode.INVALID_STATE, "Account id đã tồn tại")
    await _check_agent(services, ctx, body.agent_id)

    await services.accounts.create_account(
        ctx.clinic_id, account_id=body.id, label=body.label, channel=body.channel, agent_id=body.agent_id
    )
    patch: dict[str, object] = {"policy_profile": body.policy_profile}
    if body.channel is ChannelKind.ZALO_BOT:
        # Tài khoản bot mặc định ĐÓNG danh sách cho phép, khác tài khoản cá nhân. Bán kính khác hẳn: nick
        # cá nhân
        # phải là bạn bè mới nhắn được, còn bot thì ai có link cũng nhắn được - mở sẵn là mời người lạ
        # đốt token
        # và thử prompt injection. Chủ bot tự thêm mình vào danh sách.
        patch["allowlist"] = {"mode": "list", "user_ids": []}
    created = await services.accounts.update_account(ctx.clinic_id, body.id, patch)
    if created is None:
        raise DomainError(ErrorCode.INTERNAL, "Không tạo được account")
    await services.audit.record(
        ctx,
        "account.create",
        "account",
        body.id,
        {"channel": body.channel.value, "policy_profile": body.policy_profile.value},
    )
    log.info("Tạo account từ dashboard", account_id=body.id, channel=body.channel.value)
    return await _with_status(services, created)


@router.patch("/{account_id}", response_model=AccountOut, summary="Update an account")
async def update_account(account_id: str, body: AccountUpdate, request: Request) -> AccountOut:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    await _check_agent(services, ctx, body.agent_id)
    patch = body.model_dump(exclude_unset=True)
    # Chặn icon lạ ngay ở API thay vì để rơi về mặc định lúc chạy
    icon = patch.get("auto_react_icon")
    if icon is not None and icon not in REACTION_ICONS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Icon reaction không hợp lệ")
    # Chặn key tool lạ ngay ở API - key sai âm thầm nằm trong DB sẽ không tắt gì cả (MCP tools are namespaced
    # ``mcp.<server>.<tool>`` and are checked by their own package).
    disabled_tools: list[str] = list(patch.get("disabled_tools") or [])
    for key in disabled_tools:
        if key not in KNOWN_TOOL_KEYS and not key.startswith("mcp"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Tên công cụ không hợp lệ")

    await _require_account(services, ctx, account_id)
    account = await services.accounts.update_account(ctx.clinic_id, account_id, patch)
    if account is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Account không tồn tại")
    await services.audit.record(ctx, "account.update", "account", account_id, {"fields": sorted(patch)})

    # Toggle enabled tác động listener ngay; start fail (chưa login QR) không phải lỗi của PATCH -
    # account vẫn ở
    # trạng thái bật, `running=false` cho UI thấy
    if body.enabled is False:
        await _stop(services, account)
    elif body.enabled is True and services.registry.get_running(ctx.clinic_id, account_id) is None:
        try:
            if account.channel is ChannelKind.ZALO_PERSONAL:
                await services.manager.start_account(ctx.clinic_id, account_id)
            elif services.bot_lifecycle is not None:
                await services.bot_lifecycle.start(ctx.clinic_id, account_id)
        except (DomainError, ZaloBridgeError) as err:
            log.info("account enabled but not started", account_id=account_id, reason=type(err).__name__)

    return await _with_status(services, account)


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an account and its credential"
)
async def delete_account(account_id: str, request: Request) -> Response:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    config = await _require_account(services, ctx, account_id)
    await _stop(services, config)
    # Xóa luôn credentials (cookie mã hóa) - account đã xóa thì không giữ chìa khóa. History/contacts giữ
    # lại để
    # còn tra cứu.
    if config.channel is ChannelKind.ZALO_PERSONAL:
        await services.vault.delete_credentials(ctx.clinic_id, account_id)
    if not await services.accounts.delete_account(ctx.clinic_id, account_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Account không tồn tại")
    await services.audit.record(
        ctx, "account.delete", "account", account_id, {"channel": config.channel.value}
    )
    log.info("Xóa account + credentials từ dashboard", account_id=account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _qr_out(state: str, qr_data_uri: str | None, error: str | None) -> QrLoginStatus:
    """Map the manager statuses (``starting``, ``declined``, ``timeout`` exist there as in the original)
    onto the
    ``QrLoginState`` enum of the contract."""
    qr = qr_data_uri.split(",", 1)[1] if qr_data_uri and "," in qr_data_uri else None
    mapping: dict[str, QrLoginState] = {
        "idle": QrLoginState.IDLE,
        "starting": QrLoginState.WAITING_SCAN,
        "waiting_scan": QrLoginState.WAITING_SCAN,
        "scanned": QrLoginState.SCANNED,
        "success": QrLoginState.SUCCESS,
        "declined": QrLoginState.ERROR,
        "error": QrLoginState.ERROR,
        "timeout": QrLoginState.EXPIRED,
    }
    detail = "Đã từ chối trên điện thoại" if state == "declined" else error
    return QrLoginStatus(state=mapping.get(state, QrLoginState.ERROR), qr_png_base64=qr, detail=detail)


@router.post(
    "/{account_id}/login",
    response_model=QrLoginStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start QR login (personal account)",
)
async def start_qr_login(account_id: str, request: Request) -> QrLoginStatus:
    # Bắt đầu phiên login QR (idempotent - đang có phiên sống thì trả phiên đó).
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    config = await _require_account(services, ctx, account_id)
    # Đăng nhập QR cho một tài khoản BOT tạo ra một tài khoản nửa nọ nửa kia (gắn api zca-js vào account
    # mà DB nói
    # là bot). Giao diện đã ẩn nút, nhưng đó là lớp client.
    if config.channel is not ChannelKind.ZALO_PERSONAL:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "Tài khoản bot không đăng nhập QR - nhập token ở phần Sửa"
        )
    # Off means no traffic: neither the process flag nor the clinic switch may be off.
    if not services.flag_enabled():
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Tài khoản cá nhân đang bị tắt bằng cờ cấu hình.")
    settings = await services.settings.get(ctx.clinic_id, ChannelKind.ZALO_PERSONAL)
    if not settings.enabled:
        raise DomainError(
            ErrorCode.CHANNEL_UNAVAILABLE, "Bật kênh Zalo cá nhân ở trang Kênh trước khi quét QR."
        )
    await services.qr.start_qr_login(ctx.clinic_id, account_id)
    await services.audit.record(ctx, "account.qr_login_start", "account", account_id, None)
    state = services.qr.get_qr_login_status(ctx.clinic_id, account_id)
    return _qr_out(state.status, state.qr_data_uri, state.error)


@router.get("/{account_id}/login/status", response_model=QrLoginStatus, summary="Poll the QR login state")
async def get_qr_login_status(account_id: str, request: Request) -> QrLoginStatus:
    # UI polling mỗi ~1.5s: trạng thái + ảnh QR khi đang chờ quét. The QR image is the key to the account: it
    # travels only through this authenticated route and is never logged.
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    state = services.qr.get_qr_login_status(ctx.clinic_id, account_id)
    return _qr_out(state.status, state.qr_data_uri, state.error)

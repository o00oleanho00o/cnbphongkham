# ported from: src/server/routes/friend-routes.ts
"""Friend requests and friends of a personal account (package C2).

Tab Bạn bè (personal channel only). Pending requests come from ``agent.friend_requests`` (no running
account needed);
the friend list is read live from the bridge. The friend list returns ONLY ``user_id`` and ``display_name``:
``getAllFriends()`` returns the full user (phone number, birth date ...), and pushing that to the
dashboard would
expose friends' personal data for no reason (the bridge already strips it, this route keeps the rule).

Deviations: Hono + zod became FastAPI + the DTOs of ``pema_contracts.admin_agent``; the zca-js ``API`` of the
running account is the bridge-backed ``ZaloApi`` of the channel; ``getApi() == null`` (bot channel, not
running) is
``409 invalid_state`` and a Zalo/bridge failure is ``503 channel_unavailable`` (the original answered
502). The row
is deleted ONLY after Zalo accepted the action, so a failed action keeps it for a retry.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Request

from pema.api.deps import admin_router
from pema.channels.zalo_personal.bridge_client import ZaloApi, ZaloBridgeError
from pema.channels.zalo_personal.services import C2Services, get_c2
from pema.shared.logger import create_logger
from pema_contracts.admin_agent import FriendDecision, FriendOut, FriendRequestOut
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

router = admin_router("friends", "admin-accounts")

log = create_logger("friend-routes")

NOT_RUNNING = "Tài khoản chưa chạy hoặc là kênh bot"


def _running_api(services: C2Services, clinic_id: UUID, account_id: str) -> ZaloApi:
    running = services.manager.get_running(clinic_id, account_id)
    if running is None:
        raise DomainError(ErrorCode.INVALID_STATE, NOT_RUNNING)
    return running.api


@router.get(
    "/{account_id}/requests",
    response_model=list[FriendRequestOut],
    summary="Pending incoming friend requests",
)
async def list_friend_requests(account_id: str, request: Request) -> list[FriendRequestOut]:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    rows = await services.friends.list_friend_requests(ctx.clinic_id, account_id)
    return [
        FriendRequestOut(
            from_uid=r.from_uid,
            message=r.message,
            sender_name=r.sender_name,
            avatar_url=r.avatar_url,
            received_at=r.received_at,
        )
        for r in rows
    ]


@router.get("/{account_id}/list", response_model=list[FriendOut], summary="Friends of the account")
async def list_friends(account_id: str, request: Request) -> list[FriendOut]:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    api = _running_api(services, ctx.clinic_id, account_id)
    try:
        friends = await api.get_all_friends()
    except ZaloBridgeError as err:
        log.warning("get_all_friends failed", account_id=account_id, kind=err.kind)
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Không lấy được danh sách bạn") from err
    # CHỈ trả field UI cần: never phone number, birth date or anything else of the friend.
    out: list[FriendOut] = []
    for friend in friends:
        user_id = friend.get("userId")
        if not isinstance(user_id, str) or not user_id:
            continue
        name = friend.get("displayName") or friend.get("zaloName") or ""
        out.append(FriendOut(user_id=user_id, display_name=str(name), avatar_url=None))
    return out


async def _decide(request: Request, account_id: str, body: FriendDecision, *, accept: bool) -> None:
    """Chung cho accept + reject: validate body, lấy api, gọi hành động, xóa dòng pending."""
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_ACCOUNTS)
    if not body.uid:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Thiếu uid")
    api = _running_api(services, ctx.clinic_id, account_id)
    try:
        if accept:
            await api.accept_friend_request(body.uid)
        else:
            await api.reject_friend_request(body.uid)
    except ZaloBridgeError as err:
        log.warning("friend decision failed", account_id=account_id, kind=err.kind, accept=accept)
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Thao tác thất bại, thử lại sau") from err
    # Chỉ xóa SAU khi Zalo nhận - hành động hỏng thì giữ dòng để thử lại.
    await services.friends.xoa_friend_request(ctx.clinic_id, account_id, body.uid)
    await services.audit.record(
        ctx, "friend.accept" if accept else "friend.reject", "friend_request", account_id, {"decided": True}
    )


@router.post("/{account_id}/accept", summary="Accept a friend request")
async def accept_friend(account_id: str, body: FriendDecision, request: Request) -> None:
    await _decide(request, account_id, body, accept=True)


@router.post("/{account_id}/reject", summary="Reject a friend request")
async def reject_friend(account_id: str, body: FriendDecision, request: Request) -> None:
    await _decide(request, account_id, body, accept=False)

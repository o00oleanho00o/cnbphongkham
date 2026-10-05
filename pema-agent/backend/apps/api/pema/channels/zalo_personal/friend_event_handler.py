# ported from: src/zalo/friend-event-handler.ts
"""Xử lý một sự kiện ``friend_event`` cho một tài khoản cá nhân.

* REQUEST (không phải mình gửi): enrich tên/avatar rồi LƯU vào bảng pending.
* ADD / REJECT_REQUEST / UNDO_REQUEST: XÓA dòng pending tương ứng (đã giải quyết).
* REMOVE + loại khác: chỉ log (danh sách bạn lấy trực tiếp nên tự cập nhật).

KHÔNG ném ra listener: mọi lỗi bắt lại rồi log. Enrich hỏng vẫn lưu (sender_name None).

Forced deviation: the bridge normalises the zca-js ``FriendEvent`` (``FriendEventType`` enum) into
``{"kind": "add" | "remove" | "request" | "undo_request" | "reject_request" | "other", "thread_id", "is_self",
"data"}`` so no numeric enum value crosses the process boundary. ``data`` keeps the zca-js shape: a
request has
``fromUid``/``toUid``/``message``; reject and undo have ``fromUid``/``toUid``; for ``add`` the uid is the
thread
id. The store is a Port (Postgres in production, in-memory in tests); every call carries the clinic id.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pema.channels.zalo_personal.bridge_client import ZaloApi
from pema.channels.zalo_personal.friend_request_store import FriendRequestPort, FriendRequestRow
from pema.shared.logger import create_logger
from pema_contracts.common import JsonObject

log = create_logger("friend-event")

# Đường lấy thông tin user - tách để test tiêm giả, khỏi gọi mạng thật
type LayUser = Callable[[str], Awaitable[JsonObject]]


@dataclass
class FriendEventDeps:
    lay_user: LayUser | None = None
    now: Callable[[], datetime] | None = None


def _data(event: Mapping[str, object]) -> Mapping[str, object]:
    data = event.get("data")
    return data if isinstance(data, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def _uid_can_xoa(event: Mapping[str, object]) -> str | None:
    """uid đối phương cần xóa khỏi pending, tùy loại sự kiện. ``None`` nếu không rõ."""
    kind = event.get("kind")
    if kind == "add":
        # data là string = threadId = uid vừa thành bạn
        thread_id = event.get("thread_id")
        return thread_id if isinstance(thread_id, str) and thread_id else None
    if kind in ("reject_request", "undo_request"):
        # data { toUid, fromUid } - fromUid là người đã GỬI request (khóa của dòng pending)
        from_uid = _data(event).get("fromUid")
        return from_uid if isinstance(from_uid, str) and from_uid else None
    return None


def _doc_ho_so(resp: Mapping[str, object]) -> tuple[str | None, str | None]:
    """Đọc tên + avatar từ phản hồi getUserInfo (best-effort, sai gì cũng trả None)."""
    profiles = resp.get("changed_profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        return (None, None)
    first = next(iter(profiles.values()))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if not isinstance(first, Mapping):
        return (None, None)
    name = first.get("displayName") or first.get("zaloName") or None  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    avatar = first.get("avatar") or None  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return (
        name if isinstance(name, str) else None,
        avatar if isinstance(avatar, str) else None,
    )


async def handle_friend_event(
    clinic_id: UUID,
    account_id: str,
    api: ZaloApi,
    event: Mapping[str, object],
    store: FriendRequestPort,
    deps: FriendEventDeps | None = None,
) -> None:
    deps = deps or FriendEventDeps()
    try:
        kind = event.get("kind")
        if kind == "request":
            if event.get("is_self"):
                return  # request MÌNH gửi đi - không phải request đến
            from_uid = _data(event).get("fromUid")
            if not isinstance(from_uid, str) or not from_uid:
                return
            message = _data(event).get("message")

            # Upsert TRƯỚC (chưa enrich) để dòng tồn tại NGAY. `get_user_info` có thể mất vài giây; nếu enrich
            # xong mới ghi thì một ADD/accept chen vào giữa sẽ xóa hụt (dòng chưa có) rồi ta chèn lại một dòng
            # "ma" cho người đã thành bạn.
            await store.upsert_friend_request(
                clinic_id,
                FriendRequestRow(
                    account_id=account_id,
                    from_uid=from_uid,
                    message=message if isinstance(message, str) else "",
                    sender_name=None,
                    avatar_url=None,
                    received_at=(deps.now or (lambda: datetime.now(UTC)))(),
                ),
            )

            # Enrich SAU bằng UPDATE-only: dòng vừa bị ADD xóa thì đây là no-op.
            lay_user: LayUser = deps.lay_user or api.get_user_info
            try:
                sender_name, avatar_url = _doc_ho_so(await lay_user(from_uid))
                if sender_name or avatar_url:
                    await store.cap_nhat_ho_so_friend_request(
                        clinic_id, account_id, from_uid, sender_name, avatar_url
                    )
            except Exception as err:
                log.warning("enrich get_user_info hỏng - giữ mỗi UID", err=err, account_id=account_id)
            log.info("yêu cầu kết bạn mới", account_id=account_id)
            return

        uid = _uid_can_xoa(event)
        if uid:
            await store.xoa_friend_request(clinic_id, account_id, uid)
            log.debug("xóa pending (đã giải quyết)", account_id=account_id, kind=str(kind))
            return

        log.debug("friend_event không cần xử lý", account_id=account_id, kind=str(kind))
    except Exception as err:
        log.error("handle_friend_event lỗi - nuốt để không phá listener", err=err, account_id=account_id)

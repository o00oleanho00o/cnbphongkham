# ported from: src/conversation/friend-request-store.ts
"""Store cho bảng ``agent.friend_requests`` (yêu cầu kết bạn ĐẾN đang chờ).

Forced deviations: SQLite prepared statements at module level become SQLAlchemy ``text`` queries on Postgres,
asynchronous, one unit of work per call through ``ClinicDatabase.session()`` (no row level security; by
``clinic_id``); every method takes the clinic id first. ``received_at`` is an aware ``datetime``
(``timestamptz``)
instead of epoch milliseconds. The table is created by Alembic 0002 (``friend-schema.ts`` row of PORT-MAP).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase


@dataclass(frozen=True)
class FriendRequestRow:
    account_id: str
    from_uid: str
    message: str
    sender_name: str | None
    """Tên hiển thị enrich từ ``get_user_info`` lúc nhận sự kiện; ``None`` nếu enrich hỏng."""
    avatar_url: str | None
    received_at: datetime
    """Lúc nhận sự kiện - dùng cho delay auto-accept."""


class FriendRequestPort(Protocol):
    """What ``friend_event_handler``, the sweep and the admin routes need; the Postgres store implements
    it and
    tests may use an in-memory fake."""

    async def upsert_friend_request(self, clinic_id: UUID, row: FriendRequestRow) -> None: ...

    async def cap_nhat_ho_so_friend_request(
        self, clinic_id: UUID, account_id: str, from_uid: str, sender_name: str | None, avatar_url: str | None
    ) -> None: ...

    async def xoa_friend_request(self, clinic_id: UUID, account_id: str, from_uid: str) -> bool: ...

    async def list_friend_requests(self, clinic_id: UUID, account_id: str) -> list[FriendRequestRow]: ...

    async def lay_friend_request_qua_han(
        self, clinic_id: UUID, account_id: str, truoc_moc: datetime
    ) -> list[FriendRequestRow]: ...


_COLUMNS = "account_id, from_uid, message, sender_name, avatar_url, received_at"


def _to_row(mapping: Mapping[Any, Any]) -> FriendRequestRow:
    return FriendRequestRow(
        account_id=mapping["account_id"],
        from_uid=mapping["from_uid"],
        message=mapping["message"],
        sender_name=mapping["sender_name"],
        avatar_url=mapping["avatar_url"],
        received_at=mapping["received_at"],
    )


class FriendRequestStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def upsert_friend_request(self, clinic_id: UUID, row: FriendRequestRow) -> None:
        """Ghi/cập nhật một request. Người gửi lại (trùng PK) chỉ cập nhật, không đẻ dòng 2."""
        if not row.account_id or not row.from_uid:
            return
        async with self._db.session() as session:
            await session.execute(
                text(
                    "INSERT INTO agent.friend_requests "
                    "(clinic_id, account_id, from_uid, message, sender_name, avatar_url, received_at) "
                    "VALUES (:clinic_id, :account_id, :from_uid, :message, :sender_name, :avatar_url, "
                    ":received_at) "
                    "ON CONFLICT (clinic_id, account_id, from_uid) DO UPDATE SET "
                    "message = excluded.message, sender_name = excluded.sender_name, "
                    "avatar_url = excluded.avatar_url, received_at = excluded.received_at"
                ),
                {
                    "clinic_id": clinic_id,
                    "account_id": row.account_id,
                    "from_uid": row.from_uid,
                    "message": row.message,
                    "sender_name": row.sender_name,
                    "avatar_url": row.avatar_url,
                    "received_at": row.received_at,
                },
            )

    async def cap_nhat_ho_so_friend_request(
        self, clinic_id: UUID, account_id: str, from_uid: str, sender_name: str | None, avatar_url: str | None
    ) -> None:
        """Cập nhật tên/avatar SAU khi đã upsert (enrich ``get_user_info`` chậm, chạy sau). UPDATE-only, KHÔNG
        chèn: nếu dòng vừa bị ADD/accept xóa trong lúc enrich thì đây là no-op - tránh dựng lại một dòng
        "ma" cho
        người đã thành bạn."""
        async with self._db.session() as session:
            await session.execute(
                text(
                    "UPDATE agent.friend_requests SET sender_name = :sender_name, avatar_url = :avatar_url "
                    "WHERE account_id = :account_id AND from_uid = :from_uid"
                ),
                {
                    "sender_name": sender_name,
                    "avatar_url": avatar_url,
                    "account_id": account_id,
                    "from_uid": from_uid,
                },
            )

    async def xoa_friend_request(self, clinic_id: UUID, account_id: str, from_uid: str) -> bool:
        """Xóa dòng khi ADD/REJECT/UNDO hoặc accept/reject xong. Idempotent (xóa dòng đã mất vô hại)."""
        async with self._db.session() as session:
            result = await session.execute(
                text(
                    "DELETE FROM agent.friend_requests "
                    "WHERE account_id = :account_id AND from_uid = :from_uid"
                ),
                {"account_id": account_id, "from_uid": from_uid},
            )
            return result.rowcount > 0  # type: ignore[attr-defined]

    async def list_friend_requests(self, clinic_id: UUID, account_id: str) -> list[FriendRequestRow]:
        """Mọi request đang chờ của một account, mới nhất trước."""
        async with self._db.session() as session:
            result = await session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM agent.friend_requests WHERE account_id = :account_id "  # noqa: S608
                    "ORDER BY received_at DESC"
                ),
                {"account_id": account_id},
            )
            return [_to_row(r) for r in result.mappings().all()]

    async def lay_friend_request_qua_han(
        self, clinic_id: UUID, account_id: str, truoc_moc: datetime
    ) -> list[FriendRequestRow]:
        """Request đã chờ quá mốc (``received_at <= truoc_moc``) - cho vòng quét auto-accept.
        ``truoc_moc = now - delay_minutes``."""
        async with self._db.session() as session:
            result = await session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM agent.friend_requests "  # noqa: S608
                    "WHERE account_id = :account_id AND received_at <= :truoc_moc ORDER BY received_at"
                ),
                {"account_id": account_id, "truoc_moc": truoc_moc},
            )
            return [_to_row(r) for r in result.mappings().all()]

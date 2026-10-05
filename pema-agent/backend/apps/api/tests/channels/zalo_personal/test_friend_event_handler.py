# ported from: src/zalo/friend-event-handler.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original ran against the real SQLite store; here the handler talks to an in-memory implementation of
``FriendRequestPort`` (the Postgres store has its own tests in ``test_friend_request_store.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pema.channels.zalo_personal.friend_event_handler import FriendEventDeps, handle_friend_event
from pema.channels.zalo_personal.friend_request_store import FriendRequestRow
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.common import JsonObject

CLINIC = uuid4()
API_STUB = FakeZaloApi()


class MemoryFriendStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], FriendRequestRow] = {}

    async def upsert_friend_request(self, clinic_id: UUID, row: FriendRequestRow) -> None:
        self.rows[(row.account_id, row.from_uid)] = row

    async def cap_nhat_ho_so_friend_request(
        self, clinic_id: UUID, account_id: str, from_uid: str, sender_name: str | None, avatar_url: str | None
    ) -> None:
        current = self.rows.get((account_id, from_uid))
        if current is not None:
            self.rows[(account_id, from_uid)] = FriendRequestRow(
                account_id, from_uid, current.message, sender_name, avatar_url, current.received_at
            )

    async def xoa_friend_request(self, clinic_id: UUID, account_id: str, from_uid: str) -> bool:
        return self.rows.pop((account_id, from_uid), None) is not None

    async def list_friend_requests(self, clinic_id: UUID, account_id: str) -> list[FriendRequestRow]:
        return [r for (acc, _), r in self.rows.items() if acc == account_id]

    async def lay_friend_request_qua_han(
        self, clinic_id: UUID, account_id: str, truoc_moc: datetime
    ) -> list[FriendRequestRow]:
        return [
            r for r in await self.list_friend_requests(clinic_id, account_id) if r.received_at <= truoc_moc
        ]


def ev_request(from_uid: str, *, is_self: bool = False, message: str = "cho ket ban") -> JsonObject:
    return {
        "kind": "request",
        "data": {"fromUid": from_uid, "toUid": "me", "src": 0, "message": message},
        "thread_id": "me",
        "is_self": is_self,
    }


def lay_user_gia(name: str, avatar: str):  # type: ignore[no-untyped-def]
    async def lay(_uid: str) -> JsonObject:
        return {"changed_profiles": {"u_0": {"displayName": name, "avatar": avatar}}}

    return lay


async def lay_user_nem(_uid: str) -> JsonObject:
    raise RuntimeError("rate limit")


def ids(store: MemoryFriendStore, account: str) -> list[str]:
    return [from_uid for (acc, from_uid) in store.rows if acc == account]


def seed(store: MemoryFriendStore, account: str, from_uid: str) -> None:
    store.rows[(account, from_uid)] = FriendRequestRow(
        account, from_uid, "", None, None, datetime(2026, 9, 20, tzinfo=UTC)
    )


async def test_handle_friend_event_request_khong_phai_minh_luu_pending_enrich_dung_thoi_gian() -> None:
    """REQUEST (không phải mình) -> lưu pending, enrich tên/avatar, đúng thời gian"""
    store = MemoryFriendStore()
    moc = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    await handle_friend_event(
        CLINIC,
        "acc-1",
        API_STUB,
        ev_request("u-req", message="hi"),
        store,
        FriendEventDeps(lay_user=lay_user_gia("Hoa", "https://cdn.example.invalid/h.jpg"), now=lambda: moc),
    )
    row = store.rows.get(("acc-1", "u-req"))
    assert row is not None, "phải lưu dòng pending"
    assert row.sender_name == "Hoa"
    assert row.avatar_url == "https://cdn.example.invalid/h.jpg"
    assert row.message == "hi"
    assert row.received_at == moc


async def test_handle_friend_event_request_get_user_info_nem_van_luu_sender_name_null_khong_nem() -> None:
    """REQUEST + getUserInfo NÉM -> vẫn lưu, senderName null, KHÔNG ném"""
    store = MemoryFriendStore()
    await handle_friend_event(
        CLINIC, "acc-1", API_STUB, ev_request("u-nem"), store, FriendEventDeps(lay_user=lay_user_nem)
    )
    row = store.rows.get(("acc-1", "u-nem"))
    assert row is not None, "enrich hỏng vẫn phải lưu"
    assert row.sender_name is None
    assert row.avatar_url is None


async def test_handle_friend_event_request_is_self_minh_gui_di_khong_luu() -> None:
    """REQUEST isSelf (mình gửi đi) -> KHÔNG lưu"""
    store = MemoryFriendStore()
    await handle_friend_event(
        CLINIC,
        "acc-1",
        API_STUB,
        ev_request("u-self", is_self=True),
        store,
        FriendEventDeps(lay_user=lay_user_gia("X", "y")),
    )
    assert "u-self" not in ids(store, "acc-1")


async def test_handle_friend_event_add_xoa_dong_pending_cua_uid_vua_thanh_ban() -> None:
    """ADD -> xóa dòng pending của uid vừa thành bạn"""
    store = MemoryFriendStore()
    seed(store, "acc-2", "u-add")
    await handle_friend_event(
        CLINIC,
        "acc-2",
        API_STUB,
        {"kind": "add", "data": "u-add", "thread_id": "u-add", "is_self": False},
        store,
    )
    assert "u-add" not in ids(store, "acc-2"), "ADD phải xóa pending"


async def test_handle_friend_event_reject_request_undo_request_xoa_dong_pending_cua_from_uid() -> None:
    """REJECT_REQUEST / UNDO_REQUEST -> xóa dòng pending của fromUid"""
    store = MemoryFriendStore()
    for kind in ("reject_request", "undo_request"):
        seed(store, "acc-3", "u-rej")
        event: JsonObject = {
            "kind": kind,
            "data": {"toUid": "me", "fromUid": "u-rej"},
            "thread_id": "me",
            "is_self": False,
        }
        await handle_friend_event(CLINIC, "acc-3", API_STUB, event, store)
        assert "u-rej" not in ids(store, "acc-3"), f"{kind} phải xóa pending"


async def test_handle_friend_event_dua_dong_bi_xoa_trong_luc_enrich_khong_dung_lai_dong_ma() -> None:
    """ĐUA: dòng bị xóa TRONG lúc enrich -> KHÔNG dựng lại dòng ma

    Mô phỏng ADD/accept chen vào giữa upsert và enrich: lay_user xóa dòng rồi mới trả profile. upsert-TRƯỚC +
    cap_nhat UPDATE-only -> cap_nhat no-op -> không dòng ma. Nếu revert về enrich-TRƯỚC-ghi-SAU (bug gốc) thì
    dòng ma xuất hiện -> ca này ĐỎ.
    """
    store = MemoryFriendStore()

    async def lay_user_xoa_giua_chung(_uid: str) -> JsonObject:
        await store.xoa_friend_request(CLINIC, "acc-race", "u-race")
        return {"changed_profiles": {"u_0": {"displayName": "Ma", "avatar": "x"}}}

    await handle_friend_event(
        CLINIC,
        "acc-race",
        API_STUB,
        ev_request("u-race"),
        store,
        FriendEventDeps(lay_user=lay_user_xoa_giua_chung),
    )
    assert "u-race" not in ids(store, "acc-race"), "dòng đã bị xóa trong lúc enrich thì KHÔNG được dựng lại"


async def test_handle_friend_event_request_from_uid_rong_khong_luu_khong_nem() -> None:
    """REQUEST fromUid RỖNG -> không lưu, không ném"""
    store = MemoryFriendStore()
    await handle_friend_event(
        CLINIC, "acc-empty", API_STUB, ev_request(""), store, FriendEventDeps(lay_user=lay_user_gia("X", "y"))
    )
    assert store.rows == {}


async def test_handle_friend_event_remove_khong_dung_bang_pending_khong_nem() -> None:
    """REMOVE -> không đụng bảng pending, không ném"""
    store = MemoryFriendStore()
    seed(store, "acc-4", "u-keep")
    await handle_friend_event(
        CLINIC,
        "acc-4",
        API_STUB,
        {"kind": "remove", "data": "u-keep", "thread_id": "u-keep", "is_self": False},
        store,
    )
    assert "u-keep" in ids(store, "acc-4"), "REMOVE không xóa pending"


async def test_handle_friend_event_loi_cua_store_duoc_nuot_de_khong_pha_listener() -> None:
    """mọi lỗi bắt lại rồi log - listener không bao giờ nhận exception"""

    class Boom(MemoryFriendStore):
        async def upsert_friend_request(self, clinic_id: UUID, row: FriendRequestRow) -> None:
            raise RuntimeError("db down")

    await handle_friend_event(CLINIC, "acc-1", API_STUB, ev_request("u-1"), Boom())

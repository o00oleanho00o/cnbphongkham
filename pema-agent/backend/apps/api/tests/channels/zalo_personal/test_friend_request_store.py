# ported from: src/conversation/friend-request-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Database tests (marker ``db``): skipped without ``PEMA_TEST_DATABASE_URL`` (see ``conftest.py``). They run as the
``be_app`` role through ``ClinicDatabase`` so row level security is really in force.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pema.channels.zalo_personal.friend_request_store import FriendRequestRow, FriendRequestStore
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

T0 = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)


def req(**over: object) -> FriendRequestRow:
    base: dict[str, object] = {
        "account_id": "zp-1",
        "from_uid": "u1",
        "message": "cho ket ban nhe",
        "sender_name": "Hoa",
        "avatar_url": "https://cdn.example.invalid/a.jpg",
        "received_at": T0,
    }
    return FriendRequestRow(**{**base, **over})  # type: ignore[arg-type]


async def test_friend_request_store_upsert_roi_list_tra_dung_field(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """upsert rồi list trả đúng field"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(clinic, req(from_uid="u-list"))
    rows = [r for r in await store.list_friend_requests(clinic, "zp-1") if r.from_uid == "u-list"]
    assert rows == [req(from_uid="u-list")]


async def test_friend_request_store_upsert_trung_chi_cap_nhat_khong_de_dong_thu_hai(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """upsert TRÙNG (account, from_uid) chỉ cập nhật, KHÔNG đẻ dòng thứ hai"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(clinic, req(from_uid="u-trung", message="lần 1", received_at=T0))
    later = T0 + timedelta(seconds=1)
    await store.upsert_friend_request(clinic, req(from_uid="u-trung", message="lần 2", received_at=later))
    rows = [r for r in await store.list_friend_requests(clinic, "zp-1") if r.from_uid == "u-trung"]
    assert len(rows) == 1, "trùng PK không được đẻ dòng mới"
    assert rows[0].message == "lần 2"
    assert rows[0].received_at == later


async def test_friend_request_store_xoa_dong_roi_list_khong_con(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """xóa dòng rồi list không còn"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(clinic, req(from_uid="u-xoa"))
    assert await store.xoa_friend_request(clinic, "zp-1", "u-xoa") is True
    assert not [r for r in await store.list_friend_requests(clinic, "zp-1") if r.from_uid == "u-xoa"]
    assert await store.xoa_friend_request(clinic, "zp-1", "u-xoa") is False, (
        "xóa dòng đã mất -> False, không ném"
    )


async def test_friend_request_store_list_loc_dung_theo_account_id_hai_account_khong_lan(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """list lọc đúng theo accountId - hai account không lẫn"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(clinic, req(account_id="acc-A", from_uid="x"))
    await store.upsert_friend_request(clinic, req(account_id="acc-B", from_uid="y"))
    rows_a = await store.list_friend_requests(clinic, "acc-A")
    assert all(r.account_id == "acc-A" for r in rows_a)
    assert any(r.from_uid == "x" for r in rows_a)
    assert not any(r.from_uid == "y" for r in rows_a)


async def test_friend_request_store_lay_friend_request_qua_han_tra_dong_received_at_nho_hon_hoac_bang_moc(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """layFriendRequestQuaHan: trả dòng received_at <= mốc (BAO GỒM đúng bằng mốc)"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(
        clinic, req(account_id="acc-qh", from_uid="cu", received_at=T0 + timedelta(seconds=100))
    )
    await store.upsert_friend_request(
        clinic, req(account_id="acc-qh", from_uid="bang", received_at=T0 + timedelta(seconds=200))
    )
    await store.upsert_friend_request(
        clinic, req(account_id="acc-qh", from_uid="moi", received_at=T0 + timedelta(seconds=500))
    )
    rows = await store.lay_friend_request_qua_han(clinic, "acc-qh", T0 + timedelta(seconds=200))
    # 'bang' đúng bằng mốc phải được tính (<=), nếu đổi thành < thì rớt.
    assert [r.from_uid for r in rows] == ["cu", "bang"], (
        "cu(100) + bang(200) quá/đúng hạn; moi(500) chưa; thứ tự theo received_at tăng"
    )


async def test_friend_request_store_enrich_hong_sender_name_avatar_url_null_van_luu_duoc(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """enrich hỏng -> senderName/avatarUrl null vẫn lưu được"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(clinic, req(from_uid="u-null", sender_name=None, avatar_url=None))
    row = next(r for r in await store.list_friend_requests(clinic, "zp-1") if r.from_uid == "u-null")
    assert row.sender_name is None
    assert row.avatar_url is None


async def test_friend_request_store_cap_nhat_ho_so_cap_nhat_ten_avatar_cua_dong_da_co(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """capNhatHoSo cập nhật tên/avatar của dòng đã có"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.upsert_friend_request(
        clinic, req(account_id="acc-cap", from_uid="u", sender_name=None, avatar_url=None)
    )
    await store.cap_nhat_ho_so_friend_request(clinic, "acc-cap", "u", "Hoa", "av")
    row = (await store.list_friend_requests(clinic, "acc-cap"))[0]
    assert row.sender_name == "Hoa"
    assert row.avatar_url == "av"


async def test_friend_request_store_cap_nhat_ho_so_la_update_only_dong_khong_ton_tai_khong_tao_dong_ma(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """capNhatHoSo là UPDATE-only: dòng không tồn tại -> KHÔNG tạo dòng ma"""
    store, clinic = FriendRequestStore(be_db), clinic_ids[0]
    await store.cap_nhat_ho_so_friend_request(clinic, "acc-ma", "u-ma", "X", "y")
    assert len(await store.list_friend_requests(clinic, "acc-ma")) == 0, "update dòng đã mất phải là no-op"


async def test_friend_request_store_hai_phong_kham_khong_thay_dong_cua_nhau(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """row level security: mỗi phòng khám chỉ thấy yêu cầu kết bạn của mình"""
    store = FriendRequestStore(be_db)
    first, second = clinic_ids
    await store.upsert_friend_request(first, req(account_id="zp-1", from_uid="u-rls"))
    assert not [r for r in await store.list_friend_requests(second, "zp-1") if r.from_uid == "u-rls"]
    assert await store.xoa_friend_request(second, "zp-1", "u-rls") is False
    assert [r for r in await store.list_friend_requests(first, "zp-1") if r.from_uid == "u-rls"]

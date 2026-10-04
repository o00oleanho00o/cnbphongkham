# ported from: src/server/routes/friend-routes.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Route ``/admin/friends``. The original used the real store plus a fake ``getApi``; here the real ``AccountManager``
runs over a fake bridge whose ``ZaloApi`` is the recording fake, and the pending requests live in the in-memory
implementation of ``FriendRequestPort`` (the Postgres store has its own tests).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from pema.channels.zalo_personal.friend_request_store import FriendRequestRow
from pema.channels.zalo_personal.service_testing import TestRig, build_test_rig
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import ErrorCode
from pema_contracts.roles import Permission
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config

ClientFactory = Callable[[TestRig], httpx.AsyncClient]
BASE = "/api/v1/admin/friends"
T0 = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)


def row(account: str, uid: str, **fields: object) -> FriendRequestRow:
    base: dict[str, object] = {
        "account_id": account,
        "from_uid": uid,
        "message": "",
        "sender_name": None,
        "avatar_url": None,
        "received_at": T0,
    }
    return FriendRequestRow(**{**base, **fields})  # type: ignore[arg-type]


async def running_rig(*accounts: str) -> TestRig:
    rig = build_test_rig(
        accounts=[fake_account_config(id=a, channel=ChannelKind.ZALO_PERSONAL) for a in accounts]
    )
    for account in accounts:
        config = await rig.accounts.get_account(FAKE_CLINIC_ID, account)
        assert config is not None
        await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")
    return rig


def api_of(rig: TestRig, account: str) -> FakeZaloApi:
    api = rig.bridge.apis[account]
    return api


async def test_friend_routes_get_account_id_requests_tra_dong_da_seed_trong_db(
    make_client: ClientFactory,
) -> None:
    """GET /:accountId/requests trả dòng đã seed trong DB"""
    rig = await running_rig("acc-r")
    await rig.friends.upsert_friend_request(
        FAKE_CLINIC_ID, row("acc-r", "u-seed", message="hi", sender_name="Hoa")
    )
    res = await make_client(rig).get(f"{BASE}/acc-r/requests")

    assert res.status_code == 200
    assert [r["from_uid"] for r in res.json()] == ["u-seed"]
    assert res.json()[0]["sender_name"] == "Hoa"
    assert Permission.ADMIN_ACCOUNTS in rig.asked


async def test_friend_routes_post_accept_goi_accept_friend_request_va_xoa_dong_khoi_db(
    make_client: ClientFactory,
) -> None:
    """POST accept -> gọi acceptFriendRequest + XÓA dòng khỏi DB"""
    rig = await running_rig("acc-a")
    await rig.friends.upsert_friend_request(FAKE_CLINIC_ID, row("acc-a", "u-acc"))

    res = await make_client(rig).post(f"{BASE}/acc-a/accept", json={"uid": "u-acc"})

    assert res.status_code == 200
    assert api_of(rig, "acc-a").accepted == ["u-acc"]
    assert ("acc-a", "u-acc") not in rig.friends.rows, "phải xóa dòng sau accept"
    assert ("friend.accept", "friend_request", "acc-a") in rig.audit.records


async def test_friend_routes_post_reject_goi_reject_friend_request_va_xoa_dong(
    make_client: ClientFactory,
) -> None:
    """POST reject -> gọi rejectFriendRequest + XÓA dòng"""
    rig = await running_rig("acc-rj")
    await rig.friends.upsert_friend_request(FAKE_CLINIC_ID, row("acc-rj", "u-rej"))

    res = await make_client(rig).post(f"{BASE}/acc-rj/reject", json={"uid": "u-rej"})

    assert res.status_code == 200
    assert api_of(rig, "acc-rj").rejected == ["u-rej"]
    assert ("acc-rj", "u-rej") not in rig.friends.rows


async def test_friend_routes_api_null_bot_chua_chay_accept_tra_409_khong_xoa_dong(
    make_client: ClientFactory,
) -> None:
    """api null (bot/chưa chạy) -> accept trả 409, KHÔNG xóa dòng"""
    rig = build_test_rig()
    await rig.friends.upsert_friend_request(FAKE_CLINIC_ID, row("acc-x", "u-x"))

    res = await make_client(rig).post(f"{BASE}/acc-x/accept", json={"uid": "u-x"})

    assert res.status_code == 409
    assert res.json()["error"]["code"] == ErrorCode.INVALID_STATE.value
    assert ("acc-x", "u-x") in rig.friends.rows, "409 thì giữ dòng"


async def test_friend_routes_accept_thieu_from_uid_loi_validate(make_client: ClientFactory) -> None:
    """accept thiếu fromUid -> lỗi 4xx (422 trong API mới, 400 ở bản gốc)"""
    rig = await running_rig("acc-a")
    client = make_client(rig)

    assert (await client.post(f"{BASE}/acc-a/accept", json={})).status_code == 422
    empty = await client.post(f"{BASE}/acc-a/accept", json={"uid": ""})
    assert empty.status_code == 422
    assert api_of(rig, "acc-a").accepted == []


async def test_friend_routes_accept_friend_request_nem_tra_503_khong_xoa_dong(
    make_client: ClientFactory,
) -> None:
    """acceptFriendRequest NÉM -> lỗi, KHÔNG xóa dòng"""
    rig = await running_rig("acc-e")
    await rig.friends.upsert_friend_request(FAKE_CLINIC_ID, row("acc-e", "u-e"))
    api_of(rig, "acc-e").fail_accept_for = {"u-e"}

    res = await make_client(rig).post(f"{BASE}/acc-e/accept", json={"uid": "u-e"})

    assert res.status_code == 503
    assert res.json()["error"]["code"] == ErrorCode.CHANNEL_UNAVAILABLE.value
    assert ("acc-e", "u-e") in rig.friends.rows, "accept hỏng thì giữ dòng"


async def test_friend_routes_get_list_get_all_friends_api_null_409_get_all_friends_nem_503(
    make_client: ClientFactory,
) -> None:
    """GET list -> getAllFriends; api null -> 409; getAllFriends ném -> lỗi"""
    rig = await running_rig("acc-a")
    api = api_of(rig, "acc-a")
    # Trả cả PII để test khẳng định server ĐÃ lược bỏ.
    api.friends = [
        {"userId": "f1", "displayName": "F One", "zaloName": "z1", "phoneNumber": "0000000000", "dob": "1990"}
    ]
    client = make_client(rig)

    ok = await client.get(f"{BASE}/acc-a/list")
    assert ok.status_code == 200
    # Chỉ userId/displayName - phoneNumber/dob PHẢI bị lược bỏ.
    assert ok.json() == [{"user_id": "f1", "display_name": "F One", "avatar_url": None}]
    assert "0000000000" not in ok.text

    assert (await client.get(f"{BASE}/acc-khac/list")).status_code == 409

    async def boom() -> list[dict[str, object]]:
        from pema.channels.zalo_personal.bridge_client import ZaloBridgeError

        raise ZaloBridgeError("transport", "rate limit")

    api.get_all_friends = boom  # type: ignore[method-assign]
    assert (await client.get(f"{BASE}/acc-a/list")).status_code == 503


async def test_friend_routes_khong_dang_nhap_hoac_thieu_quyen_bi_chan_truoc_moi_thao_tac(
    make_client: ClientFactory,
) -> None:
    """(mới) deny by default: lỗi quyền chặn trước khi chạm bridge hoặc DB"""
    rig = await running_rig("acc-a")
    await rig.friends.upsert_friend_request(FAKE_CLINIC_ID, row("acc-a", "u1"))
    client = make_client(rig)

    anonymous = await client.post(
        f"{BASE}/acc-a/accept", json={"uid": "u1"}, headers={"x-test-anonymous": "1"}
    )
    rig.denied.add(Permission.ADMIN_ACCOUNTS)
    forbidden = await client.post(f"{BASE}/acc-a/accept", json={"uid": "u1"})

    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert api_of(rig, "acc-a").accepted == []
    assert ("acc-a", "u1") in rig.friends.rows

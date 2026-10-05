"""``POST /webhooks/zalo-bridge/{account_id}``: HMAC first, then the event dispatch (new module)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from pema.channels.zalo_personal.bridge_signing import compute_signature
from pema.channels.zalo_personal.friend_request_store import FriendRequestRow
from pema.channels.zalo_personal.service_testing import BRIDGE_SECRET, TestRig, build_test_rig
from pema_contracts.admin import BridgeState
from pema_contracts.channel import ChannelKind
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config

ClientFactory = Callable[[TestRig], httpx.AsyncClient]
ACC = "zp-1"
URL = f"/api/v1/webhooks/zalo-bridge/{ACC}"


def signed(
    body: dict[str, object], *, secret: str = BRIDGE_SECRET, age: int = 0
) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body, separators=(",", ":")).encode()
    ts = int(time.time()) - age
    return raw, {
        "content-type": "application/json",
        "x-pema-timestamp": str(ts),
        "x-pema-signature": compute_signature(secret, ts, raw),
    }


def message_event(text: str = "chào bot", msg_id: str = "m1") -> dict[str, object]:
    return {
        "type": "message",
        "self_id": "self-1",
        "message": {
            "threadId": "t1",
            "type": 0,
            "isSelf": False,
            "data": {
                "content": text,
                "uidFrom": "user-1",
                "dName": "Hải",
                "msgId": msg_id,
                "cliMsgId": f"c-{msg_id}",
                "idTo": "self-1",
                "ts": str(int(time.time() * 1000)),
            },
        },
    }


def rig_with_account(**kwargs: object) -> TestRig:
    rig = build_test_rig(accounts=[fake_account_config(id=ACC, channel=ChannelKind.ZALO_PERSONAL)], **kwargs)  # type: ignore[arg-type]
    rig.bridge.states[ACC] = "connected"
    return rig


async def test_chu_ky_hop_le_thi_tin_nhan_duoc_ghi_va_xep_hang(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, headers = signed(message_event())

    res = await make_client(rig).post(URL, content=raw, headers=headers)

    assert res.status_code == 200
    assert res.json() == {"ok": True, "duplicate": False}
    assert [b.msg.text for b in rig.batched] == ["chào bot"]
    assert rig.batched[0].thread_key == f"{ACC}:t1"
    assert rig.conversation.contents(ACC, "t1") == [("user", "chào bot")]


async def test_chu_ky_sai_bi_tu_choi_401_va_khong_chay_gi(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, headers = signed(message_event(), secret="another-secret-0123456789")

    res = await make_client(rig).post(URL, content=raw, headers=headers)

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "channel_webhook_rejected"
    assert rig.batched == []
    assert rig.conversation.messages == []


async def test_timestamp_cu_qua_5_phut_bi_tu_choi_chong_phat_lai(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, headers = signed(message_event(), age=3600)
    res = await make_client(rig).post(URL, content=raw, headers=headers)
    assert res.status_code == 401
    assert rig.batched == []


async def test_khong_co_header_chu_ky_bi_tu_choi(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, _ = signed(message_event())
    res = await make_client(rig).post(URL, content=raw, headers={"content-type": "application/json"})
    assert res.status_code == 401


async def test_co_tien_trinh_tat_thi_bridge_bi_tu_choi_503_ke_ca_khi_chu_ky_dung(
    make_client: ClientFactory,
) -> None:
    rig = rig_with_account(flag=False)
    raw, headers = signed(message_event())
    res = await make_client(rig).post(URL, content=raw, headers=headers)
    assert res.status_code == 503
    assert rig.batched == []


async def test_duong_dan_khong_mang_phong_kham_va_duong_dan_cu_khong_con(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    client = make_client(rig)
    raw, headers = signed(message_event())

    ok = await client.post(URL, content=raw, headers=headers)
    old = await client.post(
        f"/api/v1/webhooks/zalo-bridge/{FAKE_CLINIC_ID}/{ACC}", content=raw, headers=headers
    )

    assert ok.status_code == 200
    assert old.status_code in (404, 405)


async def test_bridge_gui_lai_cung_mot_tin_thi_chi_xu_ly_mot_lan(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    client = make_client(rig)
    raw, headers = signed(message_event(msg_id="dup-1"))

    first = await client.post(URL, content=raw, headers=headers)
    second = await client.post(URL, content=raw, headers=headers)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert len(rig.batched) == 1
    assert len(rig.conversation.messages) == 1


async def test_tin_cho_account_khong_chay_duoc_bi_bo_nhung_van_ack(make_client: ClientFactory) -> None:
    rig = build_test_rig()  # no such account
    raw, headers = signed(message_event())
    res = await make_client(rig).post(URL, content=raw, headers=headers)
    assert res.status_code == 200
    assert rig.batched == []


async def test_credential_updated_duoc_luu_ma_hoa_khong_ro(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, headers = signed(
        {"type": "credential_updated", "credential": {"cookie": [], "imei": "imei-9", "userAgent": "ua"}}
    )

    res = await make_client(rig).post(URL, content=raw, headers=headers)

    assert res.status_code == 200
    stored = rig.accounts.credentials[(FAKE_CLINIC_ID, ACC)]
    assert stored is not None
    assert stored.startswith("enc:"), "đi qua vault: không bao giờ lưu rõ"
    assert await rig.services.vault.load_credentials(FAKE_CLINIC_ID, ACC) == {
        "cookie": [],
        "imei": "imei-9",
        "userAgent": "ua",
    }


async def test_friend_event_request_luu_yeu_cau_ket_ban(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    raw, headers = signed(
        {
            "type": "friend_event",
            "event": {
                "kind": "request",
                "thread_id": "me",
                "is_self": False,
                "data": {"fromUid": "u-new", "toUid": "me", "message": "xin chào"},
            },
        }
    )

    res = await make_client(rig).post(URL, content=raw, headers=headers)

    assert res.status_code == 200
    row = rig.friends.rows[(ACC, "u-new")]
    assert row.message == "xin chào"
    assert isinstance(row, FriendRequestRow)
    assert row.received_at <= datetime.now(UTC)


async def test_account_state_bi_khoa_bat_kill_switch_roi_kenh_khoi_so_va_bao_cho_job_chuyen_gui_tay(
    make_client: ClientFactory,
) -> None:
    """khi bị khóa/đăng xuất thì báo BE để job chuyển trạng thái 'gửi tay'"""
    rig = rig_with_account()
    config = await rig.accounts.get_account(FAKE_CLINIC_ID, ACC)
    assert config is not None
    await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")
    assert rig.registry.get_running(FAKE_CLINIC_ID, ACC) is not None
    raw, headers = signed({"type": "account_state", "state": "blocked", "reason": "send_rejected_repeatedly"})

    res = await make_client(rig).post(URL, content=raw, headers=headers)

    assert res.status_code == 200
    state = rig.settings.rows[ChannelKind.ZALO_PERSONAL]
    assert state.bridge_state is BridgeState.BLOCKED
    assert state.kill_switch_on is True
    assert state.kill_switch_reason == "bridge_blocked"
    assert rig.registry.get_running(FAKE_CLINIC_ID, ACC) is None, "kênh bị gỡ khỏi sổ"
    assert rig.bridge.kill_switch is not None
    assert rig.bridge.kill_switch.on is True, "và bridge cũng được báo ngay"
    assert rig.listeners_called == [(FAKE_CLINIC_ID, ACC, "blocked")]


async def test_account_state_dang_xuat_can_quet_lai_qr_va_ket_noi_lai_khong_tat_kill_switch(
    make_client: ClientFactory,
) -> None:
    rig = rig_with_account()
    client = make_client(rig)

    raw, headers = signed({"type": "account_state", "state": "logged_out", "reason": "revoked"})
    await client.post(URL, content=raw, headers=headers)
    assert rig.settings.rows[ChannelKind.ZALO_PERSONAL].bridge_state is BridgeState.AWAITING_QR
    assert rig.settings.rows[ChannelKind.ZALO_PERSONAL].kill_switch_reason == "bridge_logged_out"

    raw, headers = signed({"type": "account_state", "state": "connected", "reason": "ok"})
    await client.post(URL, content=raw, headers=headers)
    after = rig.settings.rows[ChannelKind.ZALO_PERSONAL]
    assert after.bridge_state is BridgeState.CONNECTED
    assert after.kill_switch_on is True, "một người quyết định khi nào gửi lại"


async def test_su_kien_la_hoac_trang_thai_la_duoc_bo_qua_khong_loi(make_client: ClientFactory) -> None:
    rig = rig_with_account()
    client = make_client(rig)
    bodies: list[dict[str, object]] = [
        {"type": "something_new"},
        {"type": "account_state", "state": "weird"},
        {"nothing": 1},
    ]
    for body in bodies:
        raw, headers = signed(body)
        assert (await client.post(URL, content=raw, headers=headers)).status_code == 200
    assert rig.batched == []

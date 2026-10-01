# ported from: src/server/routes/account-routes.ts
"""``/admin/accounts``: create, update, delete, QR login. The original had no test file for these routes; the cases
pin the safety rules of the port (channel fixed at creation, closed allowlist for a new Bot account, secondary-account
defaults, credential deleted with the account, QR only for personal accounts and only when the flag and the clinic
switch are on, audit on every mutation)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from pema.channels.zalo_personal.bridge_client import BridgeQrStatus
from pema.channels.zalo_personal.service_testing import TestRig, build_test_rig
from pema_contracts.channel import ChannelKind
from pema_contracts.roles import Permission
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config

ClientFactory = Callable[[TestRig], httpx.AsyncClient]
BASE = "/api/v1/admin/accounts"


def personal(account_id: str = "zp-1", **fields: object):  # type: ignore[no-untyped-def]
    return fake_account_config(id=account_id, channel=ChannelKind.ZALO_PERSONAL, **fields)  # type: ignore[arg-type]


async def test_tao_tai_khoan_ca_nhan_mac_dinh_patient_channel_va_chua_chay(
    make_client: ClientFactory,
) -> None:
    rig = build_test_rig()
    res = await make_client(rig).post(BASE, json={"id": "zp-1", "label": "Phụ 1"})

    assert res.status_code == 201
    body = res.json()
    assert body["channel"] == "zalo_personal"
    assert body["policy_profile"] == "patient_channel", "fail safe: mọi tin ra khách đều qua người duyệt"
    assert (body["running"], body["has_credentials"]) == (False, False)
    assert ("account.create", "account", "zp-1") in rig.audit.records
    assert Permission.ADMIN_ACCOUNTS in rig.asked


async def test_tao_tai_khoan_bot_bat_dau_voi_danh_sach_cho_phep_dong(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    res = await make_client(rig).post(BASE, json={"id": "bot-1", "label": "Bot", "channel": "zalo_bot"})

    assert res.status_code == 201
    assert res.json()["allowlist"] == {"mode": "list", "user_ids": []}, "ai có link cũng nhắn được nếu mở sẵn"


async def test_tao_trung_id_la_409_va_agent_khong_ton_tai_la_422(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    client = make_client(rig)

    duplicate = await client.post(BASE, json={"id": "zp-1", "label": "x"})
    bad_agent = await client.post(BASE, json={"id": "zp-2", "label": "x", "agent_id": "khong-co"})

    assert duplicate.status_code == 409
    assert bad_agent.status_code == 422
    assert await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-2") is None


async def test_id_phai_la_kebab_case(make_client: ClientFactory) -> None:
    res = await make_client(build_test_rig()).post(BASE, json={"id": "Bad_Id", "label": "x"})
    assert res.status_code == 422


async def test_list_tra_trang_thai_chay_va_has_credentials_khong_bao_gio_tra_credential(
    make_client: ClientFactory,
) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    await rig.services.vault.save_credentials(
        FAKE_CLINIC_ID, "zp-1", {"cookie": [], "imei": "SECRET-IMEI", "userAgent": "u"}
    )
    config = await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1")
    assert config is not None
    await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")

    res = await make_client(rig).get(BASE)

    assert res.status_code == 200
    [account] = res.json()
    assert (account["running"], account["has_credentials"]) == (True, True)
    assert "SECRET-IMEI" not in res.text
    assert "credential" not in account


async def test_reaction_icons_la_nguon_duy_nhat_o_server(make_client: ClientFactory) -> None:
    res = await make_client(build_test_rig()).get(f"{BASE}/reaction-icons")
    assert res.status_code == 200
    assert [i["key"] for i in res.json()][:3] == ["heart", "like", "haha"]


async def test_patch_chan_icon_la_va_tool_la(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    client = make_client(rig)

    bad_icon = await client.patch(f"{BASE}/zp-1", json={"auto_react_icon": "khong-co"})
    bad_tool = await client.patch(f"{BASE}/zp-1", json={"disabled_tools": ["cong-cu-la"]})
    good = await client.patch(
        f"{BASE}/zp-1", json={"auto_react_icon": "rose", "disabled_tools": ["web_search"]}
    )

    assert (bad_icon.status_code, bad_tool.status_code, good.status_code) == (422, 422, 200)
    assert good.json()["auto_react_icon"] == "rose"
    assert ("account.update", "account", "zp-1") in rig.audit.records


async def test_patch_tat_account_dang_chay_dung_listener_ngay(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    config = await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1")
    assert config is not None
    await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")

    res = await make_client(rig).patch(f"{BASE}/zp-1", json={"enabled": False})

    assert res.status_code == 200
    assert res.json()["running"] is False
    assert "zp-1" in rig.bridge.stopped


async def test_patch_bat_account_chua_quet_qr_khong_loi_nhung_van_chua_chay(
    make_client: ClientFactory,
) -> None:
    """start fail (chưa login QR) không phải lỗi của PATCH"""
    rig = build_test_rig(accounts=[personal("zp-1", enabled=False)])
    res = await make_client(rig).patch(f"{BASE}/zp-1", json={"enabled": True})

    assert res.status_code == 200
    assert res.json()["running"] is False
    assert rig.bridge.started == [], "không có credential thì bridge không bị đụng tới"


async def test_patch_account_khong_ton_tai_la_404(make_client: ClientFactory) -> None:
    res = await make_client(build_test_rig()).patch(f"{BASE}/khong-co", json={"label": "x"})
    assert res.status_code == 404


async def test_xoa_account_dung_listener_xoa_credential_va_ghi_audit(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    await rig.services.vault.save_credentials(
        FAKE_CLINIC_ID, "zp-1", {"cookie": [], "imei": "i", "userAgent": "u"}
    )
    config = await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1")
    assert config is not None
    await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")

    res = await make_client(rig).delete(f"{BASE}/zp-1")

    assert res.status_code == 204
    assert await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1") is None
    assert await rig.services.vault.has_credentials(FAKE_CLINIC_ID, "zp-1") is False, "không giữ chìa khóa"
    assert "zp-1" in rig.bridge.stopped
    assert ("account.delete", "account", "zp-1") in rig.audit.records
    assert (await make_client(rig).delete(f"{BASE}/zp-1")).status_code == 404


async def test_dang_nhap_qr_chi_cho_tai_khoan_ca_nhan(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[fake_account_config(id="bot-1", channel=ChannelKind.ZALO_BOT)])
    res = await make_client(rig).post(f"{BASE}/bot-1/login")
    assert res.status_code == 422
    assert rig.bridge.qr_started == []


async def test_dang_nhap_qr_can_ca_co_tien_trinh_va_cong_tac_phong_kham(make_client: ClientFactory) -> None:
    flag_off = build_test_rig(accounts=[personal("zp-1")], flag=False)
    switch_off = build_test_rig(accounts=[personal("zp-1")], channel_enabled=False)

    assert (await make_client(flag_off).post(f"{BASE}/zp-1/login")).status_code == 503
    assert (await make_client(switch_off).post(f"{BASE}/zp-1/login")).status_code == 503
    assert flag_off.bridge.qr_started == switch_off.bridge.qr_started == []


async def test_dang_nhap_qr_luong_chuan_tu_quet_den_thanh_cong_va_kenh_vao_so(
    make_client: ClientFactory,
) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    rig.bridge.states["zp-1"] = "connected"
    rig.bridge.qr_answers = [
        BridgeQrStatus(state="starting"),
        BridgeQrStatus(state="waiting_scan", qr_png_base64="QRDATA"),
        BridgeQrStatus(state="scanned"),
        BridgeQrStatus(state="success"),
    ]
    client = make_client(rig)

    started = await client.post(f"{BASE}/zp-1/login")
    assert started.status_code == 202
    assert started.json()["state"] == "waiting_scan"
    assert ("account.qr_login_start", "account", "zp-1") in rig.audit.records

    status: dict[str, object] = {}
    for _ in range(50):
        status = (await client.get(f"{BASE}/zp-1/login/status")).json()
        if status["state"] == "success":
            break
        await asyncio.sleep(0.01)
    assert status["state"] == "success"
    assert status["qr_png_base64"] is None, "QR bị xóa sau khi xong"
    assert rig.registry.get_running(FAKE_CLINIC_ID, "zp-1") is not None, "login xong gắn thẳng vào sổ"


async def test_trang_thai_qr_idle_khi_chua_bat_dau_va_khong_lo_anh_qr_sang_phien_khac(
    make_client: ClientFactory,
) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    res = await make_client(rig).get(f"{BASE}/zp-1/login/status")
    assert res.json() == {"state": "idle", "qr_png_base64": None, "detail": None}


async def test_thieu_quyen_hoac_chua_dang_nhap_bi_chan(make_client: ClientFactory) -> None:
    rig = build_test_rig(accounts=[personal("zp-1")])
    client = make_client(rig)
    rig.denied.add(Permission.ADMIN_ACCOUNTS)

    assert (await client.get(BASE)).status_code == 403
    assert (await client.delete(f"{BASE}/zp-1")).status_code == 403
    assert (await client.get(BASE, headers={"x-test-anonymous": "1"})).status_code == 401
    assert await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1") is not None

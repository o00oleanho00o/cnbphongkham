"""``/admin/channels``: the flag, the daily cap, and the kill switch (instant, audited, pushed to the bridge)."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from pema.channels.zalo_personal.service_testing import TestRig, build_test_rig
from pema_contracts.channel import ChannelKind
from pema_contracts.roles import Permission
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config

ClientFactory = Callable[[TestRig], httpx.AsyncClient]
BASE = "/api/v1/admin/channels"


async def test_list_tra_du_ba_kenh_kenh_chua_co_hang_mac_dinh_tat(make_client: ClientFactory) -> None:
    rig = build_test_rig(channel_enabled=False)
    res = await make_client(rig).get(BASE)

    assert res.status_code == 200
    channels = {c["channel"]: c for c in res.json()}
    assert set(channels) == {"zalo_bot", "zalo_personal", "zalo_oa"}
    assert channels["zalo_personal"]["enabled"] is False
    assert channels["zalo_personal"]["kill_switch_on"] is False
    assert channels["zalo_personal"]["version"] == 0
    assert channels["zalo_bot"]["bridge_state"] is None, "bridge_state chỉ có nghĩa với kênh cá nhân"


async def test_kill_switch_bat_ngay_ghi_audit_va_bao_cho_bridge(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    client = make_client(rig)

    res = await client.post(f"{BASE}/zalo_personal/kill-switch", json={"on": True, "reason": "khẩn cấp"})

    assert res.status_code == 200
    body = res.json()
    assert (body["kill_switch_on"], body["kill_switch_reason"]) == (True, "khẩn cấp")
    assert body["kill_switch_changed_at"] is not None
    assert ("channel.kill_switch", ChannelKind.ZALO_PERSONAL) in rig.settings.audit
    assert rig.bridge.kill_switch is not None
    assert (rig.bridge.kill_switch.on, rig.bridge.kill_switch.reason) == (True, "khẩn cấp")
    assert Permission.ADMIN_KILL_SWITCH in rig.asked

    off = await client.post(f"{BASE}/zalo_personal/kill-switch", json={"on": False})
    assert off.json()["kill_switch_on"] is False
    assert rig.bridge.kill_switch.on is False


async def test_kill_switch_van_luu_khi_bridge_khong_lien_lac_duoc(make_client: ClientFactory) -> None:
    rig = build_test_rig()

    async def broken(state: object) -> None:
        raise RuntimeError("bridge down")

    rig.bridge.set_kill_switch = broken  # type: ignore[method-assign]
    res = await make_client(rig).post(f"{BASE}/zalo_personal/kill-switch", json={"on": True})

    assert res.status_code == 200
    assert res.json()["kill_switch_on"] is True, "DB là nguồn thật: mọi tiến trình đọc lại ở tin kế tiếp"


async def test_kill_switch_kenh_khac_khong_dung_den_bridge(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    res = await make_client(rig).post(f"{BASE}/zalo_bot/kill-switch", json={"on": True})
    assert res.status_code == 200
    assert rig.bridge.kill_switch is None


async def test_kill_switch_can_quyen_rieng_va_bi_chan_khi_thieu(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    rig.denied.add(Permission.ADMIN_KILL_SWITCH)
    client = make_client(rig)

    res = await client.post(f"{BASE}/zalo_personal/kill-switch", json={"on": True})

    assert res.status_code == 403
    assert rig.settings.rows[ChannelKind.ZALO_PERSONAL].kill_switch_on is False
    assert rig.bridge.kill_switch is None
    # quyền đọc cài đặt kênh vẫn là quyền khác
    assert (await client.get(BASE)).status_code == 200


async def test_put_khoa_lac_quan_version_cu_la_409(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    client = make_client(rig)

    ok = await client.put(f"{BASE}/zalo_personal", json={"version": 1, "daily_cap": 5})
    stale = await client.put(f"{BASE}/zalo_personal", json={"version": 1, "daily_cap": 6})

    assert ok.status_code == 200
    assert ok.json()["daily_cap"] == 5
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


async def test_tat_co_kenh_dung_moi_account_ngay_lap_tuc(make_client: ClientFactory) -> None:
    """flag `enabled` là công tắc 'tắt là không còn lưu lượng nào'"""
    rig = build_test_rig(accounts=[fake_account_config(id="zp-1", channel=ChannelKind.ZALO_PERSONAL)])
    config = await rig.accounts.get_account(FAKE_CLINIC_ID, "zp-1")
    assert config is not None
    await rig.services.manager.attach_account(FAKE_CLINIC_ID, config, "self-1")

    res = await make_client(rig).put(f"{BASE}/zalo_personal", json={"version": 1, "enabled": False})

    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert rig.bridge.stop_all_calls == 1
    assert rig.registry.get_running(FAKE_CLINIC_ID, "zp-1") is None


async def test_get_mot_kenh_tra_dung_hang(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    res = await make_client(rig).get(f"{BASE}/zalo_personal")
    assert res.status_code == 200
    assert res.json()["channel"] == "zalo_personal"
    assert res.json()["enabled"] is True


async def test_chua_dang_nhap_la_401(make_client: ClientFactory) -> None:
    rig = build_test_rig()
    anonymous = await make_client(rig).get(BASE, headers={"x-test-anonymous": "1"})
    assert anonymous.status_code == 401

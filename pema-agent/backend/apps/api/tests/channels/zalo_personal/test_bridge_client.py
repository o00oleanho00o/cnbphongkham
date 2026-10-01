"""``HttpBridgeClient`` against a fake bridge (``httpx.MockTransport``): signing, wire shape and error mapping."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from pema.channels.zalo_personal.bridge_client import HttpBridgeClient, KillSwitchState, ZaloBridgeError
from pema.channels.zalo_personal.bridge_signing import verify_signature
from pema_contracts.channel import QuoteRef, TextStyle, ThreadKind

SECRET = "synthetic-bridge-secret-0123456789"


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], seen: list[httpx.Request] | None = None
) -> HttpBridgeClient:
    def wrapper(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(base_url="http://bridge.invalid", transport=httpx.MockTransport(wrapper))
    return HttpBridgeClient("http://bridge.invalid", SECRET, client=http)


def ok(**fields: object) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, **fields})


async def test_moi_request_duoc_ky_hmac_va_bridge_xac_thuc_duoc() -> None:
    seen: list[httpx.Request] = []
    client = make_client(lambda r: ok(msg_id="1"), seen)
    api = client.account_api("acc-1", "self-1")

    await api.send_message(text="xin chào", thread_id="t1", thread_type=ThreadKind.USER)

    request = seen[0]
    assert verify_signature(SECRET, dict(request.headers), request.content)
    assert request.url.path == "/v1/accounts/acc-1/send"


async def test_send_message_chi_dinh_styles_va_quote_khi_co_va_mentions_khi_khong_rong() -> None:
    seen: list[httpx.Request] = []
    client = make_client(lambda r: ok(msg_id="1"), seen)
    api = client.account_api("acc-1")
    quote = QuoteRef(msg_id="m1", cli_msg_id="c1", sender_id="u1", raw={"msgId": "m1", "uidFrom": "u1"})

    await api.send_message(text="a", thread_id="t", thread_type=ThreadKind.GROUP, proactive=True)
    await api.send_message(
        text="b",
        thread_id="t",
        thread_type=ThreadKind.GROUP,
        styles=[TextStyle(start=0, length=1, style="b")],
        quote=quote,
        mentions=[{"pos": 0, "uid": "u2", "len": 3}],
    )

    plain, rich = (json.loads(r.content) for r in seen)
    assert set(plain) == {"thread_id", "thread_type", "text", "proactive"}, "không đính styles/quote rỗng"
    assert plain["thread_type"] == 1
    assert plain["proactive"] is True
    assert rich["styles"] == [{"start": 0, "len": 1, "st": "b"}]
    assert rich["quote"] == {"msgId": "m1", "uidFrom": "u1"}
    assert rich["mentions"] == [{"pos": 0, "uid": "u2", "len": 3}]


async def test_loi_may_chu_zalo_giu_ma_so_de_pipeline_biet_la_bi_tu_choi() -> None:
    client = make_client(
        lambda r: httpx.Response(
            502, json={"ok": False, "error": {"kind": "zalo_rejected", "message": "x", "code": 112}}
        )
    )
    with pytest.raises(ZaloBridgeError) as info:
        await client.account_api("acc-1").send_message(text="a", thread_id="t", thread_type=ThreadKind.USER)
    assert (info.value.kind, info.value.code) == ("zalo_rejected", 112)


async def test_loi_chan_cua_bridge_khong_co_ma_so_nen_khong_bi_gui_lai() -> None:
    client = make_client(
        lambda r: httpx.Response(409, json={"ok": False, "error": {"kind": "kill_switch", "message": "x"}})
    )
    with pytest.raises(ZaloBridgeError) as info:
        await client.account_api("acc-1").send_message(text="a", thread_id="t", thread_type=ThreadKind.USER)
    assert info.value.kind == "kill_switch"
    assert info.value.code is None


async def test_loi_mang_la_transport_khong_co_ma_so() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ZaloBridgeError) as info:
        await make_client(boom).account_api("acc-1").send_typing_event("t", ThreadKind.USER)
    assert (info.value.kind, info.value.code) == ("transport", None)


async def test_tra_loi_khong_phai_json_la_loi_transport() -> None:
    client = make_client(lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(ZaloBridgeError) as info:
        await client.get_state("acc-1")
    assert info.value.kind == "transport"


async def test_start_account_gui_credential_trong_body_da_ky_va_nhan_own_id() -> None:
    seen: list[httpx.Request] = []
    client = make_client(lambda r: ok(own_id="self-9"), seen)

    own = await client.start_account(
        "acc-1",
        clinic_slug="clinic-1",
        credential={"cookie": [], "imei": "i", "userAgent": "u"},
        kill_switch=KillSwitchState(on=True, scope="proactive", reason="r"),
    )

    assert own == "self-9"
    body = json.loads(seen[0].content)
    assert body["clinic_slug"] == "clinic-1"
    assert body["credential"]["imei"] == "i"
    assert body["kill_switch"] == {"on": True, "scope": "proactive", "reason": "r"}
    assert verify_signature(SECRET, dict(seen[0].headers), seen[0].content)


async def test_get_all_friends_chi_lay_dong_hop_le_va_get_user_info_tra_du_lieu() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/friends"):
            return ok(friends=[{"userId": "f1", "displayName": "F"}, "junk"])
        return ok(data={"changed_profiles": {}})

    client = make_client(handler)
    api = client.account_api("acc-1")
    assert await api.get_all_friends() == [{"userId": "f1", "displayName": "F"}]
    assert await api.get_user_info("u1") == {"changed_profiles": {}}


async def test_qr_va_kill_switch_dung_duong_dan() -> None:
    seen: list[httpx.Request] = []
    client = make_client(lambda r: ok(state="waiting_scan", qr_png_base64="QR"), seen)

    status = await client.start_qr_login("acc-1", clinic_slug="c")
    again = await client.get_qr_login("acc-1")
    await client.set_kill_switch(KillSwitchState(on=True, scope="all", reason=None))

    assert (status.state, status.qr_png_base64) == ("waiting_scan", "QR")
    assert again.state == "waiting_scan"
    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/v1/accounts/acc-1/login/qr"),
        ("GET", "/v1/accounts/acc-1/login/qr"),
        ("POST", "/v1/kill-switch"),
    ]

# ported from: src/zalo-bot/bot-account-runner.test.ts
"""Token check gate when a bot account starts.

Two cases must be kept APART, and the first version merged them:

* TOKEN ERROR: no amount of waiting fixes it, someone must enter it again -> RAISE so the account is not
  marked running.
* NETWORK ERROR: heals by itself -> open the polling loop anyway, the backoff does the rest.

The first version computed ``err.http_status ?? int(err.ma_loi)`` and the ``??`` branch was dead code:
``_goi`` always sets ``http_status = res.status`` and Zalo returns errors in the BODY with HTTP 200. Nothing
exercised it: the route test raised a bare ``Error``, not ``LoiZaloBotApi``. These tests therefore use the
REAL client over a fake transport, so they go through the exact error-building path of ``_goi``.

The webhook-mode cases are new (the original only long polled).
"""

from __future__ import annotations

import json

import httpx
import pytest

from pema.channels.zalo_bot.bot_account_runner import WebhookRegistration, chay_tai_khoan_bot
from pema.channels.zalo_bot.testing import FakeBotClient, RouterStack, make_router_stack, mock_client
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi, ZaloBotClient

ACC = "acc-bot"


def envelope_client(body: object, status: int = 200) -> ZaloBotClient:
    """The REAL client with only the transport replaced, so the error is built by ``_goi`` itself."""

    def handle(request: httpx.Request) -> httpx.Response:
        text = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(status, content=text)

    return mock_client(handle, token="123:abc")


async def start(s: RouterStack, client: BotApiClient, webhook: WebhookRegistration | None = None):
    return await chay_tai_khoan_bot(
        clinic_id=s.clinic_id,
        account_id=ACC,
        token="123:abc",
        router=s.router,
        registry=s.registry,
        webhook=webhook,
        client_factory=lambda _token: client,
    )


async def test_token_sai_ok_false_error_code_401_kem_http_200_thi_nem_khong_mo_vong_poll() -> None:
    """TOKEN SAI (ok:false + error_code 401 kèm HTTP 200) thì NÉM, không mở vòng poll"""
    # The REAL shape of Zalo's error. Without raising, the account is marked running, the dashboard shows a
    # green "Running", the polling loop errors every round and the bot is silent forever.
    s = make_router_stack()
    client = envelope_client({"ok": False, "description": "Invalid token", "error_code": 401})
    with pytest.raises(LoiZaloBotApi):
        await start(s, client)
    assert s.registry.get_running(s.clinic_id, ACC) is None, "token sai mà vẫn lên sóng"


async def test_403_trong_than_cung_la_loi_token() -> None:
    """403 trong thân cũng là lỗi token"""
    s = make_router_stack()
    client = envelope_client({"ok": False, "description": "Forbidden", "error_code": 403})
    with pytest.raises(LoiZaloBotApi):
        await start(s, client)


async def test_loi_mang_thi_van_mo_vong_poll_backoff_tu_lo_khong_giet_account_vinh_vien() -> None:
    """LỖI MẠNG thì VẪN mở vòng poll - backoff tự lo, không giết account vĩnh viễn"""
    # A container coming up before DNS is ready is very common. Raising here makes ``start_all`` only log and
    # skip, and nobody schedules a retry.
    s = make_router_stack()

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    client = mock_client(boom, token="123:abc")
    running = await start(s, client)
    assert s.registry.get_running(s.clinic_id, ACC) is running.kenh
    await running.dung()
    assert s.registry.get_running(s.clinic_id, ACC) is None


async def test_404_method_khong_ton_tai_khong_bi_coi_la_loi_token() -> None:
    """404 (method không tồn tại) KHÔNG bị coi là lỗi token"""
    # 13 of 17 methods answer 404 when measured. Blocking here kills every bot account at boot if Zalo drops a
    # side method.
    s = make_router_stack()
    client = envelope_client({"ok": False, "description": "Not Found", "error_code": 404})
    running = await start(s, client)
    await running.dung()


async def test_polling_go_webhook_thua_truoc_khi_poll() -> None:
    """(mới) polling: webhook còn bật thì gỡ trước, vì hai chế độ loại trừ nhau"""
    s = make_router_stack()
    fake = FakeBotClient(webhook_url="https://old.example.test/hook")
    running = await start(s, fake)
    assert fake.deleted_webhooks == 1
    assert running.poll is not None
    await running.dung()
    assert fake.closed is True


async def test_polling_chay_tiep_khi_khong_doc_duoc_webhook_info() -> None:
    """(mới) không đọc được getWebhookInfo thì vẫn chạy tiếp (chỉ cảnh báo)"""
    s = make_router_stack()
    fake = FakeBotClient(webhook_info_error=LoiZaloBotApi("x", "getWebhookInfo", 200, 404))
    running = await start(s, fake)
    assert running.poll is not None
    await running.dung()


async def test_che_do_webhook_dang_ky_url_va_secret_va_khong_poll() -> None:
    """(mới) webhook: setWebhook(url, secret), không mở vòng poll, channel verify đúng secret"""
    s = make_router_stack()
    fake = FakeBotClient()
    hook = WebhookRegistration(
        url="https://cskh.example.test/api/v1/webhooks/zalo-bot/demo/acc-bot", secret="x" * 32
    )
    running = await start(s, fake, hook)

    assert fake.set_webhooks == [(hook.url, hook.secret)]
    assert running.poll is None
    assert fake.polls == 0
    assert running.kenh.verify_webhook({"X-Bot-Api-Secret-Token": hook.secret}, b"{}") is True
    assert running.kenh.verify_webhook({"X-Bot-Api-Secret-Token": "sai"}, b"{}") is False
    await running.dung()


async def test_che_do_webhook_dang_ky_that_bai_thi_nem_va_khong_len_song() -> None:
    """(mới) setWebhook bị Zalo từ chối thì ném, không lên sóng"""
    s = make_router_stack()
    client = envelope_client({"ok": False, "description": "url must be https", "error_code": 400})
    # getMe succeeds here? the same envelope answers every method, so getMe fails with 400 (not a token error)
    # and the runner goes on to setWebhook, which fails the same way.
    with pytest.raises(LoiZaloBotApi):
        await start(s, client, WebhookRegistration(url="http://x.test/hook", secret="x" * 32))
    assert s.registry.get_running(s.clinic_id, ACC) is None

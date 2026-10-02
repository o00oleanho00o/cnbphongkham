"""Webhook receiver of the Zalo Bot API (no TypeScript original: zalo-agent only long polled).

Goes through the real FastAPI router and the real ``ZaloBotWebhookService`` with in-memory stores: no network,
no database (the Postgres de-duplication has its own test, ``test_update_dedupe_db``).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from pema.api.deps import API_PREFIX
from pema.api.errors import install_error_handlers
from pema.api.routers import webhooks_zalo_bot
from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.testing import (
    SYNTHETIC_UPDATE,
    FakeBotClient,
    RouterStack,
    make_router_stack,
    next_turn_job,
)
from pema.channels.zalo_bot.webhook import InMemoryUpdateDedupe, ZaloBotWebhookService
from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider

SECRET = "w" * 32
URL = f"{API_PREFIX}/webhooks/zalo-bot/acc-bot"
HEADERS = {"X-Bot-Api-Secret-Token": SECRET}
WRAPPED: dict[str, Any] = {"ok": True, "result": SYNTHETIC_UPDATE}


@pytest.fixture
async def stack() -> RouterStack:
    install_tuning_provider(StaticTuningProvider({"MESSAGE_BATCH_DEBOUNCE_MS": 20}))
    s = make_router_stack()
    s.registry.register(s.clinic_id, ZaloBotChannel(FakeBotClient(), "acc-bot", webhook_secret=SECRET))
    return s


def build_app(s: RouterStack, *, dedupe: InMemoryUpdateDedupe | None = None) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(webhooks_zalo_bot.router, prefix=API_PREFIX)

    app.state.zalo_bot_webhook = ZaloBotWebhookService(
        clinic_id=s.clinic_id,
        registry=s.registry,
        router=s.router,
        dedupe=dedupe or InMemoryUpdateDedupe(),
    )
    return app


@pytest.fixture
async def client(stack: RouterStack) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_app(stack), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await stack.batcher.clear_pending_batches()


async def test_webhook_hop_le_ghi_tin_va_xep_mot_turn_job_khong_chay_turn_trong_request(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """webhook hợp lệ: ghi tin, rồi worker nhận TurnJob qua hàng đợi (lượt không chạy trong request)"""
    res = await client.post(URL, json=WRAPPED, headers=HEADERS)
    assert res.status_code == 200
    assert res.json() == {"ok": True, "duplicate": False}
    assert stack.conversation.contents(stack.clinic_id, "acc-bot", "u-synthetic-1") == ["Xin chào"]
    assert len(stack.inbox.recorded) == 1

    job = await next_turn_job(stack.queue)
    assert job.messages[0].text == "Xin chào"


async def test_webhook_nhan_ca_update_tran_khong_boc_result(client: httpx.AsyncClient) -> None:
    """webhook nhận cả update trần (không bọc {ok,result})"""
    res = await client.post(URL, json=SYNTHETIC_UPDATE, headers=HEADERS)
    assert res.status_code == 200


async def test_sai_secret_bi_tu_choi_401_va_khong_ghi_gi(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """sai secret -> 401 channel_webhook_rejected, không ghi gì"""
    res = await client.post(URL, json=WRAPPED, headers={"X-Bot-Api-Secret-Token": "sai"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "channel_webhook_rejected"
    assert stack.conversation.rows == {}
    assert stack.inbox.recorded == []


async def test_thieu_header_secret_bi_tu_choi(client: httpx.AsyncClient) -> None:
    """thiếu header secret -> 401"""
    assert (await client.post(URL, json=WRAPPED)).status_code == 401


async def test_account_khong_ton_tai_tra_cung_mot_loi_khong_lo_thong_tin(
    client: httpx.AsyncClient,
) -> None:
    """account không tồn tại -> CÙNG 401 và cùng thân như sai secret (endpoint công khai, không lộ gì)"""
    wrong_secret = await client.post(URL, json=WRAPPED, headers={"X-Bot-Api-Secret-Token": "sai"})
    unknown_account = await client.post(
        f"{API_PREFIX}/webhooks/zalo-bot/khong-co", json=WRAPPED, headers=HEADERS
    )
    assert unknown_account.status_code == 401
    assert unknown_account.json() == wrong_secret.json()


async def test_duong_dan_webhook_khong_mang_phong_kham(client: httpx.AsyncClient) -> None:
    """đường dẫn cũ có đoạn phòng khám không còn tồn tại (một bản cài đặt là một phòng khám)"""
    old = await client.post(
        f"{API_PREFIX}/webhooks/zalo-bot/demo-clinic/acc-bot", json=WRAPPED, headers=HEADERS
    )
    assert old.status_code in (404, 405)


async def test_giao_lai_cung_update_id_tra_duplicate_va_khong_ghi_lan_hai(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """Zalo gửi lại cùng update -> duplicate:true, không ghi thêm history/Inbox, không thêm lượt"""
    first = await client.post(URL, json=WRAPPED, headers=HEADERS)
    again = await client.post(URL, json=WRAPPED, headers=HEADERS)
    assert first.json()["duplicate"] is False
    assert again.status_code == 200
    assert again.json() == {"ok": True, "duplicate": True}
    assert stack.conversation.contents(stack.clinic_id, "acc-bot", "u-synthetic-1") == ["Xin chào"]
    assert len(stack.inbox.recorded) == 1


async def test_xu_ly_that_bai_thi_5xx_va_go_dau_da_thay_de_zalo_thu_lai_khong_bi_coi_la_trung(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """lỗi Inbox -> 500 và gỡ dấu đã thấy; lần gửi lại (khi Inbox ổn) được xử lý, không bị nuốt như bản trùng"""
    stack.inbox.fail = True
    failed = await client.post(URL, json=WRAPPED, headers=HEADERS)
    assert failed.status_code == 500
    assert stack.conversation.rows == {}, "chưa ghi history trước khi Inbox ghi được"

    stack.inbox.fail = False
    retry = await client.post(URL, json=WRAPPED, headers=HEADERS)
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is False
    assert stack.conversation.contents(stack.clinic_id, "acc-bot", "u-synthetic-1") == ["Xin chào"]


async def test_hai_giao_hang_dong_thoi_cung_update_chi_mot_cai_duoc_xu_ly(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """hai lần giao ĐỒNG THỜI cùng update: đúng một bên thắng"""
    results = await asyncio.gather(*(client.post(URL, json=WRAPPED, headers=HEADERS) for _ in range(5)))
    assert sorted(r.json()["duplicate"] for r in results) == [False, True, True, True, True]
    assert len(stack.inbox.recorded) == 1


async def test_tin_cua_bot_khac_hoac_than_khong_doc_duoc_thi_ack_2xx_de_zalo_khong_gui_lai(
    stack: RouterStack, client: httpx.AsyncClient
) -> None:
    """tin của bot khác / thân đã xác thực nhưng không đọc được -> 200, không ghi gì"""
    bot_update = {
        "event_name": "message.text.received",
        "message": {
            **SYNTHETIC_UPDATE["message"],
            "from": {"id": "b2", "display_name": "Bot", "is_bot": True},
        },
    }
    assert (
        await client.post(URL, json={"ok": True, "result": bot_update}, headers=HEADERS)
    ).status_code == 200
    unreadable = {"event_name": "message.text.received", "message": "không phải object"}
    assert (await client.post(URL, json=unreadable, headers=HEADERS)).status_code == 200
    assert stack.inbox.recorded == []


async def test_chua_cau_hinh_dich_vu_thi_503_khong_nhan_gi(stack: RouterStack) -> None:
    """chưa nối dịch vụ webhook (app.state trống) -> 503, không nhận update nào"""
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(webhooks_zalo_bot.router, prefix=API_PREFIX)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        res = await http.post(URL, json=WRAPPED, headers=HEADERS)
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "channel_unavailable"

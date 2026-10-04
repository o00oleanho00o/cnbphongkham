# ported from: src/zalo-bot/zalo-bot-api-client.test.ts
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from pema.channels.zalo_bot.zalo_bot_api_client import LoiZaloBotApi, ZaloBotClient

TOKEN = "123456789:token-bi-mat-khong-duoc-lo"


@dataclass
class Fake:
    """A fake transport: records the calls and answers the envelope it was given."""

    status: int = 200
    body: Any = None
    calls: list[tuple[str, Any]] = field(default_factory=list[tuple[str, Any]])

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        def handle(request: httpx.Request) -> httpx.Response:
            self.calls.append((str(request.url), json.loads(request.content) if request.content else None))
            content = self.body if isinstance(self.body, str) else json.dumps(self.body)
            return httpx.Response(self.status, content=content)

        return handle

    def client(self, token: str = TOKEN) -> ZaloBotClient:
        return ZaloBotClient(token, goc_api="https://x.test", transport=httpx.MockTransport(self.handler()))


async def capture(awaitable_factory: Callable[[], Any]) -> BaseException | None:
    try:
        await awaitable_factory()
    except Exception as err:
        return err
    return None


async def test_goi_dung_duong_dan_kieu_telegram_bot_token_method() -> None:
    """gọi đúng đường dẫn kiểu Telegram: /bot{token}/{method}"""
    fake = Fake(body={"ok": True, "result": {"id": "b1"}})
    await fake.client().get_me()
    assert fake.calls[0][0] == f"https://x.test/bot{TOKEN}/getMe"


async def test_token_khong_duoc_lot_vao_thong_diep_loi() -> None:
    """TOKEN không được lọt vào thông điệp lỗi"""

    # The token is in the URL PATH, so every error message that pastes the URL leaks a secret into the log.
    # That is why the client wraps the transport error instead of raising the original.
    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"request to https://x.test/bot{TOKEN}/getMe failed")

    client = ZaloBotClient(TOKEN, goc_api="https://x.test", transport=httpx.MockTransport(boom))
    err = await capture(client.get_me)

    assert isinstance(err, LoiZaloBotApi)
    assert TOKEN not in str(err), f"thông điệp lỗi chứa token: {err}"
    assert err.method == "getMe"
    assert err.__cause__ is None
    assert err.__suppress_context__ is True, "không được xích lỗi gốc (có URL) vào traceback"


async def test_than_json_co_ok_false_thi_nem_du_http_200() -> None:
    """thân JSON có ok:false thì NÉM dù HTTP 200"""
    fake = Fake(status=200, body={"ok": False, "message": "token không hợp lệ"})
    with pytest.raises(LoiZaloBotApi, match="token không hợp lệ"):
        await fake.client().get_me()


async def test_doc_dung_truong_description_hinh_dang_loi_that_cua_zalo() -> None:
    """đọc ĐÚNG trường `description` - hình dạng lỗi THẬT của Zalo"""
    fake = Fake(
        body={"ok": False, "description": "Bad request: The chat_id must not be empty", "error_code": 400}
    )
    err = await capture(fake.client().get_me)
    assert isinstance(err, LoiZaloBotApi)
    assert "chat_id must not be empty" in str(err)
    assert err.ma_loi == 400


async def test_method_khong_ton_tai_404_trong_than_khong_phai_http_404() -> None:
    """method không tồn tại: 404 trong thân, KHÔNG phải HTTP 404"""
    fake = Fake(status=200, body={"ok": False, "description": "Not Found", "error_code": 404})
    err = await capture(fake.client().get_me)
    assert isinstance(err, LoiZaloBotApi)
    assert err.ma_loi == 404


async def test_cong_trung_gian_echo_duong_dan_token_bi_che_khong_lot_vao_thong_diep_loi() -> None:
    """cổng trung gian ECHO đường dẫn: token bị CHE, không lọt vào thông điệp lỗi"""
    fake = Fake(
        status=404,
        body=f"<!DOCTYPE HTML><html><body><p>The requested URL /bot{TOKEN}/getMe was not found on this server.</p></body></html>",
    )
    err = await capture(fake.client().get_me)

    assert isinstance(err, LoiZaloBotApi)
    assert TOKEN not in str(err), f"token lọt vào thông điệp lỗi: {err}"
    assert "<token>" in str(err), "phải thấy dấu vết đã che, không phải cắt mất đoạn"


async def test_than_json_cua_nhanh_hong_cung_bi_che() -> None:
    """thân JSON của nhánh hỏng cũng bị che"""
    fake = Fake(
        body={"ok": False, "description": f"Upstream /bot{TOKEN}/sendMessage refused", "error_code": 502}
    )
    err = await capture(fake.client().get_me)
    assert isinstance(err, LoiZaloBotApi)
    assert TOKEN not in str(err), f"token lọt qua nhánh ok:false: {err}"


async def test_che_duoc_ca_khi_cong_dung_entity_hex_hoac_chi_echo_nua_bi_mat() -> None:
    """che được cả khi cổng dùng entity HEX, hoặc chỉ echo NỬA bí mật"""
    id_, bi_mat = TOKEN.split(":")
    for than in (
        f"<html>Upstream /bot{id_}&#x3a;{bi_mat}/getMe failed</html>",
        f"<html>Auth failure for secret {bi_mat} on this gateway</html>",
    ):
        fake = Fake(status=502, body=than)
        err = await capture(fake.client().get_me)
        assert isinstance(err, LoiZaloBotApi)
        assert bi_mat not in str(err), f"bí mật lọt: {err}"


async def test_che_truoc_khi_cat_moc_200_roi_giua_bi_mat_khong_lam_lot_tien_to() -> None:
    """che TRƯỚC khi cắt - mốc 200 rơi giữa bí mật không làm lọt tiền tố"""
    # A token of its own: the secret must not start with a word of the replacement string ``<token>``.
    token_rieng = "987654321:ZZQuySieuBiMatKhongTrungChuoiChe"
    bi_mat = token_rieng.split(":")[1]
    for dem in (150, 170, 180, 190, 195):
        fake = Fake(status=502, body=f"{'x' * dem} secret {bi_mat} end")
        err = await capture(fake.client(token_rieng).get_me)
        assert isinstance(err, LoiZaloBotApi)
        for n in range(4, len(bi_mat) + 1):
            assert bi_mat[:n] not in str(err), f"đệm {dem}: lọt {n} ký tự đầu của bí mật - {str(err)[:120]}"


async def test_than_khong_phai_json_thi_bao_ro_va_cat_ngan() -> None:
    """thân không phải JSON thì báo rõ và CẮT NGẮN"""
    fake = Fake(status=502, body="<html>" + "x" * 5000 + "</html>")
    err = await capture(fake.client().get_me)
    assert isinstance(err, LoiZaloBotApi)
    assert len(str(err)) < 400, f"thông điệp dài {len(str(err))} ký tự - chưa cắt"
    assert err.http_status == 502


async def test_get_updates_tra_none_khi_het_han_cho_ma_khong_co_tin() -> None:
    """getUpdates trả null khi hết hạn chờ mà không có tin"""
    # Zalo answers an empty envelope, not an empty array like Telegram.
    fake = Fake(body={"ok": True, "result": {}})
    assert await fake.client().get_updates(1) is None


async def test_het_han_cho_408_la_poll_rong_khong_phai_loi() -> None:
    """HẾT HẠN CHỜ (408) là poll RỖNG, không phải lỗi"""
    fake = Fake(status=200, body={"ok": False, "description": "Request timeout", "error_code": 408})
    assert await fake.client().get_updates(1) is None


async def test_408_dang_chuoi_cung_la_poll_rong_error_code_khai_number_hoac_string() -> None:
    """408 dạng CHUỖI cũng là poll rỗng - `error_code` khai number|string"""
    fake = Fake(status=200, body={"ok": False, "description": "Request timeout", "error_code": "408"})
    assert await fake.client().get_updates(1) is None


async def test_loi_that_cua_get_updates_van_nem_ra_khong_nuot_cung_408() -> None:
    """lỗi THẬT của getUpdates vẫn ném ra - không nuốt cùng 408"""
    fake = Fake(status=200, body={"ok": False, "description": "Invalid token", "error_code": 401})
    with pytest.raises(LoiZaloBotApi, match="Invalid token"):
        await fake.client().get_updates(1)


async def test_429_cua_nginx_la_html_khong_phai_json_van_nem_ra_duoc() -> None:
    """429 của nginx là HTML, không phải JSON - vẫn ném ra được"""
    fake = Fake(status=429, body="<html><head><title>429 Too Many Requests</title></head></html>")
    err = await capture(lambda: fake.client().get_updates(1))
    assert isinstance(err, LoiZaloBotApi)
    assert err.http_status == 429


async def test_get_updates_tra_mot_update_khong_phai_mang() -> None:
    """getUpdates trả MỘT update, không phải mảng"""
    fake = Fake(
        body={"ok": True, "result": {"event_name": "message.text.received", "message": {"text": "hi"}}}
    )
    kq = await fake.client().get_updates(1)
    assert kq is not None
    assert kq.event_name == "message.text.received"


async def test_send_message_mac_dinh_khong_xin_server_dung_markdown() -> None:
    """sendMessage mặc định KHÔNG xin server dựng markdown"""
    fake = Fake(body={"ok": True, "result": {"message_id": "m1", "date": 1}})
    await fake.client().send_message("c1", "**đậm**")
    assert fake.calls[0][1] == {"chat_id": "c1", "text": "**đậm**"}


async def test_van_xin_duoc_server_dung_markdown_khi_truyen_tuong_minh() -> None:
    """vẫn xin được server dựng markdown khi truyền tường minh"""
    fake = Fake(body={"ok": True, "result": {"message_id": "m1", "date": 1}})
    await fake.client().send_message("c1", "**đậm**", "markdown")
    assert fake.calls[0][1] == {"chat_id": "c1", "text": "**đậm**", "parse_mode": "markdown"}


async def test_token_bi_che_ke_ca_khi_cong_url_encode_duong_dan() -> None:
    """token bị che kể cả khi cổng URL-ENCODE đường dẫn"""
    id_, bi_mat = TOKEN.split(":")
    fake = Fake(status=502, body=f"<html><body>Upstream /bot{id_}%3A{bi_mat}/getMe timed out</body></html>")
    err = await capture(fake.client().get_me)
    assert isinstance(err, LoiZaloBotApi)
    assert bi_mat not in str(err), f"bí mật lọt qua khi URL-encode: {err}"


async def test_send_photo_bo_han_caption_khi_rong_khong_gui_chuoi_rong() -> None:
    """sendPhoto bỏ hẳn caption khi rỗng, không gửi chuỗi rỗng"""
    fake = Fake(body={"ok": True, "result": {"message_id": "m1", "date": 1}})
    await fake.client().send_photo("c1", "https://anh.test/a.jpg")
    assert fake.calls[0][1] == {"chat_id": "c1", "photo": "https://anh.test/a.jpg"}


async def test_set_webhook_gui_url_va_secret_token() -> None:
    """(mới ở Pema) setWebhook gửi `url` và `secret_token`"""
    fake = Fake(body={"ok": True, "result": {"url": "https://x.test/hook"}})
    await fake.client().set_webhook("https://x.test/hook", "s" * 16)
    assert fake.calls[0][0].endswith("/setWebhook")
    assert fake.calls[0][1] == {"url": "https://x.test/hook", "secret_token": "s" * 16}

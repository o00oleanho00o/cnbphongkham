# ported from: src/zalo-bot/kenh-bot.test.ts
from __future__ import annotations

import asyncio
from typing import cast

from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.testing import SYNTHETIC_UPDATE, FakeBotClient
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.channel import (
    ChannelPort,
    InboundKind,
    MediaChannel,
    QuoteRef,
    ReactionChannel,
    ReadReceiptChannel,
    SendStatus,
    TextStyle,
    ThreadKind,
    TypingChannel,
)
from pema_contracts.errors import ErrorCode

SECRET = "s3cret-token-for-tests"


def channel(client: BotApiClient | None = None) -> tuple[ZaloBotChannel, FakeBotClient]:
    fake = FakeBotClient()
    return ZaloBotChannel(client or fake, "bot-1", webhook_secret=SECRET, typing_refresh_ms=lambda: 10), fake


async def test_khong_xin_server_dung_markdown_chu_toi_day_da_het_markdown_roi() -> None:
    """KHÔNG xin server dựng markdown - chữ tới đây đã hết markdown rồi"""
    # The reply path strips the marks into a ``Style[]``; asking the server to build markdown here could only
    # REMOVE characters (``_`` in file names, ``[`` in source labels), never add anything.
    kenh, client = channel()
    result = await kenh.send_text("c1", "file bao_gia_2026.pdf")
    assert result.status is SendStatus.SENT
    assert client.sent[0][2] is None, "vẫn xin server dựng markdown"
    assert client.sent[0][1] == "file bao_gia_2026.pdf", "chữ bị đổi trên đường gửi"


async def test_vut_styles_va_quote_bot_api_khong_hieu_hai_truong_do() -> None:
    """VỨT styles và quote - Bot API không hiểu hai trường đó"""
    kenh, client = channel()
    await kenh.send_text(
        "c1",
        "chào",
        styles=[TextStyle(start=0, length=4, style="b")],
        quote=QuoteRef(msg_id="m", cli_msg_id="m", sender_id="u"),
    )
    assert len(client.sent) == 1
    assert client.sent[0][:2] == ("c1", "chào")


async def test_khai_tran_2000_ky_tu_cua_bot_api_khong_dung_chung_tran_zca_js() -> None:
    """khai trần 2000 ký tự của Bot API, không dùng chung trần zca-js"""
    # ``ZALO_MAX_MESSAGE_CHARS`` goes up to 4000 on the dashboard. Sharing it would make a widening for the
    # personal channel lose whole bot replies (the server refuses the entire message, measured: 2001
    # characters rejected).
    kenh, client = channel()
    assert kenh.capabilities().max_text_length == 2000
    assert kenh.capabilities().supports_formatting is False
    assert kenh.capabilities().supports_quote is False

    too_long = await kenh.send_text("c1", "x" * 2001)
    assert too_long.status is SendStatus.REJECTED
    assert too_long.error_code is ErrorCode.PAYLOAD_TOO_LARGE
    assert client.sent == [], "không gọi mạng với tin chắc chắn bị từ chối"


async def test_khong_co_bien_nhan_va_tha_cam_xuc_de_trong_chu_khong_dung_stub_nem_loi() -> None:
    """KHÔNG có biên nhận và thả cảm xúc - để trống chứ không dựng stub ném lỗi"""
    kenh, _ = channel()
    assert not isinstance(kenh, ReadReceiptChannel)
    assert not isinstance(kenh, ReactionChannel)
    assert not isinstance(kenh, MediaChannel)
    assert isinstance(kenh, TypingChannel)
    assert isinstance(kenh, ChannelPort)
    assert kenh.capabilities().supports_read_receipt is False
    assert kenh.capabilities().supports_reactions is False


async def test_dau_dang_nhap_ban_ngay_roi_lap_va_dung_that_su_dung() -> None:
    """dấu 'đang nhập': bắn NGAY rồi lặp, và dung() thật sự dừng"""
    kenh, client = channel()
    dung = kenh.start_typing("c1", ThreadKind.USER)
    await doi_cho_den_khi(lambda: len(client.chat_actions) >= 1, WaitOptions(mo_ta="nhịp đầu"))
    await doi_cho_den_khi(lambda: len(client.chat_actions) >= 3, WaitOptions(mo_ta="vòng lặp"))
    dung()
    await asyncio.sleep(0.02)  # a call issued before the stop may still be in flight; it is not a leak
    sau_khi_dung = len(client.chat_actions)
    await asyncio.sleep(0.06)
    assert len(client.chat_actions) == sau_khi_dung, "vẫn bắn sau khi đã dừng - rò rỉ timer"


async def test_send_chat_action_nem_dong_bo_cung_khong_lam_vo_vong() -> None:
    """sendChatAction NÉM ĐỒNG BỘ cũng không làm vỡ vòng"""
    # A ``.catch`` only covers a promise. A raise before the coroutine is returned escapes the timer callback
    # and becomes an uncaught error.
    calls = 0

    class SyncRaises:
        def send_chat_action(self, chat_id: str, action: str = "typing") -> object:
            nonlocal calls
            calls += 1
            raise RuntimeError("hỏng ngay")

    kenh, _ = channel(cast(BotApiClient, SyncRaises()))
    dung = kenh.start_typing("c1", ThreadKind.USER)
    await doi_cho_den_khi(lambda: calls >= 2, WaitOptions(mo_ta="vòng vẫn lặp sau lỗi đồng bộ"))
    dung()


async def test_loi_api_tra_ket_qua_bi_tu_choi_khong_nem_va_khong_chua_noi_dung_tin() -> None:
    """(contract) lỗi API -> SendResult bị từ chối có ErrorCode, không ném ra, không kèm nội dung tin"""
    kenh, client = channel()
    client.send_error = LoiZaloBotApi("sendMessage thất bại: Too many requests", "sendMessage", 200, 429)
    result = await kenh.send_text("c1", "nội dung riêng tư của bệnh nhân")
    assert result.status is SendStatus.REJECTED
    assert result.error_code is ErrorCode.RATE_LIMITED
    assert "riêng tư" not in (result.detail or "")


async def test_verify_webhook_so_sanh_hang_so_khong_phan_biet_hoa_thuong_ten_header_va_fail_closed() -> None:
    """(mới) verify_webhook: header không phân biệt hoa thường; sai/thiếu secret thì False; chưa cấu hình
    secret thì False"""
    kenh, _ = channel()
    assert kenh.verify_webhook({"X-Bot-Api-Secret-Token": SECRET}, b"{}") is True
    assert kenh.verify_webhook({"x-bot-api-secret-token": SECRET}, b"{}") is True
    assert kenh.verify_webhook({"x-bot-api-secret-token": SECRET + "x"}, b"{}") is False
    assert kenh.verify_webhook({}, b"{}") is False

    no_secret = ZaloBotChannel(FakeBotClient(), "bot-1")
    assert no_secret.verify_webhook({"x-bot-api-secret-token": ""}, b"{}") is False


async def test_parse_inbound_nhan_ca_dang_boc_result_cua_webhook_va_bo_qua_tin_khong_phai_nguoi_dung() -> (
    None
):
    """(mới) parse_inbound nhận cả {ok,result} của webhook lẫn update trần; tin của bot khác -> None"""
    kenh, _ = channel()
    bare = kenh.parse_inbound(SYNTHETIC_UPDATE)
    wrapped = kenh.parse_inbound({"ok": True, "result": SYNTHETIC_UPDATE})
    assert bare is not None
    assert wrapped is not None
    assert bare.text == wrapped.text == "Xin chào"
    assert bare.kind is InboundKind.TEXT
    assert kenh.parse_inbound({"event_name": "x"}) is None
    assert kenh.parse_inbound({"event_name": 5, "message": "không phải dict"}) is None

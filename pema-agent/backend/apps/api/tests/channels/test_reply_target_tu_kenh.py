"""``reply_target_tu_kenh`` and the ``oa_api`` stub (``src/zalo/reply-target-tu-kenh.ts`` had no test
upstream)."""

from __future__ import annotations

import pytest

from pema.channels.oa_api import ZaloOaChannel
from pema.channels.reply_target_tu_kenh import DoanCanGui, SendRejectedError, reply_target_tu_kenh
from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.testing import FakeBotClient
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    ChannelPort,
    QuoteRef,
    SendResult,
    SendStatus,
    TextStyle,
    ThreadKind,
)
from pema_contracts.errors import ErrorCode
from pema_contracts.testing import FakeChannel


async def test_reply_target_mang_tran_ky_tu_va_co_dinh_dang_cua_kenh() -> None:
    """chỗ DUY NHẤT biết trường nào của kênh phải đi theo xuống đường gửi"""
    # A missing ``tran_ky_tu_mot_tin`` loses the whole reply on the bot channel (the server refuses the entire
    # message); a missing ``mang_dinh_dang`` budgets bytes for styles about to be dropped.
    target = reply_target_tu_kenh(
        kenh=ZaloBotChannel(FakeBotClient(), "bot-1"),
        thread_id="t1",
        thread_kind=ThreadKind.USER,
        thread_key="k",
    )
    assert target.tran_ky_tu_mot_tin == 2000
    assert target.mang_dinh_dang is False
    assert target.quote is None, "quote do caller thêm: chỉ lượt tin nhắn trong nhóm mới có tin để trích"
    assert (target.thread_key, target.thread_id, target.thread_type) == ("k", "t1", ThreadKind.USER)


async def test_gui_mot_doan_chuyen_text_styles_quote_va_proactive_xuong_kenh() -> None:
    """gui_mot_doan chuyển đủ text/styles/quote/proactive xuống ChannelPort.send_text"""
    channel = FakeChannel(
        caps=ChannelCapabilities(channel=ChannelKind.ZALO_PERSONAL, can_send_proactive=True)
    )
    target = reply_target_tu_kenh(
        kenh=channel, thread_id="t1", thread_kind=ThreadKind.GROUP, thread_key="k", proactive=True
    )
    style = TextStyle(start=0, length=2, style="b")
    quote = QuoteRef(msg_id="m", cli_msg_id="c", sender_id="u")
    await target.gui_mot_doan(DoanCanGui("xin chào", styles=[style], quote=quote))
    sent = channel.sent[0]
    assert (sent.thread_id, sent.text, sent.thread_kind, sent.proactive) == (
        "t1",
        "xin chào",
        ThreadKind.GROUP,
        True,
    )
    assert list(sent.styles) == [style]
    assert sent.quote == quote


async def test_kenh_tu_choi_mot_doan_thi_nem_send_rejected_khong_bi_doc_nhu_da_gui() -> None:
    """kênh trả SendResult bị từ chối -> ném SendRejectedError (đường gửi bản gốc biết lỗi qua exception)"""
    rejected = SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_DAILY_CAP_REACHED)
    channel = FakeChannel(
        caps=ChannelCapabilities(channel=ChannelKind.ZALO_BOT, can_send_proactive=True), reject_with=rejected
    )
    target = reply_target_tu_kenh(kenh=channel, thread_id="t1", thread_kind=ThreadKind.USER, thread_key="k")
    with pytest.raises(SendRejectedError) as raised:
        await target.gui_mot_doan(DoanCanGui("x"))
    assert raised.value.error_code is ErrorCode.CHANNEL_DAILY_CAP_REACHED


async def test_oa_api_la_stub_moi_loi_goi_deu_nem_not_implemented() -> None:
    """oa_api: stub - mọi lời gọi ném NotImplementedError kèm TODO(AI01-OA)"""
    channel = ZaloOaChannel("oa-1")
    assert isinstance(channel, ChannelPort)
    assert channel.kind is ChannelKind.ZALO_OA
    with pytest.raises(NotImplementedError, match="AI01-OA"):
        channel.capabilities()
    with pytest.raises(NotImplementedError):
        channel.verify_webhook({}, b"")
    with pytest.raises(NotImplementedError):
        channel.parse_inbound({})
    with pytest.raises(NotImplementedError):
        await channel.send_text("t", "x")

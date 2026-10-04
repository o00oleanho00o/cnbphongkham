# ported from: src/zalo-bot/luot-tren-kenh-bot.test.ts
"""A turn on a channel that has only 2 of the 5 abilities.

The original ran the REAL ``processBatch`` with a bot channel that lacked ``baoDaXem`` / ``tuThaCamXuc`` and
showed they are skipped quietly instead of throwing. In Pema ``processBatch`` is package C2's
``message_turn_processor`` (the worker side) and the LLM loop is D1's, neither in this worktree, so the
full-turn cases cannot run here (open item for package G).

What this package owes the turn, and is tested here with a minimal turn driver built only from the PUBLIC
pieces a real processor uses: ``capabilities()``, the optional ``TypingChannel``, ``reply_target_tu_kenh`` and
``send_text``.
"""

from __future__ import annotations

import asyncio

from pema.channels.reply_target_tu_kenh import DoanCanGui, reply_target_tu_kenh
from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.testing import FakeBotClient
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.channel import ChannelPort, ReactionChannel, ReadReceiptChannel, ThreadKind, TypingChannel


async def run_minimal_turn(channel: ChannelPort, reply: str) -> None:
    """What a turn does with a channel: typing on/off if offered, receipts/reactions only if offered, send."""
    stop_typing = (
        channel.start_typing("t-luot", ThreadKind.USER) if isinstance(channel, TypingChannel) else None
    )
    try:
        if isinstance(
            channel, ReadReceiptChannel
        ):  # absent on the bot channel: skipped, never a stub that raises
            raise AssertionError("the bot channel must not offer read receipts")
        if isinstance(channel, ReactionChannel):
            raise AssertionError("the bot channel must not offer reactions")
        target = reply_target_tu_kenh(
            kenh=channel, thread_id="t-luot", thread_kind=ThreadKind.USER, thread_key="k-t-luot"
        )
        await target.gui_mot_doan(DoanCanGui(reply))
    finally:
        if stop_typing is not None:
            stop_typing()


async def test_chay_tron_luot_voi_kenh_thieu_3_nang_luc_khong_nem_chu_toi_noi() -> None:
    """chạy trọn lượt với kênh thiếu 3 năng lực - không ném, chữ tới nơi"""
    client = FakeBotClient()
    await run_minimal_turn(ZaloBotChannel(client, "bot-1"), "Chào anh Hải")
    assert [text for _, text, _ in client.sent] == ["Chào anh Hải"], (
        "câu trả lời không tới được đường gửi của kênh"
    )


async def test_dau_dang_nhap_duoc_bat_roi_tat_ke_ca_khi_kenh_thieu_nang_luc_khac() -> None:
    """dấu 'đang nhập' được BẬT rồi TẮT, kể cả khi kênh thiếu năng lực khác"""
    client = FakeBotClient()
    channel = ZaloBotChannel(client, "bot-1", typing_refresh_ms=lambda: 10)
    await run_minimal_turn(channel, "ừ")
    await doi_cho_den_khi(lambda: len(client.chat_actions) >= 1, WaitOptions(mo_ta="đã bật dấu đang nhập"))
    after_stop = len(client.chat_actions)
    # Forgetting to stop leaves "typing" hanging in front of the sender; ``dung`` must have cancelled the
    # timer.
    await asyncio.sleep(0.05)
    assert len(client.chat_actions) == after_stop, "quên tắt là dấu 'đang nhập' treo mãi trước mặt người nhắn"


async def test_luot_van_chay_khi_kenh_khong_co_ca_dang_nhap() -> None:
    """lượt vẫn chạy khi kênh KHÔNG có cả 'đang nhập'"""
    # The most minimal channel possible: only the send path.
    from pema_contracts.channel import ChannelCapabilities, ChannelKind
    from pema_contracts.testing import FakeChannel

    channel = FakeChannel(caps=ChannelCapabilities(channel=ChannelKind.ZALO_BOT, can_send_proactive=False))
    assert not isinstance(channel, TypingChannel)
    await run_minimal_turn(channel, "vẫn chạy")
    assert [p.text for p in channel.sent] == ["vẫn chạy"]

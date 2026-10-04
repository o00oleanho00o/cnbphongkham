# ported from: src/zalo-bot/lich-hen-tren-kenh-bot.test.ts
"""Scheduled messages RUN on a Zalo Bot account, through the three entries that were once blocked (tool,
dashboard, old job in the DB).

The three block layers were never a verdict on the platform: the Bot API can message proactively (measured: 10
messages in 416 ms), but the scheduler was hard wired to the personal-account library, so a bot account had no
send path.

What belongs to this package and is translated: the capability table (``schedule_task`` is allowed, 8
entries), the persona line that must not claim the bot cannot schedule, and the SEND PATH: the scheduler gets
the running channel of an account from the ``ChannelRegistry`` and sends one part proactively; on a bot
account that reaches the Bot API.

Not translated (other packages own the code): creating a schedule from the dashboard route (S,
``admin_schedules``), ``run_scheduled_job`` / ``markRun`` behaviour of ``once`` and ``every`` jobs (S: "the
job keeps its next run after it ran"), and "deleting an account removes its jobs" (D2/S). See the open items
of the C1 report.
"""

from __future__ import annotations

import re
from uuid import UUID

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.nang_luc_kenh_bot import (
    LUAT_PERSONA_KENH_BOT,
    TOOL_KHONG_CHAY_TREN_BOT,
    tool_chay_duoc_tren_bot,
)
from pema.channels.zalo_bot.testing import FakeBotClient
from pema_contracts.channel import SendStatus, ThreadKind

CLINIC = UUID("00000000-0000-4000-8000-000000000001")


def test_schedule_task_co_trong_tool_cua_luot_chat_tren_bot() -> None:
    """`schedule_task` CÓ trong tool của lượt chat trên bot, và trang Tools hiện dùng được"""
    assert "schedule_task" not in TOOL_KHONG_CHAY_TREN_BOT
    assert tool_chay_duoc_tren_bot("schedule_task") is True


def test_bang_chan_cua_kenh_bot_con_dung_8_muc_khong_con_schedule_task() -> None:
    """bảng chặn của kênh bot còn ĐÚNG 8 mục, không còn `schedule_task`"""
    # The number is scattered over the README and the architecture docs: changing it here and forgetting the
    # text makes the docs lie about the product. 7 -> 8 at V3.21: ``tai_video`` was added (no method that
    # sends video).
    assert len(TOOL_KHONG_CHAY_TREN_BOT) == 8
    assert tool_chay_duoc_tren_bot("schedule_task") is True
    assert tool_chay_duoc_tren_bot("send_file") is False


def test_persona_kenh_bot_khong_noi_bot_khong_dat_duoc_lich() -> None:
    """persona kênh bot KHÔNG nói bot không đặt được lịch"""
    # The persona line lists only files/documents/images/reactions/tags/groups. This case guards a FUTURE
    # debt: whoever adds "cannot schedule" there makes the persona lie, and no other test catches a lie of
    # this kind.
    assert re.search(r"lịch|hẹn|schedule", LUAT_PERSONA_KENH_BOT, re.IGNORECASE) is None


async def test_job_cua_tai_khoan_bot_gio_chay_that_qua_registry_va_toi_bot_api() -> None:
    """job CŨ của tài khoản bot giờ CHẠY THẬT: scheduler lấy kênh đang chạy từ registry và gửi chủ động"""
    client = FakeBotClient()
    registry = InMemoryChannelRegistry()
    registry.register(CLINIC, ZaloBotChannel(client, "acc-bot"))

    channel = registry.get_running(CLINIC, "acc-bot")
    assert channel is not None, "tài khoản bot đang chạy phải tìm lại được đúng đối tượng kênh"
    result = await channel.send_text("t1", "nhắc uống nước", thread_kind=ThreadKind.USER, proactive=True)

    assert result.status is SendStatus.SENT
    assert [(chat, text) for chat, text, _ in client.sent] == [("t1", "nhắc uống nước")]
    assert channel.capabilities().can_send_proactive is True


async def test_tai_khoan_bot_da_dung_thi_registry_tra_none_scheduler_giu_slot_va_thu_lai() -> None:
    """tài khoản bot không chạy (chưa token / đã dừng) -> registry trả None (scheduler giữ slot, thử lại tick
    sau)"""
    registry = InMemoryChannelRegistry()
    registry.register(CLINIC, ZaloBotChannel(FakeBotClient(), "acc-bot"))
    registry.unregister(CLINIC, "acc-bot")
    assert registry.get_running(CLINIC, "acc-bot") is None

# ported from: src/zalo-bot/api-ca-nhan-guard.test.ts
"""The invariant that made it SAFE for the personal-account handle to be nullable: on the bot channel, NO tool
that is granted may need a personal-channel ability.

In Python there is no ``ToolContext.api`` handle: a tool reaches the channel through ``ToolContext.channel``
and tests ``isinstance(ctx.channel, MediaChannel)`` (``GroupChannel``, ``ReactionChannel``) for an optional
ability. The original guard therefore becomes: every tool that needs an ability ``ZaloBotChannel`` does NOT
implement is in the block table, and the other way round.

The original compared two HAND WRITTEN lists (one of them a copy of what it checks) and then moved to
measuring by BUILDING the real tool set and reading the source. The real tool set is package D4's, so the
ability each tool needs is declared here once as DATA; D4's tool tests must keep it true (open item in the C1
report).
"""

from __future__ import annotations

import pytest

from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.nang_luc_kenh_bot import TOOL_KHONG_CHAY_TREN_BOT
from pema.channels.zalo_bot.testing import FakeBotClient
from pema_contracts.channel import GroupChannel, MediaChannel, ReactionChannel
from pema_contracts.tools import BUILTIN_TOOL_KEYS

# tool key -> the optional ability of ``pema_contracts.channel`` it needs on the channel.
NEEDS_ABILITY: dict[str, type] = {
    "send_file": MediaChannel,
    "create_word_document": MediaChannel,
    "create_excel_file": MediaChannel,
    "create_image": MediaChannel,
    "tai_video": MediaChannel,
    "add_reaction": ReactionChannel,
    "tag_member": GroupChannel,
    "get_group_info": GroupChannel,
}


@pytest.fixture
def bot_channel() -> ZaloBotChannel:
    return ZaloBotChannel(FakeBotClient(), "bot-1")


def test_kenh_bot_khong_cai_dat_nang_luc_nao_cua_kenh_ca_nhan(bot_channel: ZaloBotChannel) -> None:
    """kênh bot không cài đặt năng lực nào của kênh cá nhân (media, cảm xúc, nhóm)"""
    for ability in (MediaChannel, ReactionChannel, GroupChannel):
        assert not isinstance(bot_channel, ability), ability.__name__


def test_moi_tool_can_nang_luc_ma_kenh_bot_khong_co_deu_nam_trong_bang_chan(
    bot_channel: ZaloBotChannel,
) -> None:
    """MỌI tool cần năng lực kênh bot không có đều nằm trong bảng chặn - và ngược lại"""
    can_nang_luc_vang = {k for k, ability in NEEDS_ABILITY.items() if not isinstance(bot_channel, ability)}
    assert can_nang_luc_vang == set(TOOL_KHONG_CHAY_TREN_BOT), (
        "tool cần năng lực mà bot không có phải bị chặn, và mục bị chặn phải có lý do là thiếu năng lực"
    )


def test_bang_nang_luc_chi_nhac_toi_tool_co_that() -> None:
    """bảng 'tool cần năng lực nào' không chứa key lạ"""
    assert set(NEEDS_ABILITY) <= set(BUILTIN_TOOL_KEYS)


def test_tool_khong_khai_nang_luc_nao_la_tool_thuan_va_khong_bi_chan() -> None:
    """tool không cần năng lực kênh nào thì không bị chặn (không chặn thừa)"""
    for key in BUILTIN_TOOL_KEYS:
        if key not in NEEDS_ABILITY:
            assert key not in TOOL_KHONG_CHAY_TREN_BOT, key

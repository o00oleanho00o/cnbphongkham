# ported from: src/zalo-bot/chan-tool-tren-kenh-bot.test.ts
"""Blocking tools on the bot channel.

The real ``ToolRegistry`` is package D4's and is not in this worktree. The original asserted through its
``listAvailableTools`` / ``kiemTraKhaDung``; here the same assertions run against a SMALL REFERENCE FILTER
built from the contract (``ToolRegistry`` docstring: agent x account x channel, and the channel's
``blocked_tools``), so what is checked is the DATA this package provides
(``ChannelCapabilities.blocked_tools``) and the rule that makes it bite. Package G should run the same cases
against D4's registry (open item in the C1 report).
"""

from __future__ import annotations

from collections.abc import Sequence

from pema.channels.zalo_bot.nang_luc_kenh_bot import TOOL_KHONG_CHAY_TREN_BOT, ZALO_BOT_CAPABILITIES
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.tools import BUILTIN_TOOL_KEYS, ToolAvailability, ToolScope

PERSONAL = ChannelCapabilities(
    channel=ChannelKind.ZALO_PERSONAL, can_send_proactive=True, supports_formatting=True
)


def scope(
    channel: ChannelCapabilities, agent_disabled: Sequence[str] = (), account_disabled: Sequence[str] = ()
) -> ToolScope:
    return ToolScope(
        agent_id="a1",
        agent_disabled_tools=agent_disabled,
        account_disabled_tools=account_disabled,
        channel=channel,
    )


def check_availability(key: str, s: ToolScope) -> ToolAvailability:
    """Reference of ``kiemTraKhaDung`` for the CHANNEL gate and the two disable lists (the config-dependent
    ``available()`` of single tools is deliberately left out, as the original test also measures by REASON).
    """
    hint = s.channel.blocked_tools.get(key)
    if hint is not None:
        return ToolAvailability(usable=False, hint=hint)
    if key in s.agent_disabled_tools or key in s.account_disabled_tools:
        return ToolAvailability(usable=False, hint="tắt trong cấu hình")
    return ToolAvailability(usable=True)


def keys(s: ToolScope) -> list[str]:
    return [k for k in BUILTIN_TOOL_KEYS if check_availability(k, s).usable]


BOT = scope(ZALO_BOT_CAPABILITIES)
CA_NHAN = scope(PERSONAL)


def test_7_tool_dung_kenh_khong_vao_schema_cua_luot_chay_tren_bot() -> None:
    """tool đụng kênh KHÔNG vào schema của lượt chạy trên bot"""
    # This is the real latch: a tool not in this list gets no schema, so the model cannot call it, so cannot
    # promise it.
    tren = keys(BOT)
    for k in TOOL_KHONG_CHAY_TREN_BOT:
        assert k not in tren, f'"{k}" vẫn vào schema trên kênh bot'


def test_kenh_ca_nhan_khong_bi_chan_gi_them_chi_kenh_bot_moi_hep_lai() -> None:
    """kênh cá nhân KHÔNG bị chặn gì thêm - chỉ kênh bot mới hẹp lại"""
    # The guard against "fixing for the bot broke the channel that is running", the costliest regression
    # possible here. Measured by REASON, not by the availability flag: some tools switch themselves off when
    # infrastructure is missing.
    for key, ly in TOOL_KHONG_CHAY_TREN_BOT.items():
        assert check_availability(key, BOT).hint == ly.hint, f'"{key}" phải bị cổng kênh bot chặn'
        assert check_availability(key, CA_NHAN).hint != ly.hint, (
            f'"{key}" bị cổng kênh bot chặn NHẦM trên kênh cá nhân'
        )
    assert PERSONAL.blocked_tools == {}


def test_tool_thuan_van_chay_tren_kenh_bot() -> None:
    """tool thuần vẫn chạy trên kênh bot"""
    tren = keys(BOT)
    for k in ("get_datetime", "web_search", "web_fetch", "save_memory", "kb_search", "schedule_task"):
        assert k in tren, f'"{k}" bị chặn nhầm trên kênh bot'


def test_kenh_bot_hep_hon_kenh_ca_nhan_dung_bang_bang_chan_khong_hon_khong_kem() -> None:
    """kênh bot hẹp hơn kênh cá nhân ĐÚNG bằng bảng chặn, không hơn không kém"""
    # The difference of the two sets over the WHOLE catalogue depends only on the table.
    chan_bot = [k for k in BUILTIN_TOOL_KEYS if k in keys(CA_NHAN) and k not in keys(BOT)]
    assert sorted(chan_bot) == sorted(TOOL_KHONG_CHAY_TREN_BOT)


def test_ly_do_chan_noi_ro_la_gioi_han_zalo_de_dashboard_hien_dung_nguyen_nhan() -> None:
    """lý do chặn nói rõ là giới hạn Zalo, để dashboard hiện đúng nguyên nhân"""
    kq = check_availability("send_file", BOT)
    assert kq.usable is False
    assert "Zalo Bot API" in (kq.hint or "")


def test_gioi_han_nen_tang_thang_ca_khi_tool_duoc_bat_tren_dashboard() -> None:
    """giới hạn nền tảng THẮNG cả khi tool được bật trên dashboard"""
    # The operator enabling "send file" for a bot account will happen: the dashboard does not forbid it.
    # Enabled or not it must fail the same way, so the platform limit wins.
    assert "send_file" not in keys(scope(ZALO_BOT_CAPABILITIES, agent_disabled=[], account_disabled=[]))

# ported from: src/zalo-bot/nang-luc-kenh-bot.test.ts
from __future__ import annotations

import re

from pema.channels.zalo_bot.nang_luc_kenh_bot import (
    LUAT_PERSONA_KENH_BOT,
    TOOL_KHONG_CHAY_TREN_BOT,
    ZALO_BOT_CAPABILITIES,
    tool_chay_duoc_tren_bot,
)
from pema_contracts.tools import BUILTIN_TOOL_KEYS


def test_moi_key_trong_danh_sach_chan_phai_la_tool_co_that() -> None:
    """mọi key trong danh sách chặn PHẢI là tool có thật"""
    # A guard against typos and against a tool whose key was renamed without fixing it here: a typo leaves the
    # tool running on the bot channel and failing in front of the user, with nothing to flag it.
    for key in TOOL_KHONG_CHAY_TREN_BOT:
        assert key in BUILTIN_TOOL_KEYS, f'"{key}" không phải tool có thật trong catalog'


def test_them_tool_moi_phai_quyet_dinh_no_chay_duoc_tren_bot_hay_khong() -> None:
    """THÊM TOOL MỚI phải quyết định nó chạy được trên bot hay không"""
    # Written BY HAND on purpose: a new tool whose bot behaviour nobody considered defaults to "runs",
    # silently wrong. A red test here forces whoever adds a tool to read the capability table and pick a side.
    da_xet = {
        *TOOL_KHONG_CHAY_TREN_BOT,
        # Tools that RUN: listed explicitly so this list cannot grow by itself.
        "get_datetime",
        "web_search",
        "web_fetch",
        "read_image",
        "kb_search",
        "save_memory",
        # Wired to the scheduler at V3.19: the scheduler builds the send path per CHANNEL instead of hard
        # wiring zca-js. The Bot API can message proactively (measured: 10 messages/416 ms).
        "schedule_task",
    }
    chua_xet = [k for k in BUILTIN_TOOL_KEYS if k not in da_xet]
    assert chua_xet == [], f"tool chưa xét cho kênh bot: {', '.join(chua_xet)}"


def test_8_tool_dung_nang_luc_bot_api_khong_co_thi_bi_chan_tool_thuan_thi_khong() -> None:
    """8 tool đụng năng lực Bot API KHÔNG CÓ thì bị chặn, tool thuần thì không"""
    for key in (
        "send_file",
        "create_word_document",
        "create_excel_file",
        "create_image",
        "add_reaction",
        "tag_member",
        "get_group_info",
        # Added at V3.21 with video download: no method that sends video, and the tool is built on
        # ``sendVideo`` of the personal-account library, which the bot channel does not have.
        "tai_video",
    ):
        assert tool_chay_duoc_tren_bot(key) is False, key
    assert len(TOOL_KHONG_CHAY_TREN_BOT) == 8

    # ``schedule_task`` USED to be blocked and was the ONLY entry with no 404 measurement; the real reason was
    # that the scheduler was hard wired to zca-js, fixed at V3.19.
    assert tool_chay_duoc_tren_bot("schedule_task") is True

    assert tool_chay_duoc_tren_bot("kb_search") is True
    assert tool_chay_duoc_tren_bot("web_search") is True


def test_moi_ly_do_phai_noi_duoc_gi_va_mat_gi_khong_chi_khong_ho_tro() -> None:
    """mỗi lý do phải nói ĐƯỢC GÌ và MẤT GÌ, không chỉ 'không hỗ trợ'"""
    for key, ly in TOOL_KHONG_CHAY_TREN_BOT.items():
        assert len(ly.hint) > 30, f"hint của {key} quá ngắn để nói được lý do"
        assert "Zalo Bot API" in ly.hint, f"hint của {key} không nói rõ đây là giới hạn của Zalo"


def test_persona_neu_du_ca_tam_tool_bi_chan_khong_de_model_im_lang_ve_mot_gioi_han() -> None:
    """persona nêu ĐỦ CẢ TÁM tool bị chặn - không để model im lặng về một giới hạn"""
    # What has a test guarding it survives, what depends on someone remembering drifts. The table only SHRINKS
    # over time (Zalo opens a method and one entry goes), it does not grow, so this does not make the prompt
    # grow without limit.
    #
    # Compare MATCH POSITIONS, not patterns: two different patterns can match the same stretch of text, and
    # then the later key only rides on the earlier one.
    chu_can_co = {
        "send_file": r"gửi được file",
        "create_word_document": r"tài liệu Word",
        "create_excel_file": r"Excel",
        "create_image": r"ảnh tự vẽ",
        "tai_video": r"video tải về",
        "add_reaction": r"thả được cảm xúc",
        "tag_member": r"tag được ai",
        "get_group_info": r"danh sách thành viên nhóm",
    }
    assert sorted(chu_can_co) == sorted(TOOL_KHONG_CHAY_TREN_BOT), (
        "bảng chặn đã đổi mà persona chưa theo - model sẽ nói 'không làm được' mà không nói vì sao"
    )

    doan_khop: list[tuple[str, int, int]] = []
    for key, pattern in chu_can_co.items():
        found = re.search(pattern, LUAT_PERSONA_KENH_BOT, re.IGNORECASE)
        assert found is not None, f'persona không nhắc tới giới hạn của "{key}"'
        assert len(found.group(0)) > 0, f'mẫu của "{key}" khớp chuỗi RỖNG - khẳng định rỗng, không đo gì'
        doan_khop.append((key, found.start(), found.end()))
    for a in doan_khop:
        for b in doan_khop:
            if a[0] >= b[0]:
                continue
            assert a[2] <= b[1] or b[2] <= a[1], (
                f'"{a[0]}" và "{b[0]}" khớp CHỒNG LẤN cùng một đoạn chữ - phép đo mất răng'
            )


def test_luat_persona_noi_ro_day_la_gioi_han_nen_tang_khong_phai_agent_hong() -> None:
    """luật persona nói RÕ đây là giới hạn nền tảng, không phải agent hỏng"""
    # Hiding the tool is not enough: the model would say "I cannot" without saying why and the sender would
    # think the agent is broken.
    assert "KHÔNG phải bạn bị lỗi" in LUAT_PERSONA_KENH_BOT
    assert "tài khoản cá nhân" in LUAT_PERSONA_KENH_BOT
    assert re.search(r"file", LUAT_PERSONA_KENH_BOT, re.IGNORECASE)


def test_nang_luc_cua_kenh_la_du_lieu_blocked_tools_va_persona_rule() -> None:
    """(contract) ChannelCapabilities mang đúng bảng chặn và luật persona"""
    assert set(ZALO_BOT_CAPABILITIES.blocked_tools) == set(TOOL_KHONG_CHAY_TREN_BOT)
    assert ZALO_BOT_CAPABILITIES.persona_rule == LUAT_PERSONA_KENH_BOT
    assert ZALO_BOT_CAPABILITIES.can_send_proactive is True

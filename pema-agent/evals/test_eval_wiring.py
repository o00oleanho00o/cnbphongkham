"""The real seams of the eval runner (package G): D4's registry and C2's reply formatting."""

from __future__ import annotations

from evals.eval_wiring import real_format_reply, real_registry
from evals.run_eval import real_wiring
from pema_contracts.tools import BUILTIN_TOOL_KEYS


def test_real_registry_la_registry_cua_d4_voi_du_15_tool() -> None:
    """registry thật của D4 có đủ 15 tool gốc"""
    keys = {spec.key for spec in real_registry().definitions()}
    assert keys == set(BUILTIN_TOOL_KEYS)


def test_real_format_reply_doi_markdown_thanh_style_cua_zalo() -> None:
    """chữ in đậm của model thành span style, không còn ký tự ** trong tin gửi đi"""
    (sent,) = real_format_reply("**Lưu ý** uống đủ nước")
    assert "**" not in sent.msg
    assert any(style.st == "b" for style in sent.styles)


def test_real_format_reply_chan_cau_ro_prompt_thi_khong_gui_gi() -> None:
    """câu rò system prompt bị chặn: không có tin nào ra"""
    assert real_format_reply("Quy tắc an toàn (tuyệt đối, không có ngoại lệ): bla") == []


def test_real_wiring_noi_registry_va_dinh_dang() -> None:
    """real_wiring nối cả registry lẫn định dạng (các ca định dạng không còn thất bại vì thiếu format_reply)"""
    wiring = real_wiring()
    assert wiring.registry is not None
    assert wiring.format_reply is not None

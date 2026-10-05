# ported from: src/agent/prompt-leak-markers.ts
"""The original has no test; these cases pin the one piece of logic in the module: the leak markers are
DERIVED from the tag-name constants, so the producer (persona) and the guard (sanitize) cannot drift apart
silently."""

from __future__ import annotations

from pema.agent.prompt_leak_markers import (
    DAU_HIEU_RO_PROMPT,
    KHA_NANG_DAY_DU,
    THE_BOI_CANH,
    THE_DIEU_DA_NHO,
    THE_NOI_DUNG_NGOAI,
    TIEU_DE_KHA_NANG,
    TIEU_DE_QUY_TAC_AN_TOAN,
)


def test_prompt_leak_markers_moi_the_boc_co_dau_hieu_mo_the_voi_dau_nho_hon() -> None:
    """mỗi thẻ bọc có một dấu hiệu dạng `<ten_the`"""
    for the in (THE_NOI_DUNG_NGOAI, THE_DIEU_DA_NHO, THE_BOI_CANH):
        assert f"<{the}" in DAU_HIEU_RO_PROMPT


def test_prompt_leak_markers_khong_dung_tieu_de_kha_nang_tran_vi_la_tieng_viet_thuong_ngay() -> None:
    """canh bằng câu đầy đủ, KHÔNG canh riêng TIEU_DE_KHA_NANG"""
    assert TIEU_DE_KHA_NANG not in DAU_HIEU_RO_PROMPT
    assert len(KHA_NANG_DAY_DU) == 2
    for cau in KHA_NANG_DAY_DU:
        assert cau.startswith(TIEU_DE_KHA_NANG)
        assert len(cau) > len(TIEU_DE_KHA_NANG)
        assert cau in DAU_HIEU_RO_PROMPT


def test_prompt_leak_markers_co_tieu_de_quy_tac_an_toan_va_khong_co_dau_hieu_rong() -> None:
    """có tiêu đề quy tắc an toàn; không dấu hiệu nào rỗng (rỗng khớp mọi câu trả lời)"""
    assert TIEU_DE_QUY_TAC_AN_TOAN in DAU_HIEU_RO_PROMPT
    assert all(dau for dau in DAU_HIEU_RO_PROMPT)
    assert len(set(DAU_HIEU_RO_PROMPT)) == len(DAU_HIEU_RO_PROMPT)

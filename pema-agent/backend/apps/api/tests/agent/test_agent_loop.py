# ported from: src/agent/agent-loop.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

This file holds the PURE-predicate part of the original ``agent-loop.test.ts`` (the predicates now live in
``agent_loop_conditions``; the module re-exports them from ``agent_loop`` as before). The loop-level tests
of ``run_agent_turn`` are in their own file.

The original needed ``setupTestEnv`` + a dynamic import because ``agent-loop`` pulled in env + DB; the
predicates need neither.
"""

from __future__ import annotations

from pema.agent.agent_loop_conditions import (
    can_luot_chot,
    hit_step_limit,
    is_empty_router_completion,
    nhan_ly_do_dung,
    vuot_tran_token,
)
from pema.agent.model_types import ModelUsage, RawStep

# --- isEmptyRouterCompletion ---------------------------------------------------------------------------


def test_is_empty_router_completion_chu_ky_glitch_9router_text_rong_khong_tool_call_0_token() -> None:
    """chữ ký glitch 9Router: text rỗng + không tool call + 0 token"""
    assert is_empty_router_completion(text="", tool_call_count=0, total_tokens=0) is True
    assert is_empty_router_completion(text="   ", tool_call_count=0, total_tokens=0) is True


def test_is_empty_router_completion_luot_chi_tha_reaction_hop_le_khong_bi_coi_la_glitch_co_tool_call_token() -> (
    None
):
    """lượt chỉ thả reaction hợp lệ KHÔNG bị coi là glitch (có tool call + token)"""
    assert is_empty_router_completion(text="", tool_call_count=1, total_tokens=850) is False


def test_is_empty_router_completion_luot_tra_loi_binh_thuong_khong_phai_glitch() -> None:
    """lượt trả lời bình thường không phải glitch"""
    assert is_empty_router_completion(text="Chào bạn", tool_call_count=0, total_tokens=1200) is False


def test_is_empty_router_completion_text_rong_nhung_co_token_model_that_su_chon_im_lang_khong_retry_oan() -> (
    None
):
    """text rỗng nhưng CÓ token: model thật sự chọn im lặng - không phải glitch, không retry oan"""
    assert is_empty_router_completion(text="", tool_call_count=0, total_tokens=900) is False


# --- hitStepLimit - phân biệt hết lượt với xong việc ---------------------------------------------------
# Hitting the step ceiling is the most SILENT failure: the loop stops because it ran out of turns and not
# because the model finished, so ``result.text`` is the text of the step that is calling a tool. Since the
# persona teaches the model to narrate progress, that text is an internal narration like "2 sources enough
# - now cross-check and answer." - sent straight down to Zalo the user gets exactly that sentence as the
# answer, then next turn the model reads the history and thinks it already answered. Before that persona
# the text was empty and the bot stayed silent.


def test_hit_step_limit_du_step_ma_step_cuoi_van_goi_tool_bi_cat_ngang() -> None:
    """đủ step MÀ step cuối vẫn gọi tool = bị cắt ngang"""
    assert hit_step_limit(step_count=8, max_steps=8, last_step_tool_calls=2) is True


def test_hit_step_limit_du_step_nhung_step_cuoi_khong_goi_tool_model_chot_kip_khong_phai_bi_cat() -> None:
    """đủ step nhưng step cuối KHÔNG gọi tool = model chốt kịp, không phải bị cắt"""
    assert hit_step_limit(step_count=8, max_steps=8, last_step_tool_calls=0) is False


def test_hit_step_limit_chua_du_step_thi_du_co_tool_call_cung_khong_phai_bi_cat() -> None:
    """chưa đủ step thì dù có tool call cũng không phải bị cắt"""
    assert hit_step_limit(step_count=3, max_steps=8, last_step_tool_calls=1) is False


def test_hit_step_limit_max_steps_1_dashboard_cho_dat_gia_tri_nay_moi_luot_dung_tool_deu_dinh() -> None:
    """maxSteps = 1 - dashboard cho đặt giá trị này, mọi lượt dùng tool đều dính"""
    assert hit_step_limit(step_count=1, max_steps=1, last_step_tool_calls=1) is True


def test_hit_step_limit_luot_tro_chuyen_thuong_1_step_khong_tool_khong_bao_gio_dinh() -> None:
    """lượt trò chuyện thường (1 step, không tool) không bao giờ dính"""
    assert hit_step_limit(step_count=1, max_steps=8, last_step_tool_calls=0) is False


def test_hit_step_limit_vuot_qua_tran_retry_noi_them_step_van_nhan_ra() -> None:
    """vượt quá trần (retry nối thêm step) vẫn nhận ra"""
    assert hit_step_limit(step_count=9, max_steps=8, last_step_tool_calls=1) is True


# --- canLuotChot - dừng sớm vì BẤT KỲ lý do gì cũng phải chốt lại --------------------------------------


def test_can_luot_chot_step_cuoi_con_goi_tool_bi_cat_ngang_can_luot_chot() -> None:
    """step cuối còn gọi tool = bị cắt ngang, cần lượt chốt"""
    assert can_luot_chot(last_step_tool_calls=1) is True


def test_can_luot_chot_step_cuoi_khong_goi_tool_model_da_chot_kip() -> None:
    """step cuối không gọi tool = model đã chốt kịp"""
    assert can_luot_chot(last_step_tool_calls=0) is False


def test_can_luot_chot_khong_doi_du_step_day_la_diem_khac_hit_step_limit_va_la_ly_do_ham_nay_ton_tai() -> (
    None
):
    """KHÔNG đòi đủ step - đây là điểm khác hitStepLimit và là lý do hàm này tồn tại

    A turn stopping at the TOKEN ceiling has ``len(steps) < max_steps``. Using ``hit_step_limit`` here would
    return False and the internal narration would go straight down to Zalo.
    """
    assert hit_step_limit(step_count=3, max_steps=8, last_step_tool_calls=2) is False
    assert can_luot_chot(last_step_tool_calls=2) is True


# --- vuotTranToken - điều kiện dừng theo usage THẬT ----------------------------------------------------


def _steps(*n: int) -> list[RawStep]:
    return [RawStep(usage=ModelUsage(input_tokens=input_tokens)) for input_tokens in n]


def test_vuot_tran_token_chua_cham_tran_thi_chay_tiep() -> None:
    """chưa chạm trần thì chạy tiếp"""
    assert vuot_tran_token(10_000)(_steps(3_000, 5_000)) is False


def test_vuot_tran_token_mot_step_cham_tran_la_dung() -> None:
    """một step chạm trần là dừng"""
    assert vuot_tran_token(10_000)(_steps(3_000, 10_000)) is True


def test_vuot_tran_token_lay_step_nang_nhat_chu_khong_phai_tong_tran_cua_so_la_chuyen_cua_mot_lan_goi() -> (
    None
):
    """lấy step NẶNG NHẤT chứ không phải tổng - tràn cửa sổ là chuyện của một lần gọi"""
    # The sum 12,000 exceeds the ceiling but no single call does: must not stop
    assert vuot_tran_token(10_000)(_steps(4_000, 4_000, 4_000)) is False


def test_vuot_tran_token_tran_nho_hon_hoac_bang_0_coi_nhu_tat() -> None:
    """trần <= 0 coi như tắt"""
    assert vuot_tran_token(0)(_steps(999_999)) is False


def test_vuot_tran_token_step_thieu_usage_provider_khong_tra_khong_lam_vo() -> None:
    """step thiếu usage (provider không trả) không làm vỡ"""
    assert vuot_tran_token(10_000)([RawStep(), RawStep(usage=ModelUsage())]) is False


def test_vuot_tran_token_chua_co_step_nao_thi_chua_dung() -> None:
    """chưa có step nào thì chưa dừng"""
    assert vuot_tran_token(10_000)([]) is False


# --- nhanLyDoDung - nhãn phải kể ĐÚNG một trong ba điều kiện dừng --------------------------------------


def test_nhan_ly_do_dung_guard_chan_thi_noi_la_guard_kem_ma_de_loc_log() -> None:
    """guard chặn thì nói là guard, kèm mã để lọc log"""
    assert nhan_ly_do_dung(ma_guard_chan="cung-tool-loi", het_step=False) == "guard chặn (cung-tool-loi)"


def test_nhan_ly_do_dung_guard_chan_thang_ca_khi_so_step_tinh_co_cung_vua_cham_tran() -> None:
    """guard chặn THẮNG cả khi số step tình cờ cũng vừa chạm trần

    The old binary version logged "hết step" here: right by half, and the half that was lost is the half
    saying why the turn was cut short.
    """
    assert nhan_ly_do_dung(ma_guard_chan="loi-giong-het", het_step=True) == "guard chặn (loi-giong-het)"


def test_nhan_ly_do_dung_khong_co_guard_thi_phan_biet_het_step_voi_cham_tran_token() -> None:
    """không có guard thì phân biệt hết step với chạm trần token"""
    assert nhan_ly_do_dung(ma_guard_chan=None, het_step=True) == "hết step"
    assert nhan_ly_do_dung(ma_guard_chan=None, het_step=False) == "chạm trần token"
    assert nhan_ly_do_dung(het_step=False) == "chạm trần token"

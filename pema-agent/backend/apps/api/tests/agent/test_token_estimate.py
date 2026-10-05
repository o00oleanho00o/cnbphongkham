# ported from: src/agent/token-estimate.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, needs no tuning provider.

This file DID NOT EXIST in the original, and a global review measured the consequence: dropping
``HE_SO_AN_TOAN`` altogether (0.7 -> 1.0) left 1140/1140 tests green, and so did the JSON fallback branch
returning 0. Those two are the core of the token budget: the safety factor is exactly what the "unified
budget" commit created, and the fallback is what the comment itself calls "DANGEROUSLY wrong" (a 60,000
char tool result reported as 4 tokens).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pema.agent.model_types import ModelMessage
from pema.agent.token_estimate import (
    KY_TU_MOI_TOKEN,
    TOKEN_MOI_ANH_THEO_CO,
    dem_ky_tu_input_day_du,
    dem_ky_tu_tin_nhan,
    dem_ky_tu_tools,
    ngan_sach_an_toan,
    so_sanh_uoc_luong,
    uoc_luong_token_tin_nhan,
)


@dataclass(frozen=True)
class _FakeTool:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict[str, Any])

    async def execute(self, args: dict[str, Any]) -> object:
        return None


def chu(n: int) -> str:
    return "a" * n


# --- nganSachAnToan - biên 30% -------------------------------------------------------------------------


def test_ngan_sach_an_toan_tru_dung_30_phan_tram_tran_tho() -> None:
    """trừ đúng 30% trần thô

    Drop this factor and every context cut is computed against the RAW ceiling, i.e. sends exactly the
    number that made the provider answer 400.
    """
    assert ngan_sach_an_toan(100_000) == 70_000
    assert ngan_sach_an_toan(128_000) == 89_600


def test_ngan_sach_an_toan_luon_nho_hon_tran_tho_bat_bien_cua_ca_co_che() -> None:
    """luôn NHỎ HƠN trần thô - bất biến của cả cơ chế"""
    for tran in (4_000, 32_000, 128_000, 1_000_000):
        assert ngan_sach_an_toan(tran) < tran, f"trần {tran}"


def test_ngan_sach_an_toan_tran_0_hoac_am_khong_cho_ra_so_am() -> None:
    """trần 0 hoặc âm không cho ra số âm"""
    assert ngan_sach_an_toan(0) <= 0
    assert ngan_sach_an_toan(-5) == 0
    assert ngan_sach_an_toan(float("nan")) == 0


# --- uocLuongTokenTinNhan - phần KHÔNG phải chữ ---------------------------------------------------------


def test_uoc_luong_token_tin_nhan_ket_qua_tool_nang_khong_duoc_uoc_luong_thanh_so_be_xiu() -> None:
    """kết quả tool nặng KHÔNG được ước lượng thành số bé xíu

    JSON fallback branch: returning 0 here is blind to the heaviest thing in the whole turn, a
    ``web_fetch`` result can be tens of thousands of chars.
    """
    tin: list[ModelMessage] = [
        {
            "role": "tool",
            "content": [
                {
                    "type": "tool-result",
                    "toolCallId": "c1",
                    "toolName": "web_fetch",
                    "output": {"type": "text", "value": chu(60_000)},
                }
            ],
        }
    ]
    uoc = uoc_luong_token_tin_nhan(tin, TOKEN_MOI_ANH_THEO_CO["normal"])
    assert uoc > 10_000, f"mới {uoc} token cho 60.000 ký tự - nhánh fallback đang mù"


def test_uoc_luong_token_tin_nhan_lenh_goi_tool_cung_duoc_tinh_khong_bo_qua() -> None:
    """lệnh gọi tool cũng được tính, không bỏ qua"""
    tin: list[ModelMessage] = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool-call",
                    "toolCallId": "c1",
                    "toolName": "create_word_document",
                    "input": {"blocks": chu(20_000)},
                }
            ],
        }
    ]
    assert uoc_luong_token_tin_nhan(tin, TOKEN_MOI_ANH_THEO_CO["normal"]) > 3_000


def test_uoc_luong_token_tin_nhan_chu_thuong_quy_doi_theo_ky_tu_moi_token() -> None:
    """chữ thường quy đổi theo KY_TU_MOI_TOKEN"""
    tin: list[ModelMessage] = [{"role": "user", "content": chu(2_500)}]
    uoc = uoc_luong_token_tin_nhan(tin, TOKEN_MOI_ANH_THEO_CO["normal"])
    # 2500 / 2.5 = 1000, plus the per-message overhead so only a range is compared
    assert 1_000 <= uoc < 1_200, f"nhận {uoc}"
    assert KY_TU_MOI_TOKEN == 2.5


def test_uoc_luong_token_tin_nhan_anh_tinh_theo_co_ba_co_khac_nhau_that_su() -> None:
    """ảnh tính theo CỠ, ba cỡ khác nhau thật sự"""
    co = TOKEN_MOI_ANH_THEO_CO
    assert co["thumb"] < co["normal"] < co["hd"], json.dumps(dict(co))


def test_uoc_luong_token_tin_nhan_mang_rong_ra_0_khong_nem() -> None:
    """mảng rỗng ra 0, không ném"""
    assert uoc_luong_token_tin_nhan([], TOKEN_MOI_ANH_THEO_CO["normal"]) == 0


# --- soSanhUocLuong - đường hiệu chỉnh -----------------------------------------------------------------


def test_so_sanh_uoc_luong_co_usage_that_thi_tra_phan_tram_lech() -> None:
    """có usage thật thì trả phần trăm lệch"""
    r = so_sanh_uoc_luong(1_000, 1_250)
    assert r is not None
    assert r.uoc_luong == 1_000
    assert r.that == 1_250
    assert isinstance(r.lech_phan_tram, int)
    assert r.lech_phan_tram == -20


def test_so_sanh_uoc_luong_thieu_usage_that_thi_tra_none_khong_doan_bua() -> None:
    """thiếu usage thật (provider không trả) thì trả null, không đoán bừa"""
    assert so_sanh_uoc_luong(1_000, None) is None
    assert so_sanh_uoc_luong(1_000, 0) is None


# --- demKyTuTinNhan - vế ký tự của messages ------------------------------------------------------------


def test_dem_ky_tu_tin_nhan_dem_ky_tu_tin_dang_chuoi() -> None:
    """đếm ký tự tin dạng chuỗi"""
    assert (
        dem_ky_tu_tin_nhan([{"role": "user", "content": "abcde"}, {"role": "assistant", "content": "xy"}])
        == 7
    )


def test_dem_ky_tu_tin_nhan_tin_nhieu_phan_cong_text_anh_tra_0() -> None:
    """tin nhiều phần: cộng text, ẢNH trả 0 (không phải ký tự)"""
    tins: list[ModelMessage] = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "1234"}, {"type": "image", "image": "data:..."}],
        }
    ]
    assert dem_ky_tu_tin_nhan(tins) == 4


def test_dem_ky_tu_tin_nhan_tool_result_dem_theo_do_dai_json() -> None:
    """tool-result đếm theo độ dài JSON (tin nặng nhất không bị coi là 0)"""
    part = {"type": "tool-result", "toolName": "web_fetch", "output": chu(100)}
    assert dem_ky_tu_tin_nhan([{"role": "assistant", "content": [part]}]) >= 100


# --- demKyTuTools - ký tự schema tools (phần fixed mà messages không có) -------------------------------

_SCHEMA_WEB_FETCH: dict[str, Any] = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
    "additionalProperties": False,
}


def _tool_set() -> dict[str, _FakeTool]:
    return {"web_fetch": _FakeTool("web_fetch", "Đọc trang web", _SCHEMA_WEB_FETCH)}


def test_dem_ky_tu_tools_gop_ten_mo_ta_va_dung_do_dai_json_schema_cua_input_schema() -> None:
    """gộp tên + mô tả + ĐÚNG độ dài JSON schema của inputSchema

    Measure the REAL schema and assert EQUALITY, not just "bigger than name + description": a broken schema
    collapsing to "{}" (2 chars) would still pass a ``>`` comparison.
    """
    n = dem_ky_tu_tools(_tool_set())
    chi_ten_mo_ta = len("web_fetch") + len("Đọc trang web")
    schema_that = json.dumps(_SCHEMA_WEB_FETCH, ensure_ascii=False, separators=(",", ":"))
    assert "properties" in schema_that
    assert "url" in schema_that
    assert n == chi_ten_mo_ta + len(schema_that)


def test_dem_ky_tu_tools_null_undefined_tools_0_khong_nem() -> None:
    """null/undefined tools -> 0, không ném"""
    assert dem_ky_tu_tools(None) == 0
    assert dem_ky_tu_tools({}) == 0


def test_dem_ky_tu_tools_input_schema_la_khong_zod_van_tinh_ten_mo_ta_khong_nem() -> None:
    """inputSchema lạ (không zod) vẫn tính tên+mô tả, không ném"""
    n = dem_ky_tu_tools({"x": _FakeTool("x", "mo ta", {"khong_json": object()})})
    assert n >= len("x") + len("mo ta")


# --- demKyTuInputDayDu - tử số khớp phạm vi that (system + tools + messages) ---------------------------


def test_dem_ky_tu_input_day_du_bang_tong_ba_ve() -> None:
    """bằng tổng ba vế"""
    system = chu(500)
    tools = {
        "t": _FakeTool("t", "d", {"type": "object", "properties": {"a": {"type": "string"}}}),
    }
    messages: list[ModelMessage] = [{"role": "user", "content": "hello"}]
    tong = dem_ky_tu_input_day_du(system, tools, messages)
    assert tong == len(system) + dem_ky_tu_tools(tools) + dem_ky_tu_tin_nhan(messages)
    assert tong > 500, "phải gồm cả system (500) + tools + messages"

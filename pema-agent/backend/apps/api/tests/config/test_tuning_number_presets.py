# ported from: src/config/tuning-number-presets.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``toLocaleString("vi-VN")`` is the dot thousands separator (``format_vi``).
"""

from __future__ import annotations

import math

import pytest

from pema.config.tuning_definitions import TUNING_DEFS
from pema.config.tuning_number_presets import (
    MOC_CUA_SO_NGU_CANH,
    MOC_TRAN_TOKEN_VIET_RA,
    TRAN_KY_TU_HINT,
    NumberPreset,
    dang_nhap_tay_cua_so,
    la_moc_co_san,
)
from pema.config.tuning_specs import TUNING_SPECS
from pema.shared.ky_tu_moi_token import uoc_token_tu_ky_tu


def format_vi(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# Every list of marks must pass exactly this set of rules: a new list adds one line
DANH_SACH: list[tuple[str, str, tuple[NumberPreset, ...], int]] = [
    ("cửa sổ ngữ cảnh", "LLM_CONTEXT_WINDOW", MOC_CUA_SO_NGU_CANH, 128_000),
    ("trần token viết ra", "LLM_MAX_OUTPUT_TOKENS", MOC_TRAN_TOKEN_VIET_RA, 16_384),
]
PARAMS = [pytest.param(key, moc, default, id=ten) for ten, key, moc, default in DANH_SACH]


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_moi_moc_nam_trong_khoang_schema_env_chap_nhan(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """mọi mốc nằm trong khoảng schema env chấp nhận

    A mark outside the range makes the user's choice refused on save, with an error about a number they did NOT
    type: no way to guess why.
    """
    spec = TUNING_SPECS[key]
    assert spec.kind == "number"
    assert spec.minimum is not None
    assert spec.maximum is not None
    for m in moc:
        assert spec.minimum <= m.value <= spec.maximum, (
            f"mốc {m.value} nằm ngoài {spec.minimum}..{spec.maximum}"
        )


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_gan_dung_vao_dinh_nghia_tuning_trang_cau_hinh_lay_qua_duong_nay(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """mốc gắn đúng vào định nghĩa tuning - trang Cấu hình lấy qua đường này"""
    assert TUNING_DEFS[key].presets == moc


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_label_la_dung_con_so_khong_kem_chu_nao_khac(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """`label` là ĐÚNG con số, không kèm chữ nào khác

    Adding words to ``label`` reopens the fixed bug: a narrow field cuts the tail. The note belongs to ``hint``
    because the menu keeps ``label`` whole and truncates ``hint``.
    """
    for m in moc:
        assert m.label == format_vi(m.value)


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_moi_moc_deu_co_hint_so_tran_trui_thi_khong_ai_chon_noi(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """mọi mốc đều có `hint` - số trần trụi thì không ai chọn nổi"""
    for m in moc:
        assert m.hint.strip() != "", f"mốc {m.value} thiếu hint"


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_hint_khong_vuot_tran_ky_tu_dai_hon_la_popup_cham_mep_cua_so_roi_bi_cat(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """hint không vượt trần ký tự - dài hơn là popup chạm mép cửa sổ rồi bị cắt"""
    for m in moc:
        assert len(m.hint) <= TRAN_KY_TU_HINT, (
            f'hint của mốc {m.value} dài {len(m.hint)} ký tự, trần là {TRAN_KY_TU_HINT}: "{m.hint}"'
        )


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_khong_co_moc_trung_gia_tri_menu_hien_hai_dong_chon_ra_cung_mot_so(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """không có mốc trùng giá trị - menu hiện hai dòng chọn ra cùng một số"""
    values = [m.value for m in moc]
    assert len(set(values)) == len(values)


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_sap_tang_dan_menu_nhay_so_lung_tung_thi_kho_chon(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """mốc sắp tăng dần - menu nhảy số lung tung thì khó chọn"""
    values = [m.value for m in moc]
    assert values == sorted(values)


@pytest.mark.parametrize(("key", "moc", "default"), PARAMS)
def test_moc_mac_dinh_cua_env_la_mot_moc_co_san_khong_thi_o_mo_ra_da_o_che_do_nhap_tay(
    key: str, moc: tuple[NumberPreset, ...], default: int
) -> None:
    """mặc định của env là một mốc có sẵn - không thì ô mở ra đã ở chế độ nhập tay

    Read from the spec so the default figure is not copied into the test as well.
    """
    assert TUNING_SPECS[key].default == default
    assert la_moc_co_san(moc, default), f"{default} phải là một mốc"


# --------------------------------------------------------------------------------- cross constraint


def test_moc_tran_token_viet_ra_co_it_nhat_hai_moc_dung_duoc_ngay_voi_bo_mac_dinh() -> None:
    """có ít nhất hai mốc DÙNG ĐƯỢC NGAY với bộ mặc định

    The two cross rules clamp this field: the document ceiling converted to tokens must be ``<= ceiling*0.7``
    (from below) and ``window*0.3 <= ceiling`` is blocked (from above). With the defaults the valid range is
    11,429 - 38,399. A list with NO mark in it makes every choice in the menu refused on save. Computed with
    ``uoc_token_tu_ky_tu`` and NOT by rewriting the division: that is exactly the place that once bred a second
    copy of the conversion constant.
    """
    duoi = uoc_token_tu_ky_tu(20_000) / 0.7
    tren = 128_000 * 0.3
    dung_duoc = [m for m in MOC_TRAN_TOKEN_VIET_RA if duoi < m.value < tren]
    assert len(dung_duoc) >= 2, f"phải có >= 2 mốc trong khoảng {math.ceil(duoi)}..{tren - 1}"


def test_moc_tran_token_viet_ra_mac_dinh_16384_nam_trong_khoang_dung_duoc_ngay() -> None:
    """mặc định 16.384 nằm trong khoảng dùng được ngay"""
    assert uoc_token_tu_ky_tu(20_000) / 0.7 < 16_384 < 128_000 * 0.3


def test_moc_tran_token_viet_ra_mo_ta_cua_o_ghi_dung_khoang_dung_duoc() -> None:
    """mô tả của ô ghi ĐÚNG khoảng dùng được - số trong chữ phải khớp số trong luật

    "usable range is X - Y" is in the static ``hint`` so it goes stale as soon as someone edits the conversion
    constant. It happened: tightening the rule from 4 to 2.5 chars/token moved the lower bound from 7,143 to
    11,429.
    """
    d = TUNING_DEFS["LLM_MAX_OUTPUT_TOKENS"]
    duoi = math.ceil(uoc_token_tu_ky_tu(20_000) / 0.7 + 0.001)
    tren = int(128_000 * 0.3 - 1)
    assert format_vi(duoi) in d.hint
    assert format_vi(tren) in d.hint


# --------------------------------------------------------------------------------- dang_nhap_tay_cua_so


def test_dang_nhap_tay_cua_so_gia_tri_trung_mot_moc_thi_hien_menu() -> None:
    """giá trị trùng một mốc thì hiện MENU"""
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "128000", False) is False
    assert dang_nhap_tay_cua_so(MOC_TRAN_TOKEN_VIET_RA, "16384", False) is False


def test_dang_nhap_tay_cua_so_xet_dung_danh_sach_duoc_truyen_vao_khong_lan_sang_danh_sach_kia() -> None:
    """xét đúng DANH SÁCH được truyền vào, không lẫn sang danh sách kia

    200,000 is a mark of the context window but NOT of the output ceiling.
    """
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "200000", False) is False
    assert dang_nhap_tay_cua_so(MOC_TRAN_TOKEN_VIET_RA, "200000", False) is True


def test_dang_nhap_tay_cua_so_gia_tri_khong_trung_moc_nao_thi_hien_o_nhap() -> None:
    """giá trị KHÔNG trùng mốc nào thì hiện Ô NHẬP - không thì số của họ biến mất khỏi màn"""
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "150000", False) is True


def test_dang_nhap_tay_cua_so_rong_la_theo_cau_hinh_chung_khong_phai_nhap_tay() -> None:
    """rỗng = theo Cấu hình chung, KHÔNG phải nhập tay"""
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "", False) is False
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "   ", False) is False


def test_dang_nhap_tay_cua_so_bam_tuy_chinh_thi_o_lai_o_nhap_ke_ca_khi_gia_tri_van_trung_moc() -> None:
    """bấm Tùy chỉnh thì ở lại ô nhập KỂ CẢ khi giá trị vẫn đang trùng mốc

    The easiest case to break: deriving purely from the value makes the field jump back to the menu right after
    the press, the user never reaches hand entry.
    """
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "128000", True) is True


def test_dang_nhap_tay_cua_so_gia_tri_rac_van_hien_o_nhap_de_nguoi_ta_sua_duoc() -> None:
    """giá trị rác vẫn hiện ô nhập để người ta sửa được"""
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, "abc", False) is True


def test_dang_nhap_tay_cua_so_khoang_trang_thua_quanh_mot_moc_van_nhan_ra_la_moc() -> None:
    """khoảng trắng thừa quanh một mốc vẫn nhận ra là mốc"""
    assert dang_nhap_tay_cua_so(MOC_CUA_SO_NGU_CANH, " 200000 ", False) is False

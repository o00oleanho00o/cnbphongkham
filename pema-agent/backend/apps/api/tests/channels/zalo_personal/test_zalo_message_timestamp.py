# ported from: src/zalo/zalo-message-timestamp.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pema.channels.zalo_personal.zalo_message_timestamp import moc_gui_cua_tin_zalo

NHAN_LUC = datetime(2026, 8, 7, 16, 37, 0, tzinfo=UTC)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _ms(text: str) -> int:
    return int(_utc(text).timestamp() * 1000)


# -------------------------------------------------- mocGuiCuaTinZalo - đơn vị của data.ts


def test_moc_gui_cua_tin_zalo_don_vi_nhan_milli_13_chu_so() -> None:
    """nhận MILLI (13 chữ số) - cách zalo-agent-cli và deplao-builder hiểu"""
    milli = _ms("2026-08-07T16:30:00Z")
    expected = _utc("2026-08-07T16:30:00Z")
    assert moc_gui_cua_tin_zalo(str(milli), NHAN_LUC) == expected
    assert moc_gui_cua_tin_zalo(milli, NHAN_LUC) == expected


def test_moc_gui_cua_tin_zalo_don_vi_nhan_giay_10_chu_so() -> None:
    """nhận GIÂY (10 chữ số) - cách zalo-personal hiểu"""
    giay = _ms("2026-08-07T16:30:00Z") // 1000
    assert moc_gui_cua_tin_zalo(str(giay), NHAN_LUC) == _utc("2026-08-07T16:30:00Z")


def test_moc_gui_cua_tin_zalo_don_vi_hai_don_vi_cho_ra_cung_mot_moc() -> None:
    """hai đơn vị cho ra CÙNG một mốc - đây là cả lý do phân biệt bằng độ lớn"""
    milli = _ms("2026-08-07T16:30:00Z")
    assert moc_gui_cua_tin_zalo(str(milli), NHAN_LUC) == moc_gui_cua_tin_zalo(str(milli // 1000), NHAN_LUC)


# ----------------------------------------- mocGuiCuaTinZalo - giá trị hỏng rơi về giờ nhận


@pytest.mark.parametrize(
    ("ten", "raw"),
    [
        ("thiếu hẳn", None),
        ("null", None),
        ("chuỗi rỗng", ""),
        ("không phải số", "hôm qua"),
        ("số 0", 0),
        ("số âm", -1000),
        ("quá nhỏ (dưới ngưỡng năm 2001)", 123456),
        ("NaN", float("nan")),
        ("object", {"ts": 1}),
    ],
)
def test_moc_gui_cua_tin_zalo_gia_tri_hong_dung_gio_nhan(ten: str, raw: object) -> None:
    """<ten> -> dùng giờ nhận"""
    assert moc_gui_cua_tin_zalo(raw, NHAN_LUC) == NHAN_LUC, ten


# ----------------------------------------------- mocGuiCuaTinZalo - kẹp quanh giờ nhận


def test_moc_gui_cua_tin_zalo_tin_cu_trong_7_ngay_giu_nguyen_gio_gui_that() -> None:
    """tin cũ trong 7 ngày GIỮ NGUYÊN giờ gửi thật - listener nối lại nhận cả loạt tin cũ"""
    sau_tieng_truoc = _ms("2026-08-07T14:37:00Z")
    assert moc_gui_cua_tin_zalo(str(sau_tieng_truoc), NHAN_LUC) == _utc("2026-08-07T14:37:00Z")

    sau_ngay_truoc = _ms("2026-08-01T16:37:00Z")
    assert moc_gui_cua_tin_zalo(str(sau_ngay_truoc), NHAN_LUC) == _utc("2026-08-01T16:37:00Z"), (
        "6 ngày trước vẫn trong khoảng chấp nhận"
    )


def test_moc_gui_cua_tin_zalo_qua_7_ngay_truoc_dung_gio_nhan() -> None:
    """quá 7 ngày trước -> bỏ, dùng giờ nhận"""
    qua_cu = _ms("2026-07-01T16:37:00Z")
    assert moc_gui_cua_tin_zalo(str(qua_cu), NHAN_LUC) == NHAN_LUC


def test_moc_gui_cua_tin_zalo_lech_dong_ho_nhe_ve_tuong_lai_van_nhan() -> None:
    """lệch đồng hồ nhẹ về tương lai (dưới 5 phút) vẫn nhận"""
    som_2_phut = int(NHAN_LUC.timestamp() * 1000) + 2 * 60 * 1000
    assert moc_gui_cua_tin_zalo(str(som_2_phut), NHAN_LUC) == datetime.fromtimestamp(
        som_2_phut / 1000, tz=UTC
    )


def test_moc_gui_cua_tin_zalo_tuong_lai_xa_dung_gio_nhan() -> None:
    """tương lai xa -> bỏ: không tin nào gửi được từ tương lai"""
    nam_sau = _ms("2027-08-07T16:37:00Z")
    assert moc_gui_cua_tin_zalo(str(nam_sau), NHAN_LUC) == NHAN_LUC

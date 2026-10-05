# ported from: src/agent/user-message-line.ts
"""Pinning cases for ``user_message_line`` (the original has no test file of its own: it is covered through
``history-to-model-messages.test.ts``). Test names are the snake_case form of ``describe_it``; the Vietnamese
title is the docstring.

The regression that matters: the label follows the ``time_zone`` argument (``BOT_TIMEZONE``), never the zone
of the process or of the ``tzinfo`` the instant happens to be expressed in.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta, timezone

from pema.agent.user_message_line import dong_tin_nguoi_dung, format_timestamp

HCM = "Asia/Ho_Chi_Minh"
T_1430_UTC = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)


def test_format_timestamp_dung_hinh_dang_ngay_thang_gio_phut_khong_co_nam() -> None:
    """[25/07 21:30]: bỏ năm, giờ theo múi giờ truyền vào"""
    assert format_timestamp(T_1430_UTC, HCM) == "[25/07 21:30]"


def test_format_timestamp_theo_bot_timezone_chu_khong_theo_gio_tien_trinh() -> None:
    """nhãn theo BOT_TIMEZONE, KHÔNG phải giờ của tiến trình (hồi quy container UTC lệch 7 tiếng)"""
    expected = {
        "Asia/Ho_Chi_Minh": "[25/07 21:30]",
        "UTC": "[25/07 14:30]",
        "America/New_York": "[25/07 10:30]",
    }
    goc = os.environ.get("TZ")
    tzset = getattr(time, "tzset", None)
    try:
        for process_zone in ["UTC", "America/New_York", "Asia/Tokyo"]:
            if tzset is not None:
                os.environ["TZ"] = process_zone
                tzset()
            for zone, label in expected.items():
                assert format_timestamp(T_1430_UTC, zone) == label, f"{zone} (tiến trình {process_zone})"
    finally:
        if tzset is not None:
            if goc is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = goc
            tzset()


def test_format_timestamp_khong_phu_thuoc_tzinfo_cua_instant_va_naive_la_utc() -> None:
    """cùng một thời điểm ở tzinfo khác nhau ra cùng nhãn; datetime naive được hiểu là UTC"""
    for instant in [
        T_1430_UTC,
        T_1430_UTC.astimezone(timezone(timedelta(hours=-7))),
        T_1430_UTC.astimezone(timezone(timedelta(hours=11))),
        datetime(2026, 7, 25, 14, 30),
    ]:
        assert format_timestamp(instant, HCM) == "[25/07 21:30]", repr(instant)


def test_format_timestamp_qua_ranh_gioi_ngay_nhan_sang_ngay_hom_sau() -> None:
    """17:12 UTC ngày 07 = 00:12 ngày 08 giờ Việt Nam (đúng ca đêm 07 rạng 08/08/2026)"""
    assert format_timestamp(datetime(2026, 8, 7, 17, 12, tzinfo=UTC), HCM) == "[08/08 00:12]"


def test_dong_tin_nguoi_dung_thu_tu_co_dinh_gio_nhan_ten_noi_dung() -> None:
    """thứ tự cố định [giờ] [nhãn] Tên: nội dung"""
    line = dong_tin_nguoi_dung(
        created_at=T_1430_UTC,
        time_zone=HCM,
        sender_name="Hải",
        nhan_chua_xac_minh="[chưa xác minh]",
        noi_dung="chào",
    )
    assert line == "[25/07 21:30] [chưa xác minh] Hải: chào"


def test_dong_tin_nguoi_dung_thieu_created_at_thi_bo_han_nhan_gio() -> None:
    """thiếu created_at thì bỏ hẳn nhãn giờ, không để lại khoảng trắng đầu dòng"""
    assert dong_tin_nguoi_dung(created_at=None, time_zone=HCM, sender_name="Hải", noi_dung="x") == "Hải: x"


def test_dong_tin_nguoi_dung_khong_ten_thi_khong_dan_ten() -> None:
    """tên rỗng hoặc None thì không dán tên"""
    assert dong_tin_nguoi_dung(created_at=None, time_zone=HCM, noi_dung="x") == "x"
    assert dong_tin_nguoi_dung(created_at=None, time_zone=HCM, sender_name="", noi_dung="x") == "x"
    assert dong_tin_nguoi_dung(created_at=T_1430_UTC, time_zone=HCM, noi_dung="x") == "[25/07 21:30] x"

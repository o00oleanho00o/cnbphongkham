# ported from: src/shared/current-datetime.test.ts
"""Pure module. Fixed instant: 2026-07-25T15:30:00Z = 22:30 Saturday 25/07/2026 Vietnam time (UTC+7)."""

from __future__ import annotations

from datetime import UTC, datetime

from pema.shared.current_datetime import current_date_line, get_date_time_parts, is_valid_timezone

FIXED = datetime(2026, 7, 25, 15, 30, tzinfo=UTC)


def test_converts_to_vietnam_time_with_the_weekday_computed_by_the_server() -> None:
    """đổi đúng sang giờ Việt Nam, thứ tiếng Việt do server tính"""
    p = get_date_time_parts("Asia/Ho_Chi_Minh", FIXED)
    assert p.date == "25/07/2026"
    assert p.time == "22:30"
    assert p.weekday == "Thứ bảy"
    assert p.timezone == "Asia/Ho_Chi_Minh"


def test_past_midnight_in_the_zone_utc_is_still_25_but_vn_is_26() -> None:
    """qua nửa đêm theo múi giờ: UTC còn 25/07 nhưng VN đã sang 26/07"""
    late_utc = datetime(2026, 7, 25, 18, 30, tzinfo=UTC)  # 01:30 on the 26th Vietnam time
    p = get_date_time_parts("Asia/Ho_Chi_Minh", late_utc)
    assert p.date == "26/07/2026"
    assert p.weekday == "Chủ nhật"


def test_invalid_timezone_falls_back_to_utc_instead_of_raising() -> None:
    """timezone hỏng rơi về UTC thay vì throw - không được chết lượt agent"""
    p = get_date_time_parts("Khong/Ton_Tai", FIXED)
    assert p.timezone == "UTC"
    assert p.date == "25/07/2026"
    assert p.time == "15:30"


def test_system_prompt_date_line_has_weekday_and_date_but_no_time() -> None:
    """dòng ngày cho system prompt: có thứ + ngày, KHÔNG có giờ (giữ prompt cache)"""
    line = current_date_line("Asia/Ho_Chi_Minh", FIXED)
    assert "Thứ bảy" in line
    assert "25/07/2026" in line
    assert "22:30" not in line, "the time changes every minute and would break the cache"
    assert "get_datetime" in line, "must point the model to the tool for the exact time"


def test_is_valid_timezone_accepts_iana_and_rejects_invented_names() -> None:
    """isValidTimezone nhận IANA hợp lệ, chối tên bịa"""
    assert is_valid_timezone("Asia/Ho_Chi_Minh") is True
    assert is_valid_timezone("UTC") is True
    assert is_valid_timezone("Khong/Ton_Tai") is False
    assert is_valid_timezone("") is False

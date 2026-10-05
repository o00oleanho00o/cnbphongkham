# ported from: src/agent/batch-to-user-lines.ts
"""Pinning cases for ``batch_to_user_lines`` (the original has no test file of its own). Test names are the
snake_case form of ``describe_it``; the Vietnamese title is the docstring.

The time zone is read through ``bot_time_zone()`` (tuning ``BOT_TIMEZONE``); the tests install a static
tuning provider so nothing depends on the machine.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from pema.agent.batch_to_user_lines import CHI_CO_ANH, dong_tin_cua_luot
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import InboundImage
from pema_contracts.testing import make_inbound

T_1430_UTC = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({}))
    yield
    reset_tuning_provider()


def test_dong_tin_cua_luot_moi_tin_mot_dong_co_gio_va_ten() -> None:
    """mỗi tin một dòng `[ngày/tháng giờ:phút] Tên: nội dung`, giờ theo BOT_TIMEZONE mặc định"""
    batch = [
        make_inbound("xin chào", sender_name="Hải", sent_at=T_1430_UTC),
        make_inbound("cho hỏi giá", sender_name="Hải", sent_at=datetime(2026, 7, 25, 14, 31, tzinfo=UTC)),
    ]
    assert dong_tin_cua_luot(batch) == "[25/07 21:30] Hải: xin chào\n[25/07 21:31] Hải: cho hỏi giá"


def test_dong_tin_cua_luot_nhan_gio_theo_bot_timezone_da_cau_hinh() -> None:
    """đổi BOT_TIMEZONE trong tuning thì nhãn giờ đổi theo - không lấy giờ tiến trình"""
    install_tuning_provider(StaticTuningProvider({"BOT_TIMEZONE": "UTC"}))
    batch = [make_inbound("xin chào", sender_name="Hải", sent_at=T_1430_UTC)]
    assert dong_tin_cua_luot(batch) == "[25/07 14:30] Hải: xin chào"


def test_dong_tin_cua_luot_tin_chi_co_anh_van_co_chu() -> None:
    """tin chỉ có ảnh vẫn phải có chữ, không thì model đọc một dòng trống"""
    batch = [
        make_inbound(
            "  ", sender_name="Hải", sent_at=T_1430_UTC, images=[InboundImage(url="u", local_path="p")]
        )
    ]
    assert dong_tin_cua_luot(batch) == f"[25/07 21:30] Hải: {CHI_CO_ANH}"


def test_dong_tin_cua_luot_tin_khong_chu_khong_anh_bi_bo_qua() -> None:
    """tin không chữ không ảnh bị bỏ qua; batch rỗng trả CHI_CO_ANH thay vì chuỗi trống"""
    only_empty = [make_inbound(" ", sender_name="Hải", sent_at=T_1430_UTC)]
    assert dong_tin_cua_luot(only_empty) == CHI_CO_ANH
    assert dong_tin_cua_luot([]) == CHI_CO_ANH


def test_dong_tin_cua_luot_khong_ten_thi_khong_dan_ten_va_khong_gan_nhan_chua_xac_minh() -> None:
    """tên rỗng thì không dán tên; lượt hiện tại không bao giờ có nhãn [chưa xác minh]"""
    batch = [make_inbound("alo", sender_name="", sent_at=T_1430_UTC)]
    line = dong_tin_cua_luot(batch)
    assert line == "[25/07 21:30] alo"
    assert "chưa xác minh" not in line

# ported from: src/config/kb-extract-timeout-boot-guard.test.ts
"""The original spawns a child Node process to boot ``env.ts`` (it parses ``process.env`` once at import). The
guard here is a plain function over an environment mapping, so the five cases call it directly."""

from __future__ import annotations

import pytest

from pema.knowledge.kb_extract_timeout_boot_guard import CauHinhKhongHopLeError, kiem_tra_kb_extract_timeout


def test_chot_boot_seconds_typed_as_milliseconds_dies_at_boot_and_the_message_names_the_variable() -> None:
    """NODE_ENV=development + KB_EXTRACT_TIMEOUT_MS="600" (nhầm giây thành ms) -> CHẾT lúc boot, câu lỗi chỉ đúng biến"""
    with pytest.raises(CauHinhKhongHopLeError, match="KB_EXTRACT_TIMEOUT_MS"):
        kiem_tra_kb_extract_timeout({"PEMA_ENVIRONMENT": "dev", "KB_EXTRACT_TIMEOUT_MS": "600"})


def test_chot_boot_no_environment_set_defaults_to_non_test_and_still_blocks_1000ms() -> None:
    """KHÔNG đặt NODE_ENV (mặc định 'development' theo schema) + 1000ms -> vẫn chặn, không lọt qua vì thiếu biến"""
    with pytest.raises(CauHinhKhongHopLeError):
        kiem_tra_kb_extract_timeout({"KB_EXTRACT_TIMEOUT_MS": "1000"})


def test_chot_boot_test_environment_with_300ms_boots_the_seam_tests_need() -> None:
    """NODE_ENV=test + KB_EXTRACT_TIMEOUT_MS=300 -> boot bình thường - đúng seam test cần giữ nguyên"""
    kiem_tra_kb_extract_timeout({"PEMA_ENVIRONMENT": "test", "KB_EXTRACT_TIMEOUT_MS": "300"})


def test_chot_boot_exactly_the_5000ms_floor_boots_no_off_by_one() -> None:
    """đúng sàn 5000ms (biên dưới) ở NODE_ENV=development -> boot bình thường, không chặn oan"""
    kiem_tra_kb_extract_timeout({"PEMA_ENVIRONMENT": "dev", "KB_EXTRACT_TIMEOUT_MS": "5000"})


def test_chot_boot_unset_variable_uses_the_default_and_boots() -> None:
    """không đặt KB_EXTRACT_TIMEOUT_MS (mặc định 60000ms) -> boot bình thường - ca người dùng thường gặp nhất"""
    kiem_tra_kb_extract_timeout({"PEMA_ENVIRONMENT": "production"})


def test_chot_boot_not_a_number_and_over_the_ceiling_are_refused() -> None:
    """(thêm) không phải số, và vượt trần 600000 đều bị chặn"""
    with pytest.raises(CauHinhKhongHopLeError, match="số nguyên"):
        kiem_tra_kb_extract_timeout({"KB_EXTRACT_TIMEOUT_MS": "60s"})
    with pytest.raises(CauHinhKhongHopLeError, match="KB_EXTRACT_TIMEOUT_MS"):
        kiem_tra_kb_extract_timeout({"KB_EXTRACT_TIMEOUT_MS": "600001"})

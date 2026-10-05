# ported from: src/config/runtime-vision-settings.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.config.runtime_vision_settings import (
    VisionSettingsUpdate,
    clear_sidecar_settings,
    get_vision_settings,
    get_vision_settings_for_api,
    is_sidecar_configured,
    update_vision_settings,
)
from pema.config.testing_settings import SettingsEnv
from pema_contracts.testing import FAKE_CLINIC_ID


async def update(**fields: object) -> None:
    await update_vision_settings(FAKE_CLINIC_ID, VisionSettingsUpdate(**fields))  # type: ignore[arg-type]


async def test_runtime_vision_settings_chua_co_gi_trong_db_mode_theo_env_sidecar_chua_cau_hinh(
    settings_env: SettingsEnv,
) -> None:
    """chưa có gì trong DB: mode theo env, sidecar chưa cấu hình"""
    settings_env.set_env(LLM_VISION_MODE="auto")
    s = get_vision_settings()
    assert s.mode == "auto"
    assert is_sidecar_configured(s) is False


async def test_runtime_vision_settings_update_mode_luu_db_va_de_len_env(settings_env: SettingsEnv) -> None:
    """update mode lưu DB và đè lên env"""
    await update(mode="off")
    assert get_vision_settings().mode == "off"
    await update(mode="auto")


async def test_runtime_vision_settings_sidecar_du_3_field_moi_tinh_la_cau_hinh_key_round_trip_qua_ma_hoa(
    settings_env: SettingsEnv,
) -> None:
    """sidecar đủ 3 field mới tính là cấu hình; key round-trip qua mã hóa"""
    await update(sidecar_base_url="https://gemini.test/v1beta/openai")
    assert is_sidecar_configured() is False, "mới có base URL - chưa đủ"

    await update(sidecar_model="gemini-3.5-flash-lite", sidecar_api_key="AIza-secret")
    s = get_vision_settings()
    assert is_sidecar_configured(s) is True
    assert s.sidecar.api_key == "AIza-secret", "key giải mã lại đúng nguyên văn"
    stored = (await settings_env.store.load_all(FAKE_CLINIC_ID))["vision_sidecar_api_key"]
    assert "AIza-secret" not in stored


async def test_runtime_vision_settings_api_view_mask_key_khong_lo_plaintext(
    settings_env: SettingsEnv,
) -> None:
    """API view mask key, không lộ plaintext"""
    await update(
        sidecar_base_url="https://gemini.test/v1beta/openai",
        sidecar_model="gemini-3.5-flash-lite",
        sidecar_api_key="AIza-secret",
    )
    view = get_vision_settings_for_api()
    assert view.sidecar.api_key_masked != "AIza-secret"
    assert view.sidecar.configured is True
    assert view.sidecar.has_api_key is True
    assert "AIza-secret" not in repr(view)


async def test_runtime_vision_settings_clear_sidecar_settings_xoa_sach_ca_key(
    settings_env: SettingsEnv,
) -> None:
    """clearSidecarSettings xóa sạch cả key - đường duy nhất gỡ key vì PATCH quy ước giữ key cũ"""
    await update(
        sidecar_base_url="https://gemini.test/v1beta/openai",
        sidecar_model="gemini-3.5-flash-lite",
        sidecar_api_key="AIza-can-xoa",
    )
    assert is_sidecar_configured() is True

    after = await clear_sidecar_settings(FAKE_CLINIC_ID)
    assert is_sidecar_configured(after) is False
    assert after.sidecar.base_url == ""
    assert after.sidecar.model == ""
    assert after.sidecar.api_key == "", "key phải bị gỡ khỏi DB"
    # The mode is untouched: removing the sidecar is not changing how vision is detected
    assert after.mode == get_vision_settings().mode


async def test_runtime_vision_settings_chuoi_rong_tuong_minh_xoa_field_quay_ve_env_sidecar_tat(
    settings_env: SettingsEnv,
) -> None:
    """chuỗi rỗng tường minh xóa field, quay về env (rỗng) -> sidecar tắt"""
    await update(sidecar_base_url="https://x.test/v1", sidecar_model="m", sidecar_api_key="k")
    await update(sidecar_api_key="")
    assert is_sidecar_configured() is False
    await update(sidecar_base_url="", sidecar_model="")
    s = get_vision_settings()
    assert s.sidecar.base_url == ""
    assert s.sidecar.model == ""

# ported from: src/config/runtime-llm-settings.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced differences: the DB is the in-memory snapshot of one clinic (``settings_env``), the update is async, and
"the key in the DB is ciphertext" is checked on the raw value stored in the store.
"""

from __future__ import annotations

import pytest

from pema.config.runtime_llm_settings import (
    UNSET,
    LlmSettingsUpdate,
    clear_llm_settings,
    get_effective_llm_settings,
    mask_api_key,
    update_llm_settings,
)
from pema.config.testing_settings import SettingsEnv
from pema_contracts.agents import LlmProviderKind
from pema_contracts.testing import FAKE_CLINIC_ID


@pytest.fixture
def env(settings_env: SettingsEnv) -> SettingsEnv:
    settings_env.set_env(
        LLM_PROVIDER="anthropic",
        LLM_MODEL="env-model",
        LLM_BASE_URL="https://env.test/v1",
        LLM_API_KEY="sk-env-key-123456",
    )
    return settings_env


async def update(**fields: object) -> None:
    await update_llm_settings(FAKE_CLINIC_ID, LlmSettingsUpdate(**fields))  # type: ignore[arg-type]


async def test_runtime_llm_settings_chua_co_override_thi_tra_nguyen_cau_hinh_env(env: SettingsEnv) -> None:
    """chưa có override thì trả nguyên cấu hình env"""
    s = get_effective_llm_settings()
    assert s.provider is LlmProviderKind.ANTHROPIC
    assert s.model == "env-model"
    assert s.api_key == "sk-env-key-123456"
    assert s.has_override is False


async def test_runtime_llm_settings_override_model_provider_de_len_env_field_khong_set_giu_nguyen(
    env: SettingsEnv,
) -> None:
    """override model + provider đè lên env, field không set giữ nguyên env"""
    await update(model="db-model", provider=LlmProviderKind.OPENAI_COMPATIBLE, base_url="https://r.test/v1")
    s = get_effective_llm_settings()
    assert s.model == "db-model"
    assert s.provider is LlmProviderKind.OPENAI_COMPATIBLE
    assert s.base_url == "https://r.test/v1"
    assert s.api_key == "sk-env-key-123456", "key chưa override phải giữ từ env"
    assert s.has_override is True


async def test_runtime_llm_settings_api_key_luu_db_duoc_ma_hoa_doc_lai_giai_ma_dung(env: SettingsEnv) -> None:
    """API key lưu DB được mã hóa, đọc lại giải mã đúng"""
    await update(api_key="sk-db-secret-789")
    # In the DB it must be ciphertext, not plaintext
    raw = (await env.store.load_all(FAKE_CLINIC_ID))["llm_api_key"]
    assert "sk-db-secret" not in raw, "key trong DB không được là plaintext"
    assert get_effective_llm_settings().api_key == "sk-db-secret-789"


async def test_runtime_llm_settings_api_key_rong_trong_update_giu_key_hien_tai(env: SettingsEnv) -> None:
    """apiKey rỗng trong update = giữ key hiện tại"""
    await update(api_key="sk-db-secret-789")
    await update(api_key="", model="db-model-2")
    s = get_effective_llm_settings()
    assert s.api_key == "sk-db-secret-789"
    assert s.model == "db-model-2"


async def test_runtime_llm_settings_clear_llm_settings_xoa_het_override_quay_ve_env(env: SettingsEnv) -> None:
    """clearLlmSettings xóa hết override, quay về env"""
    await update(model="x", api_key="sk-x")
    await clear_llm_settings(FAKE_CLINIC_ID)
    s = get_effective_llm_settings()
    assert s.model == "env-model"
    assert s.api_key == "sk-env-key-123456"
    assert s.has_override is False


def test_runtime_llm_settings_mask_api_key_du_nhan_dien_nhung_khong_dung_lai_duoc() -> None:
    """maskApiKey đủ nhận diện nhưng không dùng lại được"""
    assert mask_api_key("sk-abcdefghijklmnop") == "sk-ab...mnop"
    assert mask_api_key("ngan") == "***"


# Base URL only means something for ``openai-compatible``. Not telling "keep" from "delete" leaves the base URL
# of the old vendor in the DB for ever: switching to Anthropic/Google and back shows the abandoned vendor's
# endpoint in the field, read as a broken dashboard. Reported 06/08/2026.


async def test_update_llm_settings_unset_la_giu_nguyen_base_url_dang_luu(env: SettingsEnv) -> None:
    """undefined = GIỮ NGUYÊN base URL đang lưu"""
    await update(base_url="https://router.test/v1")
    await update(model="doi-model-thoi")
    assert get_effective_llm_settings().base_url == "https://router.test/v1"
    assert LlmSettingsUpdate().base_url is UNSET


async def test_update_llm_settings_none_la_xoa_han_roi_ve_env(env: SettingsEnv) -> None:
    """null = XÓA hẳn, rơi về env"""
    await update(base_url="https://router.test/v1")
    assert get_effective_llm_settings().base_url == "https://router.test/v1"
    await update(base_url=None)
    # Deletes the OVERRIDE and does not swallow the server config: it must fall back to the environment
    assert get_effective_llm_settings().base_url == "https://env.test/v1"


async def test_update_llm_settings_xoa_roi_luu_lai_duoc_khong_phai_duong_mot_chieu(env: SettingsEnv) -> None:
    """xóa rồi lưu lại được - không phải đường một chiều"""
    await update(base_url=None)
    await update(base_url="https://khac.test/v1")
    assert get_effective_llm_settings().base_url == "https://khac.test/v1"
    await update(base_url=None)


async def test_update_llm_settings_xoa_base_url_khong_dung_toi_model_hay_api_key(env: SettingsEnv) -> None:
    """xóa base URL KHÔNG đụng tới model hay API key"""
    await update(base_url="https://router.test/v1", model="m-1", api_key="sk-giu-lai")
    await update(base_url=None)
    s = get_effective_llm_settings()
    assert s.model == "m-1"
    assert s.api_key == "sk-giu-lai"

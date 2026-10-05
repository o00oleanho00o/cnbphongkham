# ported from: src/config/decrypt-failure.test.ts
"""Changing the encryption key AFTER an API key was saved on the dashboard must NOT kill the agent turn nor the
overview page.

``decrypt_secret`` raises with a wrong key, and ``get_effective_llm_settings`` sits on the path of EVERY turn and
of the Overview page. Before the fix: an agent turn got a plain ``Error`` classified ``unknown`` and the sender
read "please message again in a few minutes" for a PERMANENT state; the dashboard returned 500 on the first page
one opens to understand what is happening.

The original ran child processes because ``env.ts`` froze ``process.env`` at import. Here the settings are
re-read after ``cache_clear`` so the key can change inside the process. The overview-page case belongs to
``admin_usage`` (``get_system_info`` there reads the same ``get_effective_llm_settings``) and is tested with it.
"""

from __future__ import annotations

import pytest

from pema.agent.llm_config_error import LoiCauHinhLlm
from pema.agent.llm_provider import resolve_language_model
from pema.agent.provider_error_classifier import phan_loai_loi_provider
from pema.config.runtime_llm_settings import (
    LlmSettingsUpdate,
    get_effective_llm_settings,
    update_llm_settings,
)
from pema.config.testing_settings import SettingsEnv
from pema_contracts.agents import LlmProviderKind
from pema_contracts.testing import FAKE_CLINIC_ID
from pema_contracts.turn_errors import ProviderErrorKind


@pytest.fixture
async def saved_with_key_a(settings_env: SettingsEnv) -> SettingsEnv:
    await update_llm_settings(
        FAKE_CLINIC_ID,
        LlmSettingsUpdate(
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            base_url="https://r.test/v1",
            model="m",
            api_key="sk-that",
        ),
    )
    settings_env.change_encryption_key("b" * 64)  # the key is replaced after saving
    return settings_env


async def test_doi_khoa_ma_hoa_get_effective_llm_settings_khong_nem_va_danh_dau_api_key_hong(
    saved_with_key_a: SettingsEnv,
) -> None:
    """getEffectiveLlmSettings KHÔNG ném, và đánh dấu apiKeyHong"""
    c = get_effective_llm_settings()
    assert c.api_key_hong is True, "phải đánh dấu là hỏng"
    assert c.api_key == "", (
        "KHÔNG được âm thầm rơi về .env - bot sẽ chạy bằng khóa khác khóa người dùng vừa nhập"
    )
    assert c.model == "m", "phần không mã hóa vẫn phải đọc được"


async def test_doi_khoa_ma_hoa_luot_agent_bao_dung_benh_khong_phai_cau_thu_lai_sau(
    saved_with_key_a: SettingsEnv,
) -> None:
    """lượt agent báo ĐÚNG bệnh, không phải câu 'thử lại sau'"""
    with pytest.raises(LoiCauHinhLlm) as caught:
        resolve_language_model(None)
    assert phan_loai_loi_provider(caught.value) is ProviderErrorKind.CONFIG
    # Saying the wrong disease sends the user to re-enter the key when the root cause is the changed encryption
    # key (and then the Zalo cookies are broken too)
    assert "PEMA_SECRET_ENCRYPTION_KEY" in str(caught.value), "câu lỗi phải chỉ đúng gốc rễ"

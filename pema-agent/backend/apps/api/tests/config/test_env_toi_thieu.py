# ported from: src/config/env-toi-thieu.test.ts
"""Only the encryption key is mandatory, and a missing LLM configuration is reported by the AGENT TURN, not at boot.

Everything else is configurable on the dashboard and the dashboard overrides the environment. The accompanying
invariant: missing LLM configuration must NOT kill the process at boot: the dashboard must be reachable to enter
it, and a boot failure leaves no dashboard to open. The error must fire on the first agent turn with a sentence
that points to the place to enter it.

The original had to run child processes (``env.ts`` froze ``process.env`` at import, so editing it in a test
measured something that did not exist). ``pydantic-settings`` re-reads after ``cache_clear``, so the SAME
behaviour is measured in-process: building the settings with the minimal environment, then the model resolution.
"""

from __future__ import annotations

import pytest

from pema.agent.llm_config_error import LoiCauHinhLlm
from pema.agent.llm_provider import resolve_language_model
from pema.config.env import get_settings
from pema.config.env_llm import get_llm_env
from pema.config.secret_cipher import SecretKeyMissingError, encrypt_secret
from pema.config.testing_settings import SettingsEnv


def test_env_toi_thieu_nap_duoc_settings_va_llm_env_voi_dung_mot_bien_khong_chet(
    settings_env: SettingsEnv,
) -> None:
    """nạp được env.ts với ĐÚNG một biến, không process.exit"""
    assert get_settings().secret_encryption_key is not None
    llm = get_llm_env()
    assert llm.LLM_MODEL == ""
    assert llm.LLM_API_KEY == ""
    assert llm.LLM_BASE_URL is None


def test_env_toi_thieu_thieu_khoa_ma_hoa_thi_chan_khi_dung_den_no_khong_nam_tren_dashboard_duoc(
    settings_env: SettingsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THIẾU khóa mã hóa thì vẫn chết lúc boot - nó không nằm trên dashboard được

    Control: proves the case above is not "the schema stopped checking everything". Here a missing key surfaces
    the moment a secret is encrypted or decrypted (a process that never touches a secret needs none).
    """
    monkeypatch.delenv("PEMA_SECRET_ENCRYPTION_KEY")
    get_settings.cache_clear()
    with pytest.raises(SecretKeyMissingError, match=r"PEMA_SECRET_ENCRYPTION_KEY"):
        encrypt_secret("sk-x")


# Missing LLM configuration is reported at the TURN, with a sentence pointing at the right place.


def test_thieu_cau_hinh_llm_chua_cau_hinh_gi_luot_dau_bao_loi_chi_thang_vao_trang_providers(
    settings_env: SettingsEnv,
) -> None:
    """chưa cấu hình gì: boot xong, lượt đầu báo lỗi chỉ thẳng vào trang Providers"""
    with pytest.raises(LoiCauHinhLlm, match=r"Providers"):
        resolve_language_model(None)


def test_thieu_cau_hinh_llm_co_key_nhung_thieu_model_cau_loi_noi_ve_model(settings_env: SettingsEnv) -> None:
    """có key nhưng THIẾU MODEL: câu lỗi nói về model, không phải lỗi HTTP khó hiểu

    Before, ``LLM_MODEL`` was ``.min(1)`` so missing it killed the boot and nobody could open the dashboard.
    """
    settings_env.set_env(LLM_API_KEY="sk-thu", LLM_BASE_URL="https://r.test/v1")
    with pytest.raises(LoiCauHinhLlm, match=r"(?i)model"):
        resolve_language_model(None)


def test_thieu_cau_hinh_llm_co_key_va_model_nhung_thieu_base_url_cung_bao_o_luot(
    settings_env: SettingsEnv,
) -> None:
    """có key và model nhưng THIẾU BASE URL: cũng báo ở lượt, không chặn boot

    The old cross rule of ``env.ts`` blocked boot on a missing base URL, but the base URL is enterable on the
    dashboard, so blocking boot blocks exactly the person who must open it to enter it.
    """
    settings_env.set_env(LLM_API_KEY="sk-thu", LLM_MODEL="gpt-combo")
    with pytest.raises(LoiCauHinhLlm, match=r"(?i)base URL"):
        resolve_language_model(None)


def test_thieu_cau_hinh_llm_du_ca_ba_thi_dung_duoc_model_khong_nem(settings_env: SettingsEnv) -> None:
    """đủ cả ba thì dựng được model, không ném"""
    settings_env.set_env(LLM_API_KEY="sk-thu", LLM_MODEL="gpt-combo", LLM_BASE_URL="https://r.test/v1")
    model = resolve_language_model(None)
    assert model.model_id == "gpt-combo"

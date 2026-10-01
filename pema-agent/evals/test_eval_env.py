# ported from: none (tests of ``eval_env`` and the ``read_real_*`` modules, which the original left untested)
"""The configuration the evals run with: the DB OVER the environment (the lesson of the first false alarm), the
overrides that make the run match production, and the stop when something is missing.

No database: the real-settings loader is injected. The key is a synthetic one.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from evals.eval_env import EVAL_TUNING_OVERRIDES, dung_eval_env
from evals.read_real_llm_settings import SettingsLoader, doc_llm_tu_db_that, real_settings_loader
from evals.read_real_search_settings import doc_tra_cuu_tu_db_that
from pema.config import env as env_module
from pema.config.env_llm import get_llm_env
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.config.secret_cipher_core import encrypt_with

KEY = "b" * 64
OTHER_KEY = "c" * 64


def loader_of(rows: dict[str, str]) -> SettingsLoader:
    async def load() -> dict[str, str]:
        return rows

    return load


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    for name in (
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
        "PEMA_EVAL_DATABASE_URL",
        "PEMA_EVAL_CLINIC_ID",
        "PEMA_SECRET_ENCRYPTION_KEY",
        *EVAL_TUNING_OVERRIDES,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()
    yield
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()


def test_real_settings_loader_khong_cau_hinh_thi_none_roi_ve_moi_truong() -> None:
    """no URL or no clinic id means "no DB yet", the normal case of a fresh machine"""
    assert real_settings_loader() is None


def test_real_settings_loader_clinic_id_hong_thi_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEMA_EVAL_DATABASE_URL", "postgresql+asyncpg://u:p@localhost/x")
    monkeypatch.setenv("PEMA_EVAL_CLINIC_ID", "khong-phai-uuid")
    assert real_settings_loader() is None


async def test_doc_llm_tu_db_that_giai_ma_key_va_ghi_nguon_da_thang() -> None:
    """DB values are read, the key is decrypted, and the fields that came from the DB are listed"""
    rows = {
        "llm_provider": "openai-compatible",
        "llm_base_url": "http://localhost:11434/v1",
        "llm_model": "qwen3:8b",
        "llm_api_key": encrypt_with(KEY, "synthetic-key"),
    }
    got = await doc_llm_tu_db_that(loader_of(rows), KEY)

    assert (got.provider, got.base_url, got.model, got.api_key) == (
        "openai-compatible",
        "http://localhost:11434/v1",
        "qwen3:8b",
        "synthetic-key",
    )
    assert got.tu_db == ["provider", "baseUrl", "model", "apiKey"]


async def test_doc_llm_tu_db_that_sai_khoa_ma_hoa_thi_bo_qua_key_khong_bao_loi() -> None:
    """a wrong encryption key skips the key and falls back to the environment's, with no error"""
    rows = {"llm_model": "m", "llm_api_key": encrypt_with(KEY, "synthetic-key")}
    got = await doc_llm_tu_db_that(loader_of(rows), OTHER_KEY)

    assert got.api_key is None
    assert got.tu_db == ["model"]


async def test_doc_llm_tu_db_that_khong_co_khoa_ma_hoa_thi_bo_qua_key() -> None:
    rows = {"llm_api_key": encrypt_with(KEY, "synthetic-key")}
    got = await doc_llm_tu_db_that(loader_of(rows), None)
    assert got.api_key is None


async def test_doc_llm_tu_db_that_db_loi_thi_roi_ve_moi_truong() -> None:
    """a DB that cannot be read (old schema, locked) is not an error: the environment is used"""

    async def broken() -> dict[str, str]:
        raise ConnectionError("db down")

    got = await doc_llm_tu_db_that(broken, KEY)
    assert got.tu_db == []
    assert got.model is None


async def test_doc_tra_cuu_tu_db_that_doc_provider_va_giai_ma_khoa_brave() -> None:
    rows = {"search_provider": "brave", "search_brave_api_key": encrypt_with(KEY, "synthetic-brave")}
    got = await doc_tra_cuu_tu_db_that(loader_of(rows), KEY)

    assert got.provider == "brave"
    assert got.brave_api_key == "synthetic-brave"
    assert got.tu_db == ["searchProvider", "braveKey"]


async def test_doc_tra_cuu_tu_db_that_sai_khoa_ma_hoa_thi_van_doc_provider() -> None:
    rows = {"search_provider": "brave", "search_brave_api_key": encrypt_with(KEY, "synthetic-brave")}
    got = await doc_tra_cuu_tu_db_that(loader_of(rows), OTHER_KEY)

    assert got.provider == "brave"
    assert got.brave_api_key is None


async def test_dung_eval_env_db_de_moi_truong(monkeypatch: pytest.MonkeyPatch) -> None:
    """the DB wins over the environment (the exact production rule), and the source is reported"""
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_MODEL", "model-cu-con-sot-trong-env")
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://env.example.test/v1")
    rows = {"llm_model": "model-that-tren-dashboard"}

    res = await dung_eval_env(loader_of(rows), KEY)
    try:
        assert res.ok is True
        assert res.llm is not None
        assert res.llm.model == "model-that-tren-dashboard"
        assert res.llm.tu_db == ["model"]
        assert os.environ["LLM_MODEL"] == "model-that-tren-dashboard"
    finally:
        assert res.restore is not None
        res.restore()
    assert os.environ["LLM_MODEL"] == "model-cu-con-sot-trong-env", "restore puts the environment back"


async def test_dung_eval_env_ap_override_khop_production_roi_tra_lai(monkeypatch: pytest.MonkeyPatch) -> None:
    """the output-token ceiling, the trace flag and the shorter turn timeout are applied, then restored"""
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")

    res = await dung_eval_env(loader_of({}), KEY)
    assert res.restore is not None
    try:
        assert get_tuning_int("LLM_MAX_OUTPUT_TOKENS") == 16384
        assert get_tuning_int("LLM_TURN_TIMEOUT_MS") == 180000
        assert get_tuning_int("SEND_DELAY_MIN_MS") == 0
    finally:
        res.restore()
    assert "LLM_TURN_TIMEOUT_MS" not in os.environ
    assert get_tuning_int("LLM_TURN_TIMEOUT_MS") != 180000


async def test_dung_eval_env_thieu_api_key_thi_dung_va_nhac_ollama() -> None:
    res = await dung_eval_env(loader_of({}), KEY)
    assert res.ok is False
    assert "Thiếu API key" in res.loi
    assert "ollama" in res.loi


async def test_dung_eval_env_thieu_model_thi_dung(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    res = await dung_eval_env(loader_of({}), KEY)
    assert res.ok is False
    assert "LLM_MODEL" in res.loi


async def test_dung_eval_env_openai_compatible_thieu_base_url_thi_dung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    monkeypatch.setenv("LLM_MODEL", "m")
    res = await dung_eval_env(loader_of({}), KEY)
    assert res.ok is False
    assert "LLM_BASE_URL" in res.loi

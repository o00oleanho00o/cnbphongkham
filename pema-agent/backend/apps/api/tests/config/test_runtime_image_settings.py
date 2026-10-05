# ported from: src/config/runtime-image-settings.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from pema.config import env as env_module
from pema.config import runtime_image_settings as store
from pema.config.runtime_image_settings import ImageSettingsUpdate
from pema.config.runtime_settings_kv import (
    InMemoryRuntimeSettingsKv,
    get_runtime_settings_kv,
    install_runtime_settings_kv,
    reset_runtime_settings_kv,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "c" * 64)
    for name in ("IMAGE_GEN_BASE_URL", "IMAGE_GEN_MODEL", "IMAGE_GEN_API_KEY"):
        monkeypatch.setenv(name, "")
    env_module.get_settings.cache_clear()
    reset_runtime_settings_kv()
    yield
    reset_runtime_settings_kv()
    env_module.get_settings.cache_clear()


async def test_runtime_image_settings_nothing_in_db_and_empty_env_is_not_configured() -> None:
    """chưa có gì trong DB và env trống: chưa cấu hình"""
    assert store.is_image_gen_configured() is False


async def test_runtime_image_settings_needs_all_three_fields_and_the_key_round_trips_through_encryption() -> (
    None
):
    """đủ 3 field mới tính là cấu hình; key round-trip qua mã hóa"""
    await store.update_image_settings(ImageSettingsUpdate(base_url="https://9router.test"))
    assert store.is_image_gen_configured() is False, "mới có base URL - chưa đủ"

    await store.update_image_settings(ImageSettingsUpdate(model="cx/gpt-5.5-image"))
    assert store.is_image_gen_configured() is False, "thiếu key - chưa đủ"

    await store.update_image_settings(ImageSettingsUpdate(api_key="sk-bi-mat"))
    s = store.get_image_settings()
    assert store.is_image_gen_configured(s) is True
    assert s.api_key == "sk-bi-mat", "key giải mã lại đúng nguyên văn"
    stored = get_runtime_settings_kv().get(store.API_KEY_KEY)
    assert stored is not None
    assert "sk-bi-mat" not in stored, "key nằm trong bảng ở dạng mã hóa"


async def test_runtime_image_settings_api_view_masks_the_key_and_never_leaks_plaintext() -> None:
    """API view mask key, không lộ plaintext"""
    await store.update_image_settings(
        ImageSettingsUpdate(base_url="https://9router.test", model="cx/gpt-5.5-image", api_key="sk-bi-mat")
    )
    view = store.get_image_settings_for_api()
    assert view.api_key_masked != "sk-bi-mat"
    assert view.has_api_key is True
    assert view.configured is True
    assert view.enabled is True
    assert view.has_override is True
    assert "sk-bi-mat" not in json.dumps(view.__dict__)


async def test_runtime_image_settings_api_view_without_a_key_says_so_with_a_separate_flag() -> None:
    """cờ has_api_key riêng vì api_key_masked KHÔNG BAO GIỜ rỗng"""
    view = store.get_image_settings_for_api()
    assert view.api_key_masked == "chưa cấu hình"
    assert view.has_api_key is False
    assert view.configured is False
    assert view.has_override is False


async def test_runtime_image_settings_clear_image_settings_removes_the_key_too() -> None:
    """clearImageSettings xóa sạch cả key - đường duy nhất gỡ key vì PATCH quy ước giữ key cũ"""
    await store.update_image_settings(
        ImageSettingsUpdate(base_url="https://9router.test", model="m", api_key="sk-bi-mat")
    )
    await store.clear_image_settings()
    s = store.get_image_settings()
    assert s.api_key == ""
    assert s.base_url == ""
    assert s.model == ""
    assert store.is_image_gen_configured(s) is False


async def test_runtime_image_settings_explicit_empty_string_deletes_the_field_and_falls_back_to_env() -> None:
    """chuỗi rỗng tường minh = xóa field, quay về env"""
    await store.update_image_settings(
        ImageSettingsUpdate(base_url="https://tam.test", model="m", api_key="k")
    )
    await store.update_image_settings(ImageSettingsUpdate(base_url=""))
    assert store.get_image_settings().base_url == "", "về env (đang trống)"
    await store.clear_image_settings()


async def test_runtime_image_settings_omitting_api_key_in_an_update_keeps_the_old_key() -> None:
    """bỏ trống apiKey trong update = GIỮ key cũ, không xóa"""
    await store.update_image_settings(
        ImageSettingsUpdate(base_url="https://9router.test", model="cx/gpt-5.5-image", api_key="sk-giu-lai")
    )
    await store.update_image_settings(ImageSettingsUpdate(model="cx/gpt-5.3-image"))
    assert store.get_image_settings().api_key == "sk-giu-lai"
    await store.clear_image_settings()


async def test_runtime_image_settings_env_is_read_at_call_time_and_the_db_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ưu tiên DB -> env, env đọc lúc gọi (không chụp sẵn lúc import)"""
    monkeypatch.setenv("IMAGE_GEN_BASE_URL", "https://env.test")
    monkeypatch.setenv("IMAGE_GEN_MODEL", "env-model")
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "sk-env")
    assert store.get_image_settings() == store.ImageGenSettings("https://env.test", "env-model", "sk-env")

    await store.update_image_settings(ImageSettingsUpdate(model="db-model"))
    assert store.get_image_settings().model == "db-model"
    assert store.get_image_settings().base_url == "https://env.test"


async def test_runtime_image_settings_unreadable_stored_key_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """key hỏng (đổi khóa mã hóa) - rơi về env thay vì chết tool"""
    await store.update_image_settings(ImageSettingsUpdate(api_key="sk-bi-mat"))
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "d" * 64)
    env_module.get_settings.cache_clear()
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "sk-env")
    assert store.get_image_settings().api_key == "sk-env"


async def test_runtime_image_settings_reads_go_through_the_installed_kv() -> None:
    """đọc đồng bộ qua KV đã cài (snapshot do provider DB cấp)"""
    install_runtime_settings_kv(InMemoryRuntimeSettingsKv({store.MODEL_KEY: "from-snapshot"}))
    assert store.get_image_settings().model == "from-snapshot"

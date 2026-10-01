# ported from: src/config/runtime-tool-settings.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original tests run in order on one shared database; here each test starts from an empty store and sets up
the state it needs, so the order does not matter.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

from pema.config import env as env_module
from pema.config import runtime_tool_settings as store
from pema.config.runtime_settings_kv import get_runtime_settings_kv, reset_runtime_settings_kv
from pema.config.runtime_tool_settings import FetchSettingsUpdate, SearchSettingsUpdate
from pema_contracts.errors import DomainError, ErrorCode


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "e" * 64)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("WEB_FETCH_FALLBACK_ENABLED", raising=False)
    env_module.get_settings.cache_clear()
    reset_runtime_settings_kv()
    yield
    reset_runtime_settings_kv()
    env_module.get_settings.cache_clear()


async def _with_brave_key() -> None:
    await store.update_search_settings(
        SearchSettingsUpdate(provider="brave", brave_api_key="BSA-secret-key-123")
    )


async def test_runtime_tool_settings_default_is_duckduckgo_without_key_web_search_never_unconfigured() -> (
    None
):
    """mặc định là duckduckgo, chưa có key - web search không bao giờ 'chưa cấu hình'"""
    settings = store.get_search_settings()
    assert settings.provider == "duckduckgo"
    assert settings.brave_api_key == ""


async def test_runtime_tool_settings_choosing_brave_without_a_key_is_blocked_at_the_store() -> None:
    """chọn brave khi chưa có key thì bị chặn ngay ở store"""
    with pytest.raises(DomainError, match=r"API key Brave") as info:
        await store.update_search_settings(SearchSettingsUpdate(provider="brave"))
    assert info.value.code is ErrorCode.VALIDATION_FAILED
    assert store.get_search_settings().provider == "duckduckgo"


async def test_runtime_tool_settings_with_a_key_brave_can_be_enabled_and_the_key_reads_back_encrypted() -> (
    None
):
    """có key thì bật được brave, key lưu mã hóa nhưng đọc lại đúng"""
    nxt = await store.update_search_settings(
        SearchSettingsUpdate(provider="brave", brave_api_key="BSA-secret-key-123")
    )
    assert nxt.provider == "brave"
    assert nxt.brave_api_key == "BSA-secret-key-123"
    stored = get_runtime_settings_kv().get(store.BRAVE_KEY)
    assert stored is not None
    assert "BSA-secret" not in stored


async def test_runtime_tool_settings_api_shape_is_always_masked_and_never_leaks_the_full_key() -> None:
    """dạng trả về API luôn masked, không bao giờ lộ key đầy đủ"""
    await _with_brave_key()
    api = store.get_search_settings_for_api()
    assert api.has_brave_api_key is True
    assert "secret" not in api.brave_api_key_masked, "không được lộ ruột key"
    assert re.search(r"\.\.\.", api.brave_api_key_masked)


async def test_runtime_tool_settings_changing_only_the_provider_keeps_the_old_key() -> None:
    """đổi mỗi provider (không truyền key) thì giữ nguyên key cũ"""
    await _with_brave_key()
    await store.update_search_settings(SearchSettingsUpdate(provider="duckduckgo"))
    assert store.get_search_settings().brave_api_key == "BSA-secret-key-123"
    assert (await store.update_search_settings(SearchSettingsUpdate(provider="brave"))).provider == "brave"


async def test_runtime_tool_settings_deleting_the_key_drops_back_to_duckduckgo() -> None:
    """xóa key thì tự hạ về duckduckgo, không kẹt ở brave với key rỗng"""
    await _with_brave_key()
    nxt = await store.update_search_settings(SearchSettingsUpdate(brave_api_key=""))
    assert nxt.brave_api_key == ""
    assert nxt.provider == "duckduckgo"


async def test_runtime_tool_settings_brave_key_falls_back_to_env_read_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """key Brave hiệu lực: DB đè lên env; env đọc lúc gọi"""
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-from-env")
    assert store.get_brave_api_key() == "BSA-from-env"
    await _with_brave_key()
    assert store.get_brave_api_key() == "BSA-secret-key-123"


async def test_runtime_tool_settings_fetch_fallback_defaults_to_on_and_follows_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """chưa đặt trong DB thì theo env (mặc định bật)"""
    assert store.get_fetch_settings().fallback_enabled is True
    monkeypatch.setenv("WEB_FETCH_FALLBACK_ENABLED", "false")
    assert store.get_fetch_settings().fallback_enabled is False
    monkeypatch.setenv("WEB_FETCH_FALLBACK_ENABLED", "")
    assert store.get_fetch_settings().fallback_enabled is True


async def test_runtime_tool_settings_fetch_fallback_set_in_the_db_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """đặt rồi thì DB thắng"""
    monkeypatch.setenv("WEB_FETCH_FALLBACK_ENABLED", "true")
    assert (
        await store.update_fetch_settings(FetchSettingsUpdate(fallback_enabled=False))
    ).fallback_enabled is False
    assert store.get_fetch_settings().fallback_enabled is False
    assert (await store.update_fetch_settings(FetchSettingsUpdate())).fallback_enabled is False
    assert (
        await store.update_fetch_settings(FetchSettingsUpdate(fallback_enabled=True))
    ).fallback_enabled is True

# ported from: src/config/runtime-tool-settings.ts
"""Cấu hình các tool web sửa được từ dashboard (nút Settings trên dòng tool ở
trang Tools), lưu trong bảng runtime_settings dùng chung. Key Brave mã hóa
AES-256-GCM như key LLM.

Cả hai tool đều là CHUỖI có thứ tự (mô hình Extractor Chain của GoClaw):
thử từ trên xuống tới khi có kết quả dùng được. Bậc CUỐI của mỗi chuỗi
không tắt được - nhờ vậy tool không bao giờ rơi vào trạng thái "chưa cấu
hình": web_search luôn còn DuckDuckGo, web_fetch luôn còn tầng tự tải.

Forced deviations: the SQLite prepared statements become ``pema.config.runtime_settings_kv`` (reads stay
SYNCHRONOUS from an in-memory snapshot, the ``update_*`` writes are ``async``).
``env.BRAVE_SEARCH_API_KEY`` and ``env.WEB_FETCH_FALLBACK_ENABLED`` are not tuning keys, so they are read
with ``os.environ.get(<original unprefixed name>)`` AT CALL TIME in the accessors below (the zod
``stringbool`` default of ``true`` is kept). The original ``throw new Error`` for "brave without a key"
is ``DomainError(VALIDATION_FAILED, ...)`` (the route maps it to 422).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from pema.config.runtime_settings_kv import get_runtime_settings_kv
from pema.config.secret_cipher import decrypt_secret, encrypt_secret, mask_secret
from pema_contracts.errors import DomainError, ErrorCode

SearchProvider = Literal["duckduckgo", "brave"]


@dataclass(frozen=True)
class SearchSettings:
    provider: SearchProvider
    brave_api_key: str
    """Rỗng nghĩa là chưa có key ở cả DB lẫn env"""


PROVIDER_KEY = "search_provider"
BRAVE_KEY = "search_brave_api_key"

_FALSE_WORDS = frozenset({"false", "0", "no", "off", "n", "disabled"})


def _env_brave_api_key() -> str:
    return os.environ.get("BRAVE_SEARCH_API_KEY", "")


def _env_web_fetch_fallback_enabled() -> bool:
    raw = os.environ.get("WEB_FETCH_FALLBACK_ENABLED", "").strip().lower()
    # Empty or unset: the default of the original (true). The original refused to boot on an unknown word;
    # here it falls back to the default too.
    return raw not in _FALSE_WORDS


def _read(key: str) -> str | None:
    return get_runtime_settings_kv().get(key)


def get_brave_api_key() -> str:
    """Key Brave hiệu lực: DB (nhập từ dashboard) đè lên env"""
    stored = _read(BRAVE_KEY)
    if stored:
        try:
            return decrypt_secret(stored)
        except Exception:
            # Key hỏng (đổi PEMA_SECRET_ENCRYPTION_KEY) - rơi về env thay vì chết tool
            return _env_brave_api_key()
    return _env_brave_api_key()


def get_search_settings() -> SearchSettings:
    """Cấu hình đang hiệu lực. Chọn brave nhưng key biến mất (bị xóa tay trong DB,
    đổi khóa mã hóa) thì tự hạ về duckduckgo - thà tìm được bằng DDG còn hơn
    gọi Brave với key rỗng rồi lỗi."""
    brave_api_key = get_brave_api_key()
    stored = _read(PROVIDER_KEY)
    provider: SearchProvider = "brave" if stored == "brave" and brave_api_key else "duckduckgo"
    return SearchSettings(provider=provider, brave_api_key=brave_api_key)


@dataclass(frozen=True)
class SearchSettingsUpdate:
    provider: SearchProvider | None = None
    brave_api_key: str | None = None
    """Bỏ trống (None) = giữ key hiện tại; chuỗi rỗng tường minh = xóa key"""


async def update_search_settings(update: SearchSettingsUpdate) -> SearchSettings:
    """Ném lỗi khi chọn brave mà không có key - chặn ở tầng store để API và mọi
    caller khác đều dính cùng một luật."""
    kv = get_runtime_settings_kv()
    if update.brave_api_key is not None:
        if update.brave_api_key == "":
            await kv.adelete(BRAVE_KEY)
        else:
            await kv.aset(BRAVE_KEY, encrypt_secret(update.brave_api_key))

    if update.provider is not None:
        if update.provider == "brave" and not get_brave_api_key():
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, "Cần nhập API key Brave trước khi bật provider này"
            )
        await kv.aset(PROVIDER_KEY, update.provider)

    return get_search_settings()


@dataclass(frozen=True)
class SearchSettingsForApi:
    """Dạng an toàn để trả về dashboard - không bao giờ lộ key đầy đủ.

    Mapping to ``ToolChainSettings`` of ``web_search``: ``brave_api_key_set`` is ``has_brave_api_key``; the
    ``steps`` list (brave, duckduckgo; the last step is always enabled) is composed by the route from
    ``provider``.
    """

    provider: SearchProvider
    brave_api_key_masked: str
    has_brave_api_key: bool


def get_search_settings_for_api() -> SearchSettingsForApi:
    settings = get_search_settings()
    return SearchSettingsForApi(
        provider=settings.provider,
        brave_api_key_masked=mask_secret(settings.brave_api_key),
        has_brave_api_key=bool(settings.brave_api_key),
    )


# ===== web_fetch: chuỗi 2 tầng, tầng tự tải không tắt được =====

FETCH_FALLBACK_KEY = "fetch_fallback_enabled"


@dataclass(frozen=True)
class FetchSettings:
    fallback_enabled: bool
    """Bậc 2 (Jina Reader) - bậc 1 tự tải luôn bật, không có công tắc"""


@dataclass(frozen=True)
class FetchSettingsUpdate:
    """``Partial<FetchSettings>``"""

    fallback_enabled: bool | None = None


def get_fetch_settings() -> FetchSettings:
    stored = _read(FETCH_FALLBACK_KEY)
    # Chưa đặt trong DB thì theo env; đặt rồi thì DB thắng
    if stored is None:
        return FetchSettings(fallback_enabled=_env_web_fetch_fallback_enabled())
    return FetchSettings(fallback_enabled=stored == "true")


async def update_fetch_settings(update: FetchSettingsUpdate) -> FetchSettings:
    if update.fallback_enabled is not None:
        await get_runtime_settings_kv().aset(
            FETCH_FALLBACK_KEY, "true" if update.fallback_enabled else "false"
        )
    return get_fetch_settings()


def get_fetch_settings_for_api() -> FetchSettings:
    """Nothing secret in the fetch settings: the DTO is the settings themselves
    (``ToolChainSettings.fallback_enabled`` of ``web_fetch``)."""
    return get_fetch_settings()

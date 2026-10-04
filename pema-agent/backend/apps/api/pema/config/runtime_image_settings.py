# ported from: src/config/runtime-image-settings.ts
"""Cấu hình tool vẽ ảnh, sửa được từ modal Settings của dòng tool trên trang
Tools. Lưu bảng runtime_settings dùng chung, ưu tiên DB -> env, key mã hóa
AES-256-GCM (cùng luật với runtime-vision-settings).

Khác sidecar đọc ảnh ở một điểm quan trọng: KHÔNG tự dò được model. Endpoint
/v1/models của router chỉ liệt kê model chat - model vẽ ảnh nằm ở registry
Media Providers riêng nên không có ``capabilities`` để hỏi. Người dùng phải tự
gõ tên model, và kiểm chứng bằng nút Test (gọi thật một lần).

Forced deviations: the SQLite prepared statements become ``pema.config.runtime_settings_kv`` (reads stay
SYNCHRONOUS from an in-memory snapshot, the ``update_*`` / ``clear_*`` writes are ``async``).
``env.IMAGE_GEN_*`` are not tuning keys, so they are read with
``os.environ.get(<original unprefixed name>)`` AT CALL TIME in the small accessors below
(``IMAGE_GEN_BASE_URL`` is ignored when it does not start with ``http``, where the zod schema of the
original refused to boot). The image-generation tool is switched off in the ``patient_channel`` policy
profile by the policy layer, not here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pema.config.runtime_settings_kv import get_runtime_settings_kv
from pema.config.secret_cipher import decrypt_secret, encrypt_secret, mask_secret


@dataclass(frozen=True)
class ImageGenSettings:
    base_url: str
    model: str
    api_key: str


BASE_URL_KEY = "image_gen_base_url"
MODEL_KEY = "image_gen_model"
API_KEY_KEY = "image_gen_api_key"


def _env_base_url() -> str | None:
    value = os.environ.get("IMAGE_GEN_BASE_URL")
    if not value or not value.startswith("http"):
        return None
    return value


def _env_model() -> str:
    return os.environ.get("IMAGE_GEN_MODEL", "")


def _env_api_key() -> str:
    return os.environ.get("IMAGE_GEN_API_KEY", "")


def _read(key: str) -> str | None:
    return get_runtime_settings_kv().get(key)


def _read_api_key() -> str:
    stored = _read(API_KEY_KEY)
    if stored:
        try:
            return decrypt_secret(stored)
        except Exception:
            # Key hỏng (đổi PEMA_SECRET_ENCRYPTION_KEY) - rơi về env thay vì chết tool
            return _env_api_key()
    return _env_api_key()


def get_image_settings() -> ImageGenSettings:
    stored_base_url = _read(BASE_URL_KEY)
    stored_model = _read(MODEL_KEY)
    env_base_url = _env_base_url()
    return ImageGenSettings(
        base_url=stored_base_url if stored_base_url is not None else (env_base_url or ""),
        model=stored_model if stored_model is not None else _env_model(),
        api_key=_read_api_key(),
    )


def is_image_gen_configured(settings: ImageGenSettings | None = None) -> bool:
    """Vẽ được khi đủ cả 3: base URL + model + key"""
    resolved = settings if settings is not None else get_image_settings()
    return bool(resolved.base_url and resolved.model and resolved.api_key)


@dataclass(frozen=True)
class ImageSettingsUpdate:
    base_url: str | None = None
    """Chuỗi rỗng tường minh = xóa (quay về env)"""
    model: str | None = None
    api_key: str | None = None
    """Bỏ trống (None) = giữ key hiện tại; chuỗi rỗng tường minh = xóa key"""


async def _apply(key: str, value: str | None, *, encrypt: bool = False) -> None:
    if value is None:
        return
    kv = get_runtime_settings_kv()
    if value == "":
        await kv.adelete(key)
    else:
        await kv.aset(key, encrypt_secret(value) if encrypt else value)


async def update_image_settings(update: ImageSettingsUpdate) -> ImageGenSettings:
    await _apply(BASE_URL_KEY, update.base_url)
    await _apply(MODEL_KEY, update.model)
    await _apply(API_KEY_KEY, update.api_key, encrypt=True)
    return get_image_settings()


async def clear_image_settings() -> ImageGenSettings:
    """Xóa sạch cấu hình (gồm cả API key) - quay về env, thường là trống nghĩa là
    tắt hẳn tool. Cần hành động riêng vì đường PATCH quy ước "key bỏ trống = giữ
    key cũ", nên không có cách nào gỡ key qua PATCH từ UI."""
    kv = get_runtime_settings_kv()
    for key in (BASE_URL_KEY, MODEL_KEY, API_KEY_KEY):
        await kv.adelete(key)
    return get_image_settings()


@dataclass(frozen=True)
class ImageSettingsForApi:
    """Dạng an toàn trả về dashboard - không bao giờ lộ key đầy đủ.

    Mapping to ``ImageGenSettingsOut`` (``pema_contracts.admin_agent``): ``enabled`` is ``configured``,
    ``base_url``/``model``/``api_key_masked`` are the same, ``has_override`` is true when the database holds
    any of the three keys (the contract has no ``has_api_key``; ``has_api_key`` stays here for the UI rule
    below).
    """

    base_url: str
    model: str
    api_key_masked: str
    has_api_key: bool
    """Cờ riêng vì ``api_key_masked`` KHÔNG BAO GIỜ rỗng (trống thì ra "chưa cấu
    hình") - UI không thể suy ra "có key hay không" từ chuỗi mask"""
    configured: bool
    enabled: bool
    has_override: bool


def get_image_settings_for_api() -> ImageSettingsForApi:
    settings = get_image_settings()
    configured = is_image_gen_configured(settings)
    kv = get_runtime_settings_kv()
    return ImageSettingsForApi(
        base_url=settings.base_url,
        model=settings.model,
        api_key_masked=mask_secret(settings.api_key),
        has_api_key=bool(settings.api_key),
        configured=configured,
        enabled=configured,
        has_override=any(kv.get(key) is not None for key in (BASE_URL_KEY, MODEL_KEY, API_KEY_KEY)),
    )

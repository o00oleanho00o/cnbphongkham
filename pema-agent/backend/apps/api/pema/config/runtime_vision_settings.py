# ported from: src/config/runtime-vision-settings.ts
"""Image-reading (vision) configuration, editable on the admin screen, stored in ``agent.runtime_settings``.
Priority: DB override -> environment (``env_llm``), the same rule as ``runtime_llm_settings``. The sidecar key
is encrypted like every other key.

* mode: does the MAIN model read images? (auto = ask the router).
* sidecar: a second model that "reads images for hire" when the main model has no vision: it describes the
  image as text once (cached in the DB), the main model reads the text. Learned from ``image_input_mode``
  auto|native|text + ``auxiliary.vision`` of Hermes (``agent/image_routing.py``).

Forced deviations (SQLite -> Postgres, sync -> async): synchronous reads from the per-clinic
``RuntimeSettingsSnapshot``; async write-through updates (see ``runtime_settings_store``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import RuntimeSettingsSnapshot, get_runtime_settings
from pema.config.secret_cipher import decrypt_secret, encrypt_secret, mask_secret

type VisionMode = Literal["auto", "on", "off"]

MODE_KEY: Final = "vision_mode"
SIDECAR_BASE_URL_KEY: Final = "vision_sidecar_base_url"
SIDECAR_MODEL_KEY: Final = "vision_sidecar_model"
SIDECAR_API_KEY_KEY: Final = "vision_sidecar_api_key"


@dataclass(frozen=True)
class VisionSidecarSettings:
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class VisionSettings:
    mode: VisionMode
    sidecar: VisionSidecarSettings


def _read_sidecar_api_key() -> str:
    env_key = get_llm_env().VISION_SIDECAR_API_KEY
    stored = get_runtime_settings().read(SIDECAR_API_KEY_KEY)
    if stored:
        try:
            return decrypt_secret(stored)
        except Exception:
            # Broken key (the encryption key changed): fall back to the environment instead of killing the
            # sidecar.
            return env_key
    return env_key


def get_vision_settings() -> VisionSettings:
    snapshot = get_runtime_settings()
    env = get_llm_env()
    stored_mode = snapshot.read(MODE_KEY)
    modes: dict[str, VisionMode] = {"auto": "auto", "on": "on", "off": "off"}
    mode = modes.get(stored_mode or "", env.LLM_VISION_MODE)
    return VisionSettings(
        mode=mode,
        sidecar=VisionSidecarSettings(
            base_url=snapshot.read(SIDECAR_BASE_URL_KEY) or env.VISION_SIDECAR_BASE_URL or "",
            model=snapshot.read(SIDECAR_MODEL_KEY) or env.VISION_SIDECAR_MODEL,
            api_key=_read_sidecar_api_key(),
        ),
    )


def is_sidecar_configured(settings: VisionSettings | None = None) -> bool:
    """The sidecar is usable only with all three: base URL + model + key."""
    s = (settings or get_vision_settings()).sidecar
    return bool(s.base_url and s.model and s.api_key)


@dataclass(frozen=True)
class VisionSettingsUpdate:
    mode: VisionMode | None = None
    sidecar_base_url: str | None = None
    """An explicit empty string = delete (back to the environment)."""
    sidecar_model: str | None = None
    sidecar_api_key: str | None = None
    """None = keep the current key; an explicit empty string = delete the key."""


async def update_vision_settings(
    clinic_id: UUID,
    update: VisionSettingsUpdate,
    *,
    snapshot: RuntimeSettingsSnapshot | None = None,
) -> VisionSettings:
    snap = snapshot or get_runtime_settings()
    if update.mode is not None:
        await snap.set(clinic_id, MODE_KEY, update.mode)
    for key, value in (
        (SIDECAR_BASE_URL_KEY, update.sidecar_base_url),
        (SIDECAR_MODEL_KEY, update.sidecar_model),
    ):
        if value is None:
            continue
        if value == "":
            await snap.delete(clinic_id, key)
        else:
            await snap.set(clinic_id, key, value)
    if update.sidecar_api_key is not None:
        if update.sidecar_api_key == "":
            await snap.delete(clinic_id, SIDECAR_API_KEY_KEY)
        else:
            await snap.set(clinic_id, SIDECAR_API_KEY_KEY, encrypt_secret(update.sidecar_api_key))
    return get_vision_settings()


async def clear_sidecar_settings(
    clinic_id: UUID, *, snapshot: RuntimeSettingsSnapshot | None = None
) -> VisionSettings:
    """Wipe the whole sidecar configuration (key included): back to the environment values, usually empty,
    i.e. the sidecar is off. A separate action because the PATCH convention is "empty key = keep the old
    key", so there is no way to remove a key through PATCH from the UI."""
    snap = snapshot or get_runtime_settings()
    await snap.delete_many(clinic_id, [SIDECAR_BASE_URL_KEY, SIDECAR_MODEL_KEY, SIDECAR_API_KEY_KEY])
    return get_vision_settings()


@dataclass(frozen=True)
class VisionSidecarForApi:
    base_url: str
    model: str
    api_key_masked: str
    has_api_key: bool
    """A separate flag because ``api_key_masked`` is NEVER empty (empty reads "chưa cấu hình"): the UI cannot
    infer "is there a key" from the mask string."""
    configured: bool


@dataclass(frozen=True)
class VisionSettingsForApi:
    mode: VisionMode
    sidecar: VisionSidecarForApi


def get_vision_settings_for_api() -> VisionSettingsForApi:
    """The safe form returned to the dashboard: never the full key."""
    settings = get_vision_settings()
    return VisionSettingsForApi(
        mode=settings.mode,
        sidecar=VisionSidecarForApi(
            base_url=settings.sidecar.base_url,
            model=settings.sidecar.model,
            api_key_masked=mask_secret(settings.sidecar.api_key),
            has_api_key=bool(settings.sidecar.api_key),
            configured=is_sidecar_configured(settings),
        ),
    )

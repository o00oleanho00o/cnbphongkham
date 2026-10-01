# ported from: src/config/runtime-llm-settings.ts
"""Runtime override of the LLM configuration (changed from the admin screen, applied at once, no restart).

Priority: ``agent.runtime_settings`` (DB override) then the environment (``env_llm``). The API key kept in
the DB is encrypted with AES-256-GCM, the same cipher as every other secret (``secret_cipher``).

Forced deviations (SQLite -> Postgres, sync -> async): the synchronous reads come from the in-memory
``RuntimeSettingsSnapshot`` of the CURRENT clinic (see ``runtime_settings_store``); the writes are async, go
through the snapshot (write-through) and persist in ``agent.runtime_settings`` under RLS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import RuntimeSettingsSnapshot, get_runtime_settings
from pema.config.secret_cipher import decrypt_secret, encrypt_secret, mask_secret
from pema.shared.logger import create_logger
from pema_contracts.agents import LlmProviderKind

log = create_logger("llm-settings")

KEYS: Final = ("llm_provider", "llm_base_url", "llm_model", "llm_api_key")


@dataclass(frozen=True)
class LlmSettings:
    provider: LlmProviderKind
    base_url: str | None
    model: str
    api_key: str
    has_override: bool
    """True = at least one field comes from the DB override, False = pure environment."""
    api_key_hong: bool
    """The DB HAS a key but decrypting it FAILED, almost always because the encryption key changed since it
    was saved. Must be told apart from "never entered": both look the same (no usable key) but are fixed in
    different places: one is a first entry, the other a wrong encryption key and every other secret in the DB
    (the Zalo credentials) is broken too."""


class _Unset:
    """Marker type of the unset default of ``LlmSettingsUpdate.base_url``."""


UNSET: Final = _Unset()


@dataclass(frozen=True)
class LlmSettingsUpdate:
    provider: LlmProviderKind | None = None
    base_url: str | _Unset | None = UNSET
    """UNSET (the default) = KEEP the stored value, ``None`` = DELETE it, a string = set it.

    The two must be told apart because a base URL only means something for ``openai-compatible``: with only
    "keep", switching to Anthropic or Google would leave the old vendor's URL in the DB for ever and show it
    again on the way back; the user would see a base URL of a provider they abandoned and think the dashboard
    is broken (reported 06/08/2026).
    """
    model: str | None = None
    api_key: str | None = None
    """Empty = keep the current key."""


def _decrypt_safely(encrypted: str | None) -> tuple[str | None, bool]:
    """Decrypt the API key WITHOUT letting an error escape (``giaiMaAnToan``).

    ``decrypt_secret`` raises when the encryption key changed since the key was stored, and this function sits
    on the path of EVERY agent turn and of the overview page. Letting it escape would make every turn answer
    "please retry in a few minutes" for a PERMANENT state, and the first page one opens to understand what is
    wrong would be dead. ``hong=True`` lets the caller name the real disease instead of silently falling back
    to the environment, which is worse: the bot would run on a different key than the one the user just typed.
    """
    if not encrypted:
        return None, False
    try:
        return decrypt_secret(encrypted), False
    except Exception as exc:
        log.error(
            "cannot decrypt the stored LLM API key: is the encryption key the one used when it was saved?",
            err=exc,
        )
        return None, True


def get_effective_llm_settings() -> LlmSettings:
    """Effective LLM configuration now (the DB override of the current clinic over the environment)."""
    snapshot = get_runtime_settings()
    env = get_llm_env()
    provider = snapshot.read("llm_provider")
    base_url = snapshot.read("llm_base_url")
    model = snapshot.read("llm_model")
    encrypted_key = snapshot.read("llm_api_key")

    key, hong = _decrypt_safely(encrypted_key)
    stored_provider = _provider_or_none(provider)
    return LlmSettings(
        provider=stored_provider or env.LLM_PROVIDER,
        base_url=base_url if base_url is not None else env.LLM_BASE_URL,
        model=model if model is not None else env.LLM_MODEL,
        api_key="" if hong else (key if key is not None else env.LLM_API_KEY),
        has_override=bool(provider or base_url or model or encrypted_key),
        api_key_hong=hong,
    )


def _provider_or_none(value: str | None) -> LlmProviderKind | None:
    if not value:
        return None
    try:
        return LlmProviderKind(value)
    except ValueError:
        return None


async def update_llm_settings(
    clinic_id: UUID,
    update: LlmSettingsUpdate,
    *,
    snapshot: RuntimeSettingsSnapshot | None = None,
) -> None:
    snap = snapshot or get_runtime_settings()
    if update.provider is not None:
        await snap.set(clinic_id, "llm_provider", update.provider.value)
    if update.base_url is None:
        await snap.delete(clinic_id, "llm_base_url")
    elif not isinstance(update.base_url, _Unset):
        await snap.set(clinic_id, "llm_base_url", update.base_url)
    if update.model is not None:
        await snap.set(clinic_id, "llm_model", update.model)
    if update.api_key:
        await snap.set(clinic_id, "llm_api_key", encrypt_secret(update.api_key))


async def clear_llm_settings(clinic_id: UUID, *, snapshot: RuntimeSettingsSnapshot | None = None) -> None:
    """Delete every override: back to the environment configuration (safe rollback)."""
    snap = snapshot or get_runtime_settings()
    await snap.delete_many(clinic_id, KEYS)


def mask_api_key(value: str) -> str:
    """``sk-abc...xyz``: enough to recognise which key, not enough to reuse it."""
    return mask_secret(value)

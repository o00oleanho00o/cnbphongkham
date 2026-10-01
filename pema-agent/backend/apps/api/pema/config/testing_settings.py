# ported from: none (test helper of the runtime-settings tests, package D1)
"""``SettingsEnv``: the handle a test gets from the ``settings_env`` fixture (``tests/config/conftest.py``): a
fresh in-memory ``RuntimeSettingsSnapshot`` of one clinic with an encryption key set. Import in tests only."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pema.config import env as env_module
from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import InMemoryRuntimeSettingsStore, RuntimeSettingsSnapshot

LLM_ENV_NAMES = (
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_VISION_MODE",
    "VISION_SIDECAR_BASE_URL",
    "VISION_SIDECAR_MODEL",
    "VISION_SIDECAR_API_KEY",
)


@dataclass
class SettingsEnv:
    store: InMemoryRuntimeSettingsStore
    snapshot: RuntimeSettingsSnapshot
    monkeypatch: pytest.MonkeyPatch

    def set_env(self, **values: str) -> None:
        """Set LLM environment variables (the layer under the DB override) and re-read them."""
        for name, value in values.items():
            self.monkeypatch.setenv(name, value)
        get_llm_env.cache_clear()

    def change_encryption_key(self, key_hex: str) -> None:
        self.monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", key_hex)
        env_module.get_settings.cache_clear()

# ported from: none (test helper of the runtime-settings tests, package D1)
"""``SettingsEnv``: the handle a test gets from the ``settings_env`` fixture (``tests/config/conftest.py``): a
fresh in-memory ``RuntimeSettingsSnapshot`` of one clinic with an encryption key set. Import in tests only."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from pema.config import env as env_module
from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    install_runtime_settings,
    use_settings_clinic,
)
from pema.config.runtime_tuning_settings import reset_tuning_provider
from pema_contracts.testing import FAKE_CLINIC_ID

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


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[SettingsEnv]:
    """A fresh in-memory ``RuntimeSettingsSnapshot`` of ``FAKE_CLINIC_ID`` with an encryption key, the LLM
    environment cleared and every cache reset afterwards. Re-exported by the conftest files that need it."""
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()
    store = InMemoryRuntimeSettingsStore()
    snapshot = RuntimeSettingsSnapshot(store)
    install_runtime_settings(snapshot)
    with use_settings_clinic(FAKE_CLINIC_ID):
        yield SettingsEnv(store, snapshot, monkeypatch)
    reset_tuning_provider()
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()

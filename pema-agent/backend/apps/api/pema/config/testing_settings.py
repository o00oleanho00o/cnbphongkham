# ported from: none (test helper of the runtime-settings tests, package D1)
"""``SettingsEnv``: the handle a test gets from the ``settings_env`` fixture (``tests/config/conftest.py``): a
fresh in-memory ``RuntimeSettingsSnapshot`` with an encryption key set. Import in tests only."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from pema.config import env as env_module
from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    install_runtime_settings,
)
from pema.config.runtime_tuning_settings import reset_tuning_provider


@dataclass
class SettingsEnv:
    store: InMemoryRuntimeSettingsStore
    snapshot: RuntimeSettingsSnapshot
    monkeypatch: pytest.MonkeyPatch

    def change_encryption_key(self, key_hex: str) -> None:
        self.monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", key_hex)
        env_module.get_settings.cache_clear()


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[SettingsEnv]:
    """A fresh in-memory ``RuntimeSettingsSnapshot`` with an encryption key and every cache reset
    afterwards. Re-exported by the conftest files that need it."""
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()
    store = InMemoryRuntimeSettingsStore()
    snapshot = RuntimeSettingsSnapshot(store)
    install_runtime_settings(snapshot)
    yield SettingsEnv(store, snapshot, monkeypatch)
    reset_tuning_provider()
    env_module.get_settings.cache_clear()

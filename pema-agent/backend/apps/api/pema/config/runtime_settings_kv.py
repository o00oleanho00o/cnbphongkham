"""Key/value access to the shared ``runtime_settings`` table (no TypeScript source).

The original settings modules (``runtime-image-settings``, ``runtime-tool-settings``,
``runtime-vision-settings``, ``runtime-llm-settings``) talked to the SQLite table ``runtime_settings``
directly with prepared statements, and they READ it synchronously: ``available()`` of the tool catalog
reads the image/search settings on every turn.

Forced deviation (SQLite sync -> Postgres async): Python cannot ``await`` in a plain call, so the READ side
is a synchronous lookup in an in-memory snapshot and only the WRITE side is async. Same shape as
``install_tuning_provider`` of ``runtime_tuning_settings``:

* ``RuntimeSettingsKv.get(key)``      synchronous, cheap, ``None`` when the key is not stored;
* ``RuntimeSettingsKv.aset/adelete``  asynchronous writes; a DB-backed implementation (package G / D1)
  persists to ``agent.runtime_settings`` and refreshes its snapshot on every write, so a value written
  here is visible to the next ``get`` at once;
* ``install_runtime_settings_kv`` / ``reset_runtime_settings_kv`` / ``get_runtime_settings_kv`` : the wiring.

``InMemoryRuntimeSettingsKv`` is the default and the test double; it is also usable in production before the
DB provider lands (overrides then live only for the life of the process).

Secrets stored through this KV are ALREADY encrypted by the caller (``secret_cipher``); the KV never sees a
plaintext secret and never logs a value.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class RuntimeSettingsKv(Protocol):
    def get(self, key: str) -> str | None:
        """Stored raw value (as saved) or ``None``. Synchronous by design, see the module docstring."""
        ...

    async def aset(self, key: str, value: str) -> None:
        """Insert or update ``key`` (the original ``INSERT ... ON CONFLICT DO UPDATE``)."""
        ...

    async def adelete(self, key: str) -> None:
        """Remove ``key``; a missing key is not an error (the original ``DELETE``)."""
        ...


class InMemoryRuntimeSettingsKv:
    """Dict-based ``RuntimeSettingsKv``. Also the shape of the snapshot a DB-backed provider keeps."""

    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self._data: dict[str, str] = dict(initial or {})

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def aset(self, key: str, value: str) -> None:
        self._data[key] = value

    async def adelete(self, key: str) -> None:
        self._data.pop(key, None)

    def replace(self, data: Mapping[str, str]) -> None:
        """Swap the whole content (a DB provider refreshing its snapshot)."""
        self._data = dict(data)

    def snapshot(self) -> dict[str, str]:
        return dict(self._data)


_kv: RuntimeSettingsKv = InMemoryRuntimeSettingsKv()


def install_runtime_settings_kv(kv: RuntimeSettingsKv) -> None:
    global _kv
    _kv = kv


def reset_runtime_settings_kv() -> None:
    """Back to an EMPTY in-memory store (tests; and the state before the DB provider is wired)."""
    install_runtime_settings_kv(InMemoryRuntimeSettingsKv())


def get_runtime_settings_kv() -> RuntimeSettingsKv:
    return _kv

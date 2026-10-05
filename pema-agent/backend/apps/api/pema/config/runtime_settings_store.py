# ported from: src/config/runtime-llm-settings.ts / runtime-vision-settings.ts / runtime-tuning-settings.ts
# (the ``runtime_settings`` table access they each duplicated: ``getStmt``, ``setStmt``, ``delStmt``)
"""The "provider DB" of the runtime overrides: ``agent.runtime_settings`` (clinic_id, key, value).

zalo-agent read ``runtime_settings`` SYNCHRONOUSLY on every ``getTuning`` / ``getEffectiveLlmSettings`` call
("reading again each time is the whole point of putting it on the web": a value changed on the admin screen
takes effect on the next call, no restart). Postgres cannot be awaited from a plain function and
``get_tuning`` is called synchronously from ~55 places, so the port splits the two halves:

* ``RuntimeSettingsStore``: the async persistence (``SqlRuntimeSettingsStore`` over ``ClinicDatabase``;
  ``InMemoryRuntimeSettingsStore`` for tests);
* ``RuntimeSettingsSnapshot``: an in-memory copy read synchronously. It is refreshed on every write made
  through it (write-through: the admin screen sees its change at once) and on a timer (a change made by
  another process shows within ``interval_s``, a few seconds). It implements ``TuningProvider`` so
  ``install_tuning_provider(snapshot)`` makes ``get_tuning`` DB-backed.

Single tenant (one installation is ONE clinic): the snapshot holds ONE set of rows, the ones of the
installation clinic; a synchronous read needs no "which clinic" context any more (the per-task context
variable that used to pick the clinic is gone). Until the first ``refresh`` the snapshot is empty, so the
environment and the defaults apply. The ``clinic_id`` argument of the store and of
``refresh/set/delete`` is the installation id, kept on purpose (``agent.runtime_settings`` keeps its
``clinic_id`` column).

Secrets (the LLM API key, the vision sidecar key) are stored ENCRYPTED by the callers
(``runtime_llm_settings``); this layer stores opaque strings and never logs a value.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from typing import Protocol
from uuid import UUID

from sqlalchemy import bindparam, text

from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger

log = create_logger("runtime-settings")


class RuntimeSettingsStore(Protocol):
    async def load_all(self, clinic_id: UUID) -> dict[str, str]: ...

    async def set(self, clinic_id: UUID, key: str, value: str) -> None: ...

    async def delete(self, clinic_id: UUID, key: str) -> None: ...

    async def delete_many(self, clinic_id: UUID, keys: Sequence[str]) -> None: ...


class InMemoryRuntimeSettingsStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, dict[str, str]] = {}

    async def load_all(self, clinic_id: UUID) -> dict[str, str]:
        return dict(self._rows.get(clinic_id, {}))

    async def set(self, clinic_id: UUID, key: str, value: str) -> None:
        self._rows.setdefault(clinic_id, {})[key] = value

    async def delete(self, clinic_id: UUID, key: str) -> None:
        self._rows.get(clinic_id, {}).pop(key, None)

    async def delete_many(self, clinic_id: UUID, keys: Sequence[str]) -> None:
        for key in keys:
            await self.delete(clinic_id, key)


class SqlRuntimeSettingsStore:
    """``agent.runtime_settings`` through ``ClinicDatabase`` (single tenant: no RLS, the rows of the
    installation clinic are read by ``clinic_id``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def load_all(self, clinic_id: UUID) -> dict[str, str]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    text("SELECT key, value FROM agent.runtime_settings WHERE clinic_id = :clinic_id"),
                    {"clinic_id": clinic_id},
                )
            ).all()
        return {str(key): str(value) for key, value in rows}

    async def set(self, clinic_id: UUID, key: str, value: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                text(
                    "INSERT INTO agent.runtime_settings (clinic_id, key, value, updated_at) "
                    "VALUES (:clinic_id, :key, :value, now()) "
                    "ON CONFLICT (clinic_id, key) DO UPDATE SET value = excluded.value, "
                    "updated_at = excluded.updated_at"
                ),
                {"clinic_id": clinic_id, "key": key, "value": value},
            )

    async def delete(self, clinic_id: UUID, key: str) -> None:
        await self.delete_many(clinic_id, [key])

    async def delete_many(self, clinic_id: UUID, keys: Sequence[str]) -> None:
        if not keys:
            return
        statement = text(
            "DELETE FROM agent.runtime_settings WHERE clinic_id = :clinic_id AND key IN :keys"
        ).bindparams(bindparam("keys", expanding=True))
        async with self._db.session() as session:
            await session.execute(statement, {"clinic_id": clinic_id, "keys": list(keys)})


class RuntimeSettingsSnapshot:
    """In-memory copy of the ``runtime_settings`` of the installation clinic (a ``TuningProvider``)."""

    def __init__(self, store: RuntimeSettingsStore) -> None:
        self.store = store
        self._rows: dict[str, str] = {}
        self._clinic_id: UUID | None = None
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ reads (synchronous)
    def read(self, key: str) -> str | None:
        return self._rows.get(key)

    def override(self, key: str) -> str | None:
        """``TuningProvider``: the stored raw string of the tuning parameter ``key`` (DB ``tuning_<k>``)."""
        return self.read("tuning_" + key)

    # ------------------------------------------------------------------ refresh
    async def refresh(self, clinic_id: UUID) -> None:
        """Re-read the rows of the installation clinic (and remember its id for the timer)."""
        self._rows = await self.store.load_all(clinic_id)
        self._clinic_id = clinic_id

    def apply_local(self, key: str, value: str | None) -> None:
        if value is None:
            self._rows.pop(key, None)
        else:
            self._rows[key] = value

    # ------------------------------------------------------------------ writes (write-through)
    async def set(self, clinic_id: UUID, key: str, value: str) -> None:
        await self.store.set(clinic_id, key, value)
        self.apply_local(key, value)

    async def delete(self, clinic_id: UUID, key: str) -> None:
        await self.store.delete(clinic_id, key)
        self.apply_local(key, None)

    async def delete_many(self, clinic_id: UUID, keys: Sequence[str]) -> None:
        await self.store.delete_many(clinic_id, keys)
        for key in keys:
            self.apply_local(key, None)

    # ------------------------------------------------------------------ timer
    def start_refresh_loop(self, *, interval_s: float = 5.0) -> None:
        """Re-read the rows each ``interval_s`` seconds (once ``refresh`` gave the installation id), so a
        change made by ANOTHER process is picked up. A failed refresh keeps the previous copy and logs."""
        if self._task is not None:
            return

        async def loop() -> None:
            while True:
                await asyncio.sleep(interval_s)
                try:
                    if self._clinic_id is not None:
                        await self.refresh(self._clinic_id)
                except Exception as exc:
                    log.warning("runtime settings refresh failed", err=exc)

        self._task = asyncio.get_running_loop().create_task(loop())

    async def stop_refresh_loop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


_snapshot: RuntimeSettingsSnapshot = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())


def install_runtime_settings(snapshot: RuntimeSettingsSnapshot) -> None:
    """Wire the process-wide snapshot (``bootstrap``/worker start-up; tests install a fresh in-memory one)."""
    global _snapshot
    _snapshot = snapshot


def get_runtime_settings() -> RuntimeSettingsSnapshot:
    return _snapshot

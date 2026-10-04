# ported from: src/config/runtime-llm-settings.ts / runtime-vision-settings.ts / runtime-tuning-settings.ts
# (the ``runtime_settings`` table access they each duplicated: ``getStmt``, ``setStmt``, ``delStmt``)
"""The "provider DB" of the runtime overrides: ``agent.runtime_settings`` (clinic_id, key, value).

zalo-agent read ``runtime_settings`` SYNCHRONOUSLY on every ``getTuning`` / ``getEffectiveLlmSettings`` call
("reading again each time is the whole point of putting it on the web": a value changed on the admin screen
takes effect on the next call, no restart). Postgres cannot be awaited from a plain function and
``get_tuning`` is called synchronously from ~55 places, so the port splits the two halves:

* ``RuntimeSettingsStore``: the async persistence (``SqlRuntimeSettingsStore`` over ``ClinicDatabase``, so row
  level security applies; ``InMemoryRuntimeSettingsStore`` for tests);
* ``RuntimeSettingsSnapshot``: a per-clinic in-memory copy read synchronously. It is refreshed on every write
  made through it (write-through: the admin screen sees its change at once) and on a timer (a change made by
  another process shows within ``interval_s``, a few seconds). It implements ``TuningProvider`` so
  ``install_tuning_provider(snapshot)`` makes ``get_tuning`` DB-backed.

Which clinic a synchronous read belongs to: one worker process may serve several clinics, so the snapshot is
keyed by clinic id and ``read`` uses a ``ContextVar`` (``use_settings_clinic``). The engine sets it for the
duration of a turn, the admin routes for the duration of a request. With no clinic set nothing is overridden
(the environment and the defaults apply): fail-safe, never another clinic's value.

Secrets (the LLM API key, the vision sidecar key) are stored ENCRYPTED by the callers
(``runtime_llm_settings``); this layer stores opaque strings and never logs a value.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Generator, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
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
    """``agent.runtime_settings`` through ``ClinicDatabase`` (the session sets ``app.clinic_id`` for RLS)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def load_all(self, clinic_id: UUID) -> dict[str, str]:
        async with self._db.session(clinic_id) as session:
            rows = (await session.execute(text("SELECT key, value FROM agent.runtime_settings"))).all()
        return {str(key): str(value) for key, value in rows}

    async def set(self, clinic_id: UUID, key: str, value: str) -> None:
        async with self._db.session(clinic_id) as session:
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
        statement = text("DELETE FROM agent.runtime_settings WHERE key IN :keys").bindparams(
            bindparam("keys", expanding=True)
        )
        async with self._db.session(clinic_id) as session:
            await session.execute(statement, {"keys": list(keys)})


_current_clinic: ContextVar[UUID | None] = ContextVar("pema_settings_clinic", default=None)


@contextmanager
def use_settings_clinic(clinic_id: UUID | None) -> Generator[None]:
    """Make synchronous reads (``get_tuning``, ``get_effective_llm_settings`` ...) belong to ``clinic_id``."""
    token = _current_clinic.set(clinic_id)
    try:
        yield
    finally:
        _current_clinic.reset(token)


def set_settings_clinic(clinic_id: UUID | None) -> None:
    """Set the clinic for the rest of the current task (the engine calls it at the start of ``run_turn``;
    each asyncio task has its own copy of the context, so concurrent turns do not interfere)."""
    _current_clinic.set(clinic_id)


def current_settings_clinic() -> UUID | None:
    return _current_clinic.get()


class RuntimeSettingsSnapshot:
    """Per-clinic in-memory copy of ``runtime_settings``. Implements ``TuningProvider``."""

    def __init__(self, store: RuntimeSettingsStore) -> None:
        self.store = store
        self._by_clinic: dict[UUID, dict[str, str]] = {}
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ reads (synchronous)
    def read(self, key: str) -> str | None:
        clinic_id = _current_clinic.get()
        if clinic_id is None:
            return None
        return self._by_clinic.get(clinic_id, {}).get(key)

    def override(self, key: str) -> str | None:
        """``TuningProvider``: the stored raw string of the tuning parameter ``key`` (DB key ``tuning_<key>``)
        in the current clinic."""
        return self.read("tuning_" + key)

    # ------------------------------------------------------------------ refresh
    async def refresh(self, clinic_id: UUID) -> None:
        self._by_clinic[clinic_id] = await self.store.load_all(clinic_id)

    def apply_local(self, clinic_id: UUID, key: str, value: str | None) -> None:
        rows = self._by_clinic.setdefault(clinic_id, {})
        if value is None:
            rows.pop(key, None)
        else:
            rows[key] = value

    # ------------------------------------------------------------------ writes (write-through)
    async def set(self, clinic_id: UUID, key: str, value: str) -> None:
        await self.store.set(clinic_id, key, value)
        self.apply_local(clinic_id, key, value)

    async def delete(self, clinic_id: UUID, key: str) -> None:
        await self.store.delete(clinic_id, key)
        self.apply_local(clinic_id, key, None)

    async def delete_many(self, clinic_id: UUID, keys: Sequence[str]) -> None:
        await self.store.delete_many(clinic_id, keys)
        for key in keys:
            self.apply_local(clinic_id, key, None)

    # ------------------------------------------------------------------ timer
    def start_refresh_loop(
        self,
        clinic_ids: Callable[[], Awaitable[Sequence[UUID]]] | None = None,
        *,
        interval_s: float = 5.0,
    ) -> None:
        """Re-read every known clinic (or the ones ``clinic_ids()`` returns) each ``interval_s`` seconds, so a
        change made by ANOTHER process is picked up. A failed refresh keeps the previous copy and logs."""
        if self._task is not None:
            return

        async def loop() -> None:
            while True:
                await asyncio.sleep(interval_s)
                try:
                    ids = list(await clinic_ids()) if clinic_ids is not None else list(self._by_clinic)
                    for clinic_id in ids:
                        await self.refresh(clinic_id)
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

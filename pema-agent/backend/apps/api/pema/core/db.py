"""Async database access (single tenant: one installation is one clinic, one database).

New module (not a port: zalo-agent had one SQLite file, no tenants). Contract used by EVERY package that
touches Postgres:

* one engine per runtime role: ``ClinicDatabase(settings.database_url)`` (role ``be_app``, API process)
  or ``ClinicDatabase(settings.worker_database_url)`` (role ``agent_worker``, worker process);
* every unit of work runs in ``async with db.session() as session:``. It opens a transaction, commits when the
  block exits normally and rolls back on any exception. There is NO clinic context and NO row level security
  any more (migration ``st_0009_single_tenant``): the ``clinic_id`` column stays in every table as the fixed
  installation id, and ``get_installation_clinic_id`` is the single source of truth for its value;
* ``get_installation_clinic_id(db)`` reads the id once per process (``PEMA_CLINIC_ID`` when set, otherwise the
  only row of ``clinic.clinic`` through ``ctx.the_clinic_id()``, which both runtime roles may call) and
  caches it, also for ``pema_contracts.installation.installation_clinic_id`` (the default of the
  ``clinic_id`` field of ``ActionContext``, ``TurnJob``, ...).

Stores keep the clinic id as an explicit argument for now (``pema_contracts.conversation``); it is the
installation id and nothing validates it against the database, so pass ``get_installation_clinic_id(db)``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from pema.config.env import get_settings
from pema_contracts.installation import set_installation_clinic_id


class InstallationClinicMismatchError(RuntimeError):
    """``PEMA_CLINIC_ID`` names another clinic than the one in the database."""


class ClinicDatabase:
    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 5) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, echo=echo, pool_size=pool_size, pool_pre_ping=True
        )
        self._factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.installation_clinic_id: UUID | None = None
        """Cache of ``get_installation_clinic_id`` for the database this engine is connected to."""

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Transaction for one unit of work."""
        async with self._factory() as session, session.begin():
            yield session

    async def read_installation_clinic_id(self) -> UUID:
        """The id of the only clinic, read from the database (no cache). Raises when none is installed."""
        async with self.session() as session:
            value = (await session.execute(text("SELECT ctx.the_clinic_id()"))).scalar_one()
        return UUID(str(value))

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_installation_clinic_id(db: ClinicDatabase, *, verify: bool = False) -> UUID:
    """The id of the one clinic of this installation: read once, cached for the process.

    Order: the cache of ``db`` (one per database, so a test that swaps databases never sees a stale id);
    ``PEMA_CLINIC_ID`` when set; otherwise ``ctx.the_clinic_id()`` in ``db``. The result is also stored with
    ``pema_contracts.installation.set_installation_clinic_id``. With ``verify=True`` (start-up) a
    ``PEMA_CLINIC_ID`` is compared with the database and a difference raises
    ``InstallationClinicMismatchError``; a database with no clinic raises whatever Postgres raises
    (``ctx.the_clinic_id()`` fails closed).
    """
    configured = get_settings().clinic_id
    if verify and configured is not None:
        stored = await db.read_installation_clinic_id()
        if stored != configured:
            raise InstallationClinicMismatchError("PEMA_CLINIC_ID is not the clinic of this database")
        db.installation_clinic_id = stored
        set_installation_clinic_id(stored)
        return stored
    if db.installation_clinic_id is not None:
        return db.installation_clinic_id
    clinic_id = configured if configured is not None else await db.read_installation_clinic_id()
    db.installation_clinic_id = clinic_id
    set_installation_clinic_id(clinic_id)
    return clinic_id

"""Async database access with the clinic context (row level security).

New module (not a port: zalo-agent had one SQLite file, no tenants). Contract used by EVERY package that
touches Postgres:

* one engine per runtime role: ``ClinicDatabase(settings.database_url)`` (role ``be_app``, API process)
  or ``ClinicDatabase(settings.worker_database_url)`` (role ``agent_worker``, worker process);
* every unit of work runs in ``async with db.session(clinic_id) as session:``. It opens a transaction
  and sets the transaction-local setting ``app.clinic_id``, which the RLS policies compare with
  ``clinic_id``. An unset context returns no rows (fail closed);
* ``db.system_session()`` is for the few lookups that happen before a clinic is known
  (``resolve_clinic`` by slug, ``list_active_clinic_ids`` for the scheduler). It sets no context, so it
  sees only what the SECURITY DEFINER functions return;
* the session commits when the block exits normally and rolls back on any exception.

Stores keep the clinic id as an explicit argument (``pema_contracts.conversation``); they call
``db.session(clinic_id)`` themselves, so callers never manage RLS.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class ClinicDatabase:
    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 5) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, echo=echo, pool_size=pool_size, pool_pre_ping=True
        )
        self._factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self, clinic_id: UUID) -> AsyncGenerator[AsyncSession]:
        """Transaction with ``app.clinic_id`` set for its whole life (``set_config(..., true)``)."""
        async with self._factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.clinic_id', :clinic_id, true)"),
                {"clinic_id": str(clinic_id)},
            )
            yield session

    @asynccontextmanager
    async def system_session(self) -> AsyncGenerator[AsyncSession]:
        """Transaction without a clinic context (see module docstring)."""
        async with self._factory() as session, session.begin():
            yield session

    async def resolve_clinic(self, slug: str) -> UUID | None:
        """Clinic id from its slug (login, webhooks), through the SECURITY DEFINER lookup."""
        async with self.system_session() as session:
            row = (await session.execute(text("SELECT ctx.resolve_clinic(:slug)"), {"slug": slug})).scalar()
        return UUID(str(row)) if row is not None else None

    async def list_active_clinic_ids(self) -> list[UUID]:
        """Every active clinic (the scheduler loop iterates over them)."""
        async with self.system_session() as session:
            rows = (await session.execute(text("SELECT ctx.list_active_clinic_ids()"))).scalars().all()
        return [UUID(str(r)) for r in rows]

    async def dispose(self) -> None:
        await self.engine.dispose()

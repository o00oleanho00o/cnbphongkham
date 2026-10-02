"""Create the one clinic of an installation (single tenant, package ST-A). Idempotent.

New module (not a port). ``clinic.clinic`` holds exactly one row (``singleton`` column, ``CHECK`` and
``UNIQUE`` in the database, migration ``st_0009_single_tenant``). The migration creates it from
``PEMA_CLINIC_NAME`` on an empty database; this module is the same operation for the seed, the bootstrap and
the tests, through the SQL function ``clinic.ensure_clinic`` (the only place that INSERTs the row):

* the row exists: its id is returned, nothing changes (no rename, no new id);
* the row is missing: it is created (``id`` generated once, or the ``clinic_id`` given, or the
  ``PEMA_CLINIC_ID``);
* a ``clinic_id`` that differs from the installed one raises.

It must run as the owner / migration role (the runtime roles have no EXECUTE on the function). The CLI
``python -m pema.core.installation`` reads ``PEMA_MIGRATION_DATABASE_URL``, ``PEMA_CLINIC_NAME`` and
``PEMA_CLINIC_ID`` and prints the id.
"""

from __future__ import annotations

import os
import sys
from uuid import UUID

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.ext.asyncio import AsyncConnection

from pema.config.env import Settings

INSTALLATION_SLUG = "clinic"
"""Fixed slug of the one clinic (the column stays NOT NULL and UNIQUE; nothing routes on it any more)."""
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

_ENSURE_SQL = text("SELECT clinic.ensure_clinic(:name, :slug, :tz, CAST(:id AS uuid))")


def _params(name: str | None, clinic_id: UUID | None, timezone: str | None) -> dict[str, object]:
    settings = Settings()
    wanted_id = clinic_id if clinic_id is not None else settings.clinic_id
    return {
        "name": name if name is not None else settings.clinic_name,
        "slug": INSTALLATION_SLUG,
        "tz": timezone or DEFAULT_TIMEZONE,
        "id": str(wanted_id) if wanted_id is not None else None,
    }


def ensure_clinic(
    conn: Connection, name: str | None = None, *, clinic_id: UUID | None = None, timezone: str | None = None
) -> UUID:
    """Create the clinic if there is none and return its id (sync connection of the owner role).

    ``name`` defaults to ``PEMA_CLINIC_NAME``, ``clinic_id`` to ``PEMA_CLINIC_ID`` (or a generated id). The
    caller's transaction decides when it commits.
    """
    return UUID(str(conn.execute(_ENSURE_SQL, _params(name, clinic_id, timezone)).scalar_one()))


async def ensure_clinic_async(
    conn: AsyncConnection,
    name: str | None = None,
    *,
    clinic_id: UUID | None = None,
    timezone: str | None = None,
) -> UUID:
    """``ensure_clinic`` for an ``AsyncConnection`` of the owner role."""
    result = await conn.execute(_ENSURE_SQL, _params(name, clinic_id, timezone))
    return UUID(str(result.scalar_one()))


def main() -> int:
    url = os.environ.get("PEMA_MIGRATION_DATABASE_URL") or Settings().migration_database_url
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            clinic_id = ensure_clinic(conn)
    finally:
        engine.dispose()
    sys.stdout.write(f"{clinic_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

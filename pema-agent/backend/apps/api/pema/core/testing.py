"""Test helpers for the one clinic of an installation (single tenant, package ST-A).

New module (not a port); imported by tests and test fixtures only. After migration ``st_0009_single_tenant``
a database holds exactly ONE clinic, so a fixture no longer creates "a fresh clinic per test": it takes the
installation clinic and cleans the data between tests.

* ``ensure_test_clinic(conn)``: the one clinic of the database (created when the database has none) as a
  ``UUID``; also stored as the process installation id, so ``ActionContext()`` and the other DTOs that default
  ``clinic_id`` get it. ``conn`` is a sync ``sqlalchemy.Connection`` of the owner / superuser role (the usual
  ``admin_engine``); ``ensure_test_clinic_async`` takes an ``AsyncConnection``.
* ``truncate_installation_data(conn)``: empties every table of ``clinic.*`` and ``agent.*`` EXCEPT
  ``clinic.clinic`` (so the clinic row and its id survive) in one statement. It needs a superuser: it sets
  ``session_replication_role = replica`` for the transaction so the append-only trigger of
  ``clinic.audit_log`` does not refuse the TRUNCATE (production never truncates the audit trail; this is
  for throwaway test databases only). The caller's transaction decides when it commits.

A second clinic cannot be inserted any more (``UNIQUE (singleton)``): code that did
``INSERT INTO clinic.clinic`` per test must use these helpers instead.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncConnection

from pema.core.installation import ensure_clinic, ensure_clinic_async
from pema_contracts.installation import set_installation_clinic_id

SYNTHETIC_CLINIC_NAME = "Synthetic clinic"

_TABLES_SQL = text(
    "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables "
    "WHERE schemaname IN ('clinic', 'agent') AND NOT (schemaname = 'clinic' AND tablename = 'clinic') "
    "ORDER BY 1"
)


def ensure_test_clinic(conn: Connection, name: str = SYNTHETIC_CLINIC_NAME) -> UUID:
    """The clinic of the test database (created with ``name`` if missing), and the process installation id."""
    clinic_id = ensure_clinic(conn, name)
    set_installation_clinic_id(clinic_id)
    return clinic_id


async def ensure_test_clinic_async(conn: AsyncConnection, name: str = SYNTHETIC_CLINIC_NAME) -> UUID:
    """``ensure_test_clinic`` for an ``AsyncConnection``."""
    clinic_id = await ensure_clinic_async(conn, name)
    set_installation_clinic_id(clinic_id)
    return clinic_id


def truncate_installation_data(conn: Connection) -> None:
    """Empty every table of ``clinic.*`` and ``agent.*`` except ``clinic.clinic`` (superuser, tests only)."""
    tables = conn.execute(_TABLES_SQL).scalars().all()
    if not tables:
        return
    conn.execute(text("SET LOCAL session_replication_role = replica"))
    conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY"))

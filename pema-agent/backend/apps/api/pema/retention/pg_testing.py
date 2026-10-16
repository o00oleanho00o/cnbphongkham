"""Test support of the retention job: synthetic rows with an explicit age (not imported by production code).

Same pattern as ``pema.core.pg_testing`` (it reuses its ``PgTestServer``: a throwaway database with the
real Alembic history). Single tenant: that database holds exactly ONE clinic, created by the migration.
``RetentionEnv`` takes it (``ensure_test_clinic``) and empties the data (``truncate_installation_data``); ``Seed``
inserts as the SUPERUSER of the database so a test can place rows of any age; the code under test always runs as
``be_app``.
"""

# ruff: noqa: E501  (long SQL literals of synthetic rows)

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase
from pema.core.pg_testing import BE_PASSWORD, PgTestServer
from pema.core.testing import ensure_test_clinic, truncate_installation_data


@dataclass
class RetentionEnv:
    """The one clinic of the throwaway database, empty; ``db`` is the API role."""

    server: PgTestServer
    clinic_id: UUID
    db: ClinicDatabase

    @classmethod
    def create(cls, server: PgTestServer) -> RetentionEnv:
        with server.admin_engine.begin() as conn:
            clinic_id = ensure_test_clinic(conn)
            truncate_installation_data(conn)
        return cls(
            server=server,
            clinic_id=clinic_id,
            db=ClinicDatabase(server.role_url("be_app", BE_PASSWORD), pool_size=3),
        )

    async def fetch(self, sql: str, **params: Any) -> list[Mapping[str, Any]]:
        """Run a SELECT as the API role and return rows as mappings."""
        async with self.db.session() as session:
            result = await session.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]

    async def dispose(self) -> None:
        await self.db.dispose()


class Seed:
    """Synthetic rows with an explicit age in days (``age=40`` = created 40 days ago), inserted as superuser."""

    def __init__(self, env: RetentionEnv) -> None:
        self._env = env

    def sql(self, statement: str, **params: Any) -> Any:
        with self._env.server.admin_engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return result.scalar() if result.returns_rows else None

    def count(self, table: str, clinic: UUID, where: str = "true") -> int:
        return int(
            self.sql(f"SELECT count(*) FROM {table} WHERE clinic_id = :c AND ({where})", c=clinic)  # noqa: S608
        )

    # ---------------------------------------------------------------------------------------------- clinic
    def user(self, clinic: UUID) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.user_account (clinic_id, email, display_name, role) "
                    "VALUES (:c, :e, 'Synthetic staff', 'cs_staff') RETURNING id",
                    c=clinic,
                    e=f"staff-{uuid.uuid4().hex[:8]}@example.test",
                )
            )
        )

    def patient(self, clinic: UUID) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, :code, 'Synthetic Patient') "
                    "RETURNING id",
                    c=clinic,
                    code=f"BN-{uuid.uuid4().hex[:8]}",
                )
            )
        )

    def auth_session(self, clinic: UUID, user: UUID, expired_days_ago: int) -> None:
        """A negative ``expired_days_ago`` is a session that is still valid."""
        self.sql(
            "INSERT INTO clinic.auth_session (clinic_id, user_id, password_fingerprint, expires_at, "
            "absolute_expires_at) "
            "VALUES (:c, :u, 'fp', now() - make_interval(days => :d), now() - make_interval(days => :d)) "
            "RETURNING 1",
            c=clinic,
            u=user,
            d=expired_days_ago,
        )

    def audit(self, clinic: UUID, age: int) -> None:
        self.sql(
            "INSERT INTO clinic.audit_log (clinic_id, occurred_at, actor_type, action, entity_type) "
            "VALUES (:c, now() - make_interval(days => :age), 'system', 'synthetic.event', 'synthetic') RETURNING 1",
            c=clinic,
            age=age,
        )

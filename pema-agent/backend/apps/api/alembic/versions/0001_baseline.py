"""Baseline of the clinic database: schemas ``ctx`` and ``clinic`` in their final shape (docs/PLAN-db-baseline.md).

Replaces the 30 revisions of the zalo-agent era. ``0001_baseline.sql`` is ``pg_dump -s`` of that chain after
the cuts of the plan (no ``agent`` / ``clinic_agent`` schema, no ``agent_worker`` grant, no inbox or follow-up
queue). What the SQL cannot carry is done here:

* role ``be_app`` (NOLOGIN until ``PEMA_BE_APP_PASSWORD`` is set: then it may log in with that password);
* no TEMP right for PUBLIC on this database (when the migration role owns it);
* the one clinic row of the installation: ``PEMA_CLINIC_NAME`` (default ``Pema Clinic``), slug ``clinic`` and,
  when set, ``PEMA_CLINIC_ID`` as the id (otherwise one id is generated, once).

No agent role, schema, view or function lives in this database (.claude/rules/agent-crm-boundary.md, L3).

Revision ID: 0001_baseline
Revises:
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")
DEFAULT_CLINIC_NAME = "Pema Clinic"
INSTALLATION_SLUG = "clinic"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _ensure_be_app() -> None:
    _sql(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'be_app') "
        "THEN CREATE ROLE be_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; END IF; END $$"
    )
    secret = os.environ.get("PEMA_BE_APP_PASSWORD")
    if not secret:
        return
    # the password travels as a setting, never inside the SQL text (it would land in the server log)
    op.execute(sa.text("SELECT set_config('pema.role_secret', :s, true)").bindparams(s=secret))
    _sql(
        "DO $$ BEGIN EXECUTE format('ALTER ROLE be_app LOGIN PASSWORD %L', current_setting('pema.role_secret')); END $$"
    )
    _sql("SELECT set_config('pema.role_secret', '', true)")


def _install_id() -> str | None:
    raw = os.environ.get("PEMA_CLINIC_ID", "").strip()
    return str(uuid.UUID(raw)) if raw else None


def upgrade() -> None:
    _ensure_be_app()
    # many statements and dollar-quoted bodies: straight to the driver, which runs them as one script
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    _sql(
        """
        DO $$ BEGIN
            EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'not the database owner: REVOKE TEMPORARY ... FROM PUBLIC skipped';
        END $$
        """
    )
    op.execute(
        sa.text("SELECT clinic.ensure_clinic(:name, :slug, :tz, CAST(:id AS uuid))").bindparams(
            name=os.environ.get("PEMA_CLINIC_NAME", "").strip() or DEFAULT_CLINIC_NAME,
            slug=INSTALLATION_SLUG,
            tz=DEFAULT_TIMEZONE,
            id=_install_id(),
        )
    )


def downgrade() -> None:
    _sql("DROP SCHEMA clinic CASCADE")
    _sql("DROP SCHEMA ctx CASCADE")

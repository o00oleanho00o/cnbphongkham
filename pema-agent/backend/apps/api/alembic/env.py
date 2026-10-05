"""Alembic environment for schemas ``ctx``, ``clinic``, ``clinic_agent`` and ``agent``.

Runs as a migration/owner role (``PEMA_MIGRATION_DATABASE_URL``), never as ``be_app`` or
``agent_worker``. The version table lives in ``public`` and neither runtime role is granted access to it.

Parallel packages add their own revision files (``NNNN_<package>_<what>.py``) and never edit an existing
one; package G merges heads with ``alembic merge`` (``make db-upgrade`` runs ``upgrade heads``).
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

DEFAULT_URL = "postgresql+psycopg://postgres@localhost:5432/pema"
VERSION_TABLE = "alembic_version_pema"

config = context.config


def _url() -> str:
    return os.environ.get("PEMA_MIGRATION_DATABASE_URL", DEFAULT_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table=VERSION_TABLE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

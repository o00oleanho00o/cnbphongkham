"""The runtime role of schema ``agent_rt``: ``agent_rt_app`` may read and write the data, add to the trace and
nothing else (no DDL, no changing or deleting trace rows). Run ``agent db bootstrap-role`` as an owner role
(``AGENT_MIGRATION_DATABASE_URL``) before or after the migrations; it is safe to run again (it also resets the
password). The service then connects as ``agent_rt_app`` through ``AGENT_DATABASE_URL``.
"""

from __future__ import annotations

from typing import Final, LiteralString

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

RUNTIME_ROLE: Final = "agent_rt_app"
PASSWORD_ENV: Final = "AGENT_RT_APP_PASSWORD"  # noqa: S105 - the name of the variable, not a password
MIGRATION_URL_ENV: Final = "AGENT_MIGRATION_DATABASE_URL"
SCHEMA: Final = "agent_rt"
DATA_TABLES: Final = (
    "agent_memory",
    "agent_skill",
    "agent_session",
    "agent_message",
    "agent_conversation",
    "agent_ingress",
    "agent_model_settings",
)
TRACE_TABLES: Final = ("agent_turn", "agent_turn_event")
GRANTS: Final[tuple[tuple[tuple[str, ...], LiteralString], ...]] = (
    (DATA_TABLES, "SELECT, INSERT, UPDATE, DELETE"),
    (TRACE_TABLES, "SELECT, INSERT"),
)
MIN_PASSWORD_CHARS: Final = 16


def bootstrap_role(migration_url: str, password: str) -> list[str]:
    """Creates or updates the role and grants what exists so far; returns what it did, never the password."""
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"{PASSWORD_ENV} must have at least {MIN_PASSWORD_CHARS} characters")
    role = sql.Identifier(RUNTIME_ROLE)
    done: list[str] = []
    with psycopg.connect(_libpq_url(migration_url), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RUNTIME_ROLE,)).fetchone()
        if exists is None:
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION "
                    "NOBYPASSRLS"
                ).format(role)
            )
            done.append(f"created role {RUNTIME_ROLE}")
        conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(role, sql.Literal(password)))
        done.append("set its password and LOGIN")
        database = conn.execute("SELECT current_database()").fetchone()
        if database is not None:
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database[0]), role)
            )
            done.append(f"granted CONNECT on database {database[0]}")
        schema = conn.execute("SELECT to_regnamespace(%s) IS NOT NULL", (SCHEMA,)).fetchone()
        if schema is None or not schema[0]:
            done.append(f"schema {SCHEMA} does not exist yet: the migrations grant the tables when they run")
            return done
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(SCHEMA), role))
        for tables, rights in GRANTS:
            for table in tables:
                found = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (f"{SCHEMA}.{table}",)).fetchone()
                if found is None or not found[0]:
                    continue
                conn.execute(
                    sql.SQL("GRANT {} ON {} TO {}").format(
                        sql.SQL(rights), sql.Identifier(SCHEMA, table), role
                    )
                )
                done.append(f"granted {rights} on {SCHEMA}.{table}")
        conn.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), role
            )
        )
        done.append(f"granted USAGE, SELECT on the sequences of {SCHEMA}")
    return done


def _libpq_url(url: str) -> str:
    """SQLAlchemy URLs name the driver (``postgresql+psycopg://``); psycopg wants a plain libpq URL."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)

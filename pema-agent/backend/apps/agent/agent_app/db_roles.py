"""The runtime role of schema ``agent_rt``: ``agent_rt_app`` may read and write the data, add to the trace and
nothing else (no DDL, no changing or deleting trace rows). Run ``agent db bootstrap-role`` as an owner role
(``AGENT_MIGRATION_DATABASE_URL``) before or after the migrations; it is safe to run again (it also resets the
password). The service then connects as ``agent_rt_app`` through ``AGENT_DATABASE_URL``.

The agent has a database of its own (``pema_agent`` in the compose stack), never the clinic's: bootstrap-role
creates it when it is missing, and only ``agent_rt_app`` (and superusers) may connect to it. The role gets
CONNECT on that database alone (.claude/rules/agent-crm-boundary.md, L1).
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
    "agent_session",
    "agent_message",
    "agent_conversation",
    "agent_ingress",
    "agent_model_settings",
    "agent_model_entry",
    "agent_plugin",
    "agent_plugin_record",
)
TRACE_TABLES: Final = ("agent_turn", "agent_turn_event")
READ_TABLES: Final = ("agent_plugin_migration",)
GRANTS: Final[tuple[tuple[tuple[str, ...], LiteralString], ...]] = (
    (DATA_TABLES, "SELECT, INSERT, UPDATE, DELETE"),
    (TRACE_TABLES, "SELECT, INSERT"),
    (READ_TABLES, "SELECT"),
)
PLUGIN_TABLE_RIGHTS: Final = "SELECT, INSERT, UPDATE, DELETE"
MIN_PASSWORD_CHARS: Final = 16
# superusers still connect to them (backups, migrations); no other role needs to
MAINTENANCE_DATABASES: Final = ("postgres", "template1")


def bootstrap_role(migration_url: str, password: str) -> list[str]:
    """Creates or updates the role and grants what exists so far; returns what it did, never the password."""
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"{PASSWORD_ENV} must have at least {MIN_PASSWORD_CHARS} characters")
    role = sql.Identifier(RUNTIME_ROLE)
    done = ensure_database(migration_url)
    with psycopg.connect(libpq_url(migration_url), autocommit=True) as conn:
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
            name = sql.Identifier(database[0])
            conn.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(name))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(name, role))
            done.append(f"granted CONNECT on database {database[0]} to {RUNTIME_ROLE} only")
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
        done.extend(_grant_plugin_tables(conn))
    return done


def ensure_database(migration_url: str) -> list[str]:
    """Creates the database the URL names when the server lacks it, and shuts PUBLIC out of the maintenance
    databases (``postgres``, ``template1``), so the runtime role can connect to its own database only."""
    url = make_url(migration_url)
    name = url.database
    if not name:
        raise ValueError(f"{MIGRATION_URL_ENV} must name a database")
    maintenance = url.set(database="postgres").render_as_string(hide_password=False)
    done: list[str] = []
    with psycopg.connect(libpq_url(maintenance), autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            done.append(f"created database {name}")
        for database in MAINTENANCE_DATABASES:
            try:
                conn.execute(
                    sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
                )
            except psycopg.errors.InsufficientPrivilege:
                done.append(
                    f"could not revoke CONNECT on {database} from PUBLIC (not its owner): ask the DBA"
                )
            else:
                done.append(f"revoked CONNECT on {database} from PUBLIC")
    return done


def _grant_plugin_tables(conn: psycopg.Connection) -> list[str]:
    """The tables plugins created (``agent db migrate-plugins``), by the prefixes recorded there."""
    found = conn.execute("SELECT to_regclass('agent_rt.agent_plugin_migration') IS NOT NULL").fetchone()
    if found is None or not found[0]:
        return []
    prefixes = conn.execute("SELECT DISTINCT table_prefix FROM agent_rt.agent_plugin_migration").fetchall()
    tables = [
        table
        for (prefix,) in prefixes
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND starts_with(tablename, %s)",
            (SCHEMA, prefix),
        ).fetchall()
    ]
    for table in tables:
        conn.execute(
            sql.SQL("GRANT {} ON {} TO {}").format(
                sql.SQL(PLUGIN_TABLE_RIGHTS), sql.Identifier(SCHEMA, table), sql.Identifier(RUNTIME_ROLE)
            )
        )
    return [f"granted {PLUGIN_TABLE_RIGHTS} on {SCHEMA}.{table}" for table in tables]


def libpq_url(url: str) -> str:
    """SQLAlchemy URLs name the driver (``postgresql+psycopg://``); psycopg wants a plain libpq URL."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)

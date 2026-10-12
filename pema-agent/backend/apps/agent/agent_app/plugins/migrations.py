"""Tables a plugin keeps of its own, created by plain SQL files the plugin ships.

A plugin declares them in ``plugin.toml``::

    [migrations]
    dir = "migrations"      # 0001_create_sources.sql, 0002_add_index.sql ...
    prefix = "kb_"          # every table it creates starts with this

``agent db migrate-plugins`` (owner role, ``AGENT_MIGRATION_DATABASE_URL``) runs, in schema ``agent_rt``,
each file not run yet, one transaction per file, records it in ``agent_rt.agent_plugin_migration`` with a
checksum and grants the runtime role read and write on the plugin's tables. Files only go forward: there is
no way back, and a file changed after it ran stops the command. The service never runs DDL: a plugin whose
tables are missing says so (``PluginDatabase.require_migrations``) instead of failing later.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_app.db_roles import PLUGIN_TABLE_RIGHTS, RUNTIME_ROLE, SCHEMA, libpq_url
from agent_app.plugins.manifest import PluginError, PluginSource

FILE_PATTERN: Final = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
CREATED_TABLE: Final = re.compile(
    r"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?agent_rt\"?\.)?\"?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
NOT_MIGRATED: Final = "the plugin's tables are not there yet: run agent db migrate-plugins"


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def migration_files(source: PluginSource) -> list[MigrationFile]:
    """The plugin's files in version order; none when it declares no migrations."""
    spec = source.manifest.migrations
    if spec is None:
        return []
    folder = source.folder / spec.dir
    if not folder.is_dir():
        raise PluginError(source.name, f"migrations folder {spec.dir} is missing")
    files = [path for path in sorted(folder.iterdir()) if path.suffix == ".sql"]
    found = [_read(source, path, spec.prefix) for path in files]
    versions = [item.version for item in found]
    if versions != list(range(1, len(versions) + 1)):
        raise PluginError(source.name, f"migration versions must run 0001, 0002 ... without gaps: {versions}")
    return found


def _read(source: PluginSource, path: Path, prefix: str) -> MigrationFile:
    match = FILE_PATTERN.match(path.name)
    if match is None:
        raise PluginError(source.name, f"{path.name}: name migration files NNNN_words.sql")
    body = path.read_text(encoding="utf-8")
    outside = [table for table in CREATED_TABLE.findall(body) if not table.startswith(prefix)]
    if outside:
        raise PluginError(source.name, f"{path.name} creates tables without the prefix {prefix}: {outside}")
    return MigrationFile(int(match.group(1)), path.name, body)


def migrate_plugins(migration_url: str, sources: Iterable[PluginSource]) -> list[str]:
    """Runs every file not run yet of every plugin given; returns what it did. Stops at the first problem."""
    done: list[str] = []
    with psycopg.connect(libpq_url(migration_url)) as conn:
        for source in sources:
            files = migration_files(source)
            spec = source.manifest.migrations
            if not files or spec is None:
                continue
            applied = _applied(conn, source.name)
            for item in files:
                done.extend(_apply(conn, source.name, item, spec.prefix, applied.get(item.version)))
    return done


def _applied(conn: psycopg.Connection, plugin: str) -> dict[int, str]:
    rows = conn.execute(
        "SELECT version, checksum FROM agent_rt.agent_plugin_migration WHERE plugin = %s", (plugin,)
    ).fetchall()
    conn.commit()
    return {int(version): str(checksum) for version, checksum in rows}


def _apply(
    conn: psycopg.Connection, plugin: str, item: MigrationFile, prefix: str, checksum: str | None
) -> list[str]:
    if checksum == item.checksum:
        return []
    if checksum is not None:
        raise PluginError(plugin, f"{item.name} changed after it ran; add a new file instead of editing it")
    with conn.transaction():
        conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(SCHEMA)))
        conn.execute(item.sql.encode("utf-8"))
        conn.execute(
            "INSERT INTO agent_rt.agent_plugin_migration (plugin, version, name, checksum, table_prefix) "
            "VALUES (%s, %s, %s, %s, %s)",
            (plugin, item.version, item.name, item.checksum, prefix),
        )
        granted = grant_plugin_tables(conn, prefix)
    return [f"{plugin}: ran {item.name}", *granted]


def grant_plugin_tables(conn: psycopg.Connection, prefix: str) -> list[str]:
    """Read and write on the tables with this prefix for the runtime role, when the role exists already."""
    role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RUNTIME_ROLE,)).fetchone()
    if role is None:
        return []
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s AND starts_with(tablename, %s)",
        (SCHEMA, prefix),
    ).fetchall()
    for (table,) in tables:
        conn.execute(
            sql.SQL("GRANT {} ON {} TO {}").format(
                sql.SQL(PLUGIN_TABLE_RIGHTS), sql.Identifier(SCHEMA, table), sql.Identifier(RUNTIME_ROLE)
            )
        )
    conn.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
            sql.Identifier(SCHEMA), sql.Identifier(RUNTIME_ROLE)
        )
    )
    return [f"granted {PLUGIN_TABLE_RIGHTS} on {SCHEMA}.{table}" for (table,) in tables]


_LATEST = text("SELECT max(version) FROM agent_rt.agent_plugin_migration WHERE plugin = :plugin")


async def latest_applied(engine: AsyncEngine, plugin: str) -> int:
    """The highest version of this plugin's files that has run; 0 when none has."""
    async with engine.connect() as conn:
        value = (await conn.execute(_LATEST, {"plugin": plugin})).scalar_one_or_none()
    return int(value or 0)


def plugins_with_migrations(sources: Mapping[str, PluginSource]) -> list[PluginSource]:
    return [source for source in sources.values() if source.manifest.migrations is not None]

"""Tables a plugin keeps of its own: the SQL files it declares, how they are read and checked, and (with
``PEMA_TEST_DATABASE_URL``, a throwaway database) how ``migrate-plugins`` runs them once, grants them to the
runtime role and refuses a file edited after it ran."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import create_async_engine

from agent_app.plugins import (
    DatabaseAccess,
    PluginDatabase,
    PluginError,
    PluginHost,
    PluginSource,
    discover,
)
from agent_app.plugins.migrations import latest_applied, migrate_plugins, migration_files

APP_DIR = Path(__file__).resolve().parents[1]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"

CAPTURE = """
def register(ctx):
    ctx.config["seen"].append(ctx.database)
"""


def _plugin(root: Path, files: dict[str, str], *, prefix: str = "kbt_", name: str = "kbt") -> PluginSource:
    folder = root / name
    (folder / "migrations").mkdir(parents=True)
    (folder / "plugin.toml").write_text(
        f'name = "{name}"\n\n[migrations]\ndir = "migrations"\nprefix = "{prefix}"\n', encoding="utf-8"
    )
    (folder / "__init__.py").write_text(CAPTURE, encoding="utf-8")
    for file_name, body in files.items():
        (folder / "migrations" / file_name).write_text(body, encoding="utf-8")
    return discover([("agent", root)]).plugins[name]


CREATE = "CREATE TABLE kbt_source (id text PRIMARY KEY, title text NOT NULL);"
ADD = "ALTER TABLE kbt_source ADD COLUMN note text;"


def test_files_are_read_in_version_order(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"0002_add_note.sql": ADD, "0001_create.sql": CREATE})

    files = migration_files(source)

    assert [(f.version, f.name) for f in files] == [(1, "0001_create.sql"), (2, "0002_add_note.sql")]


def test_a_gap_in_the_versions_is_refused(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"0001_create.sql": CREATE, "0003_add_note.sql": ADD})

    with pytest.raises(PluginError, match="without gaps"):
        migration_files(source)


def test_a_table_without_the_plugins_prefix_is_refused(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"0001_create.sql": "CREATE TABLE IF NOT EXISTS agent_rt.notes (id text);"})

    with pytest.raises(PluginError, match="without the prefix kbt_"):
        migration_files(source)


def test_a_badly_named_file_is_refused(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"create.sql": CREATE})

    with pytest.raises(PluginError, match=r"NNNN_words.sql"):
        migration_files(source)


def test_a_prefix_must_be_lowercase_words_ending_in_an_underscore(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "plugin.toml").write_text('name = "bad"\n\n[migrations]\nprefix = "KB"\n', encoding="utf-8")
    (folder / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")

    found = discover([("agent", tmp_path)])

    assert "bad" not in found.plugins
    assert "prefix" in found.broken["bad"]


def test_the_core_tables_prefix_cannot_be_claimed(tmp_path: Path) -> None:
    folder = tmp_path / "greedy"
    folder.mkdir()
    (folder / "plugin.toml").write_text(
        'name = "greedy"\n\n[migrations]\nprefix = "agent_"\n', encoding="utf-8"
    )
    (folder / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")

    found = discover([("agent", tmp_path)])

    assert "greedy" not in found.plugins
    assert "reserved" in found.broken["greedy"]


def test_a_plugin_has_no_database_when_the_agent_runs_without_one(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"0001_create.sql": CREATE})
    seen: list[object] = []

    PluginHost({"kbt": source}, {}).enable("kbt", {"seen": seen})

    assert seen == [None]


def test_a_plugin_gets_the_database_scope_and_its_latest_file(tmp_path: Path) -> None:
    source = _plugin(tmp_path, {"0001_create.sql": CREATE, "0002_add_note.sql": ADD})
    engine = create_async_engine("postgresql+psycopg://u:p@localhost:1/none")
    host = PluginHost({"kbt": source}, {}, database=DatabaseAccess(engine, tenant_id="t1", agent="clinic"))
    seen: list[PluginDatabase | None] = []

    host.enable("kbt", {"seen": seen})

    (database,) = seen
    assert database is not None
    assert (database.plugin, database.tenant_id, database.agent, database.latest_migration) == (
        "kbt",
        "t1",
        "clinic",
        2,
    )


# --- on Postgres ---


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[str, Engine]]:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(sql("DROP SCHEMA IF EXISTS agent_rt CASCADE"))
        conn.execute(sql("DROP TABLE IF EXISTS public.alembic_version_agent_rt"))
    previous = os.environ.get(MIGRATION_ENV)
    os.environ[MIGRATION_ENV] = url
    try:
        command.upgrade(Config(str(APP_DIR / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop(MIGRATION_ENV, None)
        else:
            os.environ[MIGRATION_ENV] = previous
    yield url, engine
    engine.dispose()


@pytest.mark.db
def test_files_run_once_and_are_recorded(migrated: tuple[str, Engine], tmp_path: Path) -> None:
    url, engine = migrated
    source = _plugin(tmp_path, {"0001_create.sql": CREATE, "0002_add_note.sql": ADD})

    first = migrate_plugins(url, [source])
    again = migrate_plugins(url, [source])

    assert [line for line in first if line.startswith("kbt: ran")] == [
        "kbt: ran 0001_create.sql",
        "kbt: ran 0002_add_note.sql",
    ]
    assert again == []
    with engine.connect() as conn:
        columns = conn.execute(
            sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'agent_rt' AND table_name = 'kbt_source' ORDER BY ordinal_position"
            )
        ).scalars()
        assert list(columns) == ["id", "title", "note"]
    assert _latest(url, "kbt") == 2


@pytest.mark.db
def test_a_file_edited_after_it_ran_stops_the_command(migrated: tuple[str, Engine], tmp_path: Path) -> None:
    url, _ = migrated
    first = _plugin(tmp_path / "a", {"0001_create.sql": CREATE.replace("kbt_source", "kbt_edit")})
    migrate_plugins(url, [first])
    edited = _plugin(tmp_path / "b", {"0001_create.sql": CREATE.replace("kbt_source", "kbt_edit2")})

    with pytest.raises(PluginError, match="changed after it ran"):
        migrate_plugins(url, [edited])


def _latest(url: str, plugin: str) -> int:
    async def read() -> int:
        engine = create_async_engine(url)
        try:
            return await latest_applied(engine, plugin)
        finally:
            await engine.dispose()

    return asyncio.run(read(), loop_factory=asyncio.SelectorEventLoop)

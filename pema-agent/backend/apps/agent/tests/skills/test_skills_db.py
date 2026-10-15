"""The skills store on Postgres: its tables made by ``migrate-plugins``, the skills the agent wrote before the
plugin imported once, the versions every save leaves, and each tenant seeing only its own items. Needs
``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated again); skipped otherwise.

The async part runs on a selector event loop: psycopg's async driver cannot use the Windows proactor loop.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import create_async_engine

from agent_app.plugins import discover
from agent_app.plugins.migrations import migrate_plugins
from agent_app.runtime import BUNDLED_PLUGINS
from plugins.skills.models import Item
from plugins.skills.store import NameTakenError, PostgresItemStore

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[2]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"


@pytest.fixture(scope="module")
def db_url() -> str:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(sql("DROP SCHEMA IF EXISTS agent_rt CASCADE"))
        conn.execute(sql("DROP TABLE IF EXISTS public.alembic_version_agent_rt"))
    engine.dispose()
    previous = os.environ.get(MIGRATION_ENV)
    os.environ[MIGRATION_ENV] = url
    try:
        command.upgrade(Config(str(APP_DIR / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop(MIGRATION_ENV, None)
        else:
            os.environ[MIGRATION_ENV] = previous
    engine = create_engine(url)
    with engine.begin() as conn:  # a skill the agent wrote before the plugin existed
        conn.execute(
            sql(
                "INSERT INTO agent_rt.agent_skill (tenant_id, agent, name, description, body) "
                "VALUES ('clinic-a', 'clinic', 'cu', 'Kỹ năng cũ', 'Các bước cũ.')"
            )
        )
    engine.dispose()
    migrate_plugins(url, [discover([("bundled", BUNDLED_PLUGINS)]).plugins["skills"]])
    return url


def _run(url: str, work: Callable[[PostgresItemStore, PostgresItemStore], Awaitable[None]]) -> None:
    async def main() -> None:
        engine = create_async_engine(url)
        try:
            await work(
                PostgresItemStore(engine, tenant_id="clinic-a", agent="clinic"),
                PostgresItemStore(engine, tenant_id="clinic-b", agent="clinic"),
            )
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _item(item_id: str, name: str, body: str = "Nội dung.", **given: object) -> Item:
    fields: dict[str, object] = {"kind": "rules", "description": f"Về {name}", **given}
    return Item(id=item_id, name=name, body=body, **fields)  # type: ignore[arg-type]


def test_the_skills_the_agent_wrote_before_are_imported_once_with_a_first_version(db_url: str) -> None:
    async def work(mine: PostgresItemStore, theirs: PostgresItemStore) -> None:
        (imported,) = await mine.list(kind="skill")
        versions = await mine.versions(imported.id)

        assert (imported.name, imported.origin, imported.status, imported.scopes) == (
            "cu",
            "agent",
            "active",
            [],
        )
        assert imported.body == "Các bước cũ."
        assert [(v.version, v.changed_by) for v in versions] == [(1, "import")]
        assert await theirs.list(kind="skill") == []

    _run(db_url, work)


def test_the_dev_agents_one_file_skill_is_in_the_database_and_the_core_table_is_gone(db_url: str) -> None:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        seeded = conn.execute(
            sql(
                "SELECT name, status, origin, scopes, body FROM agent_rt.sk_item "
                "WHERE tenant_id = 'default' AND agent = 'dev'"
            )
        ).all()
        versions = conn.execute(
            sql(
                "SELECT version, changed_by FROM agent_rt.sk_item_version WHERE item_id = 'itm-seed-write-a-plan'"
            )
        ).all()
        gone = conn.execute(sql("SELECT to_regclass('agent_rt.agent_skill') IS NULL")).scalar()
    engine.dispose()

    assert [(r.name, r.status, r.origin, r.scopes) for r in seeded] == [
        ("write-a-plan", "active", "admin", [])
    ]
    assert seeded[0].body.splitlines()[0] == "1. Restate the goal in one sentence."
    assert [tuple(v) for v in versions] == [(1, "seed")]
    assert gone is True


def test_every_save_is_a_new_version_with_the_whole_item_and_who_made_it(db_url: str) -> None:
    async def work(mine: PostgresItemStore, theirs: PostgresItemStore) -> None:
        first = await mine.save(_item("itm-v1", "chung", "Một.", scopes=["plugin:zalo"]), by="an")
        second = await mine.save(replace(first, body="Hai.", meta={"nhan": ["gia"]}), by="binh", reason="sửa")
        read = await mine.get("itm-v1")
        versions = await mine.versions("itm-v1")

        assert (first.version, second.version) == (1, 2)
        assert read is not None
        assert (read.body, read.scopes, read.meta, read.updated_by, read.version) == (
            "Hai.",
            ["plugin:zalo"],
            {"nhan": ["gia"]},
            "binh",
            2,
        )
        assert [(v.version, v.snapshot["body"], v.reason) for v in versions] == [
            (2, "Hai.", "sửa"),
            (1, "Một.", ""),
        ]
        assert await theirs.get("itm-v1") is None

    _run(db_url, work)


def test_a_name_is_taken_once_per_kind_and_the_same_name_may_be_another_kind(db_url: str) -> None:
    async def work(mine: PostgresItemStore, theirs: PostgresItemStore) -> None:
        await mine.save(_item("itm-n1", "ten", kind="rules"), by="an")
        await mine.save(_item("itm-n2", "ten", kind="persona"), by="an")
        with pytest.raises(NameTakenError):
            await mine.save(_item("itm-n3", "ten", kind="rules"), by="an")
        await theirs.save(_item("itm-n4", "ten", kind="rules"), by="an")  # another tenant, no clash

        assert [i.id for i in await mine.list(kind="persona")] == ["itm-n2"]
        assert await mine.get("itm-n3") is None

    _run(db_url, work)


def test_the_list_filters_by_status_and_a_tenant_never_sees_anothers_items(db_url: str) -> None:
    async def work(mine: PostgresItemStore, theirs: PostgresItemStore) -> None:
        await mine.save(_item("itm-s1", "dang-dung", status="active"), by="an")
        await mine.save(_item("itm-s2", "ban-nhap", status="draft"), by="an")

        active = {i.name for i in await mine.list(status="active")}
        drafts = {i.name for i in await mine.list(status="draft")}
        theirs_all = {i.name for i in await theirs.list()}

        assert "dang-dung" in active
        assert "ban-nhap" not in active
        assert "ban-nhap" in drafts
        assert not {"dang-dung", "ban-nhap"} & theirs_all

    _run(db_url, work)

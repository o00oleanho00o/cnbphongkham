"""The names of people the Zalo plugin knows, for the dashboard's chat list: one read per account, only the
people asked for, only those with a name, and a route that refuses malformed input."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins.records import InMemoryPluginRecords
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime
from plugins.zalo.contacts import ContactBook

TOKEN = "t" * 40
ADMIN = "a" * 40
HEADERS = {"Authorization": f"Bearer {ADMIN}"}
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


async def _book() -> ContactBook:
    book = ContactBook(InMemoryPluginRecords().storage("zalo"))
    await book.record("nick", "u1", "Nguyễn Mai", NOW)
    await book.record("nick", "u2", "", NOW)
    await book.record("nick", "u3", "Lê Bình", NOW)
    await book.record("other", "u1", "Người khác", NOW)
    return book


async def test_names_are_those_asked_for_known_and_of_the_account() -> None:
    book = await _book()

    names = await book.names("nick", ["u1", "u2", "u9"])

    assert names == {"u1": "Nguyễn Mai"}


async def test_nobody_asked_for_means_no_names() -> None:
    assert await (await _book()).names("nick", []) == {}


async def test_the_names_route_answers_only_valid_ids_and_a_valid_account(tmp_path: Path) -> None:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\n\n[plugins]\nenabled = ["zalo"]\n', encoding="utf-8"
    )
    runtime = build_runtime(
        load_profile(folder), fake=True, env={"AGENT_SECRET_ENCRYPTION_KEY": "0f" * 32}, db=None
    )
    app = create_app(
        runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent/v1/plugins/zalo"
    ) as client:
        await client.get("/contacts", headers=HEADERS)
        empty = await client.get("/contacts/names?account_id=nick&ids=u1,bad/id", headers=HEADERS)
        bad_account = await client.get("/contacts/names?account_id=Nick:1&ids=u1", headers=HEADERS)
        no_scope = await client.get("/contacts/names?account_id=nick&ids=u1")

    assert (empty.status_code, empty.json()) == (200, {})
    assert (bad_account.status_code, no_scope.status_code) == (422, 401)

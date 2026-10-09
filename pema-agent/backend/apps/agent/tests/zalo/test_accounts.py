"""The Zalo plugin's accounts: created, changed and deleted through its admin routes, credentials sealed with the
service's key and never shown, the kind fixed at creation, a bot account closed to strangers by default."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginError
from agent_app.plugins.records import InMemoryPluginRecords
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from plugins.zalo.accounts import SECRET, AccountStore
from plugins.zalo.models import AccountCreate, ChannelKind
from secretcipher import decrypt_with, encrypt_with

TOKEN = "t" * 40
ADMIN = "a" * 40
KEY = "0f" * 32
OTHER_KEY = "1e" * 32
HEADERS = {"Authorization": f"Bearer {ADMIN}"}


def _runtime(tmp_path: Path) -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\n\n[plugins]\nenabled = ["zalo"]\n', encoding="utf-8"
    )
    return build_runtime(load_profile(folder), fake=True, env={"AGENT_SECRET_ENCRYPTION_KEY": KEY}, db=None)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(
        runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent/v1/plugins/zalo")


async def test_accounts_are_created_listed_changed_and_deleted(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        personal = await client.post("/accounts", json={"id": "le-tan", "label": "Lễ tân"}, headers=HEADERS)
        bot = await client.post(
            "/accounts", json={"id": "bot-1", "label": "Bot", "channel": "zalo_bot"}, headers=HEADERS
        )
        again = await client.post("/accounts", json={"id": "bot-1", "label": "x"}, headers=HEADERS)
        changed = await client.patch(
            "/accounts/le-tan",
            json={
                "label": "Lễ tân 2",
                "allowlist": {"mode": "list", "user_ids": ["u1"]},
                "auto_react_icon": "like",
            },
            headers=HEADERS,
        )
        listed = await client.get("/accounts", headers=HEADERS)
        deleted = await client.delete("/accounts/bot-1", headers=HEADERS)
        gone = await client.delete("/accounts/bot-1", headers=HEADERS)
        after = await client.get("/accounts", headers=HEADERS)

    assert personal.status_code == 201
    assert personal.json()["allowlist"] == {"mode": "all", "user_ids": []}
    assert bot.json()["allowlist"] == {"mode": "list", "user_ids": []}
    assert (bot.json()["channel"], bot.json()["running"], bot.json()["has_credentials"]) == (
        "zalo_bot",
        False,
        False,
    )
    assert again.status_code == 409
    assert (
        changed.json()["label"],
        changed.json()["allowlist"]["user_ids"],
        changed.json()["auto_react_icon"],
    ) == (
        "Lễ tân 2",
        ["u1"],
        "like",
    )
    assert [a["id"] for a in listed.json()] == ["bot-1", "le-tan"]
    assert (deleted.status_code, gone.status_code) == (204, 404)
    assert [a["id"] for a in after.json()] == ["le-tan"]
    runtime.close()


@pytest.mark.parametrize(
    "body",
    [
        {"channel": "zalo_bot"},
        {"auto_react_icon": "fire"},
        {"auto_accept_friend_delay_minutes": 5000},
        {"disabled_tools": ["bad name!"]},
        {"label": ""},
        {"has_credentials": True},
    ],
)
async def test_bad_changes_are_refused_and_the_kind_cannot_change(
    tmp_path: Path, body: dict[str, object]
) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        await client.post("/accounts", json={"id": "le-tan", "label": "Lễ tân"}, headers=HEADERS)
        refused = await client.patch("/accounts/le-tan", json=body, headers=HEADERS)
        unchanged = (await client.get("/accounts", headers=HEADERS)).json()[0]

    assert refused.status_code == 422
    assert (unchanged["channel"], unchanged["auto_react_icon"], unchanged["label"]) == (
        "zalo_personal",
        "heart",
        "Lễ tân",
    )
    runtime.close()


async def test_bad_new_accounts_and_unknown_ones_are_refused(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        bad_id = await client.post("/accounts", json={"id": "Lễ Tân", "label": "x"}, headers=HEADERS)
        long_id = await client.post("/accounts", json={"id": "a" * 59, "label": "x"}, headers=HEADERS)
        bad_kind = await client.post(
            "/accounts", json={"id": "x", "label": "x", "channel": "sms"}, headers=HEADERS
        )
        unknown = await client.patch("/accounts/nobody", json={"label": "x"}, headers=HEADERS)
        anonymous = await client.get("/accounts")

    assert (bad_id.status_code, long_id.status_code, bad_kind.status_code) == (422, 422, 422)
    assert (unknown.status_code, anonymous.status_code) == (404, 401)
    runtime.close()


async def test_the_reaction_icons_come_from_the_plugin(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        icons = (await client.get("/accounts/reaction-icons", headers=HEADERS)).json()

    assert icons[0] == {"key": "heart", "emoji": "❤️", "label": "Tim"}
    assert len(icons) == 9
    runtime.close()


def _store(key: str = KEY, records: InMemoryPluginRecords | None = None) -> AccountStore:
    storage = (records or InMemoryPluginRecords()).storage("zalo")

    def decrypt(sealed: str) -> str:
        try:
            return decrypt_with(key, sealed)
        except Exception as err:
            raise PluginError("zalo", "does not open") from err

    return AccountStore(storage, encrypt=lambda text: encrypt_with(key, text), decrypt=decrypt)


async def test_a_credential_is_sealed_read_back_once_and_removed_with_its_account() -> None:
    records = InMemoryPluginRecords()
    store = _store(records=records)
    await store.create(AccountCreate(id="bot-1", label="Bot", channel=ChannelKind.ZALO_BOT))

    await store.set_secret("bot-1", "  123456:secret-token  ")
    raw = await records.storage("zalo").get(SECRET + "bot-1")
    listed = [a.model_dump() for a in await store.list()]
    opened = await store.secret("bot-1")
    with_other_key = await _store(OTHER_KEY, records).secret("bot-1")
    await store.delete("bot-1")

    assert isinstance(raw, str)
    assert "secret-token" not in raw
    assert "secret-token" not in str(listed)
    assert (opened, with_other_key) == ("123456:secret-token", None)
    assert (await store.has_secret("bot-1"), await store.secret("bot-1")) == (False, None)


async def test_a_blank_credential_removes_the_stored_one() -> None:
    store = _store()
    await store.set_secret("a", "x")
    await store.set_secret("a", "   ")
    assert await store.has_secret("a") is False

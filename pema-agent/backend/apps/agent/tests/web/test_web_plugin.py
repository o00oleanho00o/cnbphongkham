"""The ``web`` plugin: the first visit makes the only admin account, its JWT opens the admin routes, a
password change ends older logins, failed logins are limited, API keys reach the chat routes only, and with
the plugin off nobody gets in."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from agent_app.cli import forget_records
from agent_app.gateway import GatewaySettings, create_app
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from plugins.web import tokens

KEY = "0f" * 32
EMAIL = "Owner@Clinic.test"
PASSWORD = "correct-horse-1"
CHAT = {"message_id": "m1", "user_id": "u1", "text": "hi"}


def _runtime(tmp_path: Path, plugins: list[str]) -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir(parents=True)
    names = ", ".join(f'"{name}"' for name in plugins)
    (folder / "agent.toml").write_text(
        textwrap.dedent(f"""
        [agent]
        name = "t"
        system_prompt = "p"

        [plugins]
        enabled = [{names}]
        """),
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY, "AGENT_DATA_DIR": str(tmp_path / "home")}
    return build_runtime(load_profile(folder), fake=True, env=env, db=None)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(runtime.dispatcher(), GatewaySettings(), plugins=runtime.plugin_manager)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: httpx.AsyncClient) -> str:
    created = await client.post("/v1/hooks/web/setup", json={"email": EMAIL, "password": PASSWORD})
    assert created.status_code == 201
    return created.json()["token"]


async def test_the_first_visit_makes_the_only_admin_and_its_token_opens_the_admin_routes(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, ["web"])
    async with _client(runtime) as client:
        before = (await client.get("/v1/hooks/web/state")).json()
        weak = await client.post("/v1/hooks/web/setup", json={"email": EMAIL, "password": "short"})
        token = await _setup(client)
        again = await client.post("/v1/hooks/web/setup", json={"email": "x@y.z", "password": PASSWORD})
        after = (await client.get("/v1/hooks/web/state")).json()
        me = await client.get("/v1/plugins/web/me", headers=_bearer(token))
        plugins = await client.get("/v1/admin/plugins", headers=_bearer(token))
        chat = await client.post("/v1/chat", json=CHAT, headers=_bearer(token))
        anonymous = await client.get("/v1/admin/plugins")

    assert (before, after) == ({"needs_setup": True}, {"needs_setup": False})
    assert (weak.status_code, again.status_code) == (422, 409)
    assert me.json()["email"] == "owner@clinic.test"
    assert (plugins.status_code, chat.status_code, anonymous.status_code) == (200, 200, 401)
    runtime.close()


async def test_a_password_change_ends_older_logins_and_failed_logins_are_limited(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["web"])
    async with _client(runtime) as client:
        await _setup(client)
        login = await client.post("/v1/hooks/web/login", json={"email": EMAIL, "password": PASSWORD})
        old = login.json()["token"]
        wrong = await client.post(
            "/v1/plugins/web/password",
            json={"current_password": "nope", "new_password": "another-horse-2"},
            headers=_bearer(old),
        )
        changed = await client.post(
            "/v1/plugins/web/password",
            json={"current_password": PASSWORD, "new_password": "another-horse-2"},
            headers=_bearer(old),
        )
        old_after = await client.get("/v1/plugins/web/me", headers=_bearer(old))
        new_after = await client.get("/v1/plugins/web/me", headers=_bearer(changed.json()["token"]))
        failures = [
            (await client.post("/v1/hooks/web/login", json={"email": EMAIL, "password": "bad"})).status_code
            for _ in range(5)
        ]
        locked = await client.post(
            "/v1/hooks/web/login", json={"email": EMAIL, "password": "another-horse-2"}
        )

    assert login.status_code == 200
    assert (wrong.status_code, changed.status_code) == (403, 200)
    assert (old_after.status_code, new_after.status_code) == (401, 200)
    assert failures == [401] * 5
    assert locked.status_code == 429
    runtime.close()


async def test_api_keys_reach_only_the_chat_routes_until_revoked(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["web"])
    async with _client(runtime) as client:
        admin = _bearer(await _setup(client))
        made = await client.post("/v1/plugins/web/api-keys", json={"name": "clinic backend"}, headers=admin)
        key = made.json()["key"]
        listed = await client.get("/v1/plugins/web/api-keys", headers=admin)
        chat = await client.post("/v1/chat", json=CHAT, headers=_bearer(key))
        admin_with_key = await client.get("/v1/admin/plugins", headers=_bearer(key))
        revoked = await client.delete(f"/v1/plugins/web/api-keys/{made.json()['id']}", headers=admin)
        after = await client.post("/v1/chat", json={**CHAT, "message_id": "m2"}, headers=_bearer(key))
        twice = await client.delete(f"/v1/plugins/web/api-keys/{made.json()['id']}", headers=admin)

    assert made.status_code == 201
    assert key.startswith("pak_")
    assert key not in listed.text
    assert [k["name"] for k in listed.json()] == ["clinic backend"]
    assert (chat.status_code, chat.json()["text"]) == (200, "(echo) hi")
    assert admin_with_key.status_code == 403
    assert (revoked.status_code, after.status_code, twice.status_code) == (204, 401, 404)
    runtime.close()


async def test_without_the_web_plugin_nobody_gets_in_and_forgetting_the_account_reopens_setup(
    tmp_path: Path,
) -> None:
    closed = _runtime(tmp_path / "closed", [])
    runtime = _runtime(tmp_path / "open", ["web"])
    async with _client(closed) as shut, _client(runtime) as client:
        chat = await shut.post("/v1/chat", json=CHAT, headers=_bearer("x" * 40))
        token = await _setup(client)
        forgotten = await forget_records(runtime, "web", "user:")
        state = (await client.get("/v1/hooks/web/state")).json()
        stale = await client.get("/v1/plugins/web/me", headers=_bearer(token))

    assert chat.status_code == 401
    assert forgotten == {"plugin": "web", "deleted": ["user:owner@clinic.test"]}
    assert (state, stale.status_code) == ({"needs_setup": True}, 401)
    closed.close()
    runtime.close()


def test_a_token_is_refused_when_expired_tampered_or_signed_with_another_key() -> None:
    now = datetime.now(UTC)
    expired, _ = tokens.issue("k" * 64, "a@b.c", 1, now - timedelta(hours=2), timedelta(hours=1))
    fresh, _ = tokens.issue("k" * 64, "a@b.c", 1, now, timedelta(hours=1))
    other, _ = tokens.issue("k" * 64, "x@y.z", 1, now, timedelta(hours=1))
    head, _, signature = fresh.split(".")
    swapped = f"{head}.{other.split('.')[1]}.{signature}"

    assert tokens.read("k" * 64, expired) is None
    assert tokens.read("k" * 64, fresh) == ("a@b.c", 1)
    assert tokens.read("x" * 64, fresh) is None
    assert tokens.read("k" * 64, swapped) is None


@pytest.mark.parametrize("token", ["", "pak_", "pak_zz_", "a.b", "not-a-token"])
async def test_odd_tokens_are_simply_refused(tmp_path: Path, token: str) -> None:
    runtime = _runtime(tmp_path, ["web"])
    async with _client(runtime) as client:
        refused = await client.post("/v1/chat", json=CHAT, headers=_bearer(token))

    assert refused.status_code == 401
    runtime.close()

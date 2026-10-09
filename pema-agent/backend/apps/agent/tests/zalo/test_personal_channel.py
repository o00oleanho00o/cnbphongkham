"""Personal Zalo accounts end to end against a fake bridge: QR login, the login stored sealed from a signed
event, the channel attached to the bridge's session (or logged in with the stored login), messages in and rich
text out (plain again when Zalo refuses the styles), a locked-out account waiting for a new scan, unsigned
events refused."""

from __future__ import annotations

import asyncio
import json
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_app.channel_hub import ChannelHub, DeliverySettings
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore.harness.model.scripted import ScriptedModel, reply
from plugins.zalo.personal.signing import signed_headers, verify_signature

TOKEN = "t" * 40
ADMIN = "a" * 40
KEY = "0f" * 32
SECRET = "b" * 64
HEADERS = {"Authorization": f"Bearer {ADMIN}"}
FAST = DeliverySettings(tick_s=0.01, backoff_s=(0.0,), max_attempts=3, start_retry_s=0.0)
CREDENTIAL = {"cookie": [{"key": "zpw_sek", "value": "synthetic"}], "imei": "imei-1", "userAgent": "UA"}
QR = "iVBORw0KGgoAAAANSUhEUg=="


class FakeBridge:
    """The bridge's HTTP side: checks each request's signature, keeps account states, records sends."""

    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.started: list[tuple[str, dict[str, Any]]] = []
        self.stopped: list[str] = []
        self.sent: list[dict[str, Any]] = []
        self.typing: list[str] = []
        self.refuse_styles = False
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        if not verify_signature(SECRET, request.headers, body):
            return httpx.Response(
                401, json={"ok": False, "error": {"kind": "unauthorized", "message": "bad"}}
            )
        data: dict[str, Any] = json.loads(body) if body else {}
        parts = request.url.path.split("/")
        account, action = parts[3], "/".join(parts[4:])
        if action == "state":
            state = self.states.get(account, "stopped")
            return _ok(state=state, own_id="me-1" if state == "connected" else "")
        if action == "start":
            self.started.append((account, data["credential"]))
            self.states[account] = "connected"
            return _ok(own_id="me-1")
        if action == "stop":
            self.stopped.append(account)
            self.states[account] = "stopped"
            return _ok()
        if action == "login/qr":
            return _ok(state="waiting_scan", qr_png_base64=QR)
        if action == "send":
            if self.refuse_styles and "styles" in data:
                error = {"kind": "zalo_rejected", "message": "invalid params", "code": 112}
                return httpx.Response(502, json={"ok": False, "error": error})
            self.sent.append(data)
            return _ok(msg_id="out-1")
        if action == "typing":
            self.typing.append(data["thread_id"])
            return _ok()
        return httpx.Response(404, json={"ok": False, "error": {"kind": "bad_request", "message": action}})


def _ok(**fields: Any) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, **fields})


def _runtime(tmp_path: Path, bridge: FakeBridge | None) -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        textwrap.dedent("""
        [agent]
        name = "t"
        system_prompt = "p"

        [plugins]
        enabled = ["zalo"]
        """),
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY, "AGENT_DATA_DIR": str(tmp_path / "data")}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    config: dict[str, Any] = {}
    if bridge is not None:
        config = {"bridge_transport": bridge.transport, "bridge_secret": SECRET}
    host.enable("zalo", config)
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host)


class Setup:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.dispatcher: Dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01, queue_mode="followup"))
        self.hub: ChannelHub = runtime.channel_hub(self.dispatcher, FAST)
        app = create_app(
            self.dispatcher, GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
        )
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")

    async def personal(self, account_id: str = "nick", **settings: Any) -> None:
        await self.client.post(
            "/v1/plugins/zalo/accounts", json={"id": account_id, "label": "Nick"}, headers=HEADERS
        )
        if settings:
            await self.client.patch(f"/v1/plugins/zalo/accounts/{account_id}", json=settings, headers=HEADERS)

    async def event(self, account_id: str, payload: dict[str, Any], secret: str = SECRET) -> httpx.Response:
        body = json.dumps(payload).encode()
        headers = {"content-type": "application/json", **signed_headers(secret, body)}
        return await self.client.post(
            f"/v1/hooks/zalo/webhooks/zalo-bridge/{account_id}", content=body, headers=headers
        )

    async def accounts(self) -> list[dict[str, Any]]:
        return (await self.client.get("/v1/plugins/zalo/accounts", headers=HEADERS)).json()

    async def until(self, check: Any, timeout_s: float = 5.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while not check():
            if loop.time() > deadline:
                raise AssertionError("timed out")
            await self.hub.tick()
            await asyncio.sleep(0.01)

    async def close(self) -> None:
        await self.client.aclose()
        await self.hub.close()
        await self.dispatcher.close()
        self.runtime.close()


def _message(
    text: str, *, sender: str = "u1", group: str | None = None, mentions: list[str] | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "msgId": f"m-{text}",
        "cliMsgId": "c1",
        "uidFrom": sender,
        "dName": "An",
        "content": text,
    }
    if mentions:
        data["mentions"] = [{"uid": uid, "pos": 0, "len": 3} for uid in mentions]
    return {
        "type": "message",
        "message": {"type": 1 if group else 0, "threadId": group or sender, "data": data},
    }


@pytest.fixture
def bridge() -> FakeBridge:
    return FakeBridge()


async def test_a_qr_login_is_stored_from_the_signed_event_and_the_channel_attaches(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    setup.runtime.live.use_model(ScriptedModel([reply("**Giá** khám: 200k")]))
    await setup.personal()

    login = await setup.client.post("/v1/plugins/zalo/accounts/nick/login", headers=HEADERS)
    bridge.states["nick"] = "connected"  # the bridge holds the session the scan opened
    stored = await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()
    account = (await setup.accounts())[0]
    await setup.event("nick", _message("giá khám?"))
    await setup.until(lambda: bridge.sent)

    assert login.status_code == 202
    assert login.json() == {"state": "waiting_scan", "qr_png_base64": QR, "detail": None}
    assert stored.json() == {"ok": True}
    assert (account["has_credentials"], account["running"]) == (True, True)
    assert bridge.started == []  # attached: no second Zalo login
    (sent,) = bridge.sent
    assert (sent["thread_id"], sent["thread_type"], sent["text"]) == ("u1", 0, "Giá khám: 200k")
    assert sent["styles"] == [{"start": 0, "len": 3, "st": "b"}]
    await setup.close()


async def test_a_stored_login_starts_the_account_and_refused_styles_are_sent_plain(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    setup.runtime.live.use_model(ScriptedModel([reply("**Đậm** rồi")]))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    bridge.refuse_styles = True
    await setup.hub.sync()

    await setup.event("nick", _message("chào"))
    await setup.until(lambda: bridge.sent)

    assert bridge.started == [("nick", CREDENTIAL)]
    assert bridge.sent[0]["text"] == "Đậm rồi"
    assert "styles" not in bridge.sent[0]
    await setup.close()


async def test_in_a_group_only_a_mention_is_answered_and_the_speaker_is_named(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()

    await setup.event("nick", _message("không gọi bot", group="g1"))
    await setup.event("nick", _message("@bot giá?", group="g1", mentions=["me-1"]))
    await setup.until(lambda: bridge.sent)
    await asyncio.sleep(0.05)

    assert [(s["thread_id"], s["thread_type"], s["text"]) for s in bridge.sent] == [
        ("g1", 1, "(echo) An: @bot giá?")
    ]
    await setup.close()


async def test_a_logged_out_account_stops_and_waits_for_a_new_scan(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()
    running = setup.hub.running

    await setup.event("nick", {"type": "account_state", "state": "logged_out"})
    await setup.hub.sync()
    locked = (await setup.accounts())[0]
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()

    assert running == ["zalo-nick"]
    assert (locked["running"], locked["warning"]) == (
        False,
        "Zalo đã đăng xuất hoặc khóa tài khoản này - quét lại mã QR.",
    )
    assert bridge.stopped == ["nick"]
    assert setup.hub.running == ["zalo-nick"]
    await setup.close()


async def test_bridge_events_need_the_current_signature(tmp_path: Path, bridge: FakeBridge) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()

    wrong = await setup.event(
        "nick", {"type": "credential_updated", "credential": CREDENTIAL}, secret="c" * 64
    )
    unsigned = await setup.client.post(
        "/v1/hooks/zalo/webhooks/zalo-bridge/nick",
        json={"type": "credential_updated", "credential": CREDENTIAL},
    )
    bad = await setup.event("nick", {"type": "x"} | {"credential": None})
    unknown = await setup.event("nobody", {"type": "credential_updated", "credential": CREDENTIAL})

    assert (wrong.status_code, unsigned.status_code, bad.status_code, unknown.status_code) == (
        401,
        401,
        200,
        200,
    )
    assert [a["has_credentials"] for a in await setup.accounts()] == [False]
    await setup.close()


async def test_without_the_bridge_a_qr_login_asks_to_install_it_and_bots_cannot_scan(tmp_path: Path) -> None:
    setup = Setup(_runtime(tmp_path, None))
    await setup.personal()
    await setup.client.post(
        "/v1/plugins/zalo/accounts",
        json={"id": "bot-1", "label": "Bot", "channel": "zalo_bot"},
        headers=HEADERS,
    )

    login = await setup.client.post("/v1/plugins/zalo/accounts/nick/login", headers=HEADERS)
    bot = await setup.client.post("/v1/plugins/zalo/accounts/bot-1/login", headers=HEADERS)
    status = (await setup.client.get("/v1/plugins/zalo/bridge", headers=HEADERS)).json()

    assert login.status_code == 409
    assert "Cài cầu nối" in login.json()["detail"]
    assert bot.status_code == 422
    assert (status["installed"], status["running"]) == (False, False)
    await setup.close()

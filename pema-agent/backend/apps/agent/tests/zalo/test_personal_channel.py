"""Personal Zalo accounts end to end against a fake bridge: QR login, the login stored sealed from a signed
event, the channel attached to the bridge's session (or logged in with the stored login), messages in and rich
text out (plain again when Zalo refuses the styles), a locked-out account waiting for a new scan, unsigned
events refused."""

from __future__ import annotations

import asyncio
import json
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_app.channel_hub import ChannelHub, DeliverySettings
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginHost, discover
from agent_app.plugins.records import InMemoryPluginRecords
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore.harness.model.scripted import ScriptedModel, reply
from plugins.zalo.models import AccountConfig, ChannelKind
from plugins.zalo.personal.client import ZaloBridgeError
from plugins.zalo.personal.friends import FriendRequests, auto_accept_round
from plugins.zalo.personal.receipts import quote_from, receipt_params
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
        self.receipts: list[tuple[str, str, int]] = []
        self.reactions: list[tuple[str, str, str]] = []
        self.refuse_styles = False
        self.refuse_quotes = False
        self.refuse_friends = False
        self.decided: list[tuple[str, str]] = []
        self.group_info: list[str] = []
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
            refused = (self.refuse_styles and "styles" in data) or (self.refuse_quotes and "quote" in data)
            if refused:
                error = {"kind": "zalo_rejected", "message": "invalid params", "code": 112}
                return httpx.Response(502, json={"ok": False, "error": error})
            self.sent.append(data)
            return _ok(msg_id="out-1")
        if action == "typing":
            self.typing.append(data["thread_id"])
            return _ok()
        if action in ("receipts/delivered", "receipts/seen"):
            for item in data["params"]:
                self.receipts.append((action.split("/")[1], item["msgId"], data["thread_type"]))
            return _ok()
        if action == "reaction":
            self.reactions.append((data["icon_key"], data["msg_id"], data["thread_id"]))
            return _ok()
        if action == "user-info":
            uid = request.url.params["uid"]
            return _ok(
                data={"changed_profiles": {uid: {"displayName": "Bình", "avatar": "https://a.example/b"}}}
            )
        if action == "group-info":
            thread_id = request.url.params["thread_id"]
            self.group_info.append(thread_id)
            return _ok(data={"gridInfoMap": {thread_id: {"name": "Nhóm khám"}}})
        if action == "friends":
            return _ok(
                friends=[{"userId": "f1", "displayName": "Bạn Một"}, {"userId": "f2", "zaloName": "Hai"}]
            )
        if action in ("friends/accept", "friends/reject"):
            if self.refuse_friends:
                error = {"kind": "zalo_rejected", "message": "no", "code": 1}
                return httpx.Response(502, json={"ok": False, "error": error})
            self.decided.append((action.split("/")[1], data["uid"]))
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
    # A checkout may have the bridge's packages installed (the agent image does): the tests point the plugin at a
    # folder without them, so none of them depends on it.
    config: dict[str, Any] = {"bridge_folder": str(tmp_path / "no-bridge")}
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
    text: str,
    *,
    sender: str = "u1",
    name: str = "An",
    group: str | None = None,
    mentions: list[str] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "msgId": f"m-{text}",
        "cliMsgId": "c1",
        "uidFrom": sender,
        "idTo": group or "me-1",
        "dName": name,
        "msgType": "webchat",
        "ts": "1760000000000",
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


async def test_every_message_is_marked_delivered_and_the_answered_one_seen_reacted_and_quoted(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal(auto_react_icon="like")
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()

    await setup.event("nick", _message("không gọi bot", group="g1"))
    await setup.event("nick", _message("@bot giá?", group="g1", mentions=["me-1"]))
    await setup.until(lambda: bridge.sent and len(bridge.receipts) == 3 and bridge.reactions)

    assert sorted(bridge.receipts) == [
        ("delivered", "m-@bot giá?", 1),
        ("delivered", "m-không gọi bot", 1),
        ("seen", "m-@bot giá?", 1),
    ]
    assert bridge.reactions == [("like", "m-@bot giá?", "g1")]
    (sent,) = bridge.sent
    assert sent["quote"] == {
        "content": "@bot giá?",
        "msgType": "webchat",
        "uidFrom": "u1",
        "msgId": "m-@bot giá?",
        "cliMsgId": "c1",
        "ts": "1760000000000",
        "ttl": 0,
    }
    await setup.close()


async def test_a_one_to_one_reply_has_no_quote_and_a_refused_quote_is_sent_plain(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal(auto_react_enabled=False)
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()
    bridge.refuse_quotes = True

    await setup.event("nick", _message("riêng"))
    await setup.event("nick", _message("@bot nhóm", group="g1", mentions=["me-1"]))
    await setup.until(lambda: len(bridge.sent) == 2)
    await asyncio.sleep(0.05)

    assert [("quote" in s, s["thread_id"]) for s in bridge.sent] == [(False, "u1"), (False, "g1")]
    assert bridge.reactions == []
    await setup.close()


def test_receipt_and_quote_need_their_ids_and_a_quotable_kind() -> None:
    raw = _message("hi", group="g1")["message"]["data"]

    assert receipt_params(raw) == {
        "msgId": "m-hi",
        "cliMsgId": "c1",
        "uidFrom": "u1",
        "idTo": "g1",
        "msgType": "webchat",
        "st": 0,
        "at": 0,
        "cmd": 0,
        "ts": "1760000000000",
    }
    assert receipt_params({**raw, "idTo": ""}) is None
    assert quote_from(raw, is_group=False) is None
    assert quote_from({**raw, "msgType": "group.poll"}, is_group=True) is None
    assert quote_from({**raw, "content": {"href": "x"}}, is_group=True) is None
    assert quote_from({**raw, "ts": 1760000000000.0}, is_group=True) == quote_from(raw, is_group=True)


def _friend_event(kind: str, *, thread_id: str = "", is_self: bool = False, **data: Any) -> dict[str, Any]:
    return {
        "type": "friend_event",
        "event": {"kind": kind, "thread_id": thread_id, "is_self": is_self, "data": data},
    }


async def test_a_friend_request_waits_with_the_sender_name_until_zalo_takes_a_decision(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()
    base = "/v1/plugins/zalo/friends/nick"

    async def waiting() -> list[str]:
        return [r["from_uid"] for r in (await setup.client.get(f"{base}/requests", headers=HEADERS)).json()]

    await setup.event("nick", _friend_event("request", fromUid="u7", toUid="me-1", message="chào"))
    await setup.event("nick", _friend_event("request", is_self=True, fromUid="me-1", toUid="u9"))
    (request,) = (await setup.client.get(f"{base}/requests", headers=HEADERS)).json()
    bridge.refuse_friends = True
    refused = await setup.client.post(f"{base}/accept", json={"uid": "u7"}, headers=HEADERS)
    after_refusal = await waiting()
    bridge.refuse_friends = False
    accepted = await setup.client.post(f"{base}/accept", json={"uid": "u7"}, headers=HEADERS)
    await setup.event("nick", _friend_event("request", fromUid="u8", toUid="me-1", message=""))
    await setup.event("nick", _friend_event("reject_request", fromUid="u8", toUid="me-1"))
    await setup.event("nick", _friend_event("request", fromUid="u9", toUid="me-1", message=""))
    await setup.event("nick", _friend_event("add", thread_id="u9"))
    friends = (await setup.client.get(f"{base}/list", headers=HEADERS)).json()
    bad_uid = await setup.client.post(f"{base}/reject", json={"uid": "u 1"}, headers=HEADERS)
    not_running = await setup.client.get("/v1/plugins/zalo/friends/other/list", headers=HEADERS)

    assert (request["from_uid"], request["message"], request["sender_name"], request["avatar_url"]) == (
        "u7",
        "chào",
        "Bình",
        "https://a.example/b",
    )
    assert (refused.status_code, after_refusal) == (503, ["u7"])
    assert accepted.status_code == 204
    assert bridge.decided == [("accept", "u7")]
    assert await waiting() == []
    assert friends == [
        {"user_id": "f1", "display_name": "Bạn Một", "avatar_url": None},
        {"user_id": "f2", "display_name": "Hai", "avatar_url": None},
    ]
    assert (bad_uid.status_code, not_running.status_code) == (422, 409)
    await setup.close()


async def test_the_address_book_keeps_every_sender_and_groups_get_their_name_once(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()

    await setup.event("nick", _message("một"))
    await setup.event("nick", _message("hai"))
    await setup.event("nick", _message("nhóm 1", sender="u2", name="Bình", group="g1"))
    await setup.event("nick", _message("nhóm 2", sender="u2", name="Bình", group="g1"))
    await setup.until(lambda: bridge.group_info)
    await asyncio.sleep(0.05)
    contacts = (await setup.client.get("/v1/plugins/zalo/contacts", headers=HEADERS)).json()
    found = (await setup.client.get("/v1/plugins/zalo/contacts?q=BÌ", headers=HEADERS)).json()
    deleted = await setup.client.delete("/v1/plugins/zalo/contacts/nick/u1", headers=HEADERS)
    left = (await setup.client.get("/v1/plugins/zalo/contacts?account_id=nick", headers=HEADERS)).json()
    groups = (await setup.client.get("/v1/plugins/zalo/groups", headers=HEADERS)).json()
    bad = await setup.client.get("/v1/plugins/zalo/contacts?account_id=Nick:1", headers=HEADERS)

    assert sorted((c["user_id"], c["display_name"], c["message_count"]) for c in contacts) == [
        ("u1", "An", 2),
        ("u2", "Bình", 2),
    ]
    assert [c["user_id"] for c in found] == ["u2"]
    assert deleted.status_code == 204
    assert [c["user_id"] for c in left] == ["u2"]
    assert groups == [{"account_id": "nick", "thread_id": "g1", "name": "Nhóm khám"}]
    assert bridge.group_info == ["g1"]
    assert bad.status_code == 422
    await setup.close()


class FakeFriends:
    def __init__(self) -> None:
        self.accepted: list[str] = []

    async def accept_friend_request(self, uid: str) -> None:
        if uid == "bad":
            raise ZaloBridgeError("zalo_rejected", "no", code=1)
        self.accepted.append(uid)


async def test_auto_accept_takes_the_requests_that_waited_and_keeps_a_failed_one() -> None:
    requests = FriendRequests(InMemoryPluginRecords().storage("zalo"))
    now = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
    await requests.put("nick", "old", "", now - timedelta(minutes=10))
    await requests.put("nick", "bad", "", now - timedelta(minutes=5))
    await requests.put("nick", "new", "", now - timedelta(seconds=30))
    await requests.put("off", "old", "", now - timedelta(minutes=10))
    wants = AccountConfig(id="nick", label="N", channel=ChannelKind.ZALO_PERSONAL, auto_accept_friends=True)
    off = AccountConfig(id="off", label="O", channel=ChannelKind.ZALO_PERSONAL)
    api = FakeFriends()

    await auto_accept_round(requests, [(wants, api), (off, api)], now)

    assert api.accepted == ["old"]
    assert [r.from_uid for r in await requests.list("nick")] == ["new", "bad"]
    assert [r.from_uid for r in await requests.list("off")] == ["old"]

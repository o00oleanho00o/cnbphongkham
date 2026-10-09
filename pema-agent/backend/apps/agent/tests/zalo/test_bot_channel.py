"""Zalo Bot accounts end to end against a fake Zalo: the token is checked before it is stored, an enabled bot
account with a token gets a channel, messages from allowed people reach the agent and the reply goes back as
plain text, strangers are not answered, the webhook checks its secret, the channel goes away with the account.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from agent_app.channel_hub import ChannelHub, DeliverySettings
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore import PromptEnv, ToolContext, ToolOutput, ToolSpec, TurnInfo, TurnSection
from agentcore.harness.hooks import Deny, HookContext, PreToolHook
from agentcore.harness.model.scripted import ScriptedModel, reply
from agentcore.messages import ToolUseBlock
from plugins.zalo.access import should_respond
from plugins.zalo.bot.channel import ZaloBotChannel, send_error_is_retryable
from plugins.zalo.bot.client import LoiZaloBotApi, ZaloBotClient, tao_zalo_bot_client
from plugins.zalo.bot.parser import parse_update
from plugins.zalo.bot.types import ZaloBotUpdate
from plugins.zalo.models import AccountConfig, Allowlist, AllowlistMode, ChannelKind

TOKEN = "t" * 40
ADMIN = "a" * 40
KEY = "0f" * 32
BOT_TOKEN = "12345:good-secret-token"
HEADERS = {"Authorization": f"Bearer {ADMIN}"}
FAST = DeliverySettings(tick_s=0.01, backoff_s=(0.0,), max_attempts=3, start_retry_s=0.0, typing_every_s=0.01)


def _update(
    text: str | None = "xin chào", *, sender: str = "u1", chat: str | None = None, **extra: Any
) -> ZaloBotUpdate:
    message: dict[str, Any] = {
        "from": {"id": sender, "display_name": f"Người {sender}", "is_bot": False},
        "chat": {"id": chat or sender, "chat_type": "GROUP" if chat else "PRIVATE"},
        "message_id": f"m-{sender}-{text}",
        "date": 1_760_000_000_000,
        **extra,
    }
    if text is not None:
        message["text"] = text
    return ZaloBotUpdate.model_validate({"event_name": "message.text.received", "message": message})


class FakeZalo:
    """The Bot API over HTTP (an httpx transport), so the plugin's real client talks to it. ``updates`` feeds
    ``getUpdates``: an update, or an error answer ``(http status, body)``."""

    def __init__(self) -> None:
        self.updates: asyncio.Queue[ZaloBotUpdate | tuple[int, str]] = asyncio.Queue()
        self.sent: list[tuple[str, str, str | None]] = []
        self.actions: list[str] = []
        self.webhooks: list[tuple[str, str]] = []
        self.calls: list[str] = []
        self.transport = httpx.MockTransport(self._handle)

    def client(self, token: str) -> ZaloBotClient:
        return tao_zalo_bot_client(token, transport=self.transport)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        _, bot, method = request.url.path.split("/")
        body: dict[str, Any] = json.loads(request.content or b"{}")
        self.calls.append(method)
        if bot != f"bot{BOT_TOKEN}":
            return _answer({"ok": False, "description": "Unauthorized", "error_code": 401})
        if method == "getMe":
            return _answer({"ok": True, "result": {"id": "12345", "display_name": "Pema Bot"}})
        if method == "getUpdates":
            try:
                item = await asyncio.wait_for(self.updates.get(), 0.05)
            except TimeoutError:
                return _answer({"ok": False, "description": "Request timeout", "error_code": 408})
            if isinstance(item, tuple):
                return httpx.Response(item[0], text=item[1])
            return _answer({"ok": True, "result": item.model_dump(by_alias=True, mode="json")})
        if method == "sendMessage":
            self.sent.append((body["chat_id"], body["text"], body.get("parse_mode")))
            return _answer({"ok": True, "result": {"message_id": "out-1", "date": 0}})
        if method == "sendChatAction":
            self.actions.append(body["chat_id"])
        if method == "setWebhook":
            self.webhooks.append((body["url"], body["secret_token"]))
        return _answer({"ok": True, "result": True})


def _answer(envelope: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=envelope)


def _runtime(tmp_path: Path, zalo: FakeZalo, **config: Any) -> Runtime:
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
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("zalo", {"poll_timeout_s": 5, **config, "bot_transport": zalo.transport})
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

    async def bot_account(
        self, account_id: str = "bot-1", allow: tuple[str, ...] = ("u1",)
    ) -> httpx.Response:
        await self.client.post(
            "/v1/plugins/zalo/accounts",
            json={"id": account_id, "label": "Bot", "channel": "zalo_bot"},
            headers=HEADERS,
        )
        await self.client.patch(
            f"/v1/plugins/zalo/accounts/{account_id}",
            json={"allowlist": {"mode": "list", "user_ids": list(allow)}},
            headers=HEADERS,
        )
        return await self.client.put(
            f"/v1/plugins/zalo/accounts/{account_id}/bot-token", json={"token": BOT_TOKEN}, headers=HEADERS
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


@pytest.fixture
async def zalo() -> FakeZalo:
    return FakeZalo()


async def test_a_bot_answers_an_allowed_person_in_plain_text_and_ignores_strangers(
    tmp_path: Path, zalo: FakeZalo
) -> None:
    setup = Setup(_runtime(tmp_path, zalo))
    setup.runtime.live.use_model(ScriptedModel([reply("**Giá** khám: `200k`")]))
    token = await setup.bot_account()
    await setup.hub.sync()
    running = (await setup.accounts())[0]

    await zalo.updates.put(_update("người lạ", sender="u2"))
    await zalo.updates.put(_update("giá khám bao nhiêu?"))
    await setup.until(lambda: zalo.sent)
    await asyncio.sleep(0.05)

    assert token.status_code == 200
    assert BOT_TOKEN not in token.text
    assert (running["running"], running["has_credentials"]) == (True, True)
    assert zalo.calls[:3] == ["getMe", "getMe", "deleteWebhook"]  # checked at PUT, then on start
    assert zalo.sent == [("u1", "Giá khám: 200k", None)]
    assert "zalo-bot-1" in setup.hub.running
    await setup.close()


async def test_a_refused_token_is_not_stored_and_only_bot_accounts_take_one(
    tmp_path: Path, zalo: FakeZalo
) -> None:
    setup = Setup(_runtime(tmp_path, zalo))
    await setup.client.post(
        "/v1/plugins/zalo/accounts",
        json={"id": "bot-1", "label": "Bot", "channel": "zalo_bot"},
        headers=HEADERS,
    )
    await setup.client.post(
        "/v1/plugins/zalo/accounts", json={"id": "nick", "label": "Nick"}, headers=HEADERS
    )
    refused = await setup.client.put(
        "/v1/plugins/zalo/accounts/bot-1/bot-token", json={"token": "12345:wrong-secret"}, headers=HEADERS
    )
    personal = await setup.client.put(
        "/v1/plugins/zalo/accounts/nick/bot-token", json={"token": BOT_TOKEN}, headers=HEADERS
    )
    malformed = await setup.client.put(
        "/v1/plugins/zalo/accounts/bot-1/bot-token", json={"token": "not a token"}, headers=HEADERS
    )
    unknown = await setup.client.put(
        "/v1/plugins/zalo/accounts/nobody/bot-token", json={"token": BOT_TOKEN}, headers=HEADERS
    )

    assert (refused.status_code, personal.status_code, malformed.status_code, unknown.status_code) == (
        422,
        422,
        422,
        404,
    )
    assert "wrong-secret" not in refused.text
    assert [a["has_credentials"] for a in await setup.accounts()] == [False, False]
    assert setup.runtime.plugins.contributions().channels == ()
    await setup.close()


async def test_disabling_or_deleting_the_account_stops_its_channel(tmp_path: Path, zalo: FakeZalo) -> None:
    setup = Setup(_runtime(tmp_path, zalo))
    await setup.bot_account()
    await setup.hub.sync()
    started = setup.hub.running

    await setup.client.patch("/v1/plugins/zalo/accounts/bot-1", json={"enabled": False}, headers=HEADERS)
    await setup.hub.sync()
    disabled = setup.hub.running
    await setup.client.patch("/v1/plugins/zalo/accounts/bot-1", json={"enabled": True}, headers=HEADERS)
    await setup.hub.sync()
    again = setup.hub.running
    await setup.client.delete("/v1/plugins/zalo/accounts/bot-1", headers=HEADERS)
    await setup.hub.sync()

    assert (started, disabled, again) == (["zalo-bot-1"], [], ["zalo-bot-1"])
    assert setup.hub.running == []
    await setup.close()


async def test_a_settings_change_reaches_the_running_channel_without_a_restart(
    tmp_path: Path, zalo: FakeZalo
) -> None:
    setup = Setup(_runtime(tmp_path, zalo))
    await setup.bot_account(allow=())
    await setup.hub.sync()
    await setup.client.patch(
        "/v1/plugins/zalo/accounts/bot-1",
        json={"allowlist": {"mode": "all", "user_ids": []}},
        headers=HEADERS,
    )
    await setup.hub.sync()

    await zalo.updates.put(_update("chào"))
    await setup.until(lambda: zalo.sent)

    assert zalo.calls.count("getMe") == 2
    assert zalo.sent[0][1] == "(echo) chào"
    await setup.close()


async def test_the_webhook_takes_only_deliveries_with_the_secret(tmp_path: Path, zalo: FakeZalo) -> None:
    setup = Setup(_runtime(tmp_path, zalo, public_url="https://clinic.example/"))
    await setup.bot_account()
    await setup.hub.sync()
    ((url, secret),) = zalo.webhooks
    body = {"ok": True, "result": _update("qua webhook").model_dump(by_alias=True, mode="json")}

    no_secret = await setup.client.post("/v1/hooks/zalo/bot/bot-1", json=body)
    wrong = await setup.client.post(
        "/v1/hooks/zalo/bot/bot-1", json=body, headers={"X-Bot-Api-Secret-Token": "x"}
    )
    unknown = await setup.client.post(
        "/v1/hooks/zalo/bot/nobody", json=body, headers={"X-Bot-Api-Secret-Token": secret}
    )
    bad = await setup.client.post(
        "/v1/hooks/zalo/bot/bot-1", content=b"[1]", headers={"X-Bot-Api-Secret-Token": secret}
    )
    good = await setup.client.post(
        "/v1/hooks/zalo/bot/bot-1", json=body, headers={"X-Bot-Api-Secret-Token": secret}
    )
    await setup.until(lambda: zalo.sent)

    assert url == "https://clinic.example/v1/hooks/zalo/bot/bot-1"
    assert (no_secret.status_code, wrong.status_code, unknown.status_code, bad.status_code) == (
        401,
        401,
        401,
        400,
    )
    assert good.json() == {"ok": True}
    assert zalo.sent == [("u1", "(echo) qua webhook", None)]
    assert "deleteWebhook" not in zalo.calls
    await setup.close()
    assert "deleteWebhook" in zalo.calls


async def test_the_channel_rules_and_switched_off_tools_follow_the_account(
    tmp_path: Path, zalo: FakeZalo
) -> None:
    setup = Setup(_runtime(tmp_path, zalo))
    await setup.bot_account()
    await setup.client.patch(
        "/v1/plugins/zalo/accounts/bot-1", json={"disabled_tools": ["web_search"]}, headers=HEADERS
    )
    contributions = setup.runtime.plugins.contributions()
    (section,) = [s for s in contributions.sections if s.name == "zalo_channel"]
    (hook,) = [h for h in contributions.hooks if h.name == "zalo_disabled_tools"]
    assert isinstance(section, TurnSection)
    assert isinstance(hook, PreToolHook)
    env = PromptEnv(agent_name="t", persona="", timezone="Asia/Ho_Chi_Minh", tool_names=())
    now = datetime.now(UTC)
    use = ToolUseBlock(id="1", name="web_search", args={})
    spec = ToolSpec(name="web_search", description="search", args_model=NoArgs, handler=_nothing)

    on_bot = section.render(env, TurnInfo(now=now, channel="zalo-bot-1"))
    on_http = section.render(env, TurnInfo(now=now, channel="http"))
    denied = await hook.run(use, spec, HookContext("t", "s", "u1", 1, channel="zalo-bot-1"))
    elsewhere = await hook.run(use, spec, HookContext("t", "s", "u1", 1, channel="http"))

    assert on_bot is not None
    assert "TÀI KHOẢN BOT" in on_bot
    assert on_http is None
    assert isinstance(denied, Deny)
    assert not isinstance(elsewhere, Deny)
    await setup.close()


# --- pieces ---


class NoArgs(BaseModel):
    pass


async def _nothing(args: NoArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text="")


def _bot_account(**changes: Any) -> AccountConfig:
    return AccountConfig(id="bot-1", label="Bot", channel=ChannelKind.ZALO_BOT, **changes)


def test_updates_become_messages_and_odd_ones_get_a_label_or_are_dropped() -> None:
    text = parse_update("bot-1", _update("chào"))
    group = parse_update("bot-1", _update("cả nhà", sender="u3", chat="g1"))
    sticker = parse_update(
        "bot-1",
        ZaloBotUpdate.model_validate(
            {**_update(None).model_dump(by_alias=True), "event_name": "message.sticker.received"}
        ),
    )
    photo = parse_update("bot-1", _update(None, photo="https://img.example/a.jpg"))
    from_bot = parse_update(
        "bot-1",
        ZaloBotUpdate.model_validate(
            {"event_name": "x", "message": {"from": {"id": "b", "is_bot": True}, "chat": {"id": "b"}}}
        ),
    )
    no_chat = parse_update(
        "bot-1", ZaloBotUpdate.model_validate({"event_name": "x", "message": {"from": {"id": "u"}}})
    )
    no_id = parse_update(
        "bot-1",
        ZaloBotUpdate.model_validate(
            {"event_name": "x", "message": {"from": {"id": 7}, "chat": {"id": 7}, "text": "hi"}}
        ),
    )

    assert text is not None
    assert (text.thread_id, text.sender_id, text.text, text.is_group) == ("u1", "u1", "chào", False)
    assert group is not None
    assert (group.thread_id, group.is_group, group.sender_name) == ("g1", True, "Người u3")
    assert sticker is not None
    assert sticker.text == "[gửi một sticker]"
    assert photo is not None
    assert (photo.text, photo.image_urls) == ("", ("https://img.example/a.jpg",))
    assert (from_bot, no_chat) == (None, None)
    assert no_id is not None
    assert no_id.message_id.startswith("h:")
    assert no_id.sender_id == "7"


def test_who_is_answered() -> None:
    message = parse_update("bot-1", _update("hi", sender="u2"))
    in_group = parse_update("bot-1", _update("hi", sender="u2", chat="g1"))
    assert message is not None
    assert in_group is not None
    closed = _bot_account(allowlist=Allowlist(mode=AllowlistMode.LIST, user_ids=["u1"]))
    open_ = _bot_account()

    assert should_respond(closed, message).respond is False
    assert should_respond(open_, message).respond is True
    assert should_respond(_bot_account(respond_to_groups=False), in_group).respond is False


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (LoiZaloBotApi("x", "sendMessage"), True),
        (LoiZaloBotApi("x", "sendMessage", 429), True),
        (LoiZaloBotApi("x", "sendMessage", 502), True),
        (LoiZaloBotApi("x", "sendMessage", 200, 429), True),
        (LoiZaloBotApi("x", "sendMessage", 200, 400), False),
    ],
)
def test_which_send_errors_are_tried_again(error: LoiZaloBotApi, retryable: bool) -> None:
    assert send_error_is_retryable(error) is retryable


async def test_typing_is_shown_only_when_the_account_wants_it() -> None:
    zalo = FakeZalo()
    channel = ZaloBotChannel(_bot_account(), BOT_TOKEN, client_factory=zalo.client)

    async def receive(message: Any) -> None:
        pass

    await channel.start(receive)
    await channel.typing("u1", {"thread_type": "user"})
    channel.account = _bot_account(typing_indicator_enabled=False)
    await channel.typing("u2", {"thread_type": "user"})
    await channel.stop()

    assert zalo.actions == ["u1"]


async def test_polling_retreats_after_errors_and_keeps_going() -> None:
    zalo = FakeZalo()
    pauses: list[float] = []
    heard: list[str] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    async def receive(message: Any) -> None:
        heard.append(message.text)

    channel = ZaloBotChannel(
        _bot_account(), BOT_TOKEN, client_factory=zalo.client, backoff_s=(2.0, 5.0), sleep=sleep
    )
    for _ in range(3):
        await zalo.updates.put((429, "<html>429 Too Many Requests</html>"))
    await zalo.updates.put(_update("sau lỗi"))
    await zalo.updates.put((502, "<html>Bad Gateway</html>"))
    await channel.start(receive)
    for _ in range(100):
        if len(pauses) == 4:
            break
        await asyncio.sleep(0.01)
    await channel.stop()

    assert pauses == [2.0, 4.0, 5.0, 2.0]
    assert heard == ["sau lỗi"]
    assert channel.listening is False


async def test_a_refused_start_raises_masked_and_a_leaking_reply_is_not_sent() -> None:
    zalo = FakeZalo()
    channel = ZaloBotChannel(_bot_account(), "12345:wrong-secret", client_factory=zalo.client)

    async def receive(message: Any) -> None:
        pass

    with pytest.raises(LoiZaloBotApi) as refused:
        await channel.start(receive)

    assert "wrong-secret" not in str(refused.value)
    assert channel.listening is False
    assert channel.prepare("**đậm** và `mã`") == "đậm và mã"
    assert channel.prepare("Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ...") is None

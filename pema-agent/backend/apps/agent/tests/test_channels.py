"""Chat channels run by plugins: replies split to the channel's size, sent in order, retried and resumed after
a failure, given up when refused for good; channels started and stopped with their plugin."""

from __future__ import annotations

import asyncio
import textwrap
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from agent_app.channel_hub import ChannelHub, DeliverySettings
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.gateway import GatewaySettings, create_app
from agent_app.ingress import DeliveryStatus, IngressRecord
from agent_app.plugins import PluginError
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import AssistantResult, LlmRequest, ModelError, StreamSink
from agentcore.channels import (
    ChannelCapabilities,
    ChannelSendError,
    InboundMessage,
    OutboundMessage,
    Receive,
    split_reply,
)

TOKEN = "t" * 40
ADMIN = "a" * 40
FAST = DeliverySettings(tick_s=0.01, backoff_s=(0.0,), max_attempts=3, start_retry_s=0.0)

Failure = Callable[[int], BaseException | None]

CHANNEL_PLUGIN = """
from agentcore.channels import ChannelCapabilities


class Echoes:
    def __init__(self, name, log):
        self.name = name
        self.capabilities = ChannelCapabilities(max_text_chars=100)
        self.log = log

    async def start(self, receive):
        self.log.append(f"start {self.name}")

    async def stop(self):
        self.log.append(f"stop {self.name}")

    async def send(self, message):
        self.log.append(f"send {message.text}")


def register(ctx):
    ctx.register_channel(Echoes(ctx.config.get("channel", "chat"), ctx.config["log"]))
"""


class FakeChannel:
    def __init__(
        self, name: str = "fake", *, max_chars: int | None = None, fail: Failure | None = None
    ) -> None:
        self.name = name
        self.capabilities = ChannelCapabilities(max_text_chars=max_chars)
        self.fail = fail
        self.sent: list[OutboundMessage] = []
        self.tries = 0
        self.starts = 0
        self.stopped = 0
        self.receive: Receive | None = None

    async def start(self, receive: Receive) -> None:
        self.starts += 1
        self.receive = receive

    async def stop(self) -> None:
        self.stopped += 1

    async def send(self, message: OutboundMessage) -> None:
        self.tries += 1
        error = self.fail(self.tries) if self.fail is not None else None
        if error is not None:
            raise error
        self.sent.append(message)

    async def hear(self, message_id: str, text: str, conversation: str = "c1") -> None:
        assert self.receive is not None
        await self.receive(
            InboundMessage("spoofed", conversation, "u1", message_id, text, {"thread": "group"})
        )


class StubbornChannel(FakeChannel):
    async def start(self, receive: Receive) -> None:
        self.starts += 1
        if self.starts == 1:
            raise ConnectionError("token rejected")
        self.receive = receive


class BrokenModel:
    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        raise ModelError("auth", "bad key")


def _runtime(tmp_path: Path) -> Runtime:
    folder = tmp_path / "agent"
    (folder / "plugins").mkdir(parents=True)
    (folder / "agent.toml").write_text('[agent]\nname = "t"\nsystem_prompt = "p"\n', encoding="utf-8")
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


def _hub(runtime: Runtime, *channels: FakeChannel) -> tuple[Dispatcher, ChannelHub]:
    dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01))
    return dispatcher, ChannelHub(dispatcher, channels=lambda: list(channels), settings=FAST)


async def _until(
    hub: ChannelHub, dispatcher: Dispatcher, ingress_id: int, status: DeliveryStatus, timeout_s: float = 5.0
) -> IngressRecord:
    """Ticks the hub until the message's delivery reaches ``status``."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        record = await dispatcher.ingress.get(dispatcher.tenant_id, ingress_id)
        if record is not None and record.delivery == status:
            return record
        if loop.time() > deadline:
            raise AssertionError(
                f"message {ingress_id} is {record.delivery if record else None}, not {status}"
            )
        await hub.tick()
        await asyncio.sleep(0.01)


def test_split_reply_cuts_at_paragraphs_lines_and_spaces() -> None:
    assert split_reply("  hi  ", None) == ["hi"]
    assert split_reply("", 10) == []
    assert split_reply("one two three four", 9) == ["one two", "three", "four"]
    assert split_reply("para one\n\npara two", 12) == ["para one", "para two"]
    assert split_reply("x" * 25, 10) == ["x" * 10, "x" * 10, "x" * 5]
    assert all(len(part) <= 50 for part in split_reply(("word " * 200).strip(), 50))


async def test_a_message_heard_on_a_channel_is_answered_through_it_once(tmp_path: Path) -> None:
    channel = FakeChannel()
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    await hub.sync()

    await channel.hear("m1", "hello")
    await channel.hear("m1", "hello")
    record = await _until(hub, dispatcher, 1, "sent")
    await hub.tick()

    (sent,) = channel.sent
    assert (sent.text, sent.conversation_id, sent.reply_to, sent.user_id) == (
        "(echo) hello",
        "c1",
        "m1",
        "u1",
    )
    assert dict(sent.metadata) == {"thread": "group"}
    assert (record.channel, record.delivered_parts, record.delivery_attempts) == ("fake", 1, 1)
    await dispatcher.close()


async def test_a_long_reply_is_split_and_a_retry_resumes_after_the_parts_already_sent(tmp_path: Path) -> None:
    channel = FakeChannel(max_chars=12, fail=lambda n: ChannelSendError("busy") if n == 2 else None)
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    await hub.sync()

    await channel.hear("m1", "alpha beta gamma delta")
    record = await _until(hub, dispatcher, 1, "sent")

    assert [m.text for m in channel.sent] == ["(echo) alpha", "beta gamma", "delta"]
    assert [(m.part, m.parts) for m in channel.sent] == [(1, 3), (2, 3), (3, 3)]
    assert (record.delivery_attempts, record.delivered_parts) == (2, 3)
    await dispatcher.close()


async def test_a_refused_send_is_given_up_and_endless_failures_stop_at_the_limit(tmp_path: Path) -> None:
    refused = FakeChannel("refused", fail=lambda n: ChannelSendError("user blocked the bot", retryable=False))
    flaky = FakeChannel("flaky", fail=lambda n: ChannelSendError("down"))
    dispatcher, hub = _hub(_runtime(tmp_path), refused, flaky)
    await hub.sync()

    await refused.hear("m1", "hi")
    await flaky.hear("m2", "hi")
    first = await _until(hub, dispatcher, 1, "failed")
    second = await _until(hub, dispatcher, 2, "failed")

    assert (refused.tries, first.delivery_error) == (1, "ChannelSendError: user blocked the bot")
    assert (flaky.tries, second.delivery_attempts) == (FAST.max_attempts, FAST.max_attempts)
    await dispatcher.close()


async def test_replies_leave_in_the_order_the_messages_came(tmp_path: Path) -> None:
    channel = FakeChannel(fail=lambda n: ChannelSendError("slow down", retry_after_s=0.2) if n == 1 else None)
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    await hub.sync()

    await channel.hear("m1", "first")
    await channel.hear("m2", "second")
    await _until(hub, dispatcher, 2, "sent")

    assert [m.text for m in channel.sent] == ["(echo) first", "(echo) second"]
    await dispatcher.close()


async def test_a_failed_turn_sends_nothing_and_is_marked_skipped(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(BrokenModel())
    channel = FakeChannel()
    dispatcher, hub = _hub(runtime, channel)
    await hub.sync()

    await channel.hear("m1", "hi")
    record = await _until(hub, dispatcher, 1, "skipped")

    assert (record.status, record.delivery_error) == ("failed", "no reply: auth")
    assert channel.sent == []
    await dispatcher.close()


async def test_a_failed_turn_sends_the_agents_failure_reply_when_it_has_one(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(BrokenModel())
    channel = FakeChannel()
    dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01))
    hub = ChannelHub(
        dispatcher, channels=lambda: [channel], settings=FAST, failure_reply=" Try again later. "
    )
    await hub.sync()

    await channel.hear("m1", "hi")
    record = await _until(hub, dispatcher, 1, "sent")

    assert [m.text for m in channel.sent] == ["Try again later."]
    assert (record.status, record.error_kind) == ("failed", "auth")
    await dispatcher.close()


async def test_a_channel_that_cannot_start_is_reported_and_tried_again(tmp_path: Path) -> None:
    stubborn, fine = StubbornChannel("stubborn"), FakeChannel("fine")
    dispatcher, hub = _hub(_runtime(tmp_path), stubborn, fine)

    await hub.sync()
    first = {s["name"]: s for s in hub.status()}
    await hub.sync()

    assert (first["stubborn"]["running"], first["stubborn"]["error"]) == (
        False,
        "ConnectionError: token rejected",
    )
    assert first["fine"]["running"] is True
    assert hub.running == ["fine", "stubborn"]
    await hub.close()
    assert (stubborn.stopped, fine.stopped, hub.running) == (1, 1, [])
    await dispatcher.close()


async def test_a_plugin_channel_starts_and_stops_with_its_plugin(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    plugin = tmp_path / "agent" / "plugins" / "chatter"
    plugin.mkdir()
    (plugin / "plugin.toml").write_text('name = "chatter"\n', encoding="utf-8")
    (plugin / "__init__.py").write_text(textwrap.dedent(CHANNEL_PLUGIN), encoding="utf-8")
    log: list[str] = []
    dispatcher = runtime.dispatcher()
    hub = runtime.channel_hub(dispatcher, FAST)
    await runtime.plugin_manager.start()  # finds the plugin written after the start

    runtime.live.enable("chatter", {"log": log})
    await hub.sync()
    running = hub.running
    channels = [s.channels for s in runtime.plugins.status() if s.name == "chatter"]
    runtime.live.disable("chatter")
    await hub.sync()
    with pytest.raises(PluginError, match="invalid channel name 'http'"):
        runtime.live.enable("chatter", {"log": log, "channel": "http"})

    assert (running, channels) == (["chat"], [("chat",)])
    assert (log, hub.running) == (["start chat", "stop chat"], [])
    await dispatcher.close()


async def test_the_gateway_reports_delivery_and_channels(tmp_path: Path) -> None:
    channel = FakeChannel()
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    app = create_app(dispatcher, GatewaySettings(token=TOKEN, admin_token=ADMIN), channels=hub)
    await hub.sync()
    await channel.hear("m1", "hello")
    await _until(hub, dispatcher, 1, "sent")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as client:
        message = await client.get("/v1/ingress/1", headers={"Authorization": f"Bearer {TOKEN}"})
        listed = await client.get("/v1/admin/channels", headers={"Authorization": f"Bearer {ADMIN}"})

    assert message.json()["delivery"] == {"status": "sent", "attempts": 1, "parts_sent": 1, "error": None}
    assert listed.json() == {
        "channels": [
            {"name": "fake", "running": True, "error": None, "max_text_chars": None, "markdown": False}
        ]
    }
    await dispatcher.close()

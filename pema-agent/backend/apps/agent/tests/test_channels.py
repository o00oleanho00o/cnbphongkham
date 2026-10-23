"""Chat channels run by plugins: replies split to the channel's size, sent in order, retried and resumed after
a failure, given up when refused for good; channels started and stopped with their plugin."""

from __future__ import annotations

import asyncio
import textwrap
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from agent_app.channel_hub import PACED_DELIVERY, ChannelHub, DeliverySettings
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
    Observe,
    ObservedMessage,
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


class TypingChannel(FakeChannel):
    """Hears that a person is typing: keeps the function the hub gives it."""

    def __init__(self, name: str = "fake") -> None:
        super().__init__(name)
        self.notify: Callable[[str], None] | None = None

    def on_typing(self, notify: Callable[[str], None]) -> None:
        self.notify = notify


class StubbornChannel(FakeChannel):
    async def start(self, receive: Receive) -> None:
        self.starts += 1
        if self.starts == 1:
            raise ConnectionError("token rejected")
        self.receive = receive


class CleaningChannel(FakeChannel):
    """Shows plain text only and refuses replies that mention a secret."""

    def prepare(self, text: str) -> str | None:
        return None if "secret" in text else text.replace("*", "")


async def test_a_channel_prepares_the_whole_reply_before_it_is_split_or_refuses_it(tmp_path: Path) -> None:
    channel = CleaningChannel(max_chars=12)
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    await hub.sync()

    await channel.hear("m1", "**alpha** beta")
    await channel.hear("m2", "the secret", conversation="c2")
    first = await _until(hub, dispatcher, 1, "sent")
    second = await _until(hub, dispatcher, 2, "skipped")

    assert [m.text for m in channel.sent] == ["(echo) alpha", "beta"]
    assert first.delivered_parts == 2
    assert second.delivery_error == "the channel refused the reply"
    await dispatcher.close()


class BrokenModel:
    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        raise ModelError("auth", "bad key")


def _runtime(tmp_path: Path) -> Runtime:
    folder = tmp_path / "agent"
    (folder / "plugins").mkdir(parents=True)
    (folder / "agent.toml").write_text('[agent]\nname = "t"\nsystem_prompt = "p"\n', encoding="utf-8")
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


def _hub(
    runtime: Runtime, *channels: FakeChannel, observe: Observe | None = None
) -> tuple[Dispatcher, ChannelHub]:
    dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01))
    return dispatcher, ChannelHub(dispatcher, channels=lambda: list(channels), settings=FAST, observe=observe)


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


async def test_a_reply_waits_a_random_pause_before_each_part_it_sends(tmp_path: Path) -> None:
    channel = FakeChannel(max_chars=5)
    dispatcher = _runtime(tmp_path).dispatcher(DispatchSettings(poll_s=0.01))
    waits: list[float] = []
    bounds: list[tuple[float, float]] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    def rand(low: float, high: float) -> float:
        bounds.append((low, high))
        return 12.5

    hub = ChannelHub(
        dispatcher,
        channels=lambda: [channel],
        settings=replace(FAST, reply_delay_min_s=10.0, reply_delay_max_s=20.0),
        sleep=sleep,
        rand=rand,
    )
    await hub.sync()

    await channel.hear("m1", "alpha beta")
    record = await _until(hub, dispatcher, 1, "sent")

    assert record.delivered_parts == len(channel.sent) >= 2
    assert waits == [12.5] * len(channel.sent)
    assert set(bounds) == {(10.0, 20.0)}
    await dispatcher.close()


async def test_a_reply_goes_out_at_once_when_no_delay_is_set(tmp_path: Path) -> None:
    channel = FakeChannel()
    dispatcher = _runtime(tmp_path).dispatcher(DispatchSettings(poll_s=0.01))

    async def never(seconds: float) -> None:
        raise AssertionError(f"waited {seconds} s")

    hub = ChannelHub(dispatcher, channels=lambda: [channel], settings=FAST, sleep=never)
    await hub.sync()

    await channel.hear("m1", "hi")
    await _until(hub, dispatcher, 1, "sent")
    await dispatcher.close()


def test_the_service_paces_replies_between_10_and_20_seconds() -> None:
    assert (PACED_DELIVERY.reply_delay_min_s, PACED_DELIVERY.reply_delay_max_s) == (10.0, 20.0)
    assert PACED_DELIVERY.reply_delay_max_s < PACED_DELIVERY.stale_s
    with pytest.raises(ValueError, match="invalid reply delay"):
        DeliverySettings(reply_delay_min_s=5.0, reply_delay_max_s=1.0)
    with pytest.raises(ValueError, match="invalid reply delay"):
        DeliverySettings(reply_delay_min_s=-1.0)


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
        message = await client.get("/v1/ingress/1", headers={"Authorization": f"Bearer {ADMIN}"})
        listed = await client.get("/v1/admin/channels", headers={"Authorization": f"Bearer {ADMIN}"})

    assert message.json()["delivery"] == {"status": "sent", "attempts": 1, "parts_sent": 1, "error": None}
    assert listed.json() == {
        "channels": [
            {"name": "fake", "running": True, "error": None, "max_text_chars": None, "markdown": False}
        ]
    }
    await dispatcher.close()


OBSERVER_PLUGIN = """
def register(ctx):
    log = ctx.config["log"]

    async def broken(message):
        raise RuntimeError("a listener that fails")

    async def heard(message):
        log.append((message.channel, message.origin, message.text))

    ctx.on_message(broken)
    ctx.on_message(heard)
"""


async def test_the_hub_tells_the_listeners_what_the_agent_said_once_it_is_sent(tmp_path: Path) -> None:
    told: list[ObservedMessage] = []

    async def listen(message: ObservedMessage) -> None:
        told.append(message)

    channel = FakeChannel()
    dispatcher, hub = _hub(_runtime(tmp_path), channel, observe=listen)
    await hub.sync()

    await channel.hear("m1", "hello")
    await _until(hub, dispatcher, 1, "sent")

    (reply,) = told
    assert (reply.channel, reply.conversation_id, reply.origin, reply.text) == (
        "fake",
        "c1",
        "agent",
        "(echo) hello",
    )
    assert reply.message_id == "m1#reply"
    assert reply.user_id == "u1"  # whom it answered: a plugin opens or wakes the person's case with it
    await dispatcher.close()


async def test_a_listener_that_fails_never_costs_the_reply_its_delivery(tmp_path: Path) -> None:
    async def broken(message: ObservedMessage) -> None:
        raise RuntimeError("down")

    channel = FakeChannel()
    dispatcher, hub = _hub(_runtime(tmp_path), channel, observe=broken)
    await hub.sync()

    await channel.hear("m1", "hello")
    record = await _until(hub, dispatcher, 1, "sent")

    assert record.delivery == "sent"
    await dispatcher.close()


async def test_the_host_tells_every_listening_plugin_of_a_message_and_skips_the_one_that_fails(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    plugin = tmp_path / "agent" / "plugins" / "listener"
    plugin.mkdir()
    (plugin / "plugin.toml").write_text('name = "listener"\n', encoding="utf-8")
    (plugin / "__init__.py").write_text(textwrap.dedent(OBSERVER_PLUGIN), encoding="utf-8")
    log: list[tuple[str, str, str]] = []
    await runtime.plugin_manager.start()
    runtime.live.enable("listener", {"log": log})

    await runtime.plugins.observe(ObservedMessage("zalo-a", "t1", "u1", "m1", "chào", "inbound"))
    runtime.live.disable("listener")
    await runtime.plugins.observe(ObservedMessage("zalo-a", "t1", "u1", "m2", "sau khi tắt", "inbound"))

    assert log == [("zalo-a", "inbound", "chào")]


async def test_a_channel_that_hears_typing_tells_the_dispatcher_under_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = TypingChannel("chat-a")
    dispatcher, hub = _hub(_runtime(tmp_path), channel)
    heard: list[tuple[str, str]] = []

    def note_typing(name: str, conversation: str) -> None:
        heard.append((name, conversation))

    monkeypatch.setattr(dispatcher, "note_typing", note_typing)

    await hub.sync()
    assert channel.notify is not None
    channel.notify("c9")

    assert heard == [("chat-a", "c9")]
    await dispatcher.close()

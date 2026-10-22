"""Messages the agent starts on its own (a case's turn, a reminder), through the real queue and channels: the
agent's ``SKIP`` and a failed turn send nothing, a message of its own is marked proactive, a send the channel
never took is cancelled, and the same message id runs once."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path

from agent_app.channel_hub import ChannelHub, DeliverySettings, is_skip
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.plugins import ProactiveSent
from agent_app.proactive import DispatcherOutbox
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import AssistantResult, LlmRequest, ModelError, StreamSink
from agentcore.channels import ChannelCapabilities, OutboundMessage, Receive
from agentcore.harness.model.scripted import ScriptedModel, reply

FAST = DeliverySettings(tick_s=0.01, backoff_s=(0.0,), max_attempts=3, start_retry_s=0.0)
INSTRUCTION = "[Hệ thống · chăm sóc lại] nhắn lại"


class FakeChannel:
    def __init__(self, name: str = "zalo-a1") -> None:
        self.name = name
        self.capabilities = ChannelCapabilities()
        self.sent: list[OutboundMessage] = []
        self.receive: Receive | None = None

    async def start(self, receive: Receive) -> None:
        self.receive = receive

    async def stop(self) -> None:
        return None

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)


class BrokenModel:
    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        raise ModelError("auth", "bad key")


def _runtime(tmp_path: Path) -> Runtime:
    folder = tmp_path / "agent"
    (folder / "plugins").mkdir(parents=True)
    (folder / "agent.toml").write_text('[agent]\nname = "t"\nsystem_prompt = "p"\n', encoding="utf-8")
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


@contextlib.asynccontextmanager
async def _running(
    runtime: Runtime, channel: FakeChannel | None, *, failure_reply: str = ""
) -> AsyncGenerator[tuple[Dispatcher, DispatcherOutbox]]:
    dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01))
    hub = ChannelHub(
        dispatcher,
        channels=lambda: [channel] if channel is not None else [],
        settings=FAST,
        failure_reply=failure_reply,
    )
    ticking = asyncio.create_task(hub.run())
    try:
        yield dispatcher, DispatcherOutbox(dispatcher, poll_s=0.01, delivery_timeout_s=0.3)
    finally:
        ticking.cancel()
        await asyncio.gather(ticking, return_exceptions=True)
        await hub.close()
        await dispatcher.close()


async def _send(outbox: DispatcherOutbox, message_id: str = "case:1:0") -> ProactiveSent:
    return await outbox.send_to(
        channel="zalo-a1", conversation_id="c1", user_id="u1", message_id=message_id, instruction=INSTRUCTION
    )


async def test_a_message_of_the_agents_own_goes_through_the_channel_marked_proactive(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (_, outbox):
        sent = await _send(outbox)

    assert sent == ProactiveSent(True)
    (message,) = channel.sent
    assert (message.conversation_id, message.text) == ("c1", "Chị còn quan tâm không ạ?")
    assert message.metadata["proactive"] == "1"


async def test_an_answer_of_skip_sends_nothing_and_does_not_count(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("SKIP")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (dispatcher, outbox):
        sent = await _send(outbox)
        record = await dispatcher.ingress.get(dispatcher.tenant_id, 1)

    assert sent == ProactiveSent(False, "the agent chose not to write")
    assert channel.sent == []
    assert record is not None
    assert record.delivery == "skipped"


def test_an_answer_of_skip_is_the_word_first_in_any_case() -> None:
    assert [is_skip(t) for t in ("SKIP", " skip. ", "Skip - khách đã mua rồi", "Dạ chị ơi", "skipper")] == [
        True,
        True,
        True,
        False,
        False,
    ]


async def test_a_failed_turn_is_not_answered_with_the_apology_meant_for_customers(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(BrokenModel())
    channel = FakeChannel()
    async with _running(runtime, channel, failure_reply="Xin lỗi, hệ thống đang bận.") as (_, outbox):
        sent = await _send(outbox)

    assert sent.counted is False
    assert sent.note == "no reply: auth"
    assert channel.sent == []


async def test_a_send_the_channel_never_took_is_cancelled_so_it_cannot_go_out_later(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?")]))
    async with _running(runtime, None) as (dispatcher, outbox):
        sent = await _send(outbox)
        record = await dispatcher.ingress.get(dispatcher.tenant_id, 1)

    assert sent == ProactiveSent(False, "not sent in time")
    assert record is not None
    assert (record.delivery, record.delivery_error) == ("skipped", "not sent in time")


async def test_the_same_message_asked_twice_is_sent_once(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?"), reply("lần hai")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (_, outbox):
        first = await _send(outbox)
        second = await _send(outbox)

    assert (first, second) == (ProactiveSent(True), ProactiveSent(True))
    assert [m.text for m in channel.sent] == ["Chị còn quan tâm không ạ?"]


async def test_plugins_write_to_a_chat_and_read_it_through_the_service(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Phòng khám nhắc lịch 14:00 hôm nay ạ.")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (dispatcher, outbox):
        runtime.plugins.use_proactive(outbox)
        sent = await outbox.send_to(
            channel="zalo-a1",
            conversation_id="c9",
            user_id="u9",
            message_id="crm-reminder:1",
            instruction="[Hệ thống] nhắc lịch",
        )
        history = await dispatcher.history("zalo-a1", "c9", 1)

    assert sent == ProactiveSent(True)
    (message,) = channel.sent
    assert (message.conversation_id, message.text) == ("c9", "Phòng khám nhắc lịch 14:00 hôm nay ạ.")
    assert message.metadata["proactive"] == "1"
    assert [m.text() for m in history] == ["Phòng khám nhắc lịch 14:00 hôm nay ạ."]

"""The follow-up loop, second half: writing to the customer. The limits are asked again just before the send, a
customer who wrote first cancels the appointment, a send runs once, and through the real queue and channels the
agent's ``SKIP`` and a failed turn send nothing while a message of its own is marked proactive."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_app.channel_hub import ChannelHub, DeliverySettings, is_skip
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.follow_up import (
    DEFAULT_POLICY,
    INSTRUCTION_MARK,
    DispatcherOutbox,
    FollowUp,
    FollowUpConfig,
    FollowUpPolicy,
    FollowUps,
    InMemoryFollowUpStore,
    Sent,
    instruction_for,
    render_transcript,
)
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import (
    AssistantResult,
    InMemorySessionStore,
    LlmRequest,
    Message,
    ModelError,
    StreamSink,
    TextBlock,
)
from agentcore.channels import ChannelCapabilities, OutboundMessage, Receive
from agentcore.harness.model.scripted import ScriptedModel, reply

# 12:00 in Vietnam, inside the window
NOW = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)
TENANT = "t"
CONFIG = FollowUpConfig(enabled=True, channels=("zalo-a1",))
FAST = DeliverySettings(tick_s=0.01, backoff_s=(0.0,), max_attempts=3, start_retry_s=0.0)


def _due(**kw: object) -> FollowUp:
    base = FollowUp(
        "zalo-a1",
        "c1",
        "u1",
        "s1",
        state="hesitant",
        reason="hỏi giá rồi im",
        next_at=NOW - timedelta(minutes=5),
        reviewed_through=10,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


class FakeOutbox:
    def __init__(self, result: Sent | Exception = Sent(True)) -> None:
        self.result = result
        self.calls: list[tuple[FollowUp, str, str]] = []

    async def send(self, row: FollowUp, external_id: str, instruction: str) -> Sent:
        self.calls.append((row, external_id, instruction))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Setup:
    def __init__(
        self,
        outbox: FakeOutbox | None = None,
        *,
        config: FollowUpConfig = CONFIG,
        now: datetime = NOW,
        connected: bool = True,
        policy: FollowUpPolicy = DEFAULT_POLICY,
    ) -> None:
        self.store = InMemoryFollowUpStore()
        self.outbox = outbox if outbox is not None else FakeOutbox()
        self.loop = FollowUps(
            self.store,
            InMemorySessionStore(),
            lambda: ScriptedModel([]),
            lambda: config,
            tenant_id=TENANT,
            policy=policy,
            clock=lambda: now,
            outbox=self.outbox if connected else None,
        )

    async def row(self) -> FollowUp:
        found = await self.store.get(TENANT, "zalo-a1", "c1")
        assert found is not None
        return found


# --- the checks before a send ---


async def test_a_due_follow_up_is_sent_once_and_counted() -> None:
    setup = Setup()
    await setup.store.save(TENANT, _due())

    assert await setup.loop.send_pass() == 1
    assert await setup.loop.send_pass() == 0  # no appointment left

    ((row, external_id, instruction),) = setup.outbox.calls
    assert (row.conversation_id, external_id) == ("c1", "followup:c1:10:0")
    assert instruction.startswith(INSTRUCTION_MARK)
    assert "hesitant (hỏi giá rồi im)" in instruction
    stored = await setup.row()
    assert (stored.next_at, stored.unanswered, stored.last_sent_at) == (None, 1, NOW)
    assert stored.state == "hesitant"


async def test_nothing_is_sent_while_the_loop_is_off_or_has_nowhere_to_send() -> None:
    off = Setup(config=FollowUpConfig(enabled=False, channels=("zalo-a1",)))
    other_channel = Setup(config=FollowUpConfig(enabled=True, channels=("zalo-b2",)))
    nowhere = Setup(connected=False)
    for setup in (off, other_channel, nowhere):
        await setup.store.save(TENANT, _due())

    assert [await s.loop.send_pass() for s in (off, other_channel, nowhere)] == [0, 0, 0]
    assert off.outbox.calls == other_channel.outbox.calls == []


@pytest.mark.parametrize(
    "row",
    [
        _due(next_at=NOW + timedelta(hours=1)),
        _due(paused_until=NOW + timedelta(days=3)),
        _due(stopped=True),
        _due(unanswered=2),
        _due(last_sent_at=NOW - timedelta(hours=3)),
    ],
    ids=["not due", "paused", "stopped", "too many unanswered", "too soon after the last one"],
)
async def test_the_limits_are_asked_again_just_before_the_send(row: FollowUp) -> None:
    setup = Setup()
    await setup.store.save(TENANT, row)

    assert await setup.loop.send_pass() == 0
    assert setup.outbox.calls == []


async def test_outside_the_hours_nothing_is_sent_and_the_appointment_waits() -> None:
    setup = Setup(now=datetime(2026, 10, 17, 16, 0, tzinfo=UTC))  # 23:00 in Vietnam
    await setup.store.save(TENANT, _due())

    assert await setup.loop.send_pass() == 0
    assert setup.outbox.calls == []
    assert (await setup.row()).next_at is not None


async def test_a_customer_who_wrote_before_the_appointment_cancels_it() -> None:
    setup = Setup()
    await setup.store.save(TENANT, _due())
    setup.store.add_message("zalo-a1", "c1", 11)

    assert await setup.loop.send_pass() == 0

    stored = await setup.row()
    assert setup.outbox.calls == []
    assert stored.next_at is None
    assert stored.unanswered == 0
    assert stored.reason.startswith("Khách nhắn lại trước giờ hẹn")
    assert "hỏi giá rồi im" in stored.reason


async def test_an_appointment_long_past_due_is_dropped_not_kept() -> None:
    setup = Setup()
    await setup.store.save(TENANT, _due(next_at=NOW - timedelta(days=3)))

    assert await setup.loop.send_pass() == 0
    assert setup.outbox.calls == []
    assert (await setup.row()).next_at is None


async def test_a_message_that_did_not_go_out_is_not_counted() -> None:
    setup = Setup(FakeOutbox(Sent(False, "the agent chose not to write")))
    await setup.store.save(TENANT, _due())

    assert await setup.loop.send_pass() == 0

    stored = await setup.row()
    assert (stored.next_at, stored.unanswered, stored.last_sent_at) == (None, 0, None)
    assert stored.reason.startswith("Không nhắn: the agent chose not to write.")


async def test_one_conversation_failing_does_not_stop_the_others() -> None:
    setup = Setup()
    setup.outbox.result = RuntimeError("boom")
    await setup.store.save(TENANT, _due())
    await setup.store.save(TENANT, _due(conversation_id="c2"))

    assert await setup.loop.send_pass() == 0

    assert len(setup.outbox.calls) == 2
    assert (await setup.row()).next_at is not None  # still due: the next pass tries again


async def test_the_cost_of_a_pass_is_bounded() -> None:
    setup = Setup(policy=replace(DEFAULT_POLICY, per_pass=2))
    for n in range(5):
        await setup.store.save(TENANT, _due(conversation_id=f"c{n}"))

    assert await setup.loop.send_pass() == 2


async def test_the_id_of_a_send_changes_with_the_state_of_the_conversation_only() -> None:
    first = Setup()
    await first.store.save(TENANT, _due())
    await first.loop.send_pass()
    again = Setup()
    await again.store.save(TENANT, _due())
    await again.loop.send_pass()
    later = Setup()
    await later.store.save(TENANT, _due(reviewed_through=40, unanswered=1))
    await later.loop.send_pass()

    assert first.outbox.calls[0][1] == again.outbox.calls[0][1] == "followup:c1:10:0"
    assert later.outbox.calls[0][1] == "followup:c1:40:1"


# --- what the agent is told, and what the judge reads ---


def test_the_instruction_says_what_to_write_and_how_to_decline() -> None:
    text = instruction_for(_due())

    assert text.startswith(INSTRUCTION_MARK)
    assert "SKIP" in text
    assert "MỘT tin" in text


@pytest.mark.parametrize(
    ("text", "skipped"),
    [
        ("SKIP", True),
        (" skip. ", True),
        ("Skip - khách đã mua rồi", True),
        ("Dạ chị ơi", False),
        ("skipper", False),
    ],
)
def test_an_answer_of_skip_is_nothing_to_send(text: str, skipped: bool) -> None:
    assert is_skip(text) is skipped


def test_the_judge_does_not_read_the_loops_instruction_nor_a_skip() -> None:
    history = [
        Message.user("giá bao nhiêu?"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ 500k ạ")]),
        Message.user(instruction_for(_due())),
        Message(role="assistant", blocks=[TextBlock(text="SKIP")]),
        Message.user("ok em"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ vâng")]),
        Message.user(instruction_for(_due())),
        Message(role="assistant", blocks=[TextBlock(text="Chị còn quan tâm không ạ?")]),
    ]

    assert render_transcript(history).split("\n") == [
        "Khách: giá bao nhiêu?",
        "Agent: Dạ 500k ạ",
        "Khách: ok em",
        "Agent: Dạ vâng",
        "Agent: Chị còn quan tâm không ạ?",
    ]


# --- through the real queue and channels ---


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


async def test_a_follow_up_goes_through_the_channel_marked_proactive(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (_, outbox):
        sent = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))

    assert sent == Sent(True)
    (message,) = channel.sent
    assert (message.conversation_id, message.text) == ("c1", "Chị còn quan tâm không ạ?")
    assert message.metadata["proactive"] == "1"


async def test_an_answer_of_skip_sends_nothing_and_does_not_count(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("SKIP")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (dispatcher, outbox):
        sent = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))
        record = await dispatcher.ingress.get(dispatcher.tenant_id, 1)

    assert sent == Sent(False, "the agent chose not to write")
    assert channel.sent == []
    assert record is not None
    assert record.delivery == "skipped"


async def test_a_failed_turn_is_not_answered_with_the_apology_meant_for_customers(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(BrokenModel())
    channel = FakeChannel()
    async with _running(runtime, channel, failure_reply="Xin lỗi, hệ thống đang bận.") as (_, outbox):
        sent = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))

    assert sent.counted is False
    assert sent.note == "no reply: auth"
    assert channel.sent == []


async def test_a_send_the_channel_never_took_is_cancelled_so_it_cannot_go_out_later(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?")]))
    async with _running(runtime, None) as (dispatcher, outbox):
        sent = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))
        record = await dispatcher.ingress.get(dispatcher.tenant_id, 1)

    assert sent == Sent(False, "not sent in time")
    assert record is not None
    assert (record.delivery, record.delivery_error) == ("skipped", "not sent in time")


async def test_the_same_follow_up_asked_twice_is_sent_once(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Chị còn quan tâm không ạ?"), reply("lần hai")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (_, outbox):
        first = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))
        second = await outbox.send(_due(), "followup:c1:10:0", instruction_for(_due()))

    assert (first, second) == (Sent(True), Sent(True))
    assert [m.text for m in channel.sent] == ["Chị còn quan tâm không ạ?"]


def test_the_judge_leaves_out_an_answer_that_was_never_sent_because_the_customer_wrote_again() -> None:
    history = [
        Message.user("hours?"),
        Message(role="assistant", blocks=[TextBlock(text="draft nobody saw")]),
        Message.user("[System] The person wrote again before your last answer was sent."),
        Message.user("and the price?"),
        Message(role="assistant", blocks=[TextBlock(text="hours and price in one answer")]),
    ]

    assert render_transcript(history).split("\n") == [
        "Khách: hours?",
        "Khách: and the price?",
        "Agent: hours and price in one answer",
    ]


async def test_a_plugin_writes_to_a_chat_through_the_same_outbox(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.live.use_model(ScriptedModel([reply("Phòng khám nhắc lịch 14:00 hôm nay ạ.")]))
    channel = FakeChannel()
    async with _running(runtime, channel) as (_, outbox):
        runtime.plugins.use_proactive(outbox)
        sent = await outbox.send_to(
            channel="zalo-a1",
            conversation_id="c9",
            user_id="u9",
            message_id="crm-reminder:1",
            instruction="[Hệ thống] nhắc lịch",
        )

    assert sent == Sent(True)
    (message,) = channel.sent
    assert (message.conversation_id, message.text) == ("c9", "Phòng khám nhắc lịch 14:00 hôm nay ạ.")
    assert message.metadata["proactive"] == "1"

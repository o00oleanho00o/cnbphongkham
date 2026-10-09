"""What happens to messages that come while their conversation's turn runs: one turn each (followup), one turn
for a burst from one person (collect), or joining a turn that uses tools (steer)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_app.dispatcher import Dispatcher, DispatchSettings, QueueMode
from agent_app.ingress import IngressRecord
from agent_app.profile import Profile, load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import AssistantResult, InMemoryTracer, LlmRequest, ModelError, StreamSink
from agentcore.channels import InboundMessage
from agentcore.harness.model.scripted import calls, reply, tool_call

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"

Step = Callable[[LlmRequest], Awaitable[AssistantResult]]


class Model:
    """Plays its steps in order and remembers the newest user text of each request."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.asked: list[str] = []
        self.started = asyncio.Event()

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.started.set()
        user = next(m for m in reversed(request.messages) if m.role == "user")
        self.asked.append(user.text().split("<agent-context>")[0].strip())
        return await self.steps.pop(0)(request)


def _answer(text: str) -> Step:
    async def step(request: LlmRequest) -> AssistantResult:
        return reply(text)

    return step


def _runtime(tmp_path: Path) -> Runtime:
    path = tmp_path / "agent.toml"
    path.write_text('[agent]\nname = "t"\ntools = ["get_datetime"]\n', encoding="utf-8")
    return build_runtime(load_profile(path), fake=True, env={}, db=None)


def _dispatcher(runtime: Runtime, model: Model, mode: QueueMode) -> Dispatcher:
    runtime.live.use_model(model)
    settings = DispatchSettings(queue_mode=mode, debounce_s=0.05, max_wait_s=0.5, poll_s=0.01)
    return runtime.dispatcher(settings)


def _inbound(message_id: str, text: str, user: str = "u1") -> InboundMessage:
    return InboundMessage("http", "c1", user, message_id, text)


async def _all(dispatcher: Dispatcher, *message_ids: str, user: str = "u1") -> list[IngressRecord]:
    records = [(await dispatcher.accept(_inbound(m, f"text {m}", user)))[0] for m in message_ids]
    return [await dispatcher.wait(r.id, 5.0) for r in records]


async def test_followup_runs_one_turn_per_message(tmp_path: Path) -> None:
    model = Model([_answer("one"), _answer("two")])
    dispatcher = _dispatcher(_runtime(tmp_path), model, "followup")

    first, second = await _all(dispatcher, "m1", "m2")

    assert model.asked == ["text m1", "text m2"]
    assert (first.reply and first.reply.text, second.reply and second.reply.text) == ("one", "two")
    await dispatcher.close()


async def test_collect_joins_a_burst_from_one_person_into_one_turn(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    model = Model([_answer("all at once")])
    dispatcher = _dispatcher(runtime, model, "collect")

    records = await _all(dispatcher, "m1", "m2", "m3")

    assert model.asked == ["text m1\n\ntext m2\n\ntext m3"]
    assert {(r.status, r.reply and r.reply.text) for r in records} == {("done", "all at once")}
    assert len({r.reply and r.reply.turn_id for r in records}) == 1
    tracer = runtime.tracer
    assert isinstance(tracer, InMemoryTracer)
    (trace,) = tracer.traces
    assert [dict(e.detail) for e in trace.events if e.kind == "inbox"] == [{"mode": "collect", "messages": 3}]
    await dispatcher.close()


async def test_collect_never_lets_a_reply_jump_ahead_of_another_persons_message(tmp_path: Path) -> None:
    model = Model([_answer("a"), _answer("b"), _answer("c")])
    dispatcher = _dispatcher(_runtime(tmp_path), model, "collect")

    records = [
        (await dispatcher.accept(_inbound("m1", "from one", "u1")))[0],
        (await dispatcher.accept(_inbound("m2", "from two", "u2")))[0],
        (await dispatcher.accept(_inbound("m3", "one again", "u1")))[0],
    ]
    for record in records:
        await dispatcher.wait(record.id, 5.0)

    assert model.asked == ["from one", "from two", "one again"]
    await dispatcher.close()


async def test_steer_brings_a_new_message_into_the_turn_while_it_uses_tools(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def call_a_tool(request: LlmRequest) -> AssistantResult:
        await release.wait()
        return calls(tool_call("get_datetime", {}))

    runtime = _runtime(tmp_path)
    model = Model([call_a_tool, _answer("both answered")])
    dispatcher = _dispatcher(runtime, model, "steer")

    first, _ = await dispatcher.accept(_inbound("m1", "what time is it"), deliver=True)
    await asyncio.wait_for(model.started.wait(), 5.0)
    second, _ = await dispatcher.accept(_inbound("m2", "and the date?"), deliver=True)
    release.set()
    done = [await dispatcher.wait(r.id, 5.0) for r in (first, second)]

    assert model.asked == ["what time is it", "and the date?"]
    history = await runtime.store.load("default", first.session_id)
    assert [m.role for m in history] == ["user", "assistant", "tool", "user", "assistant"]
    assert {(r.status, r.reply and r.reply.text) for r in done} == {("done", "both answered")}
    assert (done[0].delivery, done[1].delivery) == ("pending", "skipped")
    assert done[1].delivery_error == f"answered together with message {first.id}"
    await dispatcher.close()


async def test_a_failed_turn_fails_every_message_it_took(tmp_path: Path) -> None:
    async def broken(request: LlmRequest) -> AssistantResult:
        raise ModelError("auth", "bad key")

    model = Model([broken])
    dispatcher = _dispatcher(_runtime(tmp_path), model, "collect")

    records = await _all(dispatcher, "m1", "m2")

    assert {(r.status, r.error_kind) for r in records} == {("failed", "auth")}
    await dispatcher.close()


def test_the_profile_chooses_the_mode_per_channel_and_checks_the_waits(tmp_path: Path) -> None:
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    settings = runtime.dispatcher().settings
    custom = Profile.model_validate(
        {"agent": {"name": "t"}, "loop": {"queue_mode": "collect", "queue_by_channel": {"http": "followup"}}}
    )

    assert (settings.queue_mode, settings.debounce_s, settings.max_wait_s) == ("steer", 0.8, 3.0)
    assert custom.loop.queue_by_channel == {"http": "followup"}
    with pytest.raises(ValidationError, match="queue_max_wait_s"):
        Profile.model_validate(
            {"agent": {"name": "t"}, "loop": {"queue_debounce_s": 2, "queue_max_wait_s": 1}}
        )
    assert DispatchSettings(queue_by_channel={"zalo": "collect"}).mode_for("zalo") == "collect"
    assert DispatchSettings(queue_by_channel={"zalo": "collect"}).mode_for("http") == "followup"
    runtime.close()

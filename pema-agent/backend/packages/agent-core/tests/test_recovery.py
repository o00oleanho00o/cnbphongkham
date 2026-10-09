"""What the turn does when a model call fails: retries with growing pauses (or the provider's Retry-After), a
harder compaction when the provider finds the request too long, and a last answer when time runs out."""

from __future__ import annotations

import pytest

from agentcore import (
    AssistantResult,
    ContextManager,
    ContextPolicy,
    InMemorySessionStore,
    InMemoryTracer,
    LlmRequest,
    LoopPolicy,
    Message,
    ModelError,
    ModelErrorKind,
    PromptBuilder,
    RetryPolicy,
    StreamSink,
    TextBlock,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    TurnResult,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, ScriptStep, calls, reply, tool_call
from agentcore.prompt import FINAL_TURN_NOTE

SESSION = "s1"
NO_JITTER = RetryPolicy(jitter=0.0)


def _fail(kind: ModelErrorKind, *, retry_after_s: float | None = None) -> ScriptStep:
    def step(request: LlmRequest) -> AssistantResult:
        raise ModelError(kind, f"{kind} on purpose", retry_after_s=retry_after_s)

    return step


class Pauses:
    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)


async def _run(
    model: ScriptedModel | StutteringModel,
    *,
    policy: LoopPolicy | None = None,
    store: InMemorySessionStore | None = None,
    context: ContextManager | None = None,
    tools: ToolRegistry | None = None,
    pauses: Pauses | None = None,
    tracer: InMemoryTracer | None = None,
    observer: Recorder | None = None,
    timer: Clock | None = None,
) -> TurnResult:
    return await run_turn(
        session_id=SESSION,
        user_text="hi",
        prompt=PromptBuilder.fixed("sys"),
        model=model,
        tools=tools or ToolRegistry(),
        store=store or InMemorySessionStore(),
        policy=policy or LoopPolicy(retry=NO_JITTER),
        context=context,
        sleep=pauses or Pauses(),
        tracer=tracer,
        observer=observer,
        timer=timer or Clock(),
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def text(self, delta: str) -> None:
        self.events.append(f"text:{delta}")

    def thinking(self, delta: str) -> None:
        self.events.append(f"thinking:{delta}")

    def tool_call(self, use: ToolUseBlock) -> None:
        self.events.append(f"call:{use.name}")

    def tool_result(self, result: ToolResultBlock) -> None:
        self.events.append(f"result:{result.name}")

    def retry(self, error_kind: str) -> None:
        self.events.append(f"retry:{error_kind}")


class StutteringModel:
    """Streams a little, then the connection drops; the next call goes through."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.calls += 1
        if self.calls == 1:
            if sink is not None:
                sink.text("half an ans")
            raise ModelError("transient", "connection reset")
        if sink is not None:
            sink.text("the whole answer")
        return reply("the whole answer")


def test_the_pause_doubles_up_to_the_cap_and_retry_after_wins() -> None:
    policy = RetryPolicy(base_s=0.5, max_s=10.0, jitter=0.2)
    transient = ModelError("transient", "x")

    assert [policy.delay(n, transient, rand=lambda: 0.0) for n in range(1, 7)] == [0.5, 1, 2, 4, 8, 10]
    assert policy.delay(1, transient, rand=lambda: 1.0) == pytest.approx(0.6)
    assert policy.delay(3, ModelError("rate_limit", "x", retry_after_s=7.0)) == 7.0
    assert not policy.retries(ModelError("auth", "x"))
    with pytest.raises(ValueError, match="invalid retry policy"):
        RetryPolicy(max_s=0.1)


async def test_passing_failures_are_retried_with_growing_pauses_and_traced() -> None:
    pauses, tracer = Pauses(), InMemoryTracer()
    model = ScriptedModel(
        [_fail("transient"), _fail("empty_response"), _fail("rate_limit", retry_after_s=7.0), reply("ok")]
    )

    result = await _run(model, pauses=pauses, tracer=tracer)

    assert (result.text, result.steps, len(model.requests)) == ("ok", 1, 4)
    assert pauses.seconds == [0.5, 1.0, 7.0]
    (trace,) = tracer.traces
    retries = [e for e in trace.events if e.kind == "model_retry"]
    assert [(e.detail["error_kind"], e.detail["retry"], e.duration_s) for e in retries] == [
        ("transient", 1, 0.5),
        ("empty_response", 2, 1.0),
        ("rate_limit", 3, 7.0),
    ]
    assert [e.kind for e in trace.events].count("model_call") == 4


async def test_retries_stop_at_the_limit() -> None:
    pauses = Pauses()
    model = ScriptedModel([_fail("transient")] * 3 + [reply("never")])

    with pytest.raises(ModelError) as caught:
        await _run(model, policy=LoopPolicy(retry=RetryPolicy(max_retries=2, jitter=0.0)), pauses=pauses)

    assert caught.value.kind == "transient"
    assert pauses.seconds == [0.5, 1.0]


async def test_a_bad_key_is_not_retried() -> None:
    pauses = Pauses()

    with pytest.raises(ModelError) as caught:
        await _run(ScriptedModel([_fail("auth"), reply("never")]), pauses=pauses)

    assert (caught.value.kind, pauses.seconds) == ("auth", [])


async def test_text_streamed_before_a_drop_is_announced_void_to_the_observer() -> None:
    recorder = Recorder()

    result = await _run(StutteringModel(), observer=recorder)

    assert recorder.events == ["text:half an ans", "retry:transient", "text:the whole answer"]
    assert result.text == "the whole answer"


async def _store_with_history() -> InMemorySessionStore:
    store = InMemorySessionStore()
    for message in [
        Message.user("old question " * 50),
        Message(role="assistant", blocks=[TextBlock(text="old answer " * 50)]),
    ]:
        await store.append("default", SESSION, message)
    return store


def _context(summary: str = "SUMMARY") -> ContextManager:
    policy = ContextPolicy(window_tokens=1_000_000, compact_at=1.0, keep_recent_ratio=0.0)
    return ContextManager(policy, ScriptedModel([reply(summary)]))


async def test_a_request_the_provider_finds_too_long_is_compacted_harder_once_and_sent_again() -> None:
    store, tracer = await _store_with_history(), InMemoryTracer()
    model = ScriptedModel([_fail("context_overflow"), reply("answer")])

    result = await _run(model, store=store, context=_context(), tracer=tracer)

    assert (result.text, result.compactions) == ("answer", 1)
    resent = model.requests[1]
    assert all("old question" not in m.text() for m in resent.messages)
    compacted = await store.load_compaction("default", SESSION)
    assert compacted is not None
    assert compacted.summary == "SUMMARY"
    (trace,) = tracer.traces
    (compaction,) = [e for e in trace.events if e.kind == "compaction"]
    assert compaction.detail["forced"] is True


async def test_a_second_overflow_or_no_context_manager_fails_the_turn() -> None:
    twice = ScriptedModel([_fail("context_overflow"), _fail("context_overflow"), reply("never")])
    with pytest.raises(ModelError) as caught:
        await _run(twice, store=await _store_with_history(), context=_context())
    assert caught.value.kind == "context_overflow"

    without = ScriptedModel([_fail("context_overflow"), reply("never")])
    with pytest.raises(ModelError):
        await _run(without, store=await _store_with_history())
    assert len(without.requests) == 1


async def test_when_time_runs_out_no_new_step_starts_and_a_last_call_answers() -> None:
    clock = Clock()

    def slow_tool_call(request: LlmRequest) -> AssistantResult:
        clock.now += 200
        return calls(tool_call("nope"))

    model = ScriptedModel([slow_tool_call, slow_tool_call, reply("what I have so far")])

    result = await _run(model, policy=LoopPolicy(max_turn_s=300, retry=NO_JITTER), timer=clock)

    assert (result.stop, result.steps, result.text) == ("deadline", 3, "what I have so far")
    final = model.requests[-1]
    assert final.tools == []
    assert FINAL_TURN_NOTE in final.messages[-1].text()

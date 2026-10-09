"""The loop guard: reminders for identical tool calls in a row and for failing calls in a row, a stop when a
turn keeps going round, and the turn's token budget."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import BaseModel

from agentcore import (
    AssistantResult,
    InMemorySessionStore,
    InMemoryTracer,
    LlmRequest,
    LoopGuardPolicy,
    LoopPolicy,
    Message,
    PromptBuilder,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    TurnResult,
    Usage,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, ScriptStep, calls, reply, tool_call
from agentcore.loop.guard import GENTLE_REMINDER, LoopGuard, canonical_arguments
from agentcore.prompt import FINAL_TURN_NOTE

SESSION = "s1"


class LookArgs(BaseModel):
    query: str = ""
    page: int = 1


async def _look(args: LookArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text=f"nothing for {args.query}")


LOOK = ToolSpec(name="look", description="Look something up.", args_model=LookArgs, handler=_look)


def _use(name: str = "look", **args: object) -> ToolUseBlock:
    return ToolUseBlock(id=f"c-{name}", name=name, args=dict(args))


def _result(*, error: bool = False) -> ToolResultBlock:
    return ToolResultBlock(tool_use_id="c", name="look", content="x", is_error=error)


async def _run(
    steps: list[ScriptStep], policy: LoopPolicy, tracer: InMemoryTracer | None = None
) -> tuple[TurnResult, ScriptedModel, InMemorySessionStore]:
    model, store = ScriptedModel(steps), InMemorySessionStore()
    result = await run_turn(
        session_id=SESSION,
        user_text="find it",
        prompt=PromptBuilder.fixed("sys"),
        model=model,
        tools=ToolRegistry([LOOK]),
        store=store,
        policy=policy,
        tracer=tracer,
    )
    return result, model, store


def test_arguments_compare_with_their_keys_sorted_and_raw_text_when_not_json() -> None:
    assert canonical_arguments(_use(page=2, query="a")) == canonical_arguments(_use(query="a", page=2))
    assert canonical_arguments(ToolUseBlock(id="x", name="look", raw_args="{query: a")) == "{query: a"


def test_reminders_come_at_the_thresholds_and_a_different_call_starts_over() -> None:
    guard = LoopGuard(LoopGuardPolicy(repeat_thresholds=(3, 5), stop_after_repeats=None, preview_chars=12))
    seen = [guard.observe(_use(query="same thing here"), _result()) for _ in range(5)]
    other = guard.observe(_use(query="else"), _result())
    again = [guard.observe(_use(query="same thing here"), _result()) for _ in range(3)]

    assert [len(notes) for notes in seen] == [0, 0, 1, 0, 1]
    assert seen[2][0].text == GENTLE_REMINDER
    detailed = seen[4][0].text
    assert "- tool: look" in detailed
    assert "- consecutive_calls: 5" in detailed
    assert "(+" in detailed  # the arguments are cut to preview_chars
    assert other == []
    assert [len(notes) for notes in again] == [0, 0, 1]


def test_an_excluded_tool_neither_counts_nor_breaks_the_run() -> None:
    guard = LoopGuard(LoopGuardPolicy(repeat_thresholds=(3,), exclude=("clock",), stop_after_repeats=None))

    notes = [guard.observe(_use(q="a"), _result()), guard.observe(_use("clock"), _result())]
    notes.append(guard.observe(_use(q="a"), _result()))
    notes.append(guard.observe(_use(q="a"), _result()))

    assert [len(n) for n in notes] == [0, 0, 0, 1]


def test_failing_calls_in_a_row_earn_a_reminder_then_a_stop_and_a_success_starts_over() -> None:
    guard = LoopGuard(LoopGuardPolicy(error_streak_remind=2, error_streak_stop=3, stop_after_repeats=None))

    first = [guard.observe(_use(q=str(i)), _result(error=True)) for i in range(2)]
    guard.observe(_use(q="ok"), _result())
    second = [guard.observe(_use(q=f"b{i}"), _result(error=True)) for i in range(3)]

    assert [n[0].reason for n in first if n] == ["errors"]
    assert "The last 2 tool calls failed" in first[1][0].text
    assert [(n[0].count, n[0].stop) for n in second if n] == [(2, False), (3, True)]


@pytest.mark.parametrize(
    "build",
    [
        lambda: LoopGuardPolicy(repeat_thresholds=()),
        lambda: LoopGuardPolicy(repeat_thresholds=(1, 3)),
        lambda: LoopGuardPolicy(repeat_thresholds=(3, 3)),
        lambda: LoopGuardPolicy(repeat_thresholds=(3, 5), stop_after_repeats=5),
        lambda: LoopGuardPolicy(error_streak_remind=3, error_streak_stop=3),
        lambda: LoopGuardPolicy(error_streak_remind=0),
    ],
)
def test_a_wrong_guard_policy_is_refused(build: Callable[[], LoopGuardPolicy]) -> None:
    with pytest.raises(ValueError, match=r"repeat_thresholds|stop_after_repeats|error.streak"):
        build()


async def test_a_reminder_reaches_the_next_request_but_never_the_history() -> None:
    same = calls(tool_call("look", {"query": "x"}))
    tracer = InMemoryTracer()
    policy = LoopPolicy(guard=LoopGuardPolicy(repeat_thresholds=(2,), stop_after_repeats=None))

    result, model, store = await _run([same, same, reply("gave up")], policy, tracer)

    assert result.stop == "completed"
    assert GENTLE_REMINDER not in model.requests[1].messages[-1].text()
    assert GENTLE_REMINDER in model.requests[2].messages[-1].text()
    history = await store.load("default", SESSION)
    assert all(GENTLE_REMINDER not in m.text() for m in history)
    (trace,) = tracer.traces
    (event,) = [e for e in trace.events if e.kind == "guard"]
    assert (event.name, event.step, dict(event.detail)) == (
        "look",
        2,
        {"reason": "repeat", "count": 2, "stop": False},
    )


async def test_a_turn_going_round_stops_using_tools_and_answers() -> None:
    same = calls(tool_call("look", {"query": "x"}))
    policy = LoopPolicy(max_steps=10, guard=LoopGuardPolicy(repeat_thresholds=(2,), stop_after_repeats=3))

    result, model, _ = await _run([same, same, same, reply("what I found")], policy)

    assert (result.stop, result.steps, result.text) == ("loop", 4, "what I found")
    assert model.requests[-1].tools == []
    assert FINAL_TURN_NOTE in model.requests[-1].messages[-1].text()


async def test_failing_calls_in_a_row_stop_the_turn_too() -> None:
    broken = calls(tool_call("missing"))
    policy = LoopPolicy(max_steps=10, guard=LoopGuardPolicy(error_streak_remind=1, error_streak_stop=2))

    result, model, _ = await _run([broken, calls(tool_call("gone")), reply("sorry")], policy)

    assert (result.stop, result.text) == ("loop", "sorry")
    assert "The last 1 tool calls failed" in model.requests[1].messages[-1].text()


async def test_a_spent_token_budget_starts_no_new_step() -> None:
    def costly(request: LlmRequest) -> AssistantResult:
        message = Message(
            role="assistant",
            blocks=[tool_call("look", {"query": "x"})],
            usage=Usage(input_tokens=900, output_tokens=200),
        )
        return AssistantResult(message=message, stop_reason="tool_use")

    result, model, _ = await _run([costly, reply("short answer")], LoopPolicy(max_turn_tokens=1000))

    assert (result.stop, result.steps) == ("budget", 2)
    assert model.requests[-1].tools == []

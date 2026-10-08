"""The turn loop, driven by a scripted model: tool round trips, tool failures, the step budget and the empty
completion retry."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from agentcore import (
    AssistantResult,
    InMemorySessionStore,
    LlmRequest,
    LoopPolicy,
    ModelError,
    PromptBuilder,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolResultBlock,
    ToolSpec,
    TurnResult,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, ScriptStep, calls, reply, tool_call
from agentcore.prompt import FINAL_TURN_NOTE

SESSION = "s1"


class AddArgs(BaseModel):
    a: int
    b: int


async def _add(args: AddArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text=str(args.a + args.b))


ADD = ToolSpec(name="add", description="Add two integers.", args_model=AddArgs, handler=_add)


class NoArgs(BaseModel):
    pass


def _tool(name: str, handler_text: str, *, max_result_chars: int) -> ToolSpec[NoArgs]:
    async def handler(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        return ToolOutput(text=handler_text)

    return ToolSpec(
        name=name, description=name, args_model=NoArgs, handler=handler, max_result_chars=max_result_chars
    )


async def _run(
    steps: list[ScriptStep],
    tools: ToolRegistry,
    *,
    store: InMemorySessionStore | None = None,
    policy: LoopPolicy | None = None,
) -> tuple[TurnResult, ScriptedModel, InMemorySessionStore]:
    model = ScriptedModel(steps)
    used_store = store or InMemorySessionStore()
    result = await run_turn(
        session_id=SESSION,
        user_text="hi",
        prompt=PromptBuilder.fixed("system"),
        model=model,
        tools=tools,
        store=used_store,
        policy=policy,
    )
    return result, model, used_store


def _results(result: TurnResult) -> list[ToolResultBlock]:
    return [b for m in result.new_messages for b in m.blocks if isinstance(b, ToolResultBlock)]


async def test_a_text_reply_completes_the_turn_in_one_step() -> None:
    result, model, store = await _run([reply("hello", input_tokens=5, output_tokens=2)], ToolRegistry([ADD]))

    assert result.text == "hello"
    assert result.stop == "completed"
    assert result.steps == 1
    assert (result.usage.input_tokens, result.usage.output_tokens) == (5, 2)
    history = await store.load("default", SESSION)
    assert [m.role for m in history] == ["user", "assistant"]
    assert model.requests[0].tools[0].name == "add"


async def test_a_tool_call_is_run_and_its_result_goes_back_to_the_model() -> None:
    call = tool_call("add", {"a": 2, "b": 3}, call_id="c1")
    result, model, store = await _run([calls(call), reply("5")], ToolRegistry([ADD]))

    assert result.text == "5"
    assert result.steps == 2
    history = await store.load("default", SESSION)
    assert [m.role for m in history] == ["user", "assistant", "tool", "assistant"]
    sent_back = model.requests[1].messages[-1].blocks[0]
    assert isinstance(sent_back, ToolResultBlock)
    assert (sent_back.tool_use_id, sent_back.content, sent_back.is_error) == ("c1", "5", False)


async def test_the_assistant_message_is_stored_before_its_tool_runs() -> None:
    store = InMemorySessionStore()
    roles_seen_by_tool: list[list[str]] = []

    async def probe(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        history = await store.load(ctx.tenant_id, ctx.session_id)
        roles_seen_by_tool.append([m.role for m in history])
        return ToolOutput(text="ok")

    probe_tool = ToolSpec(name="probe", description="probe", args_model=NoArgs, handler=probe)
    await _run([calls(tool_call("probe")), reply("done")], ToolRegistry([probe_tool]), store=store)

    assert roles_seen_by_tool == [["user", "assistant"]]


async def test_an_unknown_tool_gives_an_error_result_and_the_turn_goes_on() -> None:
    result, _, _ = await _run([calls(tool_call("nope")), reply("sorry")], ToolRegistry([ADD]))

    (error,) = _results(result)
    assert error.is_error
    assert "Unknown tool: nope" in error.content
    assert result.text == "sorry"


async def test_arguments_that_fail_the_schema_are_reported_with_the_field() -> None:
    result, _, _ = await _run([calls(tool_call("add", {"a": "x"})), reply("ok")], ToolRegistry([ADD]))

    (error,) = _results(result)
    assert error.is_error
    assert error.content.startswith("Invalid arguments:")
    assert "a:" in error.content
    assert "b:" in error.content


async def test_arguments_that_are_not_json_are_reported() -> None:
    bad = tool_call("add", raw_args="{a: 1")
    result, _, _ = await _run([calls(bad), reply("ok")], ToolRegistry([ADD]))

    (error,) = _results(result)
    assert error.is_error
    assert "not valid JSON" in error.content


async def test_a_tool_that_raises_gives_an_error_result_without_ending_the_turn() -> None:
    async def boom(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        raise ConnectionError("upstream down")

    broken = ToolSpec(name="broken", description="broken", args_model=NoArgs, handler=boom)
    result, _, _ = await _run([calls(tool_call("broken")), reply("recovered")], ToolRegistry([broken]))

    (error,) = _results(result)
    assert error.is_error
    assert error.content == "ConnectionError: upstream down"
    assert result.text == "recovered"


async def test_a_slow_tool_times_out() -> None:
    async def slow(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        await asyncio.sleep(5)
        return ToolOutput(text="late")

    slow_tool = ToolSpec(name="slow", description="slow", args_model=NoArgs, handler=slow, timeout_s=0.01)
    result, _, _ = await _run([calls(tool_call("slow")), reply("ok")], ToolRegistry([slow_tool]))

    (error,) = _results(result)
    assert error.is_error
    assert "timed out" in error.content


async def test_a_long_tool_result_is_truncated() -> None:
    long_tool = _tool("long", handler_text="x" * 50, max_result_chars=10)
    result, _, _ = await _run([calls(tool_call("long")), reply("ok")], ToolRegistry([long_tool]))

    (out,) = _results(result)
    assert not out.is_error
    assert out.content == "x" * 10 + "…[truncated 40 chars]"


async def test_two_calls_in_one_message_get_two_results_in_order() -> None:
    first = tool_call("add", {"a": 1, "b": 1}, call_id="first")
    second = tool_call("add", {"a": 2, "b": 2}, call_id="second")
    result, _, _ = await _run([calls(first, second), reply("2 and 4")], ToolRegistry([ADD]))

    assert [(r.tool_use_id, r.content) for r in _results(result)] == [("first", "2"), ("second", "4")]


async def test_the_step_budget_ends_with_a_final_call_without_tools() -> None:
    steps: list[ScriptStep] = [
        calls(tool_call("add", {"a": 1, "b": 1})),
        calls(tool_call("add", {"a": 2, "b": 2})),
        reply("best answer so far"),
    ]
    result, model, store = await _run(steps, ToolRegistry([ADD]), policy=LoopPolicy(max_steps=2))

    assert result.stop == "max_steps"
    assert result.steps == 3
    assert result.text == "best answer so far"
    final_request = model.requests[-1]
    assert final_request.tools == []
    assert final_request.messages[-1].role == "user"
    assert FINAL_TURN_NOTE in final_request.messages[-1].text()
    history = await store.load("default", SESSION)
    assert all(FINAL_TURN_NOTE not in m.text() for m in history)
    assert history[-1].text() == "best answer so far"


async def test_a_tool_call_in_the_final_reply_is_dropped() -> None:
    steps: list[ScriptStep] = [
        calls(tool_call("add", {"a": 1, "b": 1})),
        calls(tool_call("add", {"a": 1, "b": 1}), text="partial"),
    ]
    result, _, store = await _run(steps, ToolRegistry([ADD]), policy=LoopPolicy(max_steps=1))

    history = await store.load("default", SESSION)
    assert not history[-1].tool_uses()
    assert result.text == "partial"


def _empty(request: LlmRequest) -> AssistantResult:
    raise ModelError("empty_response", "empty")


async def test_one_empty_completion_is_retried() -> None:
    result, model, _ = await _run([_empty, reply("second try")], ToolRegistry())

    assert result.text == "second try"
    assert len(model.requests) == 2


async def test_two_empty_completions_in_a_row_raise() -> None:
    with pytest.raises(ModelError) as caught:
        await _run([_empty, _empty], ToolRegistry())

    assert caught.value.kind == "empty_response"


async def test_other_model_errors_are_not_retried() -> None:
    def denied(request: LlmRequest) -> AssistantResult:
        raise ModelError("auth", "bad key")

    with pytest.raises(ModelError) as caught:
        await _run([denied, reply("never")], ToolRegistry())

    assert caught.value.kind == "auth"

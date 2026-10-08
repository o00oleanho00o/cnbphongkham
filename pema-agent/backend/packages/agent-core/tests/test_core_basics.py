"""Message helpers, the in-memory store, loop policy limits and tool spec limits."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentcore import (
    InMemorySessionStore,
    LoopPolicy,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    Usage,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call


def test_message_text_joins_text_blocks_only() -> None:
    message = Message(
        role="assistant",
        blocks=[
            ThinkingBlock(text="hidden"),
            TextBlock(text="Hello "),
            ToolUseBlock(id="c1", name="t"),
            TextBlock(text="world"),
        ],
    )

    assert message.text() == "Hello world"
    assert [u.id for u in message.tool_uses()] == ["c1"]


def test_a_message_round_trips_through_json_with_its_block_types() -> None:
    message = Message(
        role="assistant",
        blocks=[
            TextBlock(text="x"),
            ThinkingBlock(text="t", signature="sig"),
            ToolUseBlock(id="c1", name="t", args={"a": 1}, provider_meta={"thought_signature": "abc"}),
        ],
        usage=Usage(input_tokens=1, output_tokens=2),
    )

    assert Message.model_validate_json(message.model_dump_json()) == message


def test_usage_adds_up() -> None:
    total = Usage(input_tokens=1, output_tokens=2) + Usage(input_tokens=10, output_tokens=20)

    assert (total.input_tokens, total.output_tokens) == (11, 22)


async def test_the_store_keeps_sessions_and_tenants_apart() -> None:
    store = InMemorySessionStore()
    await store.append("t1", "s1", Message.user("a"))
    await store.append("t1", "s2", Message.user("b"))
    await store.append("t2", "s1", Message.user("c"))

    assert [m.text() for m in await store.load("t1", "s1")] == ["a"]
    assert [m.text() for m in await store.load("t2", "s1")] == ["c"]
    assert await store.load("t1", "missing") == []


async def test_editing_a_loaded_or_appended_message_does_not_change_the_store() -> None:
    store = InMemorySessionStore()
    original = Message.user("kept")
    await store.append("t", "s", original)
    original.blocks.append(TextBlock(text=" changed after append"))

    loaded = await store.load("t", "s")
    loaded[0].blocks.append(TextBlock(text=" changed after load"))

    assert [m.text() for m in await store.load("t", "s")] == ["kept"]


@pytest.mark.parametrize(("max_steps", "max_output_tokens"), [(0, 100), (1, 0)])
def test_a_loop_policy_needs_positive_limits(max_steps: int, max_output_tokens: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        LoopPolicy(max_steps=max_steps, max_output_tokens=max_output_tokens)


class NoArgs(BaseModel):
    pass


async def _ok(args: NoArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text="ok")


@pytest.mark.parametrize(("timeout_s", "max_result_chars"), [(0.0, 10), (-1.0, 10), (1.0, 0)])
def test_a_tool_spec_needs_positive_limits(timeout_s: float, max_result_chars: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ToolSpec(
            name="t",
            description="t",
            args_model=NoArgs,
            handler=_ok,
            timeout_s=timeout_s,
            max_result_chars=max_result_chars,
        )


async def test_a_turn_is_stored_under_its_tenant() -> None:
    store = InMemorySessionStore()

    await run_turn(
        session_id="s1",
        user_text="hi",
        system_prompt="",
        model=ScriptedModel([reply("hello")]),
        tools=ToolRegistry(),
        store=store,
        tenant_id="clinic-a",
    )

    assert [m.role for m in await store.load("clinic-a", "s1")] == ["user", "assistant"]
    assert await store.load("default", "s1") == []


async def test_the_tool_context_carries_the_session_and_tenant() -> None:
    seen: list[ToolContext] = []

    async def capture(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        seen.append(ctx)
        return ToolOutput(text="ok")

    tool = ToolSpec(name="capture", description="capture", args_model=NoArgs, handler=capture)
    await run_turn(
        session_id="s9",
        user_text="hi",
        system_prompt="",
        model=ScriptedModel([calls(tool_call("capture")), reply("done")]),
        tools=ToolRegistry([tool]),
        store=InMemorySessionStore(),
        tenant_id="clinic-b",
    )

    assert seen == [ToolContext(session_id="s9", tenant_id="clinic-b")]


async def test_an_error_reported_by_the_tool_itself_is_kept() -> None:
    async def refuse(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        return ToolOutput(text="not allowed today", is_error=True)

    tool = ToolSpec(name="refuse", description="refuse", args_model=NoArgs, handler=refuse)
    result = await run_turn(
        session_id="s1",
        user_text="hi",
        system_prompt="",
        model=ScriptedModel([calls(tool_call("refuse")), reply("ok")]),
        tools=ToolRegistry([tool]),
        store=InMemorySessionStore(),
    )

    (out,) = [b for m in result.new_messages for b in m.blocks if isinstance(b, ToolResultBlock)]
    assert (out.content, out.is_error) == ("not allowed today", True)


async def test_the_system_prompt_and_output_limit_reach_the_model() -> None:
    model = ScriptedModel([reply("hi")])

    await run_turn(
        session_id="s1",
        user_text="hi",
        system_prompt="be brief",
        model=model,
        tools=ToolRegistry(),
        store=InMemorySessionStore(),
        policy=LoopPolicy(max_output_tokens=123),
    )

    (request,) = model.requests
    assert (request.system, request.max_output_tokens, request.tools) == ("be brief", 123, [])

"""Prompt sections, the frozen system prompt, the context block and how the turn loop sends them."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from agentcore import (
    InMemorySessionStore,
    LoopPolicy,
    Message,
    PromptBuilder,
    PromptEnv,
    SectionRegistry,
    SessionSection,
    StepInfo,
    StepSection,
    StoredPrompt,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolResultBlock,
    ToolSpec,
    TurnInfo,
    TurnSection,
    builtin_sections,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from agentcore.prompt import CONTEXT_EXPLAINER, DEFAULT_SECTIONS, FINAL_TURN_NOTE, with_context
from agentcore.prompt.builtin import TOOL_USAGE

NOW = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)
ENV = PromptEnv(agent_name="dev", persona="Be kind.", timezone="Asia/Ho_Chi_Minh", tool_names=("t",))


def _builder(*names: str, env: PromptEnv = ENV) -> PromptBuilder:
    return PromptBuilder(env, builtin_sections().select(names or DEFAULT_SECTIONS))


def test_the_registry_selects_sections_in_the_order_asked() -> None:
    assert [s.name for s in builtin_sections().select(["status", "identity"])] == ["status", "identity"]
    assert builtin_sections().names() == list(DEFAULT_SECTIONS)


def test_the_registry_refuses_unknown_bad_and_repeated_names() -> None:
    with pytest.raises(ValueError, match="Unknown prompt section"):
        builtin_sections().select(["identity", "nope"])
    with pytest.raises(ValueError, match="Invalid section name"):
        SectionRegistry([SessionSection("Bad-Name", lambda env: "x")])
    with pytest.raises(ValueError, match="already registered"):
        SectionRegistry([SessionSection("a", lambda env: "x"), SessionSection("a", lambda env: "y")])


def test_a_section_listed_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="listed twice"):
        _builder("identity", "identity")


def test_bad_time_zone_and_naive_time_are_refused() -> None:
    with pytest.raises(ValueError, match="Unknown time zone"):
        PromptEnv(agent_name="a", persona="", timezone="Mars/Base")
    with pytest.raises(ValueError, match="timezone-aware"):
        TurnInfo(now=datetime(2026, 10, 8, 7, 0))


def test_the_system_prompt_joins_session_sections_and_explains_the_context_block() -> None:
    assert _builder().render_system() == f"Be kind.\n\n{TOOL_USAGE}\n\n{CONTEXT_EXPLAINER}"


def test_without_tools_or_context_sections_the_system_prompt_is_only_the_identity() -> None:
    env = PromptEnv(agent_name="dev", persona="  ")

    assert _builder("identity", "tool_usage", env=env).render_system() == (
        'You are "dev", a general-purpose assistant.'
    )


async def test_the_system_prompt_is_frozen_for_the_session() -> None:
    counter = iter(range(100))
    changing = SessionSection("changing", lambda env: f"version {next(counter)}")
    builder = PromptBuilder(ENV, [changing])
    store = InMemorySessionStore()

    first = await builder.system(store, "t", "s1")
    again = await builder.system(store, "t", "s1")
    other_session = await builder.system(store, "t", "s2")

    assert (first, again, other_session) == ("version 0", "version 0", "version 1")
    assert await store.load_prompt("t", "s1") == StoredPrompt(
        text="version 0", fingerprint=builder.fingerprint
    )
    assert await store.load_prompt("other-tenant", "s1") is None


async def test_a_new_configuration_rebuilds_the_prompt_and_logs_a_cache_break(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemorySessionStore()
    await _builder("identity").system(store, "t", "s1")
    changed = PromptEnv(agent_name="dev", persona="Be brief.", timezone="Asia/Ho_Chi_Minh", tool_names=("t",))

    with caplog.at_level(logging.WARNING, logger="agentcore.prompt.builder"):
        text = await _builder("identity", env=changed).system(store, "t", "s1")

    assert text == "Be brief."
    assert "prompt cache break: session s1" in caplog.text


def test_the_fingerprint_follows_the_configuration_only() -> None:
    assert _builder().fingerprint == _builder().fingerprint
    assert _builder().fingerprint != _builder("identity").fingerprint
    assert _builder().fingerprint != _builder(env=PromptEnv(agent_name="x", persona="Be kind.")).fingerprint


def test_the_context_block_has_the_time_in_the_agent_zone_and_the_step() -> None:
    turn = _builder().start_turn(TurnInfo(now=NOW, channel="cli"))

    assert turn.context(StepInfo(step=1, max_steps=3)) == (
        "<agent-context>\n"
        "Current time: 2026-10-08T14:00:00+07:00 (Thursday, Asia/Ho_Chi_Minh)\n"
        "Channel: cli\n"
        "Step 1 of 3.\n"
        "</agent-context>"
    )


def test_the_status_warns_on_the_last_step_and_the_final_call_gets_the_note() -> None:
    turn = _builder("status").start_turn(TurnInfo(now=NOW))

    assert "the last step that may call tools" in (turn.context(StepInfo(step=3, max_steps=3)) or "")
    assert turn.context(StepInfo(step=4, max_steps=3, final=True)) == (
        f"<agent-context>\n{FINAL_TURN_NOTE}\n</agent-context>"
    )


def test_the_final_note_is_sent_even_without_context_sections() -> None:
    turn = _builder("identity").start_turn(TurnInfo(now=NOW))

    assert turn.context(StepInfo(step=1, max_steps=2)) is None
    assert FINAL_TURN_NOTE in (turn.context(StepInfo(step=3, max_steps=2, final=True)) or "")


def test_turn_sections_render_once_per_turn_and_step_sections_every_step() -> None:
    renders: list[str] = []

    def per_turn(env: PromptEnv, turn: TurnInfo) -> str:
        renders.append("turn")
        return "T"

    def per_step(env: PromptEnv, turn: TurnInfo, step: StepInfo) -> str:
        renders.append("step")
        return f"S{step.step}"

    builder = PromptBuilder(ENV, [StepSection("b", per_step), TurnSection("a", per_turn)])
    turn = builder.start_turn(TurnInfo(now=NOW))

    assert turn.context(StepInfo(step=1, max_steps=2)) == "<agent-context>\nS1\nT\n</agent-context>"
    assert turn.context(StepInfo(step=2, max_steps=2)) == "<agent-context>\nS2\nT\n</agent-context>"
    assert renders == ["turn", "step", "step"]


def test_the_context_joins_a_last_user_message_without_changing_it() -> None:
    history = [Message.user("hi")]

    sent = with_context(history, "<ctx>")

    assert len(sent) == 1
    assert sent[0].text() == "hi\n\n<ctx>"
    assert history[0].text() == "hi"
    assert with_context(history, None) == history


def test_after_a_tool_result_the_context_is_a_new_user_message() -> None:
    result = Message(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", name="t", content="ok")])

    sent = with_context([Message.user("hi"), result], "<ctx>")

    assert [(m.role, m.text()) for m in sent] == [("user", "hi"), ("tool", ""), ("user", "<ctx>")]


class NoArgs(BaseModel):
    pass


async def _ok(args: NoArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text="ok")


async def test_the_turn_sends_the_frozen_system_and_a_fresh_context_and_stores_neither() -> None:
    tool = ToolSpec(name="t", description="t", args_model=NoArgs, handler=_ok)
    model = ScriptedModel([calls(tool_call("t", call_id="c1")), reply("done"), reply("again")])
    store = InMemorySessionStore()
    builder = _builder()
    times = iter([NOW, NOW + timedelta(days=1)])

    async def turn(text: str) -> None:
        await run_turn(
            session_id="s1",
            user_text=text,
            prompt=builder,
            model=model,
            tools=ToolRegistry([tool]),
            store=store,
            policy=LoopPolicy(max_steps=3),
            channel="cli",
            clock=lambda: next(times),
        )

    await turn("hi")
    await turn("hello")

    first, second, third = model.requests
    assert first.system == second.system == third.system == builder.render_system()
    assert first.messages[-1].text() == (
        "hi\n\n<agent-context>\n"
        "Current time: 2026-10-08T14:00:00+07:00 (Thursday, Asia/Ho_Chi_Minh)\n"
        "Channel: cli\n"
        "Step 1 of 3.\n"
        "</agent-context>"
    )
    assert second.messages[-1].role == "user"
    assert "Step 2 of 3." in second.messages[-1].text()
    assert "2026-10-09T14:00:00+07:00 (Friday" in third.messages[-1].text()
    history = await store.load("default", "s1")
    assert all("<agent-context>" not in m.text() for m in history)
    assert [m.role for m in history] == ["user", "assistant", "tool", "assistant", "user", "assistant"]

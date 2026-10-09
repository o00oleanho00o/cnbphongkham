"""A history left with a tool call and no result (a crash mid-turn) is repaired before the next turn; how a
conversation maps to a session id."""

from __future__ import annotations

import pytest

from agentcore import (
    InMemorySessionStore,
    InMemoryTracer,
    Message,
    PromptBuilder,
    TextBlock,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    run_turn,
)
from agentcore.channels import MAX_SESSION_ID_CHARS, session_id_for
from agentcore.harness.model.scripted import ScriptedModel, reply
from agentcore.loop.repair import INTERRUPTED_TEXT, missing_tool_results


def _calls(*ids: str) -> Message:
    return Message(role="assistant", blocks=[ToolUseBlock(id=i, name="lookup", args={}) for i in ids])


def _result(call_id: str) -> Message:
    return Message(role="tool", blocks=[ToolResultBlock(tool_use_id=call_id, name="lookup", content="ok")])


def test_only_calls_of_the_last_assistant_message_without_a_result_are_repaired() -> None:
    history = [Message.user("hi"), _calls("a", "b", "c"), _result("a")]

    repairs = missing_tool_results(history)

    assert [m.blocks[0] for m in repairs] == [
        ToolResultBlock(tool_use_id=i, name="lookup", content=INTERRUPTED_TEXT, is_error=True)
        for i in ("b", "c")
    ]
    assert missing_tool_results([*history, *repairs]) == []
    assert missing_tool_results([]) == []
    assert missing_tool_results([Message.user("hi")]) == []
    assert missing_tool_results([Message(role="assistant", blocks=[TextBlock(text="done")])]) == []


async def test_the_next_turn_repairs_the_history_before_the_new_message() -> None:
    store = InMemorySessionStore()
    for message in [Message.user("look it up"), _calls("a")]:
        await store.append("default", "s1", message)
    model = ScriptedModel([reply("sorry, that was interrupted")])
    tracer = InMemoryTracer()

    result = await run_turn(
        session_id="s1",
        user_text="any news?",
        prompt=PromptBuilder.fixed("sys"),
        model=model,
        tools=ToolRegistry(),
        store=store,
        tracer=tracer,
    )

    roles = [m.role for m in model.requests[0].messages]
    assert roles == ["user", "assistant", "tool", "user"]
    assert result.new_messages[0] == Message.user("any news?")
    (trace,) = tracer.traces
    assert (trace.events[0].kind, trace.events[0].detail) == ("repair", {"tool_calls": 1})


def test_a_session_id_is_agent_channel_conversation_and_epoch() -> None:
    assert session_id_for("dev", "http", "u-1", 0) == "dev:http:u-1:0"
    assert session_id_for("dev", "zalo", "thread:42", 3) == "dev:zalo:thread:42:3"

    long_id = session_id_for("dev", "http", "x" * 300, 1)
    assert len(long_id) <= MAX_SESSION_ID_CHARS
    assert long_id.startswith("dev:http:#")
    assert long_id.endswith(":1")
    assert long_id == session_id_for("dev", "http", "x" * 300, 1)


@pytest.mark.parametrize(
    ("agent", "channel", "conversation", "epoch"),
    [("Dev", "http", "c", 0), ("dev", "a:b", "c", 0), ("dev", "http", "", 0), ("dev", "http", "c", -1)],
)
def test_a_bad_session_part_is_refused(agent: str, channel: str, conversation: str, epoch: int) -> None:
    with pytest.raises(ValueError, match=r"invalid|needs a conversation"):
        session_id_for(agent, channel, conversation, epoch)

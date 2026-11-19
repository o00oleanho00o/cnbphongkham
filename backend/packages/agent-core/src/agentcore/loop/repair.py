"""Repairs a history left invalid by a run that stopped between storing a tool call and storing its result
(a crash or a deploy mid-turn). Providers refuse a tool call without a result, so without this every later
message of the session would fail."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from agentcore.messages import Message, ToolResultBlock

INTERRUPTED_TEXT: Final = (
    "Interrupted: the previous run stopped before this tool call returned, so its effect is unknown. "
    "Check before repeating it."
)


def missing_tool_results(history: Sequence[Message]) -> list[Message]:
    """Error results for the calls of the last assistant message that have none; empty when the history is
    valid. Only the last assistant message can be affected: a turn never continues past a missing result."""
    last = next((i for i in range(len(history) - 1, -1, -1) if history[i].role == "assistant"), None)
    if last is None:
        return []
    answered = {
        block.tool_use_id
        for message in history[last + 1 :]
        for block in message.blocks
        if isinstance(block, ToolResultBlock)
    }
    return [
        Message(
            role="tool",
            blocks=[
                ToolResultBlock(tool_use_id=use.id, name=use.name, content=INTERRUPTED_TEXT, is_error=True)
            ],
        )
        for use in history[last].tool_uses()
        if use.id not in answered
    ]

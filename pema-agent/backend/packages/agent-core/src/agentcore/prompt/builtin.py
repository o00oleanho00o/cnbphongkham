"""The built-in prompt sections: ``identity``, ``tool_usage``, ``environment`` and ``status``."""

from __future__ import annotations

from typing import Final

from agentcore.clock import describe_time
from agentcore.prompt.sections import (
    PromptEnv,
    SectionRegistry,
    SessionSection,
    StepInfo,
    StepSection,
    TurnInfo,
    TurnSection,
)

TOOL_USAGE: Final = """## Using tools
- Call a tool when it gives a better answer than guessing. Never invent what a tool would return.
- When a tool returns an error, read it: fix the arguments or try another way; tell the user if you cannot.
- Never say you ran a tool that you did not run."""

DEFAULT_SECTIONS: Final = ("identity", "tool_usage", "environment", "status")


def _identity(env: PromptEnv) -> str:
    return env.persona.strip() or f'You are "{env.agent_name}", a general-purpose assistant.'


def _tool_usage(env: PromptEnv) -> str | None:
    return TOOL_USAGE if env.tool_names else None


def _environment(env: PromptEnv, turn: TurnInfo) -> str:
    lines = [f"Current time: {describe_time(turn.now, env.timezone)}"]
    if turn.channel:
        lines.append(f"Channel: {turn.channel}")
    return "\n".join(lines)


def _status(env: PromptEnv, turn: TurnInfo, step: StepInfo) -> str | None:
    if step.final:
        return None
    if step.step >= step.max_steps:
        return f"Step {step.step} of {step.max_steps}: the last step that may call tools; answer after it."
    return f"Step {step.step} of {step.max_steps}."


def builtin_sections() -> SectionRegistry:
    return SectionRegistry(
        [
            SessionSection("identity", _identity),
            SessionSection("tool_usage", _tool_usage),
            TurnSection("environment", _environment),
            StepSection("status", _status),
        ]
    )

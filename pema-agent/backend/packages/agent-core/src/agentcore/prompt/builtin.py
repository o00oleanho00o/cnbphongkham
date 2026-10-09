"""The built-in prompt sections.

Session (system prompt, in this order by default): ``identity`` (SOUL.md), ``rules`` (AGENTS.md),
``tool_usage``, ``skills``, ``memory``, ``user_memory``. Context block: ``environment`` (turn), ``status``
(step). The most stable text comes first so the provider's prefix cache reaches furthest.
"""

from __future__ import annotations

from typing import Final

from agentcore.clock import describe_time
from agentcore.memory.service import ENTRY_SEPARATOR
from agentcore.prompt.data import SessionData
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

MEMORY_GUIDANCE: Final = (
    "Save with the memory tool what will matter in later conversations: the user's preferences and "
    "corrections, lasting facts about the work. Do not save task progress or anything temporary. Keep notes "
    "short; merge or remove old ones when space runs low."
)
SKILLS_GUIDANCE: Final = "Before a task a skill covers, read it with skill_view and follow it."
SKILLS_WRITE_GUIDANCE: Final = (
    "When you work out a procedure worth reusing, save it with skill_write; improve one with skill_patch."
)
SKILLS_SHOWN: Final = 50
SKILLS_INDEX_CHARS: Final = 4_000

DEFAULT_SECTIONS: Final = (
    "identity",
    "rules",
    "tool_usage",
    "skills",
    "memory",
    "user_memory",
    "environment",
    "status",
)


def _identity(env: PromptEnv, data: SessionData) -> str:
    return env.persona.strip() or f'You are "{env.agent_name}", a general-purpose assistant.'


def _rules(env: PromptEnv, data: SessionData) -> str | None:
    return env.rules.strip() or None


def _tool_usage(env: PromptEnv, data: SessionData) -> str | None:
    return TOOL_USAGE if env.tool_names else None


def _skills(env: PromptEnv, data: SessionData) -> str | None:
    can_write = "skill_write" in env.tool_names
    if not data.skills and not can_write:
        return None
    lines = ["## Skills"]
    if data.skills:
        lines.append(SKILLS_GUIDANCE)
    if can_write:
        lines.append(SKILLS_WRITE_GUIDANCE)
    used = 0
    shown = 0
    for entry in data.skills[:SKILLS_SHOWN]:
        line = f"- {entry.name}: {entry.description}"
        if used + len(line) > SKILLS_INDEX_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1
    if shown < len(data.skills):
        lines.append(f"- … and {len(data.skills) - shown} more (see skill_list)")
    if not data.skills:
        lines.append("No skills yet.")
    return "\n".join(lines)


def _memory(env: PromptEnv, data: SessionData) -> str | None:
    can_save = "memory" in env.tool_names
    if not data.agent_notes and not can_save:
        return None
    usage = _usage(data.agent_notes, data.agent_notes_limit)
    lines = [f"## Memory\nYour notes from earlier sessions ({usage}):"]
    lines.extend(f"- {note}" for note in data.agent_notes)
    if not data.agent_notes:
        lines.append("(none yet)")
    if can_save:
        lines.append(MEMORY_GUIDANCE)
    return "\n".join(lines)


def _user_memory(env: PromptEnv, data: SessionData) -> str | None:
    if not data.has_user or (not data.user_notes and "memory" not in env.tool_names):
        return None
    usage = _usage(data.user_notes, data.user_notes_limit)
    lines = [f"## About this user\nWhat you saved about them ({usage}):"]
    lines.extend(f"- {note}" for note in data.user_notes)
    if not data.user_notes:
        lines.append('(nothing yet; save with the memory tool, target "user")')
    return "\n".join(lines)


def _usage(notes: tuple[str, ...], limit: int) -> str:
    return f"{len(ENTRY_SEPARATOR.join(notes))}/{limit} chars"


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
            SessionSection("rules", _rules),
            SessionSection("tool_usage", _tool_usage),
            SessionSection("skills", _skills),
            SessionSection("memory", _memory),
            SessionSection("user_memory", _user_memory),
            TurnSection("environment", _environment),
            StepSection("status", _status),
        ]
    )

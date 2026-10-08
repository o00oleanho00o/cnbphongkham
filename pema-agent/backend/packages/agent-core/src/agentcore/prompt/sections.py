"""Prompt sections and what each one may read.

A section's scope decides where its text goes and how long it lives:

- ``session``: part of the system prompt, rendered once per session and frozen, so the provider's prompt
  cache keeps working.
- ``turn``: rendered once at the start of a turn, sent in the transient context block, never stored.
- ``step``: rendered before every model call, sent in the same block.

Each scope has its own section type, so a session section cannot read the clock or the step by mistake.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from agentcore.clock import zone

SECTION_NAME_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")

Scope = Literal["session", "turn", "step"]


@dataclass(frozen=True, slots=True)
class PromptEnv:
    """What the agent is, fixed for a session. A change here rebuilds the frozen system prompt."""

    agent_name: str
    persona: str
    timezone: str = "UTC"
    tool_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        zone(self.timezone)


@dataclass(frozen=True, slots=True)
class TurnInfo:
    now: datetime
    channel: str | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None:
            raise ValueError("TurnInfo.now must be timezone-aware")


@dataclass(frozen=True, slots=True)
class StepInfo:
    step: int
    max_steps: int
    final: bool = False
    """The call after the step budget ran out: no tools are offered."""


@dataclass(frozen=True, slots=True)
class SessionSection:
    name: str
    render: Callable[[PromptEnv], str | None]

    @property
    def scope(self) -> Scope:
        return "session"


@dataclass(frozen=True, slots=True)
class TurnSection:
    name: str
    render: Callable[[PromptEnv, TurnInfo], str | None]

    @property
    def scope(self) -> Scope:
        return "turn"


@dataclass(frozen=True, slots=True)
class StepSection:
    name: str
    render: Callable[[PromptEnv, TurnInfo, StepInfo], str | None]

    @property
    def scope(self) -> Scope:
        return "step"


Section = SessionSection | TurnSection | StepSection


class SectionRegistry:
    def __init__(self, sections: Iterable[Section] = ()) -> None:
        self._sections: dict[str, Section] = {}
        for section in sections:
            self.register(section)

    def register(self, section: Section) -> None:
        if not SECTION_NAME_PATTERN.fullmatch(section.name):
            raise ValueError(f"Invalid section name {section.name!r}: use lowercase letters, digits and '_'")
        if section.name in self._sections:
            raise ValueError(f"Section already registered: {section.name}")
        self._sections[section.name] = section

    def names(self) -> list[str]:
        return list(self._sections)

    def select(self, names: Iterable[str]) -> list[Section]:
        """The named sections in the given order."""
        wanted = list(names)
        unknown = [name for name in wanted if name not in self._sections]
        if unknown:
            raise ValueError(f"Unknown prompt section(s): {', '.join(unknown)}")
        return [self._sections[name] for name in wanted]

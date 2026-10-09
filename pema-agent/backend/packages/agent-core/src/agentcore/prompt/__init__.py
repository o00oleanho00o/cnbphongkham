"""Prompt sections and the builder that turns them into a frozen system prompt and a context block."""

from __future__ import annotations

from agentcore.prompt.builder import (
    CONTEXT_CLOSE,
    CONTEXT_EXPLAINER,
    CONTEXT_OPEN,
    FINAL_TURN_NOTE,
    PromptBuilder,
    TurnPrompt,
    with_context,
)
from agentcore.prompt.builtin import DEFAULT_SECTIONS, builtin_sections
from agentcore.prompt.data import SessionData, SkillEntry, load_session_data
from agentcore.prompt.sections import (
    PromptEnv,
    Scope,
    Section,
    SectionRegistry,
    SessionSection,
    StepInfo,
    StepSection,
    TurnInfo,
    TurnSection,
)

__all__ = [
    "CONTEXT_CLOSE",
    "CONTEXT_EXPLAINER",
    "CONTEXT_OPEN",
    "DEFAULT_SECTIONS",
    "FINAL_TURN_NOTE",
    "PromptBuilder",
    "PromptEnv",
    "Scope",
    "Section",
    "SectionRegistry",
    "SessionData",
    "SessionSection",
    "SkillEntry",
    "StepInfo",
    "StepSection",
    "TurnInfo",
    "TurnPrompt",
    "TurnSection",
    "builtin_sections",
    "load_session_data",
    "with_context",
]

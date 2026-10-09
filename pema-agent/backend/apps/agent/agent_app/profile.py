"""Agent profile: a TOML file naming the model, prompt, tools and limits an agent runs with.

A profile never holds a secret: the API key comes from the environment only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentcore import ContextPolicy, LoopPolicy
from agentcore.context import DEFAULT_CHARS_PER_TOKEN
from agentcore.prompt import DEFAULT_SECTIONS


class _Section(BaseModel):
    # A misspelt key fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class AgentSection(_Section):
    name: str
    system_prompt: str = ""
    system_prompt_file: str | None = None
    """A UTF-8 text file, relative to the profile; ``load_profile`` reads it into ``system_prompt``."""
    tools: list[str] = Field(default_factory=list[str])
    timezone: str = "UTC"

    @model_validator(mode="after")
    def _one_prompt_source(self) -> Self:
        if self.system_prompt and self.system_prompt_file:
            raise ValueError("set system_prompt or system_prompt_file, not both")
        return self


class ModelSection(_Section):
    provider: Literal["openai-compatible"] = "openai-compatible"
    model: str = ""
    base_url: str = ""
    timeout_s: float = Field(default=120.0, gt=0)


class LoopSection(_Section):
    max_steps: int = Field(default=6, ge=1, le=50)
    max_output_tokens: int = Field(default=2048, ge=64)


class PromptSection(_Section):
    sections: list[str] = Field(default_factory=lambda: list(DEFAULT_SECTIONS))
    """Prompt sections in order; session sections form the system prompt, the others the context block."""


class ContextSection(_Section):
    window_tokens: int | None = Field(default=None, gt=0)
    """The model's context window; without it nothing is compacted."""
    compact_at: float = Field(default=0.75, gt=0, le=1)
    keep_recent_ratio: float = Field(default=0.20, ge=0, lt=1)
    chars_per_token: float = Field(default=DEFAULT_CHARS_PER_TOKEN, gt=0)


class Profile(_Section):
    agent: AgentSection
    model: ModelSection = Field(default_factory=ModelSection)
    prompt: PromptSection = Field(default_factory=PromptSection)
    context: ContextSection = Field(default_factory=ContextSection)
    loop: LoopSection = Field(default_factory=LoopSection)

    def loop_policy(self) -> LoopPolicy:
        return LoopPolicy(max_steps=self.loop.max_steps, max_output_tokens=self.loop.max_output_tokens)

    def context_policy(self) -> ContextPolicy | None:
        if self.context.window_tokens is None:
            return None
        return ContextPolicy(
            window_tokens=self.context.window_tokens,
            compact_at=self.context.compact_at,
            keep_recent_ratio=self.context.keep_recent_ratio,
            chars_per_token=self.context.chars_per_token,
        )


def load_profile(path: Path) -> Profile:
    with path.open("rb") as file:
        profile = Profile.model_validate(tomllib.load(file))
    prompt_file = profile.agent.system_prompt_file
    if prompt_file is None:
        return profile
    text = (path.parent / prompt_file).read_text(encoding="utf-8")
    return profile.model_copy(update={"agent": profile.agent.model_copy(update={"system_prompt": text})})

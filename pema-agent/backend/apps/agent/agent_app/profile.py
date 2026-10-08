"""Agent profile: a TOML file naming the model, prompt, tools and limits an agent runs with.

A profile never holds a secret: the API key comes from the environment only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentcore import LoopPolicy


class _Section(BaseModel):
    # A misspelt key fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class AgentSection(_Section):
    name: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list[str])
    timezone: str = "UTC"


class ModelSection(_Section):
    provider: Literal["openai-compatible"] = "openai-compatible"
    model: str = ""
    base_url: str = ""
    timeout_s: float = Field(default=120.0, gt=0)


class LoopSection(_Section):
    max_steps: int = Field(default=6, ge=1, le=50)
    max_output_tokens: int = Field(default=2048, ge=64)


class Profile(_Section):
    agent: AgentSection
    model: ModelSection = Field(default_factory=ModelSection)
    loop: LoopSection = Field(default_factory=LoopSection)

    def loop_policy(self) -> LoopPolicy:
        return LoopPolicy(max_steps=self.loop.max_steps, max_output_tokens=self.loop.max_output_tokens)


def load_profile(path: Path) -> Profile:
    with path.open("rb") as file:
        return Profile.model_validate(tomllib.load(file))

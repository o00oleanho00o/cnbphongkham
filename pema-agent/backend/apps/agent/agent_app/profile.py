"""Agent profile: the folder that defines an agent, written by people and only read by the agent.

``agents/<name>/`` holds ``agent.toml`` (model, tools, limits), ``SOUL.md`` (who the agent is), ``AGENTS.md``
(how it works) and ``skills/<skill>/SKILL.md`` (bundled skills). A profile never holds a secret: the API key
comes from the environment only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from agentcore import ContextPolicy, LoopPolicy
from agentcore.context import DEFAULT_CHARS_PER_TOKEN
from agentcore.memory import MemoryLimits
from agentcore.memory.service import AGENT_NOTES_CHARS, USER_NOTES_CHARS
from agentcore.prompt import DEFAULT_SECTIONS

PROFILE_FILE: Final = "agent.toml"
SOUL_FILE: Final = "SOUL.md"
RULES_FILE: Final = "AGENTS.md"


class _Section(BaseModel):
    # A misspelt key fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class AgentSection(_Section):
    name: str
    system_prompt: str = ""
    """Who the agent is; ``load_profile`` fills it from SOUL.md when the folder has one."""
    rules: str = ""
    """How the agent works; ``load_profile`` fills it from AGENTS.md when the folder has one."""
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


class PromptSection(_Section):
    sections: list[str] = Field(default_factory=lambda: list(DEFAULT_SECTIONS))
    """Prompt sections in order; session sections form the system prompt, the others the context block."""


class ContextSection(_Section):
    window_tokens: int | None = Field(default=None, gt=0)
    """The model's context window; without it nothing is compacted."""
    compact_at: float = Field(default=0.75, gt=0, le=1)
    keep_recent_ratio: float = Field(default=0.20, ge=0, lt=1)
    chars_per_token: float = Field(default=DEFAULT_CHARS_PER_TOKEN, gt=0)


class MemorySection(_Section):
    enabled: bool = False
    agent_chars: int = Field(default=AGENT_NOTES_CHARS, ge=100, le=20_000)
    user_chars: int = Field(default=USER_NOTES_CHARS, ge=100, le=20_000)


class SkillsSection(_Section):
    enabled: bool = False
    dir: str = "skills"
    """Bundled skills, relative to the agent folder."""


class Profile(_Section):
    agent: AgentSection
    model: ModelSection = Field(default_factory=ModelSection)
    prompt: PromptSection = Field(default_factory=PromptSection)
    context: ContextSection = Field(default_factory=ContextSection)
    memory: MemorySection = Field(default_factory=MemorySection)
    skills: SkillsSection = Field(default_factory=SkillsSection)
    loop: LoopSection = Field(default_factory=LoopSection)
    _folder: Path | None = PrivateAttr(default=None)

    @property
    def folder(self) -> Path | None:
        """The agent folder the profile was loaded from."""
        return self._folder

    def in_folder(self, folder: Path) -> Profile:
        located = self.model_copy()
        located._folder = folder
        return located

    def loop_policy(self) -> LoopPolicy:
        return LoopPolicy(max_steps=self.loop.max_steps, max_output_tokens=self.loop.max_output_tokens)

    def memory_limits(self) -> MemoryLimits:
        return MemoryLimits(agent_chars=self.memory.agent_chars, user_chars=self.memory.user_chars)

    def bundled_skills_dir(self) -> Path | None:
        return self._folder / self.skills.dir if self._folder is not None else None

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
    """``path`` is an agent folder (holding agent.toml) or a TOML file; SOUL.md and AGENTS.md next to it fill
    the persona and the rules."""
    folder, file = (path, path / PROFILE_FILE) if path.is_dir() else (path.parent, path)
    with file.open("rb") as handle:
        profile = Profile.model_validate(tomllib.load(handle))
    agent = profile.agent
    soul = _read_markdown(folder / SOUL_FILE)
    rules = _read_markdown(folder / RULES_FILE)
    if soul is not None and agent.system_prompt:
        raise ValueError(f"{folder}: give the persona in {SOUL_FILE} or in system_prompt, not both")
    if rules is not None and agent.rules:
        raise ValueError(f"{folder}: give the rules in {RULES_FILE} or in rules, not both")
    filled = agent.model_copy(
        update={"system_prompt": soul or agent.system_prompt, "rules": rules or agent.rules}
    )
    return profile.model_copy(update={"agent": filled}).in_folder(folder)


def _read_markdown(path: Path) -> str | None:
    return path.read_text(encoding="utf-8").lstrip("\ufeff") if path.is_file() else None

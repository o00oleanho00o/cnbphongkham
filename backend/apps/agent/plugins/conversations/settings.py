"""The settings of the conversations plugin, kept as one record in the plugin's storage."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentcore.channels import valid_channel_name

from .scenario_models import Scope

MAX_STAFF: Final = 200
MAX_RETENTION_DAYS: Final = 3650


class ChannelSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    """Keep this channel's conversations."""
    staff: list[str] = Field(default_factory=list[str], max_length=MAX_STAFF)
    """Ids of the people on this channel who are staff (their messages are the staff's, not a customer's)."""
    use_scenarios: bool = True
    """Show the agent scenarios when it answers on this channel (they still have to be in reach)."""

    @field_validator("staff")
    @classmethod
    def _ids(cls, ids: list[str]) -> list[str]:
        cleaned = [i.strip() for i in ids if i.strip()]
        if any(len(i) > 100 for i in cleaned):
            raise ValueError("a staff id has at most 100 characters")
        return sorted(set(cleaned))


class ScenarioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    scope: Scope = "plugin"
    """Whose scenarios a question may use: its own channel's, every channel of its chat plugin, or all."""
    results: int = Field(default=3, ge=1, le=5)
    """Scenarios shown with one question."""
    min_similarity: float = Field(default=0.55, ge=0.2, le=0.95)
    """How alike a question and a scenario must be (by meaning) for the scenario to be shown."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: dict[str, ChannelSetting] = Field(default_factory=dict[str, ChannelSetting], max_length=500)
    retention_days: int = Field(default=0, ge=0, le=MAX_RETENTION_DAYS)
    """Messages older than this many days are deleted; 0 keeps them for ever."""
    scenarios: ScenarioSettings = Field(default_factory=ScenarioSettings)

    @field_validator("channels")
    @classmethod
    def _names(cls, channels: dict[str, ChannelSetting]) -> dict[str, ChannelSetting]:
        bad = [name for name in channels if not valid_channel_name(name)]
        if bad:
            raise ValueError(f"invalid channel name {bad[0]!r}")
        return channels

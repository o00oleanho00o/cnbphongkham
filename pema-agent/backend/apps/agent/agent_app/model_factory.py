"""Builds the model client of a profile. The profile names the provider and the model; the API key and any
change an admin makes are stored in the database (``agent_app.model_settings``), set on the dashboard or with
``agent model``. No environment variable is read."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from agent_app.profile import Profile
from agentcore import ModelClient, ReasoningEffort
from agentcore.harness.model.anthropic import AnthropicConfig, AnthropicModel
from agentcore.harness.model.openai_compat import OpenAICompatConfig, OpenAICompatModel
from agentcore.harness.model.reasoning import OpenAIDialect
from agentcore.harness.model.scripted import EchoModel

Provider = Literal["openai-compatible", "anthropic"]
DEFAULT_HOSTS: Final[dict[Provider, str]] = {
    "openai-compatible": "api.openai.com",
    "anthropic": "api.anthropic.com",
}


@dataclass(frozen=True, slots=True)
class ModelSettings:
    provider: Provider
    model: str
    api_key: str
    base_url: str | None
    timeout_s: float
    reasoning: ReasoningEffort | None
    dialect: OpenAIDialect | None = None


def resolve_model_settings(profile: Profile) -> ModelSettings:
    """The profile's model, without a key."""
    return ModelSettings(
        provider=profile.model.provider,
        model=profile.model.model,
        api_key="",
        base_url=profile.model.base_url or None,
        timeout_s=profile.model.timeout_s,
        reasoning=profile.model.reasoning,
        dialect=profile.model.dialect,
    )


def resolve_model_config(profile: Profile) -> OpenAICompatConfig:
    return _openai_config(resolve_model_settings(profile))


def _openai_config(settings: ModelSettings) -> OpenAICompatConfig:
    return OpenAICompatConfig(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout_s=settings.timeout_s,
        dialect=settings.dialect,
    )


def build_model(profile: Profile, *, fake: bool) -> ModelClient:
    if fake:
        return EchoModel()
    return client_for(resolve_model_settings(profile))


def client_for(settings: ModelSettings) -> ModelClient:
    """Raises ``ModelConfigError`` when a required value (the API key, the model) is missing."""
    if settings.provider == "anthropic":
        config = AnthropicConfig(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_s=settings.timeout_s,
        )
        return AnthropicModel(config)
    return OpenAICompatModel(_openai_config(settings))


def describe_model(profile: Profile, *, fake: bool) -> str:
    if fake:
        return "echo (no provider)"
    return describe_settings(resolve_model_settings(profile))


def describe_settings(settings: ModelSettings) -> str:
    where = settings.base_url or DEFAULT_HOSTS[settings.provider]
    reasoning = f", reasoning {settings.reasoning}" if settings.reasoning else ""
    return f"{settings.model} via {where} ({settings.provider}{reasoning})"

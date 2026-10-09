"""Builds the model client of a profile. The environment overrides the profile (``LLM_PROVIDER``,
``LLM_MODEL``, ``LLM_BASE_URL``, ``LLM_REASONING``); the API key comes from ``LLM_API_KEY`` only."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast, get_args

from agent_app.profile import Profile
from agentcore import ModelClient, ReasoningEffort
from agentcore.harness.model.anthropic import AnthropicConfig, AnthropicModel
from agentcore.harness.model.openai_compat import OpenAICompatConfig, OpenAICompatModel
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


def resolve_model_settings(profile: Profile, env: Mapping[str, str]) -> ModelSettings:
    provider = _choice(env.get("LLM_PROVIDER"), get_args(Provider), "LLM_PROVIDER")
    reasoning = _choice(env.get("LLM_REASONING"), get_args(ReasoningEffort), "LLM_REASONING")
    return ModelSettings(
        provider=provider or profile.model.provider,
        model=env.get("LLM_MODEL") or profile.model.model,
        api_key=env.get("LLM_API_KEY", ""),
        base_url=env.get("LLM_BASE_URL") or profile.model.base_url or None,
        timeout_s=profile.model.timeout_s,
        reasoning=reasoning or profile.model.reasoning,
    )


def resolve_model_config(profile: Profile, env: Mapping[str, str]) -> OpenAICompatConfig:
    settings = resolve_model_settings(profile, env)
    return OpenAICompatConfig(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout_s=settings.timeout_s,
        dialect=profile.model.dialect,
    )


def build_model(profile: Profile, *, fake: bool, env: Mapping[str, str]) -> ModelClient:
    if fake:
        return EchoModel()
    settings = resolve_model_settings(profile, env)
    if settings.provider == "anthropic":
        config = AnthropicConfig(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_s=settings.timeout_s,
        )
        return AnthropicModel(config)
    return OpenAICompatModel(resolve_model_config(profile, env))


def describe_model(profile: Profile, *, fake: bool, env: Mapping[str, str]) -> str:
    if fake:
        return "echo (no provider)"
    settings = resolve_model_settings(profile, env)
    where = settings.base_url or DEFAULT_HOSTS[settings.provider]
    reasoning = f", reasoning {settings.reasoning}" if settings.reasoning else ""
    return f"{settings.model} via {where} ({settings.provider}{reasoning})"


def _choice[T: str](value: str | None, allowed: tuple[T, ...], name: str) -> T | None:
    if not value:
        return None
    if value not in allowed:
        raise ValueError(f"{name}={value!r}: use one of {', '.join(allowed)}")
    return cast(T, value)

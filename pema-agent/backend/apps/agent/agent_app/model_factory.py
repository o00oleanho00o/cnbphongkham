"""Builds the model client of a profile. The environment overrides the profile; the API key is read from the
environment only."""

from __future__ import annotations

from collections.abc import Mapping

from agent_app.profile import Profile
from agentcore import ModelClient
from agentcore.harness.model.openai_compat import OpenAICompatConfig, OpenAICompatModel
from agentcore.harness.model.scripted import EchoModel


def resolve_model_config(profile: Profile, env: Mapping[str, str]) -> OpenAICompatConfig:
    return OpenAICompatConfig(
        model=env.get("LLM_MODEL") or profile.model.model,
        api_key=env.get("LLM_API_KEY", ""),
        base_url=env.get("LLM_BASE_URL") or profile.model.base_url or None,
        timeout_s=profile.model.timeout_s,
    )


def build_model(profile: Profile, *, fake: bool, env: Mapping[str, str]) -> ModelClient:
    if fake:
        return EchoModel()
    return OpenAICompatModel(resolve_model_config(profile, env))


def describe_model(profile: Profile, *, fake: bool, env: Mapping[str, str]) -> str:
    if fake:
        return "echo (no provider)"
    config = resolve_model_config(profile, env)
    return f"{config.model} via {config.base_url or 'api.openai.com'}"

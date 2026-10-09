"""Builds a runnable agent from its profile: model, tools, prompt, context manager, memory and skills."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from agent_app.model_factory import build_model, resolve_model_settings
from agent_app.profile import Profile
from agentcore import (
    ContextManager,
    LoopPolicy,
    ModelClient,
    PromptBuilder,
    PromptEnv,
    ToolRegistry,
    builtin_sections,
)
from agentcore.harness.hooks import HookSet, injection_guard, result_warning, secret_redactor
from agentcore.harness.tools.builtin import builtin_tools
from agentcore.memory import InMemoryMemoryBackend, MemoryBackend, MemoryService, make_memory_tool
from agentcore.skills import InMemorySkillStore, SkillLibrary, SkillStore, load_bundled_skills, skill_tools


@dataclass(frozen=True, slots=True)
class Agent:
    profile: Profile
    model: ModelClient
    tools: ToolRegistry
    prompt: PromptBuilder
    context: ContextManager | None
    memory: MemoryService | None
    skills: SkillLibrary | None
    policy: LoopPolicy
    hooks: HookSet


def build_agent(
    profile: Profile,
    *,
    fake: bool,
    env: Mapping[str, str],
    memory_backend: MemoryBackend | None = None,
    skill_store: SkillStore | None = None,
    model: ModelClient | None = None,
) -> Agent:
    """Without a backend or store, memory and agent-written skills live in process memory. A given ``model``
    (the settings-aware one of a service) picks its own reasoning effort, so the policy leaves it unset."""
    name = profile.agent.name
    client = model or build_model(profile, fake=fake, env=env)
    tools = builtin_tools(timezone=profile.agent.timezone).subset(profile.agent.tools)
    memory: MemoryService | None = None
    if profile.memory.enabled:
        memory = MemoryService(memory_backend or InMemoryMemoryBackend(), profile.memory_limits())
        tools.register(make_memory_tool(memory, agent=name))
    skills: SkillLibrary | None = None
    if profile.skills.enabled:
        folder = profile.bundled_skills_dir()
        skills = SkillLibrary(
            skill_store or InMemorySkillStore(), load_bundled_skills(folder) if folder else []
        )
        for spec in skill_tools(skills, agent=name):
            tools.register(spec)
    prompt = build_prompt(profile, tool_names=tools.names(), memory=memory, skills=skills)
    context_policy = profile.context_policy()
    context = ContextManager(context_policy, client) if context_policy else None
    if model is not None:
        policy = replace(profile.loop_policy(), reasoning=None)
    else:
        policy = profile.loop_policy(
            reasoning=None if fake else resolve_model_settings(profile, env).reasoning
        )
    return Agent(
        profile,
        client,
        tools,
        prompt,
        context,
        memory,
        skills,
        policy,
        build_hooks(profile, env),
    )


def build_hooks(profile: Profile, env: Mapping[str, str]) -> HookSet:
    hooks = HookSet()
    if profile.guards.injection_scan:
        hooks.add(injection_guard())
    if profile.guards.redact_secrets:
        hooks.add(secret_redactor(env))
    if profile.guards.warn_tool_results:
        hooks.add(result_warning())
    return hooks


def build_prompt(
    profile: Profile,
    *,
    tool_names: Sequence[str],
    memory: MemoryService | None = None,
    skills: SkillLibrary | None = None,
) -> PromptBuilder:
    env = PromptEnv(
        agent_name=profile.agent.name,
        persona=profile.agent.system_prompt,
        timezone=profile.agent.timezone,
        tool_names=tuple(tool_names),
        rules=profile.agent.rules,
    )
    sections = builtin_sections().select(profile.prompt.sections)
    return PromptBuilder(env, sections, memory=memory, skills=skills)

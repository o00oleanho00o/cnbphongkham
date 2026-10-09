"""Builds a runnable agent from its profile: model, tools, prompt, context manager, memory and skills."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


def build_agent(
    profile: Profile,
    *,
    fake: bool,
    env: Mapping[str, str],
    memory_backend: MemoryBackend | None = None,
    skill_store: SkillStore | None = None,
) -> Agent:
    """Without a backend or store, memory and agent-written skills live in process memory."""
    name = profile.agent.name
    model = build_model(profile, fake=fake, env=env)
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
    context = ContextManager(context_policy, model) if context_policy else None
    reasoning = None if fake else resolve_model_settings(profile, env).reasoning
    return Agent(
        profile, model, tools, prompt, context, memory, skills, profile.loop_policy(reasoning=reasoning)
    )


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

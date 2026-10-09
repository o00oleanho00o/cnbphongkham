"""Wires an agent to its storage: Postgres when a database is given, process memory otherwise."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from agent_app.assembly import Agent, build_agent
from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.ingress import (
    ConversationStore,
    IngressStore,
    InMemoryConversationStore,
    InMemoryIngressStore,
    InMemorySessionLocks,
    SessionLocks,
)
from agent_app.ingress_store import PostgresConversationStore, PostgresIngressStore, PostgresSessionLocks
from agent_app.model_settings import (
    SECRET_KEY_ENV,
    DynamicModel,
    InMemoryModelSettingsStore,
    ModelAdmin,
    ModelSettingsStore,
    PostgresModelSettingsStore,
)
from agent_app.profile import Profile
from agent_app.storage import (
    AgentDatabase,
    PostgresMemoryBackend,
    PostgresSessionStore,
    PostgresSkillStore,
    PostgresTracer,
)
from agentcore import DEFAULT_TENANT, InMemorySessionStore, InMemoryTracer, SessionStore, TurnTrace


class TraceLog(Protocol):
    async def record(self, trace: TurnTrace) -> None: ...

    async def last(self, tenant_id: str, session_id: str) -> TurnTrace | None: ...


@dataclass(frozen=True, slots=True)
class Runtime:
    agent: Agent
    store: SessionStore
    tracer: TraceLog
    locks: SessionLocks
    ingress: IngressStore
    conversations: ConversationStore
    sessions: PostgresSessionStore | None
    db: AgentDatabase | None
    model_admin: ModelAdmin
    dynamic_model: DynamicModel | None
    """None with ``--fake``: the echo model ignores the settings."""

    def dispatcher(self, settings: DispatchSettings | None = None) -> Dispatcher:
        return Dispatcher(
            self.agent,
            store=self.store,
            tracer=self.tracer,
            ingress=self.ingress,
            conversations=self.conversations,
            locks=self.locks,
            sessions=self.sessions,
            settings=settings,
        )


def build_runtime(
    profile: Profile,
    *,
    fake: bool,
    env: Mapping[str, str],
    db: AgentDatabase | None,
    tenant_id: str = DEFAULT_TENANT,
) -> Runtime:
    """Model settings come from the database (or process memory without one), then the environment, then
    the profile; a missing API key is reported on the first model call, so an admin can still set one."""
    name = profile.agent.name
    settings_store: ModelSettingsStore = (
        InMemoryModelSettingsStore() if db is None else PostgresModelSettingsStore(db, agent=name)
    )
    secret_key = env.get(SECRET_KEY_ENV) or None
    dynamic = (
        None
        if fake
        else DynamicModel(profile, env, settings_store, tenant_id=tenant_id, secret_key=secret_key)
    )
    admin = ModelAdmin(
        profile, env, settings_store, tenant_id=tenant_id, secret_key=secret_key, dynamic=dynamic
    )
    if db is None:
        return Runtime(
            agent=build_agent(profile, fake=fake, env=env, model=dynamic),
            store=InMemorySessionStore(),
            tracer=InMemoryTracer(),
            locks=InMemorySessionLocks(),
            ingress=InMemoryIngressStore(),
            conversations=InMemoryConversationStore(),
            sessions=None,
            db=None,
            model_admin=admin,
            dynamic_model=dynamic,
        )
    agent = build_agent(
        profile,
        fake=fake,
        env=env,
        memory_backend=PostgresMemoryBackend(db),
        skill_store=PostgresSkillStore(db),
        model=dynamic,
    )
    sessions = PostgresSessionStore(db, agent=name)
    model_name: Callable[[], str] = (lambda: "echo") if dynamic is None else (lambda: dynamic.model_name)
    return Runtime(
        agent=agent,
        store=sessions,
        tracer=PostgresTracer(db, agent=name, model=model_name),
        locks=PostgresSessionLocks(db),
        ingress=PostgresIngressStore(db, agent=name),
        conversations=PostgresConversationStore(db, agent=name),
        sessions=sessions,
        db=db,
        model_admin=admin,
        dynamic_model=dynamic,
    )

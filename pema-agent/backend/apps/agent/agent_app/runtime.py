"""Wires an agent to its storage: Postgres when a database is given, process memory otherwise."""

from __future__ import annotations

from collections.abc import Mapping
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
from agent_app.model_factory import resolve_model_settings
from agent_app.profile import Profile
from agent_app.storage import (
    AgentDatabase,
    PostgresMemoryBackend,
    PostgresSessionStore,
    PostgresSkillStore,
    PostgresTracer,
)
from agentcore import InMemorySessionStore, InMemoryTracer, SessionStore, TurnTrace


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
    profile: Profile, *, fake: bool, env: Mapping[str, str], db: AgentDatabase | None
) -> Runtime:
    if db is None:
        return Runtime(
            agent=build_agent(profile, fake=fake, env=env),
            store=InMemorySessionStore(),
            tracer=InMemoryTracer(),
            locks=InMemorySessionLocks(),
            ingress=InMemoryIngressStore(),
            conversations=InMemoryConversationStore(),
            sessions=None,
            db=None,
        )
    name = profile.agent.name
    agent = build_agent(
        profile,
        fake=fake,
        env=env,
        memory_backend=PostgresMemoryBackend(db),
        skill_store=PostgresSkillStore(db),
    )
    sessions = PostgresSessionStore(db, agent=name)
    model_name = "echo" if fake else resolve_model_settings(profile, env).model
    return Runtime(
        agent=agent,
        store=sessions,
        tracer=PostgresTracer(db, agent=name, model=model_name),
        locks=PostgresSessionLocks(db),
        ingress=PostgresIngressStore(db, agent=name),
        conversations=PostgresConversationStore(db, agent=name),
        sessions=sessions,
        db=db,
    )

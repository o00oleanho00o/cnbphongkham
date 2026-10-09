"""Wires an agent to its storage: Postgres when a database is given, process memory otherwise."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import agent_app
from agent_app.assembly import Agent, build_agent
from agent_app.channel_hub import ChannelHub, DeliverySettings
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
from agent_app.live import LiveAgent
from agent_app.model_factory import build_model
from agent_app.model_settings import (
    SECRET_KEY_ENV,
    DynamicModel,
    InMemoryModelSettingsStore,
    ModelAdmin,
    ModelSettingsStore,
    PostgresModelSettingsStore,
)
from agent_app.plugins import (
    Contributions,
    Discovery,
    PluginError,
    PluginHost,
    PluginOrigin,
    StorageFor,
    discover,
)
from agent_app.plugins.install import PluginInstaller
from agent_app.plugins.jobs import JobRunner, JobSettings
from agent_app.plugins.manager import PluginManager
from agent_app.plugins.records import InMemoryPluginRecords, PostgresPluginRecords
from agent_app.plugins.state import InMemoryPluginStateStore, PostgresPluginStateStore
from agent_app.profile import Profile
from agent_app.storage import (
    AgentDatabase,
    PostgresMemoryBackend,
    PostgresSessionStore,
    PostgresSkillStore,
    PostgresTracer,
)
from agentcore import (
    DEFAULT_TENANT,
    InMemorySessionStore,
    InMemoryTracer,
    ModelClient,
    SessionStore,
    TurnTrace,
)
from agentcore.memory import InMemoryMemoryBackend, MemoryBackend
from agentcore.skills import InMemorySkillStore, SkillStore

PLUGIN_DIR_ENV: Final = "AGENT_PLUGIN_DIR"
BUNDLED_PLUGINS: Final = Path(agent_app.__file__).resolve().parents[1] / "plugins"
"""``apps/agent/plugins``: the plugins shipped with the service."""


class TraceLog(Protocol):
    async def record(self, trace: TurnTrace) -> None: ...

    async def last(self, tenant_id: str, session_id: str) -> TurnTrace | None: ...


@dataclass(frozen=True, slots=True)
class Runtime:
    live: LiveAgent
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
    plugin_manager: PluginManager

    @property
    def agent(self) -> Agent:
        return self.live.current()

    @property
    def plugins(self) -> PluginHost:
        return self.live.host

    def close(self) -> None:
        self.plugins.close()

    def channel_hub(self, dispatcher: Dispatcher, settings: DeliverySettings | None = None) -> ChannelHub:
        """Runs the chat channels of the enabled plugins for ``dispatcher`` and sends their replies."""
        return ChannelHub(
            dispatcher,
            channels=lambda: self.plugins.contributions().channels,
            refresh=self.plugin_manager.refresh,
            settings=settings,
            failure_reply=self.agent.profile.agent.failure_reply,
        )

    def job_runner(self, settings: JobSettings | None = None) -> JobRunner:
        """Runs the background jobs of the enabled plugins."""
        return JobRunner(lambda: self.plugins.contributions().jobs, settings=settings)

    def dispatcher(self, settings: DispatchSettings | None = None) -> Dispatcher:
        """Without ``settings`` the profile's ``[loop]`` decides how waiting messages are handled."""
        loop = self.agent.profile.loop
        return Dispatcher(
            self.live,
            store=self.store,
            tracer=self.tracer,
            ingress=self.ingress,
            conversations=self.conversations,
            locks=self.locks,
            sessions=self.sessions,
            settings=settings
            or DispatchSettings(
                queue_mode=loop.queue_mode,
                queue_by_channel=dict(loop.queue_by_channel),
                debounce_s=loop.queue_debounce_s,
                max_wait_s=loop.queue_max_wait_s,
                max_batch=loop.queue_max_batch,
            ),
            before_turn=self.plugin_manager.refresh,
        )


def plugin_roots(profile: Profile, env: Mapping[str, str]) -> list[tuple[PluginOrigin, Path]]:
    """Bundled plugins, then the agent folder's, then the installed ones (``AGENT_PLUGIN_DIR``)."""
    roots: list[tuple[PluginOrigin, Path]] = [("bundled", BUNDLED_PLUGINS)]
    own = profile.plugins_dir()
    if own is not None:
        roots.append(("agent", own))
    installed = env.get(PLUGIN_DIR_ENV)
    if installed:
        roots.append(("installed", Path(installed)))
    return roots


def start_plugins(
    profile: Profile,
    env: Mapping[str, str],
    discovery: Discovery | None = None,
    *,
    storage: StorageFor | None = None,
) -> PluginHost:
    """Enables the plugins the profile lists; any of them failing stops the start, naming the plugin."""
    found = discovery or discover(plugin_roots(profile, env))
    host = PluginHost(found.plugins, env, storage=storage)
    try:
        for name in profile.plugins.enabled:
            if name not in found.plugins and name in found.broken:
                raise PluginError(name, found.broken[name])
            host.enable(name, profile.plugins.config(name))
    except Exception:
        host.close()
        raise
    return host


def build_runtime(
    profile: Profile,
    *,
    fake: bool,
    env: Mapping[str, str],
    db: AgentDatabase | None,
    tenant_id: str = DEFAULT_TENANT,
    plugins: PluginHost | None = None,
    model_wrapper: Callable[[ModelClient], ModelClient] | None = None,
) -> Runtime:
    """Model settings come from the database (or process memory without one), then the environment, then
    the profile; a missing API key is reported on the first model call, so an admin can still set one.
    Without a given plugin host, the profile's plugins are found and enabled here. ``model_wrapper`` wraps
    the model every call goes through, the summariser's too (recording, replay)."""
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
    memory_backend: MemoryBackend = InMemoryMemoryBackend() if db is None else PostgresMemoryBackend(db)
    skill_store: SkillStore = InMemorySkillStore() if db is None else PostgresSkillStore(db)
    records = (
        InMemoryPluginRecords() if db is None else PostgresPluginRecords(db, agent=name, tenant_id=tenant_id)
    )
    model: ModelClient | None = dynamic
    if model_wrapper is not None:
        model = model_wrapper(dynamic if dynamic is not None else build_model(profile, fake=True, env=env))

    def build(added: Contributions) -> Agent:
        return build_agent(
            profile,
            fake=fake,
            env=env,
            memory_backend=memory_backend,
            skill_store=skill_store,
            model=model,
            plugins=added,
        )

    live = LiveAgent(build, plugins or start_plugins(profile, env, storage=records.storage))
    installed = env.get(PLUGIN_DIR_ENV)
    plugin_manager = PluginManager(
        live,
        InMemoryPluginStateStore() if db is None else PostgresPluginStateStore(db, agent=name),
        profile=profile,
        roots=lambda: plugin_roots(profile, env),
        tenant_id=tenant_id,
        secret_key=secret_key,
        installer=PluginInstaller(Path(installed)) if installed else None,
    )
    if db is None:
        return Runtime(
            live=live,
            store=InMemorySessionStore(),
            tracer=InMemoryTracer(),
            locks=InMemorySessionLocks(),
            ingress=InMemoryIngressStore(),
            conversations=InMemoryConversationStore(),
            sessions=None,
            db=None,
            model_admin=admin,
            dynamic_model=dynamic,
            plugin_manager=plugin_manager,
        )
    sessions = PostgresSessionStore(db, agent=name)
    model_name: Callable[[], str] = (lambda: "echo") if dynamic is None else (lambda: dynamic.model_name)
    return Runtime(
        live=live,
        store=sessions,
        tracer=PostgresTracer(db, agent=name, model=model_name),
        locks=PostgresSessionLocks(db),
        ingress=PostgresIngressStore(db, agent=name),
        conversations=PostgresConversationStore(db, agent=name),
        sessions=sessions,
        db=db,
        model_admin=admin,
        dynamic_model=dynamic,
        plugin_manager=plugin_manager,
    )

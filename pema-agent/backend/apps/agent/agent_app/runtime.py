"""Wires an agent to its storage: Postgres when a database is given, process memory otherwise."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Final, Protocol
from zoneinfo import ZoneInfo

import agent_app
from agent_app.agent_settings import (
    AgentSettings,
    InMemoryAgentSettingsStore,
    PostgresAgentSettingsStore,
)
from agent_app.assembly import Agent, build_agent
from agent_app.cases import CaseEngine, CaseStore, InMemoryCaseStore, PostgresCaseStore
from agent_app.channel_hub import PACED_DELIVERY, ChannelHub, DeliverySettings
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
from agent_app.model_entries import InMemoryModelEntryStore, ModelEntryStore, PostgresModelEntryStore
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
    DatabaseAccess,
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

PLUGIN_DIR_ENV: Final = "AGENT_PLUGIN_DIR"
"""The service setting naming the folder of installed plugins (``agent_app.home``); not read from the
environment."""
BUNDLED_PLUGINS: Final = Path(agent_app.__file__).resolve().parents[1] / "plugins"
"""``apps/agent/plugins``: the plugins shipped with the service."""


def background_lock(
    locks: SessionLocks, tenant_id: str, agent: str
) -> Callable[[str], AbstractAsyncContextManager[None]]:
    """(work) -> the session locks' advisory lock, tried once (``SessionBusyError`` when another process
    holds it), under a name no session id takes (``agent:work``). Plugin jobs take none: several keep a
    cache of their own process fresh, and each would hold a pooled connection for as long as it runs."""
    return lambda work: locks.hold(tenant_id, f"{agent}:{work}", timeout_s=0)


class TraceLog(Protocol):
    async def record(self, trace: TurnTrace) -> None: ...

    async def last(self, tenant_id: str, session_id: str) -> TurnTrace | None: ...

    async def used_since(self, tenant_id: str, session_id: str, since: datetime) -> tuple[int, int]: ...


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
    agent_settings: AgentSettings
    """Judges the conversations that went quiet (Postgres only); runs once an admin switches it on."""
    cases: CaseEngine | None = None
    """Runs the cases plugins declare; runs once an admin switches cases on."""

    async def start(self) -> None:
        """Applies what is stored: the plugins that are on, then the agent's settings."""
        await self.plugin_manager.start()
        await self.agent_settings.start()

    async def refresh(self) -> None:
        """Before a turn: follows changes made since the last look (through this or another process)."""
        await self.plugin_manager.refresh()
        await self.agent_settings.refresh()

    async def over_budget(self, tenant_id: str, session_id: str) -> str | None:
        """Why a turn of this session may not run today (the settings' ``TokenBudget``), or None."""
        effective = self.agent_settings.effective
        local = datetime.now(ZoneInfo(effective.profile.agent.timezone))
        start = datetime.combine(local.date(), time(0), local.tzinfo)
        return effective.budget.spent(*await self.tracer.used_since(tenant_id, session_id, start))

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
            refresh=self.refresh,
            settings=settings or PACED_DELIVERY,
            failure_reply=lambda: self.agent.profile.agent.failure_reply,
            observe=self.plugins.observe,
            heard=None if self.cases is None else self.cases.on_inbound,
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
                wait_by_prefix={
                    k: (v.debounce_s, v.max_wait_s) for k, v in loop.queue_wait_by_prefix.items()
                },
                typing_hold_s=loop.queue_typing_hold_s,
                typing_max_wait_s=loop.queue_typing_max_wait_s,
            ),
            before_turn=self.refresh,
            over_budget=self.over_budget,
        )


def plugin_roots(profile: Profile, env: Mapping[str, str]) -> list[tuple[PluginOrigin, Path]]:
    """Bundled plugins, then the agent folder's, then the installed ones."""
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
    database: DatabaseAccess | None = None,
) -> PluginHost:
    """Enables the plugins the profile lists; any of them failing stops the start, naming the plugin."""
    found = discovery or discover(plugin_roots(profile, env))
    host = PluginHost(
        found.plugins,
        env,
        storage=storage,
        database=database,
    )
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
    """Model settings come from the database (or process memory without one), then the profile; a missing
    API key is reported on the first model call, so an admin can still set one. ``env`` holds the service's
    settings (the secret key, the home folders: see ``agent_app.home``) and the variables plugins may read.
    Without a given plugin host, the profile's plugins are found and enabled here. ``model_wrapper`` wraps
    the model every call goes through, the summariser's too (recording, replay)."""
    name = profile.agent.name
    settings_store: ModelSettingsStore = (
        InMemoryModelSettingsStore() if db is None else PostgresModelSettingsStore(db, agent=name)
    )
    secret_key = env.get(SECRET_KEY_ENV) or None
    dynamic = (
        None if fake else DynamicModel(profile, settings_store, tenant_id=tenant_id, secret_key=secret_key)
    )
    entry_store: ModelEntryStore = (
        InMemoryModelEntryStore() if db is None else PostgresModelEntryStore(db, agent=name)
    )
    admin = ModelAdmin(
        profile,
        settings_store,
        tenant_id=tenant_id,
        secret_key=secret_key,
        dynamic=dynamic,
        entries=entry_store,
    )
    memory_backend: MemoryBackend = InMemoryMemoryBackend() if db is None else PostgresMemoryBackend(db)
    records = (
        InMemoryPluginRecords() if db is None else PostgresPluginRecords(db, agent=name, tenant_id=tenant_id)
    )
    model: ModelClient | None = dynamic
    if model_wrapper is not None:
        model = model_wrapper(dynamic if dynamic is not None else build_model(profile, fake=True))

    agent_settings = AgentSettings(
        profile,
        InMemoryAgentSettingsStore() if db is None else PostgresAgentSettingsStore(db, agent=name),
        tenant_id=tenant_id,
    )

    case_store: CaseStore = (
        InMemoryCaseStore() if db is None else PostgresCaseStore(db, tenant_id=tenant_id, agent=name)
    )
    locks: SessionLocks = InMemorySessionLocks() if db is None else PostgresSessionLocks(db)
    # in one process (no database) every pass and job runs there: no lock to take
    background = None if db is None else background_lock(locks, tenant_id, name)
    cases = CaseEngine(
        case_store,
        lambda: {spec.kind: (plugin, spec) for plugin, spec in live.host.contributions().cases},
        config=lambda: agent_settings.effective.cases,
        zone=lambda: ZoneInfo(agent_settings.effective.profile.agent.timezone),
        lock=background,
    )

    def dynamic_window() -> int | None:
        return None if dynamic is None else dynamic.window_tokens

    def build(added: Contributions) -> Agent:
        effective = agent_settings.effective
        return build_agent(
            effective.profile,
            fake=fake,
            env=env,
            memory_backend=memory_backend,
            model=model,
            plugins=added,
            disabled_tools=effective.disabled_tools,
            # only while a plugin declares cases: an agent without any keeps its prompt (and its cache)
            case_tools=cases.tools() if added.cases else (),
            window=None if dynamic is None else dynamic_window,
        )

    access = None if db is None else DatabaseAccess(db.engine, tenant_id=tenant_id, agent=name)
    live = LiveAgent(build, plugins or start_plugins(profile, env, storage=records.storage, database=access))
    agent_settings.attach(live)
    live.host.use_cases(cases)
    live.host.use_model(model or build_model(profile, fake=True))
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
            locks=locks,
            ingress=InMemoryIngressStore(),
            conversations=InMemoryConversationStore(),
            sessions=None,
            db=None,
            model_admin=admin,
            dynamic_model=dynamic,
            plugin_manager=plugin_manager,
            agent_settings=agent_settings,
            cases=cases,
        )
    sessions = PostgresSessionStore(db, agent=name)
    model_name: Callable[[], str] = (lambda: "echo") if dynamic is None else (lambda: dynamic.model_name)
    return Runtime(
        live=live,
        store=sessions,
        tracer=PostgresTracer(db, agent=name, model=model_name),
        locks=locks,
        ingress=PostgresIngressStore(db, agent=name),
        conversations=PostgresConversationStore(db, agent=name),
        sessions=sessions,
        db=db,
        model_admin=admin,
        dynamic_model=dynamic,
        plugin_manager=plugin_manager,
        agent_settings=agent_settings,
        cases=cases,
    )

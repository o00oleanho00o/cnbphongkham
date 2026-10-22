"""Settings of the agent an admin changes at runtime (dashboard or ``agent settings``): time zone, the reply
after a failed turn, the values of the persona's variables, the persona and the rules, the memory limits and
which tools are on. They are stored per (tenant, agent), resolved field by field as database > profile, and
applied from the next turn on without a restart.

What stays in the profile (``agent.toml``): the guards, the loop, the context and the prompt sections. They
are limits of the service, not choices of whoever runs the clinic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text as sql

from agent_app.cases.engine import CasesConfig
from agent_app.dispatcher import TokenBudget
from agent_app.follow_up import MAX_CHANNELS, FollowUpConfig
from agent_app.live import LiveAgent
from agent_app.profile import Profile, fill_variables
from agent_app.storage import AgentDatabase, retrying
from agentcore import ToolSpec
from agentcore.channels import valid_channel_name
from agentcore.harness.tools.builtin import builtin_tools
from agentcore.memory.tool import DESCRIPTION as MEMORY_DESCRIPTION

REFRESH_S: Final = 5.0
MAX_TEXT_CHARS: Final = 20_000
MAX_FAILURE_REPLY_CHARS: Final = 1000
MAX_VARIABLES: Final = 50
MAX_VARIABLE_CHARS: Final = 500
MIN_MEMORY_CHARS: Final = 100
MEMORY_TOOL: Final = "memory"
"""Not a flag of the tools map: it is ``memory_enabled``, which also decides the memory part of the prompt."""
VARIABLE_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TEXT_FIELDS: Final = ("timezone", "failure_reply", "persona", "rules")
MEMORY_FIELDS: Final = ("memory_enabled", "memory_agent_chars", "memory_user_chars")
CASE_FIELDS: Final = ("cases_enabled", "proactive_per_person_per_day")
BUDGET_FIELDS: Final = ("tokens_per_session_per_day", "tokens_per_day")
SCALAR_FIELDS: Final = (*TEXT_FIELDS, *MEMORY_FIELDS, "follow_up_enabled", *CASE_FIELDS, *BUDGET_FIELDS)
MAX_PROACTIVE_PER_DAY: Final = 20
TOKEN_LIMITS: Final = {
    "tokens_per_session_per_day": (10_000, 100_000_000),
    "tokens_per_day": (100_000, 2_000_000_000),
}

FieldSource = Literal["db", "profile"]

logger = logging.getLogger(__name__)


class SettingsError(ValueError):
    """The change is refused; ``code`` says why (``invalid``, ``unknown_tool``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoredAgentSettings:
    """What an admin stored; None (and an empty map) leaves the field to the profile."""

    timezone: str | None = None
    failure_reply: str | None = None
    persona: str | None = None
    """The text with its ``{{variables}}``, as in SOUL.md."""
    rules: str | None = None
    memory_enabled: bool | None = None
    memory_agent_chars: int | None = None
    memory_user_chars: int | None = None
    follow_up_enabled: bool | None = None
    follow_up_channels: tuple[str, ...] = ()
    """The channels the follow-up loop watches, by the name the channel hub gives them."""
    cases_enabled: bool | None = None
    """The emergency switch of every case (off until switched on)."""
    proactive_per_person_per_day: int | None = None
    """Messages all cases together may start with one person in one local day (None: the default, 2)."""
    tokens_per_session_per_day: int | None = None
    tokens_per_day: int | None = None
    """The daily token budget (``TokenBudget``) of one session and of the whole agent (None: the default)."""
    variables: Mapping[str, str] = field(default_factory=dict[str, str])
    """Only the variables whose value an admin changed; the others keep the profile's."""
    tools: Mapping[str, bool] = field(default_factory=dict[str, bool])
    """Only the tools an admin switched on or off by hand."""
    version: int = 0
    updated_by: str | None = None

    @property
    def empty(self) -> bool:
        return (
            not self.variables
            and not self.tools
            and not self.follow_up_channels
            and all(getattr(self, n) is None for n in SCALAR_FIELDS)
        )


@dataclass(frozen=True, slots=True)
class EffectiveAgent:
    profile: Profile
    """The profile with the stored settings laid over it; the agent is built from this one."""
    disabled_tools: frozenset[str]
    """Plugin tools an admin switched off."""
    sources: Mapping[str, FieldSource]
    version: int
    follow_up: FollowUpConfig = field(default_factory=FollowUpConfig)
    cases: CasesConfig = field(default_factory=CasesConfig)
    budget: TokenBudget = field(default_factory=TokenBudget)


def core_tool_names() -> list[str]:
    return builtin_tools().names()


def resolve_agent(profile: Profile, stored: StoredAgentSettings | None) -> EffectiveAgent:
    """``ValueError`` when the persona or the rules name a variable that has no value."""
    stored = stored or StoredAgentSettings()
    agent = profile.agent
    sources: dict[str, FieldSource] = {}
    changes: dict[str, Any] = {}
    for name in ("timezone", "failure_reply"):
        value = getattr(stored, name)
        sources[name] = "db" if value is not None else "profile"
        if value is not None:
            changes[name] = value
    variables = {**agent.variables, **stored.variables}
    sources["variables"] = "db" if stored.variables else "profile"
    for key, filled, template in (
        ("persona", "system_prompt", "persona_template"),
        ("rules", "rules", "rules_template"),
    ):
        text = getattr(stored, key)
        sources[key] = "db" if text is not None else "profile"
        if text is not None or stored.variables:
            raw = text if text is not None else getattr(agent, template) or getattr(agent, filled)
            changes[filled] = fill_variables(raw, variables, key)
    core = core_tool_names()
    changes["tools"] = [n for n in agent.tools if stored.tools.get(n, True)] + [
        n for n in core if n not in agent.tools and stored.tools.get(n, False)
    ]
    memory: dict[str, Any] = {}
    for key, attr in (
        ("memory_enabled", "enabled"),
        ("memory_agent_chars", "agent_chars"),
        ("memory_user_chars", "user_chars"),
    ):
        value = getattr(stored, key)
        sources[key] = "db" if value is not None else "profile"
        if value is not None:
            memory[attr] = value
    laid = profile.model_copy(
        update={
            "agent": agent.model_copy(update=changes),
            "memory": profile.memory.model_copy(update=memory),
        }
    )
    disabled = frozenset(n for n, on in stored.tools.items() if not on and n not in core)
    sources["follow_up_enabled"] = "db" if stored.follow_up_enabled is not None else "profile"
    sources["follow_up_channels"] = "db" if stored.follow_up_channels else "profile"
    follow_up = FollowUpConfig(bool(stored.follow_up_enabled), tuple(stored.follow_up_channels))
    for name in CASE_FIELDS:
        sources[name] = "db" if getattr(stored, name) is not None else "profile"
    cases = CasesConfig(
        bool(stored.cases_enabled), stored.proactive_per_person_per_day or CasesConfig().per_person_per_day
    )
    for name in BUDGET_FIELDS:
        sources[name] = "db" if getattr(stored, name) is not None else "profile"
    default = TokenBudget()
    budget = TokenBudget(
        stored.tokens_per_session_per_day or default.per_session_per_day,
        stored.tokens_per_day or default.per_day,
    )
    return EffectiveAgent(
        profile=laid,
        disabled_tools=disabled,
        sources=sources,
        version=stored.version,
        follow_up=follow_up,
        cases=cases,
        budget=budget,
    )


class InMemoryAgentSettingsStore:
    def __init__(self) -> None:
        self._rows: dict[str, StoredAgentSettings] = {}

    async def get(self, tenant_id: str) -> StoredAgentSettings | None:
        return self._rows.get(tenant_id)

    async def version(self, tenant_id: str) -> int:
        row = self._rows.get(tenant_id)
        return 0 if row is None else row.version

    async def save(self, tenant_id: str, settings: StoredAgentSettings) -> StoredAgentSettings:
        saved = replace(settings, version=await self.version(tenant_id) + 1)
        self._rows[tenant_id] = saved
        return saved


_GET = sql(
    "SELECT timezone, failure_reply, persona, rules, memory_enabled, memory_agent_chars, memory_user_chars, "
    "variables, tools, follow_up_enabled, follow_up_channels, cases_enabled, proactive_per_person_per_day, "
    "tokens_per_session_per_day, tokens_per_day, version, updated_by FROM agent_rt.agent_settings "
    "WHERE tenant_id = :tenant_id AND agent = :agent"
)
_VERSION = sql("SELECT version FROM agent_rt.agent_settings WHERE tenant_id = :tenant_id AND agent = :agent")
_SAVE = sql(
    "INSERT INTO agent_rt.agent_settings (tenant_id, agent, timezone, failure_reply, persona, rules, "
    "memory_enabled, memory_agent_chars, memory_user_chars, follow_up_enabled, follow_up_channels, "
    "cases_enabled, proactive_per_person_per_day, tokens_per_session_per_day, tokens_per_day, variables, "
    "tools, updated_by) "
    "VALUES (:tenant_id, :agent, :timezone, :failure_reply, :persona, :rules, :memory_enabled, "
    ":memory_agent_chars, :memory_user_chars, :follow_up_enabled, CAST(:follow_up_channels AS jsonb), "
    ":cases_enabled, :proactive_per_person_per_day, :tokens_per_session_per_day, :tokens_per_day, "
    "CAST(:variables AS jsonb), CAST(:tools AS jsonb), :updated_by) "
    "ON CONFLICT (tenant_id, agent) DO UPDATE SET timezone = EXCLUDED.timezone, "
    "failure_reply = EXCLUDED.failure_reply, persona = EXCLUDED.persona, rules = EXCLUDED.rules, "
    "memory_enabled = EXCLUDED.memory_enabled, memory_agent_chars = EXCLUDED.memory_agent_chars, "
    "memory_user_chars = EXCLUDED.memory_user_chars, follow_up_enabled = EXCLUDED.follow_up_enabled, "
    "follow_up_channels = EXCLUDED.follow_up_channels, cases_enabled = EXCLUDED.cases_enabled, "
    "proactive_per_person_per_day = EXCLUDED.proactive_per_person_per_day, "
    "tokens_per_session_per_day = EXCLUDED.tokens_per_session_per_day, "
    "tokens_per_day = EXCLUDED.tokens_per_day, "
    "variables = EXCLUDED.variables, "
    "tools = EXCLUDED.tools, updated_by = EXCLUDED.updated_by, "
    "version = agent_rt.agent_settings.version + 1, updated_at = now() RETURNING version"
)


class PostgresAgentSettingsStore:
    """A clear keeps the row with every field empty, so the version never goes back to a value a running
    service may have cached."""

    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    async def get(self, tenant_id: str) -> StoredAgentSettings | None:
        async def work() -> StoredAgentSettings | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_GET, {"tenant_id": tenant_id, "agent": self._agent})).one_or_none()
            if row is None:
                return None
            return StoredAgentSettings(
                timezone=row.timezone,
                failure_reply=row.failure_reply,
                persona=row.persona,
                rules=row.rules,
                memory_enabled=row.memory_enabled,
                memory_agent_chars=row.memory_agent_chars,
                memory_user_chars=row.memory_user_chars,
                follow_up_enabled=row.follow_up_enabled,
                follow_up_channels=tuple(row.follow_up_channels),
                cases_enabled=row.cases_enabled,
                proactive_per_person_per_day=row.proactive_per_person_per_day,
                tokens_per_session_per_day=row.tokens_per_session_per_day,
                tokens_per_day=row.tokens_per_day,
                variables=dict(row.variables),
                tools=dict(row.tools),
                version=row.version,
                updated_by=row.updated_by,
            )

        return await retrying("load agent settings", work)

    async def version(self, tenant_id: str) -> int:
        async def work() -> int:
            async with self._engine.connect() as conn:
                found = await conn.execute(_VERSION, {"tenant_id": tenant_id, "agent": self._agent})
                return found.scalar_one_or_none() or 0

        return await retrying("agent settings version", work)

    async def save(self, tenant_id: str, settings: StoredAgentSettings) -> StoredAgentSettings:
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            **{name: getattr(settings, name) for name in SCALAR_FIELDS},
            "follow_up_channels": json.dumps(list(settings.follow_up_channels)),
            "variables": json.dumps(dict(settings.variables), ensure_ascii=False),
            "tools": json.dumps(dict(settings.tools)),
            "updated_by": settings.updated_by,
        }

        async def work() -> StoredAgentSettings:
            async with self._engine.begin() as conn:
                version = (await conn.execute(_SAVE, params)).scalar_one()
            return replace(settings, version=version)

        return await retrying("save agent settings", work)


AgentSettingsStore = InMemoryAgentSettingsStore | PostgresAgentSettingsStore


class AgentSettings:
    """What the admin endpoints and ``agent settings`` / ``agent tools`` do, and what the agent is built from:
    ``effective`` follows the stored settings, looked at most every ``refresh_s`` before a turn (so a change
    made through another process applies within a few seconds) and at once after a change made here."""

    def __init__(
        self,
        profile: Profile,
        store: AgentSettingsStore,
        *,
        tenant_id: str,
        refresh_s: float = REFRESH_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._profile = profile
        self._store = store
        self._tenant_id = tenant_id
        self._refresh_s = refresh_s
        self._clock = clock
        self._effective = resolve_agent(profile, None)
        self._seen: int | None = None
        self._checked = -math.inf
        self._lock = asyncio.Lock()
        self._live: LiveAgent | None = None

    def attach(self, live: LiveAgent) -> None:
        """The agent to build again when the settings change, and where the plugins' tools are read from."""
        self._live = live

    @property
    def effective(self) -> EffectiveAgent:
        return self._effective

    async def start(self) -> None:
        await self.refresh(force=True)

    async def refresh(self, *, force: bool = False) -> None:
        if not force and self._clock() - self._checked < self._refresh_s:
            return
        async with self._lock:
            if force or await self._store.version(self._tenant_id) != self._seen:
                await self._load()
            self._checked = self._clock()

    async def _load(self) -> None:
        stored = await self._store.get(self._tenant_id) or StoredAgentSettings()
        try:
            effective = resolve_agent(self._profile, stored)
        except ValueError as err:  # the profile changed under stored text (a new variable without a value)
            logger.warning("stored agent settings ignored: %s", err)
            effective = resolve_agent(self._profile, None)
        self._seen = stored.version
        changed = effective != self._effective
        self._effective = effective
        if changed and self._live is not None:
            self._live.rebuild()

    # --- settings ---

    async def show(self) -> dict[str, Any]:
        stored = await self._store.get(self._tenant_id) or StoredAgentSettings()
        effective = resolve_agent(self._profile, stored)
        agent, memory = effective.profile.agent, effective.profile.memory
        return {
            "timezone": agent.timezone,
            "failure_reply": agent.failure_reply,
            "variables": {**self._profile.agent.variables, **stored.variables},
            "persona": stored.persona
            if stored.persona is not None
            else self._profile.agent.persona_template or self._profile.agent.system_prompt,
            "rules": stored.rules
            if stored.rules is not None
            else self._profile.agent.rules_template or self._profile.agent.rules,
            "memory_enabled": memory.enabled,
            "memory_agent_chars": memory.agent_chars,
            "memory_user_chars": memory.user_chars,
            "follow_up_enabled": effective.follow_up.enabled,
            "follow_up_channels": list(effective.follow_up.channels),
            "cases_enabled": effective.cases.enabled,
            "proactive_per_person_per_day": effective.cases.per_person_per_day,
            "tokens_per_session_per_day": effective.budget.per_session_per_day,
            "tokens_per_day": effective.budget.per_day,
            "sources": dict(effective.sources),
            "stored": not stored.empty,
            "version": stored.version,
            "updated_by": stored.updated_by,
        }

    async def update(self, changes: Mapping[str, Any], *, by: str | None = None) -> dict[str, Any]:
        """``changes`` holds only the fields to change: a value sets it, None gives it back to the profile.
        ``variables`` maps a name to its value (None: the profile's again), or is None for all of them."""
        current = await self._store.get(self._tenant_id) or StoredAgentSettings()
        updates: dict[str, Any] = {name: changes[name] for name in SCALAR_FIELDS if name in changes}
        for name, value in updates.items():
            _check_scalar(name, value)
        if "variables" in changes:
            updates["variables"] = _merged_variables(current.variables, changes["variables"])
        if "follow_up_channels" in changes:
            updates["follow_up_channels"] = _checked_channels(changes["follow_up_channels"])
        changed = list(updates)
        await self._save(replace(current, **updates, updated_by=by), changed)
        return await self.show()

    async def clear(self, *, by: str | None = None) -> dict[str, Any]:
        await self._save(StoredAgentSettings(updated_by=by), ["all"])
        return await self.show()

    # --- tools ---

    async def tools(self) -> dict[str, Any]:
        """Every tool the agent has or may have: the core ones and those of the plugins that are on."""
        stored = await self._store.get(self._tenant_id) or StoredAgentSettings()
        agent, memory = self._profile.agent, self._profile.memory
        shown: list[dict[str, Any]] = []
        registry = builtin_tools()
        for name in registry.names():
            spec = registry.get(name)
            shown.append(
                _tool(
                    name,
                    spec.description if spec else "",
                    "core",
                    stored.tools.get(name, name in agent.tools),
                    name in agent.tools,
                    name in stored.tools,
                )
            )
        enabled = memory.enabled if stored.memory_enabled is None else stored.memory_enabled
        shown.append(
            _tool(
                MEMORY_TOOL,
                MEMORY_DESCRIPTION,
                "core",
                enabled,
                memory.enabled,
                stored.memory_enabled is not None,
            )
        )
        for spec in self._plugin_tools():
            shown.append(
                _tool(
                    spec.name,
                    spec.description,
                    "plugin",
                    stored.tools.get(spec.name, True),
                    True,
                    spec.name in stored.tools,
                )
            )
        return {"tools": shown, "version": stored.version}

    async def set_tool(self, name: str, enabled: bool | None, *, by: str | None = None) -> dict[str, Any]:
        """Switches a tool on or off; None gives it back to the profile (core) or to on (plugin)."""
        current = await self._store.get(self._tenant_id) or StoredAgentSettings()
        if name == MEMORY_TOOL:
            await self._save(replace(current, memory_enabled=enabled, updated_by=by), [f"tool {name}"])
            return await self.tools()
        known = {*core_tool_names(), *current.tools, *(spec.name for spec in self._plugin_tools())}
        if name not in known:
            raise SettingsError("unknown_tool", f"no tool {name!r} (is its plugin on?)")
        flags = {n: on for n, on in current.tools.items() if n != name}
        if enabled is not None:
            flags[name] = enabled
        await self._save(replace(current, tools=flags, updated_by=by), [f"tool {name}"])
        return await self.tools()

    def _plugin_tools(self) -> list[ToolSpec[Any]]:
        if self._live is None:
            return []
        core = set(core_tool_names())
        return [spec for spec in self._live.host.contributions().tools if spec.name not in core]

    async def _save(self, new: StoredAgentSettings, changed: list[str]) -> None:
        try:
            resolve_agent(self._profile, new)
        except ValueError as err:
            raise SettingsError("invalid", str(err)) from err
        saved = await self._store.save(self._tenant_id, new)
        # Names only: the persona, the rules and the variables never reach the log.
        logger.info("agent settings changed (version %d): %s", saved.version, ", ".join(changed))
        await self.refresh(force=True)


def _tool(
    name: str, description: str, source: str, enabled: bool, default: bool, stored: bool
) -> dict[str, Any]:
    first = description.strip().split("\n\n", 1)[0].replace("\n", " ")
    return {
        "name": name,
        "description": first[:300],
        "source": source,
        "enabled": enabled,
        "default": default,
        "stored": stored,
    }


def _check_scalar(name: str, value: Any) -> None:
    if value is None:
        return
    if name == "timezone":
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError, OSError) as err:
            raise SettingsError("invalid", f"unknown time zone {value!r}") from err
    elif name == "failure_reply" and len(value) > MAX_FAILURE_REPLY_CHARS:
        raise SettingsError("invalid", f"the reply holds at most {MAX_FAILURE_REPLY_CHARS} characters")
    elif name in ("persona", "rules") and len(value) > MAX_TEXT_CHARS:
        raise SettingsError("invalid", f"the {name} hold at most {MAX_TEXT_CHARS} characters")
    elif (
        name in ("memory_agent_chars", "memory_user_chars")
        and not MIN_MEMORY_CHARS <= value <= MAX_TEXT_CHARS
    ):
        raise SettingsError("invalid", f"{name} is between {MIN_MEMORY_CHARS} and {MAX_TEXT_CHARS}")
    elif name == "proactive_per_person_per_day" and not 1 <= value <= MAX_PROACTIVE_PER_DAY:
        raise SettingsError("invalid", f"{name} is between 1 and {MAX_PROACTIVE_PER_DAY}")
    elif name in TOKEN_LIMITS and not TOKEN_LIMITS[name][0] <= value <= TOKEN_LIMITS[name][1]:
        low, high = TOKEN_LIMITS[name]
        raise SettingsError("invalid", f"{name} is between {low} and {high}")


def _merged_variables(current: Mapping[str, str], changes: Mapping[str, str | None] | None) -> dict[str, str]:
    if changes is None:
        return {}
    merged = dict(current)
    for name, value in changes.items():
        if not VARIABLE_NAME.match(name):
            raise SettingsError("invalid", f"variable name {name!r}: use a-z, 0-9 and '_'")
        if value is None:
            merged.pop(name, None)
        elif not 0 < len(value) <= MAX_VARIABLE_CHARS:
            raise SettingsError("invalid", f"variable {name}: 1 to {MAX_VARIABLE_CHARS} characters")
        else:
            merged[name] = value
    if len(merged) > MAX_VARIABLES:
        raise SettingsError("invalid", f"at most {MAX_VARIABLES} variables")
    return merged


def _checked_channels(channels: Sequence[str] | None) -> tuple[str, ...]:
    if channels is None:
        return ()
    names = tuple(dict.fromkeys(channels))
    bad = [name for name in names if not valid_channel_name(name)]
    if bad:
        raise SettingsError("invalid", f"channel name {bad[0]!r}: use a-z, 0-9, '_' and '-'")
    if len(names) > MAX_CHANNELS:
        raise SettingsError("invalid", f"at most {MAX_CHANNELS} channels")
    return names

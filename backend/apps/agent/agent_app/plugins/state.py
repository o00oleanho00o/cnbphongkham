"""What an admin decided about each plugin, per (tenant, agent): on or off, its settings (the sensitive ones
encrypted together), where it was installed from and why it was last switched off."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast

from sqlalchemy import text as sql

from agent_app.storage import AgentDatabase, retrying


@dataclass(frozen=True, slots=True)
class PluginState:
    name: str
    enabled: bool = False
    config: Mapping[str, Any] = field(default_factory=dict[str, Any])
    """Plain settings; they override the profile's ``[plugins.<name>]`` key by key."""
    secrets_enc: str | None = None
    """The sensitive settings: one JSON object, encrypted."""
    install: Mapping[str, Any] | None = None
    error: str | None = None


class InMemoryPluginStateStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], PluginState] = {}
        self._changes = 0

    async def list(self, tenant_id: str) -> list[PluginState]:
        return [row for (tenant, _), row in sorted(self._rows.items()) if tenant == tenant_id]

    async def get(self, tenant_id: str, name: str) -> PluginState | None:
        return self._rows.get((tenant_id, name))

    async def save(self, tenant_id: str, state: PluginState) -> None:
        self._rows[(tenant_id, state.name)] = replace(state, config=dict(state.config))
        self._changes += 1

    async def delete(self, tenant_id: str, name: str) -> None:
        if self._rows.pop((tenant_id, name), None) is not None:
            self._changes += 1

    async def fingerprint(self, tenant_id: str) -> str:
        return str(self._changes)


_LIST = sql(
    "SELECT name, enabled, config, secrets_enc, install, last_error FROM agent_rt.agent_plugin "
    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY name"
)
_GET = sql(
    "SELECT name, enabled, config, secrets_enc, install, last_error FROM agent_rt.agent_plugin "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND name = :name"
)
_SAVE = sql(
    "INSERT INTO agent_rt.agent_plugin (tenant_id, agent, name, enabled, config, secrets_enc, install, "
    "last_error) VALUES (:tenant_id, :agent, :name, :enabled, CAST(:config AS jsonb), :secrets_enc, "
    "CAST(:install AS jsonb), :last_error) ON CONFLICT (tenant_id, agent, name) DO UPDATE SET "
    "enabled = EXCLUDED.enabled, config = EXCLUDED.config, secrets_enc = EXCLUDED.secrets_enc, "
    "install = EXCLUDED.install, last_error = EXCLUDED.last_error, updated_at = clock_timestamp()"
)
_DELETE = sql(
    "DELETE FROM agent_rt.agent_plugin WHERE tenant_id = :tenant_id AND agent = :agent AND name = :name"
)
_FINGERPRINT = sql(
    "SELECT count(*) AS n, max(updated_at) AS latest FROM agent_rt.agent_plugin "
    "WHERE tenant_id = :tenant_id AND agent = :agent"
)


class PostgresPluginStateStore:
    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    async def list(self, tenant_id: str) -> list[PluginState]:
        async def work() -> list[PluginState]:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(_LIST, {"tenant_id": tenant_id, "agent": self._agent})).all()
            return [_state(row) for row in rows]

        return await retrying("list plugin states", work)

    async def get(self, tenant_id: str, name: str) -> PluginState | None:
        async def work() -> PluginState | None:
            params = {"tenant_id": tenant_id, "agent": self._agent, "name": name}
            async with self._engine.connect() as conn:
                row = (await conn.execute(_GET, params)).one_or_none()
            return None if row is None else _state(row)

        return await retrying("load plugin state", work)

    async def save(self, tenant_id: str, state: PluginState) -> None:
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            "name": state.name,
            "enabled": state.enabled,
            "config": json.dumps(dict(state.config), ensure_ascii=False),
            "secrets_enc": state.secrets_enc,
            "install": None if state.install is None else json.dumps(dict(state.install), ensure_ascii=False),
            "last_error": state.error,
        }

        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_SAVE, params)

        await retrying("save plugin state", work)

    async def delete(self, tenant_id: str, name: str) -> None:
        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_DELETE, {"tenant_id": tenant_id, "agent": self._agent, "name": name})

        await retrying("delete plugin state", work)

    async def fingerprint(self, tenant_id: str) -> str:
        async def work() -> str:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_FINGERPRINT, {"tenant_id": tenant_id, "agent": self._agent})).one()
            return f"{row.n}:{row.latest.isoformat() if row.latest else ''}"

        return await retrying("plugin state fingerprint", work)


PluginStateStore = InMemoryPluginStateStore | PostgresPluginStateStore


def _state(row: Any) -> PluginState:
    return PluginState(
        name=row.name,
        enabled=row.enabled,
        config=cast(dict[str, Any], row.config),
        secrets_enc=row.secrets_enc,
        install=cast(dict[str, Any] | None, row.install),
        error=row.last_error,
    )

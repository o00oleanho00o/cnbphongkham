"""Where a plugin keeps its own data (accounts, contacts, anything it needs to remember), as JSON values under
string keys, per (tenant, agent, plugin). A plugin sees only its own keys, through ``ctx.storage``; the data
stays when the plugin is disabled and comes back when it is enabled again."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Final, Protocol, cast

from sqlalchemy import text as sql

from agent_app.storage import AgentDatabase, retrying

MAX_KEY_CHARS: Final = 300
MAX_VALUE_BYTES: Final = 256 * 1024
MAX_LIST: Final = 1000


class PluginStorage(Protocol):
    """One plugin's records. Values are anything ``json.dumps`` takes; reading gives back plain JSON."""

    async def get(self, key: str) -> Any | None: ...

    async def put(self, key: str, value: Any) -> None: ...

    async def delete(self, key: str) -> bool: ...

    async def list(self, prefix: str = "", *, limit: int = MAX_LIST) -> list[tuple[str, Any]]:
        """The records whose key starts with ``prefix``, in key order."""
        ...


StorageFor = Callable[[str], PluginStorage]
"""The storage of the plugin with this name."""


def _encoded(key: str, value: Any) -> str:
    _check_key(key)
    if value is None:
        raise ValueError("store a value, not None; delete the key instead")
    data = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if "\\u0000" in data:
        raise ValueError("a stored value may not contain the NUL character")
    if len(data.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError(f"a stored value may have at most {MAX_VALUE_BYTES} bytes as JSON")
    return data


def _check_key(key: str) -> None:
    if not key or len(key) > MAX_KEY_CHARS or "\x00" in key:
        raise ValueError(f"a key has 1 to {MAX_KEY_CHARS} characters and no NUL")


def _limited(limit: int) -> int:
    return max(1, min(limit, MAX_LIST))


class InMemoryPluginRecords:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def storage(self, plugin: str) -> PluginStorage:
        return _MemoryStorage(self._data, plugin)


class _MemoryStorage:
    def __init__(self, data: dict[tuple[str, str], str], plugin: str) -> None:
        self._data = data
        self._plugin = plugin

    async def get(self, key: str) -> Any | None:
        _check_key(key)
        found = self._data.get((self._plugin, key))
        return None if found is None else json.loads(found)

    async def put(self, key: str, value: Any) -> None:
        self._data[(self._plugin, key)] = _encoded(key, value)

    async def delete(self, key: str) -> bool:
        _check_key(key)
        return self._data.pop((self._plugin, key), None) is not None

    async def list(self, prefix: str = "", *, limit: int = MAX_LIST) -> list[tuple[str, Any]]:
        keys = sorted(k for p, k in self._data if p == self._plugin and k.startswith(prefix))
        return [(k, json.loads(self._data[(self._plugin, k)])) for k in keys[: _limited(limit)]]


_GET = sql(
    "SELECT value FROM agent_rt.agent_plugin_record "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND plugin = :plugin AND key = :key"
)
_PUT = sql(
    "INSERT INTO agent_rt.agent_plugin_record (tenant_id, agent, plugin, key, value) "
    "VALUES (:tenant_id, :agent, :plugin, :key, CAST(:value AS jsonb)) "
    "ON CONFLICT (tenant_id, agent, plugin, key) DO UPDATE SET value = EXCLUDED.value, "
    "updated_at = clock_timestamp()"
)
_DELETE = sql(
    "DELETE FROM agent_rt.agent_plugin_record "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND plugin = :plugin AND key = :key RETURNING key"
)
_LIST = sql(
    "SELECT key, value FROM agent_rt.agent_plugin_record "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND plugin = :plugin AND starts_with(key, :prefix) "
    "ORDER BY key LIMIT :limit"
)


class PostgresPluginRecords:
    def __init__(self, db: AgentDatabase, *, agent: str, tenant_id: str) -> None:
        self._db = db
        self._agent = agent
        self._tenant_id = tenant_id

    def storage(self, plugin: str) -> PluginStorage:
        return _PostgresStorage(
            self._db, {"tenant_id": self._tenant_id, "agent": self._agent, "plugin": plugin}
        )


class _PostgresStorage:
    def __init__(self, db: AgentDatabase, scope: dict[str, str]) -> None:
        self._engine = db.engine
        self._scope = scope

    async def get(self, key: str) -> Any | None:
        _check_key(key)

        async def work() -> Any | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_GET, {**self._scope, "key": key})).one_or_none()
            return None if row is None else row.value

        return await retrying("load plugin record", work)

    async def put(self, key: str, value: Any) -> None:
        params = {**self._scope, "key": key, "value": _encoded(key, value)}

        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_PUT, params)

        await retrying("save plugin record", work)

    async def delete(self, key: str) -> bool:
        _check_key(key)

        async def work() -> bool:
            async with self._engine.begin() as conn:
                return (await conn.execute(_DELETE, {**self._scope, "key": key})).first() is not None

        return await retrying("delete plugin record", work)

    async def list(self, prefix: str = "", *, limit: int = MAX_LIST) -> list[tuple[str, Any]]:
        params = {**self._scope, "prefix": prefix, "limit": _limited(limit)}

        async def work() -> list[tuple[str, Any]]:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(_LIST, params)).all()
            return [(cast(str, row.key), row.value) for row in rows]

        return await retrying("list plugin records", work)

"""The models an admin keeps ready: several connections (a provider, a model, an address and its own API key),
of which one is in use. Using one copies its fields into the model settings row (see ``model_settings``), so
the running agent reads one place only; the list is what the admin picks from.

The API key of an entry is stored encrypted like the settings' one, and never leaves the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Protocol

from sqlalchemy import Row
from sqlalchemy import text as sql

from agent_app.model_factory import Provider
from agent_app.storage import AgentDatabase, retrying
from agentcore import ReasoningEffort
from agentcore.harness.model.reasoning import OpenAIDialect

MAX_ENTRIES: Final = 50
"""How many models one agent keeps in its list."""


@dataclass(frozen=True, slots=True)
class ModelEntry:
    id: str
    label: str
    provider: Provider
    model: str
    base_url: str | None = None
    reasoning: ReasoningEffort | None = None
    dialect: OpenAIDialect | None = None
    api_key_enc: str | None = None


class ModelEntryStore(Protocol):
    async def list(self, tenant_id: str) -> list[ModelEntry]: ...

    async def get(self, tenant_id: str, entry_id: str) -> ModelEntry | None: ...

    async def save(self, tenant_id: str, entry: ModelEntry) -> None:
        """Adds the entry or replaces the one with the same id."""
        ...

    async def delete(self, tenant_id: str, entry_id: str) -> bool: ...


class InMemoryModelEntryStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, ModelEntry]] = {}

    async def list(self, tenant_id: str) -> list[ModelEntry]:
        return list(self._rows.get(tenant_id, {}).values())

    async def get(self, tenant_id: str, entry_id: str) -> ModelEntry | None:
        return self._rows.get(tenant_id, {}).get(entry_id)

    async def save(self, tenant_id: str, entry: ModelEntry) -> None:
        self._rows.setdefault(tenant_id, {})[entry.id] = entry

    async def delete(self, tenant_id: str, entry_id: str) -> bool:
        return self._rows.get(tenant_id, {}).pop(entry_id, None) is not None


_LIST = sql(
    "SELECT id, label, provider, model, base_url, reasoning, dialect, api_key_enc "
    "FROM agent_rt.agent_model_entry "
    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY created_at, id"
)
_GET = sql(
    "SELECT id, label, provider, model, base_url, reasoning, dialect, api_key_enc "
    "FROM agent_rt.agent_model_entry "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_SAVE = sql(
    "INSERT INTO agent_rt.agent_model_entry (tenant_id, agent, id, label, provider, model, base_url, "
    "reasoning, dialect, api_key_enc) VALUES (:tenant_id, :agent, :id, :label, :provider, :model, :base_url, "
    ":reasoning, :dialect, :api_key_enc) ON CONFLICT (tenant_id, agent, id) DO UPDATE SET "
    "label = EXCLUDED.label, provider = EXCLUDED.provider, model = EXCLUDED.model, "
    "base_url = EXCLUDED.base_url, reasoning = EXCLUDED.reasoning, dialect = EXCLUDED.dialect, "
    "api_key_enc = EXCLUDED.api_key_enc, updated_at = now()"
)
_DELETE = sql(
    "DELETE FROM agent_rt.agent_model_entry WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)


def _entry(row: Row[Any]) -> ModelEntry:
    return ModelEntry(
        id=row.id,
        label=row.label,
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        reasoning=row.reasoning,
        dialect=row.dialect,
        api_key_enc=row.api_key_enc,
    )


class PostgresModelEntryStore:
    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    async def list(self, tenant_id: str) -> list[ModelEntry]:
        async def work() -> list[ModelEntry]:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(_LIST, {"tenant_id": tenant_id, "agent": self._agent})).all()
            return [_entry(row) for row in rows]

        return await retrying("list models", work)

    async def get(self, tenant_id: str, entry_id: str) -> ModelEntry | None:
        async def work() -> ModelEntry | None:
            async with self._engine.connect() as conn:
                found = await conn.execute(
                    _GET, {"tenant_id": tenant_id, "agent": self._agent, "id": entry_id}
                )
                row = found.one_or_none()
            return None if row is None else _entry(row)

        return await retrying("load a model", work)

    async def save(self, tenant_id: str, entry: ModelEntry) -> None:
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            "id": entry.id,
            "label": entry.label,
            "provider": entry.provider,
            "model": entry.model,
            "base_url": entry.base_url,
            "reasoning": entry.reasoning,
            "dialect": entry.dialect,
            "api_key_enc": entry.api_key_enc,
        }

        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_SAVE, params)

        await retrying("save a model", work)

    async def delete(self, tenant_id: str, entry_id: str) -> bool:
        async def work() -> bool:
            async with self._engine.begin() as conn:
                done = await conn.execute(
                    _DELETE, {"tenant_id": tenant_id, "agent": self._agent, "id": entry_id}
                )
            return done.rowcount > 0

        return await retrying("delete a model", work)

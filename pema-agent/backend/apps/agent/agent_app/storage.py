"""Postgres storage for what the agent writes itself: notes (``agent_rt.agent_memory``) and its own skills
(``agent_rt.agent_skill``). Every statement is parameterised; the schema comes from ``apps/agent/alembic``.

On Windows the async psycopg driver needs a selector event loop (see ``agent_app.cli``).
"""

from __future__ import annotations

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from agentcore.memory import MemoryKey, StoredNotes
from agentcore.skills import Skill


class AgentDatabase:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True, pool_size=5)

    async def dispose(self) -> None:
        await self.engine.dispose()


_LOAD_NOTES = sql(
    "SELECT content, version FROM agent_rt.agent_memory "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND target = :target AND user_id = :user_id"
)
_INSERT_NOTES = sql(
    "INSERT INTO agent_rt.agent_memory (tenant_id, agent, target, user_id, content, version) "
    "VALUES (:tenant_id, :agent, :target, :user_id, :content, 1) ON CONFLICT DO NOTHING"
)
_UPDATE_NOTES = sql(
    "UPDATE agent_rt.agent_memory SET content = :content, version = version + 1, updated_at = now() "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND target = :target AND user_id = :user_id "
    "AND version = :version"
)


def _key_params(key: MemoryKey) -> dict[str, str]:
    return {"tenant_id": key.tenant_id, "agent": key.agent, "target": key.target, "user_id": key.user_id}


class PostgresMemoryBackend:
    def __init__(self, db: AgentDatabase) -> None:
        self._engine = db.engine

    async def load(self, key: MemoryKey) -> StoredNotes:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_LOAD_NOTES, _key_params(key))).one_or_none()
        return StoredNotes() if row is None else StoredNotes(text=row.content, version=row.version)

    async def save(self, key: MemoryKey, text: str, expected_version: int) -> bool:
        params = {**_key_params(key), "content": text, "version": expected_version}
        statement = _INSERT_NOTES if expected_version == 0 else _UPDATE_NOTES
        async with self._engine.begin() as conn:
            result = await conn.execute(statement, params)
        return result.rowcount == 1


class PostgresSkillStore:
    def __init__(self, db: AgentDatabase) -> None:
        self._engine = db.engine

    async def list(self, tenant_id: str, agent: str) -> list[Skill]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sql(
                    "SELECT name, description, body FROM agent_rt.agent_skill "
                    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY name"
                ),
                {"tenant_id": tenant_id, "agent": agent},
            )
            return [Skill(name=r.name, description=r.description, body=r.body) for r in rows]

    async def get(self, tenant_id: str, agent: str, name: str) -> Skill | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    sql(
                        "SELECT name, description, body FROM agent_rt.agent_skill "
                        "WHERE tenant_id = :tenant_id AND agent = :agent AND name = :name"
                    ),
                    {"tenant_id": tenant_id, "agent": agent, "name": name},
                )
            ).one_or_none()
        return None if row is None else Skill(name=row.name, description=row.description, body=row.body)

    async def put(self, tenant_id: str, agent: str, skill: Skill) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                sql(
                    "INSERT INTO agent_rt.agent_skill (tenant_id, agent, name, description, body) "
                    "VALUES (:tenant_id, :agent, :name, :description, :body) "
                    "ON CONFLICT (tenant_id, agent, name) DO UPDATE SET description = EXCLUDED.description, "
                    "body = EXCLUDED.body, version = agent_rt.agent_skill.version + 1, updated_at = now()"
                ),
                {
                    "tenant_id": tenant_id,
                    "agent": agent,
                    "name": skill.name,
                    "description": skill.description,
                    "body": skill.body,
                },
            )

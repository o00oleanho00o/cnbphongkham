# ported from: src/mcp/mcp-agent-binding.ts
"""Binding of MCP servers to agents. An agent with NO bound server gets NOTHING (default CLOSED). Reversing
that would let a new agent use the servers of another by accident. Copy of ``kb-agent-binding.ts`` with the
table and names changed, as the original says.

Forced deviations (SQLite -> Postgres, sync -> async, one tenant -> clinics):

* module-level functions become ``PgMcpPolicyStore`` (implements ``McpPolicyStore`` of the contract plus the
  extra reads the routes and the manager need, ``McpBindingStore``). Names: ``serversCuaAgent`` is
  ``servers_of_agent``, ``agentCuaServer`` is ``agents_of_server`` (contract), ``datServerChoAgent`` is
  ``set_servers_for_agent`` (contract), ``datAgentChoServer`` is ``set_agents_for_server`` (contract),
  ``demAgentTheoServer`` is ``count_agents_by_server`` and ``xoaGanServerCuaAgent`` is ``clear_for_agent``;
* the tables have real foreign keys, so binding an agent or a server that does not exist is a
  ``DomainError(NOT_FOUND)`` instead of an orphan row; deleting an agent cascades (the cleanup that
  ``agent-store.ts`` called ``xoaGanServerCuaAgent`` on delete is done by ``ON DELETE CASCADE``, and
  ``clear_for_agent`` stays for callers that want it explicit);
* ``policy_for_agent`` is the EFFECTIVE permission: raw bindings, then the profile gate
  (``mcp_profile_gate``): an agent whose policy profile may not use MCP gets an empty policy;
* ``McpBindingCache`` is new. ``McpToolProvider.tools_for_agent`` is synchronous (the registry calls it on
  every turn) and the original answered it from SQLite synchronously; async Postgres cannot, so the manager
  keeps this in-memory copy of the bindings, refreshed on every write through the admin API and on the health
  tick. It only decides what goes into the model schema (door 1); the execution re-check (door 2) always asks
  the database.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from pema.core.db import ClinicDatabase
from pema.mcp.mcp_profile_gate import MCP_ALLOWED_PROFILES, mcp_allowed_for_profile
from pema.mcp.mcp_schema import agent_mcp_servers
from pema_contracts.agents import AgentStore
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.mcp import McpPolicy, McpPolicyStore
from pema_contracts.policy import PolicyProfileKey

_NOT_FOUND_MESSAGE = "Agent hoặc server MCP không tồn tại."


class McpBindingStore(McpPolicyStore, Protocol):
    """``McpPolicyStore`` of the contract plus the reads the admin routes and the manager need."""

    async def servers_of_agent(self, clinic_id: UUID, agent_id: str) -> list[str]:
        """RAW bindings (what the admin screen edits), without the profile gate."""
        ...

    async def is_bound(self, clinic_id: UUID, agent_id: str, server_id: str) -> bool: ...

    async def count_agents_by_server(self, clinic_id: UUID) -> dict[str, int]:
        """A server with no agent is ABSENT from the mapping: the caller reads 'no key' as 0."""
        ...

    async def list_all_bindings(self, clinic_id: UUID) -> dict[str, list[str]]:
        """``agent_id -> [server_id]`` for the whole clinic, one query (feeds ``McpBindingCache``)."""
        ...

    async def clear_for_agent(self, clinic_id: UUID, agent_id: str) -> None: ...


class McpBindingCache:
    """In-memory copy of ``agent_mcp_servers`` for the synchronous schema-building door."""

    def __init__(self) -> None:
        self._by_agent: dict[tuple[UUID, str], frozenset[str]] = {}

    def replace_clinic(self, clinic_id: UUID, bindings: Mapping[str, Collection[str]]) -> None:
        """Atomic per clinic: drop the old entries of the clinic, then add the new ones."""
        kept = {k: v for k, v in self._by_agent.items() if k[0] != clinic_id}
        for agent_id, server_ids in bindings.items():
            if server_ids:
                kept[(clinic_id, agent_id)] = frozenset(server_ids)
        self._by_agent = kept

    def is_bound(self, clinic_id: UUID, agent_id: str, server_id: str) -> bool:
        return server_id in self._by_agent.get((clinic_id, agent_id), frozenset())

    def servers_of_agent(self, agent_id: str) -> list[tuple[UUID, str]]:
        """``(clinic_id, server_id)`` of every bound server of ``agent_id`` across clinics."""
        return [
            (clinic_id, server_id)
            for (clinic_id, agent), server_ids in self._by_agent.items()
            if agent == agent_id
            for server_id in sorted(server_ids)
        ]


def _unique(ids: list[str]) -> list[str]:
    """Filter duplicates (``new Set``), keeping the first-seen order."""
    return list(dict.fromkeys(ids))


class PgMcpPolicyStore:
    def __init__(
        self,
        db: ClinicDatabase,
        *,
        agent_store: AgentStore,
        allowed_profiles: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES,
        binding_cache: McpBindingCache | None = None,
    ) -> None:
        self._db = db
        self._agent_store = agent_store
        self._allowed_profiles = allowed_profiles
        self._cache = binding_cache

    async def _refresh_cache(self, clinic_id: UUID) -> None:
        """After a write: the in-memory copy of THIS process follows at once (other processes follow on the
        health tick of their manager)."""
        if self._cache is not None:
            self._cache.replace_clinic(clinic_id, await self.list_all_bindings(clinic_id))

    async def policy_for_agent(self, clinic_id: UUID, agent_id: str) -> McpPolicy:
        """Effective policy. Empty when the agent is unknown or its profile may not use MCP (fail closed)."""
        agent = await self._agent_store.get_agent(clinic_id, agent_id)
        if agent is None or not mcp_allowed_for_profile(agent.policy_profile, self._allowed_profiles):
            return McpPolicy(clinic_id=clinic_id, agent_id=agent_id)
        return McpPolicy(
            clinic_id=clinic_id,
            agent_id=agent_id,
            bound_server_ids=await self.servers_of_agent(clinic_id, agent_id),
        )

    async def servers_of_agent(self, clinic_id: UUID, agent_id: str) -> list[str]:
        async with self._db.session(clinic_id) as session:
            rows = (
                await session.execute(
                    select(agent_mcp_servers.c.server_id)
                    .where(agent_mcp_servers.c.agent_id == agent_id)
                    .order_by(agent_mcp_servers.c.server_id)
                )
            ).scalars()
            return list(rows)

    async def agents_of_server(self, clinic_id: UUID, server_id: str) -> list[str]:
        """The REVERSE direction: which agents a server is bound to (the dashboard asks before deleting)."""
        async with self._db.session(clinic_id) as session:
            rows = (
                await session.execute(
                    select(agent_mcp_servers.c.agent_id)
                    .where(agent_mcp_servers.c.server_id == server_id)
                    .order_by(agent_mcp_servers.c.agent_id)
                )
            ).scalars()
            return list(rows)

    async def is_bound(self, clinic_id: UUID, agent_id: str, server_id: str) -> bool:
        async with self._db.session(clinic_id) as session:
            row = await session.execute(
                select(agent_mcp_servers.c.server_id).where(
                    agent_mcp_servers.c.agent_id == agent_id, agent_mcp_servers.c.server_id == server_id
                )
            )
            return row.first() is not None

    async def set_servers_for_agent(self, clinic_id: UUID, agent_id: str, server_ids: list[str]) -> None:
        """REPLACES the whole list of the agent, never accumulates. One transaction."""
        unique = _unique(server_ids)
        try:
            async with self._db.session(clinic_id) as session:
                await session.execute(
                    delete(agent_mcp_servers).where(agent_mcp_servers.c.agent_id == agent_id)
                )
                if unique:
                    await session.execute(
                        insert(agent_mcp_servers),
                        [{"clinic_id": clinic_id, "agent_id": agent_id, "server_id": s} for s in unique],
                    )
        except IntegrityError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, _NOT_FOUND_MESSAGE) from exc
        await self._refresh_cache(clinic_id)

    async def set_agents_for_server(self, clinic_id: UUID, server_id: str, agent_ids: list[str]) -> None:
        """Reverse of ``set_servers_for_agent``: bind one server to a list of agents (replaces)."""
        unique = _unique(agent_ids)
        try:
            async with self._db.session(clinic_id) as session:
                await session.execute(
                    delete(agent_mcp_servers).where(agent_mcp_servers.c.server_id == server_id)
                )
                if unique:
                    await session.execute(
                        insert(agent_mcp_servers),
                        [{"clinic_id": clinic_id, "agent_id": a, "server_id": server_id} for a in unique],
                    )
        except IntegrityError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, _NOT_FOUND_MESSAGE) from exc
        await self._refresh_cache(clinic_id)

    async def count_agents_by_server(self, clinic_id: UUID) -> dict[str, int]:
        async with self._db.session(clinic_id) as session:
            rows = (
                await session.execute(
                    select(agent_mcp_servers.c.server_id, func.count().label("n")).group_by(
                        agent_mcp_servers.c.server_id
                    )
                )
            ).all()
        return {str(r[0]): int(r[1]) for r in rows}

    async def list_all_bindings(self, clinic_id: UUID) -> dict[str, list[str]]:
        async with self._db.session(clinic_id) as session:
            rows = (
                await session.execute(
                    select(agent_mcp_servers.c.agent_id, agent_mcp_servers.c.server_id).order_by(
                        agent_mcp_servers.c.agent_id, agent_mcp_servers.c.server_id
                    )
                )
            ).all()
        bindings: dict[str, list[str]] = {}
        for agent_id, server_id in rows:
            bindings.setdefault(str(agent_id), []).append(str(server_id))
        return bindings

    async def clear_for_agent(self, clinic_id: UUID, agent_id: str) -> None:
        """Clean all bindings of an agent: call when the agent is DELETED (anti-resurrection of orphan
        rows)."""
        async with self._db.session(clinic_id) as session:
            await session.execute(delete(agent_mcp_servers).where(agent_mcp_servers.c.agent_id == agent_id))
        await self._refresh_cache(clinic_id)

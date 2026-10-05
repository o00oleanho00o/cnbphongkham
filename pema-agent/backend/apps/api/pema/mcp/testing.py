"""Fakes for the MCP module (new, not a port; like ``pema_contracts.testing`` for the contracts).

* ``InMemoryMcpStore``: ``McpServerStore`` + ``McpBindingStore`` over dicts, for the manager and route tests
  (the Postgres stores are covered by the ``db``-marked tests). It mimics the database where behaviour
  matters: deleting a server deletes its bindings, binding an unknown agent or server is ``NOT_FOUND`` (the
  foreign keys), and the profile gate of ``policy_for_agent`` is applied. Headers are kept in plain text in
  memory (this is a fake; the encryption is tested on the Postgres store);
* ``FakeMcpConnection`` / ``FakeConnector``: a connection and a ``connect`` function that never touch the
  network.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from pema.mcp.mcp_agent_binding import McpBindingCache
from pema.mcp.mcp_client_connect import ConnectConfig, McpConnection
from pema.mcp.mcp_profile_gate import MCP_ALLOWED_PROFILES, mcp_allowed_for_profile
from pema.mcp.mcp_types import McpRemoteTool, McpServer, McpServerInternal, McpServerStatus, McpToolInfo
from pema_contracts.agents import AgentStore
from pema_contracts.common import JsonObject
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.mcp import McpPolicy
from pema_contracts.policy import PolicyProfileKey

_NOT_FOUND_MESSAGE = "Agent hoặc server MCP không tồn tại."


@dataclass
class _Row:
    server: McpServer
    headers: dict[str, str]
    fingerprint: str = ""


class InMemoryMcpStore:
    def __init__(
        self,
        *,
        agent_store: AgentStore,
        allowed_profiles: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES,
        binding_cache: McpBindingCache | None = None,
    ) -> None:
        self._agent_store = agent_store
        self._allowed_profiles = allowed_profiles
        self._cache = binding_cache
        self._rows: dict[tuple[UUID, str], _Row] = {}
        self._bindings: set[tuple[UUID, str, str]] = set()
        self.status_log: list[tuple[str, McpServerStatus]] = []
        """Every ``set_status`` call as ``(server_id, status)``, in order (tests read it)."""

    # ------------------------------------------------------------------ servers

    async def create_server(
        self,
        clinic_id: UUID,
        *,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> McpServer:
        now = datetime.now(UTC)
        server = McpServer(
            id=secrets.token_hex(8),
            name=name,
            url=url,
            enabled=enabled,
            status=McpServerStatus.CONNECTING,
            has_headers=bool(headers),
            created_at=now,
            updated_at=now,
        )
        self._rows[(clinic_id, server.id)] = _Row(server=server, headers=dict(headers or {}))
        return server

    async def get_server(self, clinic_id: UUID, server_id: str) -> McpServer | None:
        row = self._rows.get((clinic_id, server_id))
        return row.server if row else None

    async def get_internal(self, clinic_id: UUID, server_id: str) -> McpServerInternal | None:
        row = self._rows.get((clinic_id, server_id))
        return McpServerInternal(clinic_id, row.server, dict(row.headers)) if row else None

    async def list_servers(self, clinic_id: UUID) -> list[McpServer]:
        return [r.server for (c, _), r in self._rows.items() if c == clinic_id]

    async def list_internal(self, clinic_id: UUID) -> list[McpServerInternal]:
        return [
            McpServerInternal(c, r.server, dict(r.headers))
            for (c, _), r in self._rows.items()
            if c == clinic_id
        ]

    def _replace(self, clinic_id: UUID, server_id: str, **changes: object) -> bool:
        row = self._rows.get((clinic_id, server_id))
        if row is None:
            return False
        row.server = row.server.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        return True

    async def update_server(
        self,
        clinic_id: UUID,
        server_id: str,
        *,
        name: str | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> bool:
        row = self._rows.get((clinic_id, server_id))
        if row is None:
            return False
        changes: dict[str, object] = {}
        if name is not None:
            changes["name"] = name
        if url is not None:
            changes["url"] = url
        if enabled is not None:
            changes["enabled"] = enabled
        if headers is not None:
            row.headers = dict(headers)
            changes["has_headers"] = bool(headers)
        return self._replace(clinic_id, server_id, **changes) if changes else True

    async def clear_headers(self, clinic_id: UUID, server_id: str) -> bool:
        row = self._rows.get((clinic_id, server_id))
        if row is None:
            return False
        row.headers = {}
        return self._replace(clinic_id, server_id, has_headers=False)

    async def delete_server(self, clinic_id: UUID, server_id: str) -> bool:
        self._bindings = {b for b in self._bindings if not (b[0] == clinic_id and b[2] == server_id)}
        return self._rows.pop((clinic_id, server_id), None) is not None

    async def set_status(
        self, clinic_id: UUID, server_id: str, status: McpServerStatus, error: str = ""
    ) -> None:
        self.status_log.append((server_id, status))
        self._replace(clinic_id, server_id, status=status, error=error)

    async def save_snapshot_fingerprint(
        self, clinic_id: UUID, server_id: str, snapshot: list[McpToolInfo], fingerprint_json: str
    ) -> None:
        row = self._rows.get((clinic_id, server_id))
        if row is not None:
            row.fingerprint = fingerprint_json
            self._replace(clinic_id, server_id, tools_snapshot=snapshot)

    async def get_fingerprint(self, clinic_id: UUID, server_id: str) -> str:
        row = self._rows.get((clinic_id, server_id))
        return row.fingerprint if row else ""

    # ------------------------------------------------------------------ bindings

    def _sync_cache(self, clinic_id: UUID) -> None:
        if self._cache is not None:
            bindings: dict[str, list[str]] = {}
            for c, agent_id, server_id in sorted(self._bindings):
                if c == clinic_id:
                    bindings.setdefault(agent_id, []).append(server_id)
            self._cache.replace_clinic(clinic_id, bindings)

    async def policy_for_agent(self, clinic_id: UUID, agent_id: str) -> McpPolicy:
        agent = await self._agent_store.get_agent(clinic_id, agent_id)
        if agent is None or not mcp_allowed_for_profile(agent.policy_profile, self._allowed_profiles):
            return McpPolicy(clinic_id=clinic_id, agent_id=agent_id)
        return McpPolicy(
            clinic_id=clinic_id,
            agent_id=agent_id,
            bound_server_ids=await self.servers_of_agent(clinic_id, agent_id),
        )

    async def servers_of_agent(self, clinic_id: UUID, agent_id: str) -> list[str]:
        return sorted(s for c, a, s in self._bindings if c == clinic_id and a == agent_id)

    async def agents_of_server(self, clinic_id: UUID, server_id: str) -> list[str]:
        return sorted(a for c, a, s in self._bindings if c == clinic_id and s == server_id)

    async def is_bound(self, clinic_id: UUID, agent_id: str, server_id: str) -> bool:
        return (clinic_id, agent_id, server_id) in self._bindings

    async def set_servers_for_agent(self, clinic_id: UUID, agent_id: str, server_ids: list[str]) -> None:
        unique = list(dict.fromkeys(server_ids))
        if await self._agent_store.get_agent(clinic_id, agent_id) is None or any(
            (clinic_id, s) not in self._rows for s in unique
        ):
            raise DomainError(ErrorCode.NOT_FOUND, _NOT_FOUND_MESSAGE)
        self._bindings = {b for b in self._bindings if not (b[0] == clinic_id and b[1] == agent_id)}
        self._bindings |= {(clinic_id, agent_id, s) for s in unique}
        self._sync_cache(clinic_id)

    async def set_agents_for_server(self, clinic_id: UUID, server_id: str, agent_ids: list[str]) -> None:
        unique = list(dict.fromkeys(agent_ids))
        known = [await self._agent_store.get_agent(clinic_id, a) for a in unique]
        if (clinic_id, server_id) not in self._rows or any(a is None for a in known):
            raise DomainError(ErrorCode.NOT_FOUND, _NOT_FOUND_MESSAGE)
        self._bindings = {b for b in self._bindings if not (b[0] == clinic_id and b[2] == server_id)}
        self._bindings |= {(clinic_id, a, server_id) for a in unique}
        self._sync_cache(clinic_id)

    async def count_agents_by_server(self, clinic_id: UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c, _, s in self._bindings:
            if c == clinic_id:
                counts[s] = counts.get(s, 0) + 1
        return counts

    async def list_all_bindings(self, clinic_id: UUID) -> dict[str, list[str]]:
        bindings: dict[str, list[str]] = {}
        for c, agent_id, server_id in sorted(self._bindings):
            if c == clinic_id:
                bindings.setdefault(agent_id, []).append(server_id)
        return bindings

    def simulate_binding_written_by_another_process(
        self, clinic_id: UUID, agent_id: str, server_id: str
    ) -> None:
        """A binding appears in the database WITHOUT this process's cache hearing about it."""
        self._bindings.add((clinic_id, agent_id, server_id))

    def simulate_all_bindings_revoked_by_another_process(self) -> None:
        """Every binding vanishes from the database; this process's cache stays stale."""
        self._bindings.clear()

    async def clear_for_agent(self, clinic_id: UUID, agent_id: str) -> None:
        self._bindings = {b for b in self._bindings if not (b[0] == clinic_id and b[1] == agent_id)}
        self._sync_cache(clinic_id)


class FakeMcpConnection:
    """A connection with a fixed tool list that never touches the network."""

    def __init__(
        self,
        tools: Sequence[McpRemoteTool],
        *,
        call_result: object = "ok",
        call: Callable[[str, JsonObject], Awaitable[object]] | None = None,
        hang_on_list_tools: bool = False,
    ) -> None:
        self._tools = list(tools)
        self._call_result = call_result
        self._call = call
        self._hang_on_list_tools = hang_on_list_tools
        self.closed = False
        self.calls: list[tuple[str, JsonObject]] = []

    async def list_tools(self) -> list[McpRemoteTool]:
        if self._hang_on_list_tools:
            await asyncio.Event().wait()
        return list(self._tools)

    async def call_tool(self, name: str, args: JsonObject) -> object:
        self.calls.append((name, args))
        if self._call is not None:
            return await self._call(name, args)
        return self._call_result

    async def close(self) -> None:
        self.closed = True


def remote_tools(*names: str) -> list[McpRemoteTool]:
    """Tools with a description ``mô tả <name>`` and an empty object schema."""
    return [McpRemoteTool(name=n, description=f"mô tả {n}") for n in names]


@dataclass
class FakeConnector:
    """A ``connect`` function (``ConnectFn``): hands out ``FakeMcpConnection``s and records every attempt."""

    tools: list[McpRemoteTool] = field(default_factory=list[McpRemoteTool])
    fail_urls_containing: str | None = None
    connections: list[FakeMcpConnection] = field(default_factory=list[FakeMcpConnection])
    configs: list[ConnectConfig] = field(default_factory=list[ConnectConfig])
    connection_kwargs: dict[str, object] = field(default_factory=dict[str, object])

    async def __call__(self, cfg: ConnectConfig) -> McpConnection:
        self.configs.append(cfg)
        await asyncio.sleep(0)  # a handshake is a network round trip: other tasks run meanwhile
        if self.fail_urls_containing is not None and self.fail_urls_containing in cfg.url:
            raise ConnectionError("chết")
        connection = FakeMcpConnection(self.tools, **self.connection_kwargs)  # type: ignore[arg-type]
        self.connections.append(connection)
        return connection

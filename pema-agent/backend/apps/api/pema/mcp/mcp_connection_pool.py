# ported from: src/mcp/mcp-connection-pool.ts
"""MCP connection pool: the ONLY place that holds live clients (a dict in RAM) plus the function that connects
a server, discovers its tools, checks drift and builds the ``ToolSpec``s. Split from ``mcp_manager`` (which
keeps the re-entrancy latch and the health loop). Boundary: this file knows nothing about the latch, only
"connect one server" and "which connections exist"; ``mcp_manager`` decides WHEN to connect or disconnect and
loops the health.

``tool_specs_for_agent`` (the registry reads it every turn) only reads the dict ``connected`` and the binding
cache: SYNCHRONOUS, no network, no database, so it is safely empty when the manager has not started (for
example another test imports the registry without needing MCP).

The dependency direction is deliberately one way: this file imports the store, the binding and the tool
definition, it NEVER imports the tool registry. The registry is the caller of the provider; the reverse import
would create a cycle.

Forced deviations (sync -> async, one tenant -> clinics, ``ai`` SDK -> ``mcp`` SDK):

* the module-level ``dangNoi`` Map becomes the instance attribute ``connected`` keyed by ``(clinic_id,
  server_id)``. Being an instance, a test builds a fresh pool and ``resetPoolChoTest`` is not needed;
  ``datKetNoiServerChoTest`` is the ``connect`` constructor argument;
* ``nap`` is ``connect_and_load``; ``ngatServer`` is ``disconnect``; ``dongTatCaKetNoi`` is ``close_all``
  (awaited: Python can wait for the close, JS fired ``void``); ``mcpToolDefinitions`` is
  ``tool_specs_for_agent``; ``trangThaiCacServer`` is ``runtime_status``;
* the original gated ``MCP_ENABLED`` in ``mcpToolDefinitions`` (read by the registry every turn) and NOT only
  at boot, so a kill switch flipped on the dashboard while connections are open blocks at once. Kept;
* ``tool_specs_for_agent(agent_id)`` has no clinic argument (contract: ``McpToolProvider``). Single tenant:
  one installation is one clinic, so an agent id is unambiguous and there is no ``..._in_clinic`` variant and
  no "bound in several clinics" fail-closed branch any more (both existed only because two clinics could
  share an agent id). The execution re-check (door 2) still checks the binding with the clinic of the turn;
* ``config_stamp`` is new: a hash of the url and headers a connection was opened with, so the health sync can
  see that another process changed them (the admin API and the worker are different processes).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from pema.agent.tools.tool_failure_result import ket_qua_loi as tool_failure_result
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tuning_settings import get_tuning_bool, get_tuning_int
from pema.mcp.mcp_agent_binding import McpBindingCache, McpBindingStore
from pema.mcp.mcp_client_connect import ConnectConfig, ConnectFn, McpConnection, connect_server
from pema.mcp.mcp_profile_gate import MCP_ALLOWED_PROFILES
from pema.mcp.mcp_server_store import McpServerStore
from pema.mcp.mcp_tool_definition import (
    FailFn,
    WrapFn,
    call_with_timeout,
    create_mcp_tool_spec,
)
from pema.mcp.mcp_tool_drift import compare_with_baseline, snapshot_fingerprint
from pema.mcp.mcp_types import (
    McpRemoteTool,
    McpRuntimeStatus,
    McpServerInternal,
    McpServerStatus,
    McpToolInfo,
)
from pema.shared.logger import create_logger
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import ToolSpec

_log = create_logger("mcp.pool")

type ServerKey = tuple[UUID, str]


@dataclass
class ConnectedServer:
    """``ServerDangNoi``: a live connection and the specs built from it."""

    connection: McpConnection
    specs: list[ToolSpec]
    config_stamp: str


def config_stamp(server: McpServerInternal) -> str:
    """Identity of what a connection was opened with. A hash, so no header value is kept in this field."""
    material = json.dumps(
        {"url": server.server.url, "headers": sorted(server.headers.items())}, ensure_ascii=False
    )
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()


def _safe_description(description: str | None) -> str:
    """``moTaAnToan``: the MCP ``tools/list`` description is a plain string; anything else becomes empty."""
    return description if isinstance(description, str) else ""


class McpConnectionPool:
    def __init__(
        self,
        *,
        server_store: McpServerStore,
        binding_store: McpBindingStore,
        bindings: McpBindingCache,
        connect: ConnectFn = connect_server,
        wrap: WrapFn = wrap_untrusted_content,
        fail: FailFn = tool_failure_result,
        allowed_profiles: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES,
    ) -> None:
        self._servers = server_store
        self._binding_store = binding_store
        self._bindings = bindings
        self._connect = connect
        self._wrap = wrap
        self._fail = fail
        self._allowed_profiles = allowed_profiles
        self.connected: dict[ServerKey, ConnectedServer] = {}

    def tool_specs_for_agent(self, agent_id: str) -> list[ToolSpec]:
        """``mcpToolDefinitions``: tools of servers that are CONNECTED (in ``connected``) AND BOUND to this
        agent.

        The ``MCP_ENABLED`` gate is HERE, not only at ``start()``: the registry calls this EVERY turn and it
        reads the RAM cache. Turning the switch off from the dashboard while the manager is RUNNING
        (connections already open) must block AT ONCE; without the gate here the kill switch would only work
        at boot, which is useless between two restarts for exactly what it exists to stop."""
        if not get_tuning_bool("MCP_ENABLED"):
            return []
        wanted = set(self._bindings.servers_of_agent(agent_id))
        specs: list[ToolSpec] = []
        for key, server in self.connected.items():
            if key in wanted:
                specs.extend(server.specs)
        return specs

    async def runtime_status(self, clinic_id: UUID) -> list[McpRuntimeStatus]:
        """For the dashboard: every server in the database (also not connected / failed), with the number of
        tools currently cached."""
        servers = await self._servers.list_servers(clinic_id)
        return [
            McpRuntimeStatus(
                server_id=s.id,
                status=s.status,
                tool_count=len(self.connected[(clinic_id, s.id)].specs)
                if (clinic_id, s.id) in self.connected
                else 0,
                error=s.error,
            )
            for s in servers
        ]

    async def connect_and_load(self, clinic_id: UUID, server_id: str, *, save_baseline: bool) -> None:
        """``nap``: connect + discover tools + check drift + build the ``ToolSpec``s, then load the cache.

        ``save_baseline=True`` (only from ``reapprove_drift``) SKIPS the drift check and ALWAYS overwrites the
        baseline with the current tool set: the semantics of "the operator just looked at the new set and
        approved it". ``save_baseline=False`` (an ordinary reconnect) compares with the baseline; if the
        server has NEVER had one (first time) it must still be saved, otherwise every later time would be "no
        baseline" and drift could never be caught."""
        internal = await self._servers.get_internal(clinic_id, server_id)
        if internal is None:
            return
        # A DISABLED server: the callers (``reconnect_server`` / ``reapprove_drift``) always ``disconnect``
        # BEFORE calling this, and ``disconnect`` does not change ``status``; without this guard a PATCH that
        # disables a running server would RECONNECT it exactly as when enabled (the "disconnect then
        # reconnect" bug), and a server created ``enabled: false`` would also connect at once. Reset to
        # ``cho_ket_noi`` so the dashboard does not show "connected" for a server just disconnected and left
        # disconnected.
        if not internal.server.enabled:
            await self._servers.set_status(clinic_id, server_id, McpServerStatus.CONNECTING)
            return
        connection = await self._connect(
            ConnectConfig(
                url=internal.server.url,
                headers=internal.headers,
                connect_timeout_ms=get_tuning_int("MCP_CONNECT_TIMEOUT_MS"),
            )
        )
        try:
            # ``connect`` only wraps the ceiling around the HANDSHAKE. Discovering tools (``list_tools()``,
            # the ``tools/list`` request) is a separate network round trip after that, outside that ceiling.
            # Without a ceiling here a server that passes the handshake and then hangs on listing keeps this
            # call alive for ever; since the status would not change, every health tick would call this again,
            # leaking connections cumulatively.
            tools = await call_with_timeout(connection.list_tools, get_tuning_int("MCP_CONNECT_TIMEOUT_MS"))
            baseline = await self._servers.get_fingerprint(clinic_id, server_id)
            if not save_baseline:
                result = compare_with_baseline(tools, baseline)
                if result.drift:
                    await connection.close()
                    counts = f"thêm {len(result.added)}, đổi {len(result.changed)}, bỏ {len(result.removed)}"
                    await self._servers.set_status(
                        clinic_id, server_id, McpServerStatus.NEEDS_REAPPROVAL, f"Bộ tool đổi ({counts})"
                    )
                    return
            specs = self._build_specs(clinic_id, internal, connection, tools)
            if save_baseline or baseline == "":
                snapshot = [
                    McpToolInfo(name=t.name, description=_safe_description(t.description)) for t in tools
                ]
                await self._servers.save_snapshot_fingerprint(
                    clinic_id, server_id, snapshot, snapshot_fingerprint(tools)
                )
            # Defence the original did not need (its callers always disconnect first): never overwrite a live
            # handle without closing it.
            await self.disconnect(clinic_id, server_id)
            self.connected[(clinic_id, server_id)] = ConnectedServer(
                connection=connection, specs=specs, config_stamp=config_stamp(internal)
            )
            await self._servers.set_status(clinic_id, server_id, McpServerStatus.CONNECTED)
        except BaseException:
            # ANY error AFTER we hold a handle (including a ``list_tools`` timeout) must close it before
            # re-raising, otherwise ``connected`` (the only place ``disconnect`` knows to close later) never
            # saw this handle: a permanent leak.
            try:
                await connection.close()
            except Exception:  # closing a failed connection is not something the caller needs to handle
                _log.warning("closing a failed mcp connection raised", server_id=server_id)
            raise

    def _build_specs(
        self,
        clinic_id: UUID,
        internal: McpServerInternal,
        connection: McpConnection,
        tools: list[McpRemoteTool],
    ) -> list[ToolSpec]:
        server_id = internal.server.id
        tool_timeout_ms = get_tuning_int("MCP_TOOL_TIMEOUT_MS")

        def is_granted(agent_id: str) -> bool:
            return self._bindings.is_bound(clinic_id, agent_id, server_id)

        async def confirm_grant(agent_id: str) -> bool:
            return await self._binding_store.is_bound(clinic_id, agent_id, server_id)

        return [
            create_mcp_tool_spec(
                clinic_id=clinic_id,
                server_id=server_id,
                server_name=internal.server.name,
                tool_name=tool.name,
                description=_safe_description(tool.description),
                input_schema=tool.input_schema,
                call_tool=connection.call_tool,
                tool_call_timeout_ms=tool_timeout_ms,
                is_granted=is_granted,
                confirm_grant=confirm_grant,
                allowed_profiles=self._allowed_profiles,
                wrap=self._wrap,
                fail=self._fail,
            )
            for tool in tools
        ]

    async def disconnect(self, clinic_id: UUID, server_id: str) -> None:
        """``ngatServer``: close the client and drop it from the cache (call when a server is deleted or
        disabled, or before reconnecting)."""
        server = self.connected.pop((clinic_id, server_id), None)
        if server is None:
            return
        try:
            await server.connection.close()
        except Exception:  # a failing close is not something the caller needs to handle
            _log.warning("closing an mcp connection raised", server_id=server_id)

    async def close_all(self) -> None:
        """``dongTatCaKetNoi``: close EVERY open connection (shutdown)."""
        for clinic_id, server_id in list(self.connected):
            await self.disconnect(clinic_id, server_id)

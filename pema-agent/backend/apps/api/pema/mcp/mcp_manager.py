# ported from: src/mcp/mcp-manager.ts
"""The public FRONT of the MCP module: holds the re-entrancy latch ``connecting`` and the boot/health loop.
The real connections (the dict ``connected``, ``connect_and_load`` / ``disconnect``) live in
``mcp_connection_pool``, split so both files stay under 200 lines; the boundary is "knows WHEN to call
connect" (here) versus "knows HOW to connect one server" (the pool). To the outside the MCP module is still
ONE front.

Implements ``McpManager`` of the contract (``reconnect_server`` = ``ketNoiLaiServer``, ``reapprove_drift`` =
``duyetLaiDrift``, ``tools_for_agent`` = ``mcpToolDefinitions``).

Forced deviations (sync -> async, one process -> API + worker; single tenant: one installation is one clinic,
``clinic_ids`` is kept only so callers written for the multi-clinic version still work, and defaults to the
installation clinic):

* ``startMcpManager()`` returned a stop function; here ``await manager.start()`` / ``await manager.stop()``.
  ``start`` registers the manager as the source of the process-wide ``mcp_tool_provider``
  (``datNguonToolMcp``) BEFORE connecting, so there is no gap between "manager is on" and "registry still sees
  the empty default";
* the original ran in one process, so a PATCH on the dashboard and the agent turn shared the same ``dangNoi``.
  Here the admin API (process ``api``) and the turns (process ``worker``) are different processes: each has
  its own manager and its own connections, and the DATABASE is what they share. The health tick therefore also
  runs ``sync_once``: it reloads the bindings, connects an enabled server that is not connected here (also one
  that another process just created or re-approved), drops a connection whose server was disabled, deleted,
  changed (url or headers) or sent to ``can_duyet_lai`` elsewhere. The original health only retried ``loi``;
* the latch ``dangNap`` is keyed by ``(clinic_id, server_id)``;
* a ``Set`` of tasks keeps the background connects alive (an asyncio task with no reference can be collected).

Kept: a failing server never blocks another (each call catches its own error into ``loi``); health retries
only ``loi`` servers; a ``can_duyet_lai`` server is NEVER reconnected by itself, it waits for
``reapprove_drift``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Collection, Sequence
from uuid import UUID

from pema.agent.tools.tool_failure_result import ket_qua_loi as tool_failure_result
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tuning_settings import get_tuning_bool, get_tuning_int
from pema.mcp.mcp_agent_binding import McpBindingCache, McpBindingStore
from pema.mcp.mcp_client_connect import ConnectFn, connect_server, describe_error
from pema.mcp.mcp_connection_pool import McpConnectionPool, config_stamp
from pema.mcp.mcp_profile_gate import MCP_ALLOWED_PROFILES
from pema.mcp.mcp_server_store import McpServerStore
from pema.mcp.mcp_tool_definition import FailFn, WrapFn
from pema.mcp.mcp_tool_provider import SwitchableMcpToolProvider, mcp_tool_provider
from pema.mcp.mcp_types import McpRuntimeStatus, McpServerStatus
from pema.shared.logger import create_logger
from pema_contracts.installation import installation_clinic_id
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import ToolSpec

_log = create_logger("mcp.manager")


class DefaultMcpManager:
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
        provider: SwitchableMcpToolProvider = mcp_tool_provider,
    ) -> None:
        self._servers = server_store
        self._binding_store = binding_store
        self._bindings = bindings
        self._provider = provider
        self._pool = McpConnectionPool(
            server_store=server_store,
            binding_store=binding_store,
            bindings=bindings,
            connect=connect,
            wrap=wrap,
            fail=fail,
            allowed_profiles=allowed_profiles,
        )
        self._connecting: set[tuple[UUID, str]] = set()
        """``dangNap``: re-entrancy latch SHARED by ``reconnect_server`` AND ``reapprove_drift``."""
        self._tasks: set[asyncio.Task[None]] = set()
        self._loop_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ reads

    def tools_for_agent(self, agent_id: str) -> Sequence[ToolSpec]:
        """``mcpToolDefinitions`` (``McpToolProvider``): synchronous, never raises."""
        try:
            return self._pool.tool_specs_for_agent(agent_id)
        except Exception as exc:  # contract: never raises
            _log.error("mcp tool lookup failed", err=exc, agent_id=agent_id)
            return []

    def connected_server_ids(self, clinic_id: UUID) -> set[str]:
        """Servers of the clinic this process holds a live connection to."""
        return {server_id for clinic, server_id in self._pool.connected if clinic == clinic_id}

    async def runtime_status(self, clinic_id: UUID) -> list[McpRuntimeStatus]:
        """``trangThaiCacServer``."""
        return await self._pool.runtime_status(clinic_id)

    async def refresh_bindings(self, clinic_id: UUID) -> None:
        """Reload the in-memory copy of the bindings of a clinic (the schema door reads it synchronously)."""
        self._bindings.replace_clinic(clinic_id, await self._binding_store.list_all_bindings(clinic_id))

    # ------------------------------------------------------------------ connect, disconnect, re-approve

    async def disconnect_server(self, clinic_id: UUID, server_id: str) -> None:
        """``ngatServer`` (re-exported by the original front)."""
        await self._pool.disconnect(clinic_id, server_id)

    async def _reconnect(self, clinic_id: UUID, server_id: str, *, save_baseline: bool) -> None:
        key = (clinic_id, server_id)
        if key in self._connecting:
            return
        self._connecting.add(key)
        try:
            await self._pool.disconnect(clinic_id, server_id)
            try:
                await self._pool.connect_and_load(clinic_id, server_id, save_baseline=save_baseline)
            except Exception as exc:
                await self._servers.set_status(
                    clinic_id, server_id, McpServerStatus.ERROR, describe_error(exc)
                )
        finally:
            self._connecting.discard(key)

    async def reconnect_server(self, clinic_id: UUID, server_id: str) -> None:
        """``ketNoiLaiServer``: (re)connect one server: close the old handle (if any) then connect from the
        start.
        A failure goes to ``loi``, it is NOT raised.

        Blocks RE-ENTRY through ``connecting``: the health tick (every ``MCP_HEALTH_INTERVAL_MS``) targets
        ``loi`` servers. A ``connect_and_load`` still RUNNING (it has not yet changed the status) would match
        that condition again at the next tick; without the latch every tick would stack another parallel
        connect on the SAME server, opening one more handle that ``disconnect`` (run before EACH call) cannot
        close because it never reached ``connected``."""
        await self._reconnect(clinic_id, server_id, save_baseline=False)

    async def reapprove_drift(self, clinic_id: UUID, server_id: str) -> None:
        """``duyetLaiDrift``: the operator looked at the changed tool set and agreed: take the CURRENT set as
        the
        new baseline, then load it.

        Uses the SAME latch as ``reconnect_server`` (not a separate set): both call ``connect_and_load`` on
        the SAME server, so they must exclude each other whichever path they come from; two sets would be two
        locks for one resource and would not stop a race between them. The real case the latch stops: the
        operator clicks "Re-approve" twice in a row (double click) before the first call changed the status.
        It is NOT the health tick: the health loop only targets ``loi`` servers, never ``can_duyet_lai``."""
        await self._reconnect(clinic_id, server_id, save_baseline=True)

    # ------------------------------------------------------------------ boot and health

    def _spawn(self, work: Awaitable[None]) -> None:
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def boot(self) -> None:
        """Connect every ``enabled`` server of the installation. One broken server blocks neither another nor
        the boot, because each call catches its own error."""
        try:
            await self._boot_clinic(installation_clinic_id())
        except Exception as exc:
            _log.error("mcp boot of the clinic failed", err=exc)

    async def _boot_clinic(self, clinic_id: UUID) -> None:
        await self.refresh_bindings(clinic_id)
        servers = await self._servers.list_servers(clinic_id)
        await asyncio.gather(*(self.reconnect_server(clinic_id, s.id) for s in servers if s.enabled))

    async def sync_once(self) -> None:
        """One health tick (see the module docstring for why it does more than the original's ``loi``
        retry)."""
        try:
            await self._sync_clinic(installation_clinic_id())
        except Exception as exc:
            _log.error("mcp health sync of the clinic failed", err=exc)

    async def _sync_clinic(self, clinic_id: UUID) -> None:
        await self.refresh_bindings(clinic_id)
        servers = await self._servers.list_internal(clinic_id)
        present = {s.server.id for s in servers}
        for key in [k for k in self._pool.connected if k[0] == clinic_id and k[1] not in present]:
            await self._pool.disconnect(*key)
        for internal in servers:
            server = internal.server
            live = self._pool.connected.get((clinic_id, server.id))
            if live is not None:
                gone = (
                    not server.enabled
                    or server.status is McpServerStatus.NEEDS_REAPPROVAL
                    or live.config_stamp != config_stamp(internal)
                )
                if not gone:
                    continue
                await self._pool.disconnect(clinic_id, server.id)
            if server.enabled and server.status is not McpServerStatus.NEEDS_REAPPROVAL:
                self._spawn(self.reconnect_server(clinic_id, server.id))

    async def start(self) -> None:
        """``startMcpManager``: a no-op when ``MCP_ENABLED`` is off. Registers the tool source NOW, before the
        connect loop, so the registry (through the pure provider layer) reads this pool's cache with no
        gap."""
        if not get_tuning_bool("MCP_ENABLED") or self._loop_task is not None:
            return
        self._provider.set_source(self.tools_for_agent)
        self._loop_task = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        await self.boot()
        while True:
            await asyncio.sleep(get_tuning_int("MCP_HEALTH_INTERVAL_MS") / 1000)
            await self.sync_once()

    async def stop(self) -> None:
        """The stop function of ``startMcpManager``: stop the loop and close every connection."""
        loop_task, self._loop_task = self._loop_task, None
        if loop_task is not None:
            loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await loop_task
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._pool.close_all()
        self._provider.set_source(None)

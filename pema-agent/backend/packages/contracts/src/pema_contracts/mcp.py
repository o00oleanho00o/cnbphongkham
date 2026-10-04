"""MCP client contract (package D5 implements; the tool registry (D4) and the admin API use it).

Port of src/mcp: ``McpServer`` / ``McpServerView`` (mcp-types.ts), agent binding
(mcp-agent-binding.ts) and tool drift (mcp-tool-drift.ts). Transport is HTTP (streamable). Tables:
``agent.mcp_servers`` and ``agent.agent_mcp_servers``.

Normative rules kept from the original:

* PER-AGENT DEFAULT-DENY: an agent sees the tools of a server only when the server is bound to it
  (``McpPolicy.bound_server_ids``). New agents start with no server.
* FINGERPRINT DRIFT: the tool list of a server is fingerprinted when approved; if the server later
  changes a tool name or description the server goes to ``can_duyet_lai`` (needs re-approval) and its
  tools are withheld until a human approves again (``POST /admin/mcp/servers/{id}/reapprove``).
* Headers (often bearer tokens) are encrypted at rest and write-only: DTOs carry ``has_headers`` only.
* MCP tools inherit every registry filter (agent, account, channel, policy profile). They are group
  ``action`` and ``runs_in_scheduled_turn=False`` (mcp-tool-definition.ts); their output is wrapped as
  untrusted content and every failure is a tool-failure result, never an exception.
* The model-facing tool name is ``mcp__<server slug>__<tool>`` (``tenToolMcp``), capped at 64 chars with
  a sha256 suffix on any lossy normalisation.

Status values are the original Vietnamese ones: ``cho_ket_noi`` connecting, ``da_ket_noi`` connected,
``loi`` error, ``can_duyet_lai`` needs re-approval.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.tools import McpToolProvider


class McpServerStatus(StrEnum):
    CONNECTING = "cho_ket_noi"
    CONNECTED = "da_ket_noi"
    ERROR = "loi"
    NEEDS_REAPPROVAL = "can_duyet_lai"


class McpToolInfo(ApiModel):
    name: str = Field(description="``ten``")
    description: str = Field(default="", description="``moTa``")


class McpServer(ApiModel):
    id: str
    name: str = Field(description="``ten``")
    url: str
    enabled: bool = True
    status: McpServerStatus = Field(description="``trangThai``")
    error: str = Field(default="", description="``loi``")
    tools_snapshot: list[McpToolInfo] = Field(default_factory=list[McpToolInfo])
    has_headers: bool = False
    created_at: VnDatetime
    updated_at: VnDatetime


class McpServerView(McpServer):
    """What the admin API returns: adds the number of agents bound to the server."""

    bound_agent_count: int = Field(default=0, description="``soAgentGan``")


class McpPolicy(ApiModel):
    """Effective MCP permission of ONE agent. Default-deny: an empty ``bound_server_ids`` means none."""

    clinic_id: UUID
    agent_id: str
    bound_server_ids: list[str] = Field(default_factory=list[str])
    default_deny: bool = Field(default=True, description="Always true; present so a reader sees the rule.")


class McpPolicyStore(Protocol):
    async def policy_for_agent(self, clinic_id: UUID, agent_id: str) -> McpPolicy: ...

    async def set_servers_for_agent(self, clinic_id: UUID, agent_id: str, server_ids: list[str]) -> None: ...

    async def set_agents_for_server(self, clinic_id: UUID, server_id: str, agent_ids: list[str]) -> None: ...

    async def agents_of_server(self, clinic_id: UUID, server_id: str) -> list[str]: ...


class McpManager(McpToolProvider, Protocol):
    """Connection pool + registry. ``tools_for_agent`` (from ``McpToolProvider``) is sync and never
    raises: it reads the in-memory snapshot of connected, approved, bound servers."""

    async def reconnect_server(self, clinic_id: UUID, server_id: str) -> None: ...

    async def reapprove_drift(self, clinic_id: UUID, server_id: str) -> None: ...

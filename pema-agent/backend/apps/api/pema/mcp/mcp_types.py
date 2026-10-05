# ported from: src/mcp/mcp-types.ts
"""Shared types of the MCP client module, kept in their own file to avoid import cycles: the store, the
manager and the admin routes all need these types but must not pull in the database or the client.

The public DTOs (``McpServer``, ``McpServerView``, ``McpToolInfo``, the status enum) live in
``pema_contracts.mcp`` (contract of package A) and are re-exported here under the names of the original
(``TrangThaiServer`` is ``McpServerStatus``).

Forced deviations:

* ``McpServerNoiBo`` (a server WITH decrypted headers) becomes the dataclass ``McpServerInternal``. It wraps
  the public ``McpServer`` instead of extending it and hides ``headers`` from ``repr``, so a traceback or a
  log line never prints a bearer token.
* every row carries ``clinic_id`` (tenant). The original had one SQLite file and no tenants.
* ``McpRemoteTool`` is new. The Vercel AI SDK handed the original a ready-made ``Tool`` (schema + executor);
  the Python ``mcp`` SDK hands back plain ``Tool`` metadata, so the module keeps it in this small value
  object and calls the server through ``McpConnection.call_tool``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pema_contracts.common import JsonObject
from pema_contracts.mcp import McpServer, McpServerStatus, McpServerView, McpToolInfo

__all__ = [
    "McpRemoteTool",
    "McpRuntimeStatus",
    "McpServer",
    "McpServerInternal",
    "McpServerStatus",
    "McpServerView",
    "McpToolInfo",
]


@dataclass(frozen=True)
class McpRemoteTool:
    """One tool as declared by an external MCP server (``tools/list``): what is shown on the dashboard and
    what the drift fingerprint covers (description, input schema, title)."""

    name: str
    description: str = ""
    title: str | None = None
    input_schema: JsonObject = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True)
class McpServerInternal:
    """``McpServerNoiBo``: a server WITH its decrypted headers. Internal use only (the manager connects with
    it); never returned by the API."""

    clinic_id: UUID
    server: McpServer
    headers: dict[str, str] = field(default_factory=dict[str, str], repr=False)


@dataclass(frozen=True)
class McpRuntimeStatus:
    """One row of ``trangThaiCacServer``: the state of every server in the database (also the ones that are
    not connected or failed) plus the number of tools currently cached in memory."""

    server_id: str
    status: McpServerStatus
    tool_count: int
    error: str

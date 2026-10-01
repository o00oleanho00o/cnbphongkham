"""MCP servers and per-agent bindings (package D5 implements). Port of mcp-routes.ts.

Headers are write-only. A server whose tool fingerprint drifted is ``can_duyet_lai`` and its tools stay
withheld until ``reapprove``. Bindings are default-deny.
"""

from __future__ import annotations

from fastapi import status

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import IdList, McpServerCreate, McpServerUpdate
from pema_contracts.mcp import McpServerView

router = admin_router("mcp", "admin-mcp")


@router.get("/servers", response_model=list[McpServerView], summary="MCP servers with state")
async def list_mcp_servers() -> list[McpServerView]:
    not_implemented()


@router.post(
    "/servers", response_model=McpServerView, status_code=status.HTTP_201_CREATED, summary="Add a server"
)
async def create_mcp_server(body: McpServerCreate) -> McpServerView:
    not_implemented()


@router.patch("/servers/{server_id}", response_model=McpServerView, summary="Update a server")
async def update_mcp_server(server_id: str, body: McpServerUpdate) -> McpServerView:
    not_implemented()


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a server")
async def delete_mcp_server(server_id: str) -> None:
    not_implemented()


@router.delete(
    "/servers/{server_id}/headers", status_code=status.HTTP_204_NO_CONTENT, summary="Remove stored headers"
)
async def clear_mcp_server_headers(server_id: str) -> None:
    not_implemented()


@router.post(
    "/servers/{server_id}/reapprove",
    response_model=McpServerView,
    summary="Accept the drifted tool list (re-approval)",
)
async def reapprove_mcp_server(server_id: str) -> McpServerView:
    not_implemented()


@router.get("/servers/{server_id}/agents", response_model=IdList, summary="Agents bound to a server")
async def get_agents_of_mcp_server(server_id: str) -> IdList:
    not_implemented()


@router.put("/servers/{server_id}/agents", response_model=IdList, summary="Set the agents of a server")
async def set_agents_of_mcp_server(server_id: str, body: IdList) -> IdList:
    not_implemented()


@router.get("/agents/{agent_id}/servers", response_model=IdList, summary="Servers bound to an agent")
async def get_mcp_servers_of_agent(agent_id: str) -> IdList:
    not_implemented()


@router.put("/agents/{agent_id}/servers", response_model=IdList, summary="Set the servers of an agent")
async def set_mcp_servers_of_agent(agent_id: str, body: IdList) -> IdList:
    not_implemented()

# ported from: src/server/routes/mcp-routes.ts
"""MCP servers and per-agent bindings (package D5). Port of ``mcp-routes.ts``: CRUD of external MCP servers,
the
binding to agents and the connection state.

Headers are write-only. A server whose tool fingerprint drifted is ``can_duyet_lai`` and its tools stay
withheld until ``reapprove``. Bindings are default-deny.

The routes are thin: the stores and the manager come from ``McpAdminContext`` (``mcp_route_guards``), the
route only validates, calls and shapes the answer, as the original did with its ``deps.manager``.

Forced deviations (Hono -> FastAPI, one tenant -> clinics):

* paths follow the OpenAPI skeleton of package A: ``duyet-lai`` is ``reapprove`` and removing and binding
  answer ``204`` or an ``IdList``; the dashboard ``GET /agents`` (agent list) is served by ``admin_agents``
  (D2);
* "connect in the background, do not block the response" (``void deps.manager.ketNoiLaiServer``) becomes a
  FastAPI ``BackgroundTasks`` job that runs after the response is sent;
* an id that does not exist is ``404``: the original answered ``{ok: true}`` for ``PATCH`` / ``DELETE`` on an
  unknown id;
* after ``DELETE /servers/{id}/headers`` the server is reconnected in the background, so a connection opened
  with the removed token does not stay alive (the original did not reconnect, and the health tick that notices
  a changed header only exists since the API and the worker are separate processes).
"""

from __future__ import annotations

from fastapi import BackgroundTasks, status

from pema.api.deps import admin_router
from pema.api.mcp_route_guards import (
    McpAdmin,
    check_agent_ids,
    check_create,
    check_server_ids,
    check_update,
)
from pema_contracts.admin_agent import IdList, McpServerCreate, McpServerUpdate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.mcp import McpServer, McpServerView

router = admin_router("mcp", "admin-mcp")


def _view(server: McpServer, bound_agent_count: int) -> McpServerView:
    return McpServerView(**server.model_dump(), bound_agent_count=bound_agent_count)


def _server_not_found() -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy máy chủ MCP.")


async def _require_view(ctx: McpAdmin, server_id: str) -> McpServerView:
    server = await ctx.servers.get_server(ctx.clinic_id, server_id)
    if server is None:
        raise _server_not_found()
    counts = await ctx.bindings.count_agents_by_server(ctx.clinic_id)
    return _view(server, counts.get(server_id, 0))


@router.get("/servers", response_model=list[McpServerView], summary="MCP servers with state")
async def list_mcp_servers(ctx: McpAdmin) -> list[McpServerView]:
    counts = await ctx.bindings.count_agents_by_server(ctx.clinic_id)
    servers = await ctx.servers.list_servers(ctx.clinic_id)
    return [_view(s, counts.get(s.id, 0)) for s in servers]


@router.post(
    "/servers", response_model=McpServerView, status_code=status.HTTP_201_CREATED, summary="Add a server"
)
async def create_mcp_server(
    body: McpServerCreate, ctx: McpAdmin, background: BackgroundTasks
) -> McpServerView:
    check_create(body)
    server = await ctx.servers.create_server(
        ctx.clinic_id, name=body.name, url=body.url, headers=body.headers, enabled=body.enabled
    )
    # Connect only when created ENABLED: a server created ``enabled: false`` would be connected and then
    # pushed back to ``cho_ket_noi`` by the guard in ``connect_and_load``, which is churn for nothing.
    if server.enabled:
        background.add_task(ctx.manager.reconnect_server, ctx.clinic_id, server.id)  # in the background
    return _view(server, 0)


@router.patch("/servers/{server_id}", response_model=McpServerView, summary="Update a server")
async def update_mcp_server(
    server_id: str, body: McpServerUpdate, ctx: McpAdmin, background: BackgroundTasks
) -> McpServerView:
    check_update(body)
    found = await ctx.servers.update_server(
        ctx.clinic_id,
        server_id,
        name=body.name,
        url=body.url,
        headers=body.headers,
        enabled=body.enabled,
    )
    if not found:
        raise _server_not_found()
    # Unconditional, as in the original: a changed url / headers / enabled all need a reconnect, and the
    # disabled case is handled by the guard in ``connect_and_load`` (disconnect, do NOT reconnect).
    background.add_task(ctx.manager.reconnect_server, ctx.clinic_id, server_id)
    return await _require_view(ctx, server_id)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a server")
async def delete_mcp_server(server_id: str, ctx: McpAdmin) -> None:
    if await ctx.servers.get_server(ctx.clinic_id, server_id) is None:
        raise _server_not_found()
    # await: the client must be CLOSED before the row goes; deleting first would leave the manager without a
    # way to look the server up for the half-finished cleanup.
    await ctx.manager.disconnect_server(ctx.clinic_id, server_id)
    await ctx.servers.delete_server(ctx.clinic_id, server_id)  # one transaction: also drops the bindings
    await ctx.manager.refresh_bindings(ctx.clinic_id)


@router.delete(
    "/servers/{server_id}/headers", status_code=status.HTTP_204_NO_CONTENT, summary="Remove stored headers"
)
async def clear_mcp_server_headers(server_id: str, ctx: McpAdmin, background: BackgroundTasks) -> None:
    if not await ctx.servers.clear_headers(ctx.clinic_id, server_id):
        raise _server_not_found()
    background.add_task(ctx.manager.reconnect_server, ctx.clinic_id, server_id)


@router.post(
    "/servers/{server_id}/reapprove",
    response_model=McpServerView,
    summary="Accept the drifted tool list (re-approval)",
)
async def reapprove_mcp_server(server_id: str, ctx: McpAdmin) -> McpServerView:
    await _require_view(ctx, server_id)
    await ctx.manager.reapprove_drift(ctx.clinic_id, server_id)
    return await _require_view(ctx, server_id)


@router.get("/servers/{server_id}/agents", response_model=IdList, summary="Agents bound to a server")
async def get_agents_of_mcp_server(server_id: str, ctx: McpAdmin) -> IdList:
    return IdList(ids=await ctx.bindings.agents_of_server(ctx.clinic_id, server_id))


@router.put("/servers/{server_id}/agents", response_model=IdList, summary="Set the agents of a server")
async def set_agents_of_mcp_server(server_id: str, body: IdList, ctx: McpAdmin) -> IdList:
    check_agent_ids(body.ids)
    await ctx.bindings.set_agents_for_server(ctx.clinic_id, server_id, body.ids)
    return IdList(ids=await ctx.bindings.agents_of_server(ctx.clinic_id, server_id))


@router.get("/agents/{agent_id}/servers", response_model=IdList, summary="Servers bound to an agent")
async def get_mcp_servers_of_agent(agent_id: str, ctx: McpAdmin) -> IdList:
    return IdList(ids=await ctx.bindings.servers_of_agent(ctx.clinic_id, agent_id))


@router.put("/agents/{agent_id}/servers", response_model=IdList, summary="Set the servers of an agent")
async def set_mcp_servers_of_agent(agent_id: str, body: IdList, ctx: McpAdmin) -> IdList:
    check_server_ids(body.ids)
    await ctx.bindings.set_servers_for_agent(ctx.clinic_id, agent_id, body.ids)
    return IdList(ids=await ctx.bindings.servers_of_agent(ctx.clinic_id, agent_id))

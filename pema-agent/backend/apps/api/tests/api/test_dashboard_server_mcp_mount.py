# ported from: src/server/dashboard-server-mcp-mount.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original built the dashboard app with ``DASHBOARD_PASSWORD`` set and asked ``/api/mcp`` without a session:
``401`` (mounted AFTER the auth middleware) and not ``404`` (not mounted). In FastAPI the routers are mounted by
``build_api_router`` and the session requirement is declared on every admin router (``SessionCookie``); the actual
session check is package B1's and G wires it. This keeps what the original proved: the MCP routes are MOUNTED
(not ``404``) and sit behind the session scheme. Unwired, they answer ``501`` (``get_mcp_admin_context`` default):
a route can never run without the dependency that checks the ``admin.mcp`` permission.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from pema.bootstrap import create_app

BASE = "/api/v1/admin/mcp"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_mount_api_mcp_is_mounted_not_404_and_answers_501_until_the_admin_context_is_wired(
    client: httpx.AsyncClient,
) -> None:
    """không session -> 401 (đã mount sau auth), không phải 404"""
    res = await client.get(f"{BASE}/servers")
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "not_implemented"


async def test_mount_api_mcp_every_route_declares_the_session_cookie_scheme() -> None:
    """mọi route /admin/mcp khai báo SessionCookie (đứng sau lớp xác thực)"""
    schema: dict[str, Any] = create_app().openapi()
    paths = {p: item for p, item in schema["paths"].items() if p.startswith(BASE)}
    assert len(paths) >= 5
    for path, item in paths.items():
        for method, op in item.items():
            assert any("SessionCookie" in req for req in op["security"]), f"{method} {path}"

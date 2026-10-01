# ported from: src/server/routes/mcp-routes.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original injected a fake ``manager`` through ``deps`` and called ``createMcpRoutes`` on its own Hono app. Here
the real app is built (``create_app``) and the dependency ``get_mcp_admin_context`` is overridden with an
``McpAdminContext`` over ``InMemoryMcpStore`` and a recording fake manager (``FakeManager``), which keeps the same
shape of test: no network, the calls the route made are listed in ``manager.calls``.

Differences from the original, all in the module docstring of ``admin_mcp``: the paths of the OpenAPI skeleton
(``reapprove``), ``204`` for the deletes, ``422`` (the error envelope of the API) instead of ``400`` for a body
that does not validate, and ``404`` for an unknown id.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

import httpx
import pytest

from pema.api.mcp_route_guards import (
    McpAdminContext,
    check_server_url,
    get_mcp_admin_context,
)
from pema.bootstrap import create_app
from pema.mcp.mcp_agent_binding import McpBindingCache
from pema.mcp.testing import InMemoryMcpStore
from pema_contracts.errors import DomainError
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAgentStore, fake_agent_profile

BASE = "/api/v1/admin/mcp"


@dataclass
class FakeManager:
    calls: list[str] = field(default_factory=list[str])

    async def reconnect_server(self, clinic_id: UUID, server_id: str) -> None:
        self.calls.append(f"noi:{server_id}")

    async def disconnect_server(self, clinic_id: UUID, server_id: str) -> None:
        self.calls.append(f"ngat:{server_id}")

    async def reapprove_drift(self, clinic_id: UUID, server_id: str) -> None:
        self.calls.append(f"duyet:{server_id}")

    async def refresh_bindings(self, clinic_id: UUID) -> None:
        self.calls.append("lam-moi-gan")


@dataclass
class Setup:
    client: httpx.AsyncClient
    store: InMemoryMcpStore
    manager: FakeManager


@pytest.fixture
async def setup() -> AsyncIterator[Setup]:
    agents = InMemoryAgentStore(fake_agent_profile(id="agent-a"), fake_agent_profile(id="agent-b"))
    store = InMemoryMcpStore(agent_store=agents, binding_cache=McpBindingCache())
    manager = FakeManager()
    context = McpAdminContext(clinic_id=FAKE_CLINIC_ID, servers=store, bindings=store, manager=manager)
    app = create_app()
    app.dependency_overrides[get_mcp_admin_context] = lambda: context
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Setup(client=client, store=store, manager=manager)


async def _make(setup: Setup, **kwargs: object) -> str:
    created = await setup.store.create_server(FAKE_CLINIC_ID, name="svr", url="https://x/mcp", **kwargs)  # type: ignore[arg-type]
    return created.id


async def test_mcp_routes_post_creates_a_server_and_connects_it(setup: Setup) -> None:
    """POST / tạo server + gọi ketNoiLaiServer"""
    res = await setup.client.post(f"{BASE}/servers", json={"name": "svr", "url": "https://x/mcp"})
    assert res.status_code == 201
    assert len(await setup.store.list_servers(FAKE_CLINIC_ID)) == 1
    assert any(call.startswith("noi:") for call in setup.manager.calls)
    body = res.json()
    assert body["bound_agent_count"] == 0
    assert body["status"] == "cho_ket_noi"


async def test_mcp_routes_post_enabled_false_does_not_connect(setup: Setup) -> None:
    """POST / enabled:false -> KHÔNG gọi ketNoiLaiServer (server tạo sẵn TẮT)"""
    res = await setup.client.post(
        f"{BASE}/servers", json={"name": "svr", "url": "https://x/mcp", "enabled": False}
    )
    assert res.status_code == 201
    assert len(await setup.store.list_servers(FAKE_CLINIC_ID)) == 1
    assert setup.manager.calls == []


async def test_mcp_routes_post_empty_url_is_rejected(setup: Setup) -> None:
    """POST / url rỗng -> 400 (ở đây là 422 của envelope lỗi API)"""
    res = await setup.client.post(f"{BASE}/servers", json={"name": "svr", "url": ""})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"
    assert await setup.store.list_servers(FAKE_CLINIC_ID) == []


async def test_mcp_routes_patch_updates_and_reconnects(setup: Setup) -> None:
    """PATCH /:id sửa + gọi ketNoiLaiServer nối lại"""
    server_id = await _make(setup)
    res = await setup.client.patch(f"{BASE}/servers/{server_id}", json={"name": "svr moi"})
    assert res.status_code == 200
    assert (await setup.store.list_servers(FAKE_CLINIC_ID))[0].name == "svr moi"
    assert f"noi:{server_id}" in setup.manager.calls
    assert res.json()["name"] == "svr moi"


async def test_mcp_routes_reapprove_calls_the_manager(setup: Setup) -> None:
    """POST /:id/duyet-lai gọi duyetLaiDrift"""
    server_id = await _make(setup)
    res = await setup.client.post(f"{BASE}/servers/{server_id}/reapprove")
    assert res.status_code == 200
    assert f"duyet:{server_id}" in setup.manager.calls


async def test_mcp_routes_put_agent_servers_saves_the_binding(setup: Setup) -> None:
    """PUT /agents/:agentId/servers lưu gán"""
    server_id = await _make(setup)
    res = await setup.client.put(f"{BASE}/agents/agent-a/servers", json={"ids": [server_id]})
    assert res.status_code == 200
    assert res.json() == {"ids": [server_id]}
    assert await setup.store.servers_of_agent(FAKE_CLINIC_ID, "agent-a") == [server_id]


async def test_mcp_routes_put_server_agents_saves_the_reverse_binding(setup: Setup) -> None:
    """PUT /:id/agents lưu gán chiều ngược"""
    server_id = await _make(setup)
    res = await setup.client.put(f"{BASE}/servers/{server_id}/agents", json={"ids": ["agent-b"]})
    assert res.status_code == 200
    assert await setup.store.agents_of_server(FAKE_CLINIC_ID, server_id) == ["agent-b"]
    got = await setup.client.get(f"{BASE}/servers/{server_id}/agents")
    assert got.json() == {"ids": ["agent-b"]}


async def test_mcp_routes_delete_disconnects_then_deletes(setup: Setup) -> None:
    """DELETE /:id ngắt rồi xóa"""
    server_id = await _make(setup)
    res = await setup.client.delete(f"{BASE}/servers/{server_id}")
    assert res.status_code == 204
    assert await setup.store.list_servers(FAKE_CLINIC_ID) == []
    assert setup.manager.calls[0] == f"ngat:{server_id}"


async def test_mcp_routes_delete_headers_removes_the_header(setup: Setup) -> None:
    """DELETE /:id/headers xóa header"""
    server_id = await _make(setup, headers={"Authorization": "Bearer x"})
    assert (await setup.store.list_servers(FAKE_CLINIC_ID))[0].has_headers is True
    res = await setup.client.delete(f"{BASE}/servers/{server_id}/headers")
    assert res.status_code == 204
    assert (await setup.store.list_servers(FAKE_CLINIC_ID))[0].has_headers is False


# ------------------------------------------- additions of the Python port (not in the original test file)


async def test_mcp_routes_list_shows_the_bound_agent_count_and_never_the_headers(setup: Setup) -> None:
    """danh sách có soAgentGan và KHÔNG lộ header"""
    server_id = await _make(setup, headers={"Authorization": "Bearer top-secret-value"})
    await setup.store.set_servers_for_agent(FAKE_CLINIC_ID, "agent-a", [server_id])
    await setup.store.set_servers_for_agent(FAKE_CLINIC_ID, "agent-b", [server_id])
    res = await setup.client.get(f"{BASE}/servers")
    assert res.status_code == 200
    (row,) = res.json()
    assert row["bound_agent_count"] == 2
    assert row["has_headers"] is True
    assert "top-secret-value" not in res.text
    assert "headers" not in row


async def test_mcp_routes_unknown_server_is_404_on_every_route_that_needs_one(setup: Setup) -> None:
    """id không tồn tại -> 404 (bản gốc trả ok:true)"""
    for method, path, body in (
        ("PATCH", f"{BASE}/servers/khong-co", {"name": "x"}),
        ("DELETE", f"{BASE}/servers/khong-co", None),
        ("DELETE", f"{BASE}/servers/khong-co/headers", None),
        ("POST", f"{BASE}/servers/khong-co/reapprove", None),
    ):
        res = await setup.client.request(method, path, json=body)
        assert res.status_code == 404, (method, path)
        assert res.json()["error"]["code"] == "not_found"
    assert setup.manager.calls == []


async def test_mcp_routes_binding_an_unknown_agent_is_404_and_binds_nothing(setup: Setup) -> None:
    """gán agent không tồn tại -> 404, không có dòng mồ côi"""
    server_id = await _make(setup)
    res = await setup.client.put(f"{BASE}/servers/{server_id}/agents", json={"ids": ["ma-ma"]})
    assert res.status_code == 404
    assert await setup.store.agents_of_server(FAKE_CLINIC_ID, server_id) == []


async def test_mcp_routes_get_agent_servers_is_default_deny(setup: Setup) -> None:
    """agent chưa gán -> danh sách rỗng"""
    res = await setup.client.get(f"{BASE}/agents/agent-a/servers")
    assert res.json() == {"ids": []}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "svr", "url": "ftp://x/mcp"},
        {"name": "svr", "url": "https://" + "a" * 2050},
        {"name": "svr", "url": "https://x/mcp", "headers": {"Bad Name": "v"}},
        {"name": "svr", "url": "https://x/mcp", "headers": {"X-A": "v\r\nX-B: injected"}},
        {"name": "svr", "url": "https://x/mcp", "headers": {"X-A": "v" * 4001}},
    ],
)
async def test_mcp_routes_the_guards_reject_a_bad_url_or_header_before_anything_is_stored(
    setup: Setup, payload: dict[str, object]
) -> None:
    """guard: URL/header sai bị chặn ở biên, không lưu gì"""
    res = await setup.client.post(f"{BASE}/servers", json=payload)
    assert res.status_code == 422
    assert await setup.store.list_servers(FAKE_CLINIC_ID) == []
    assert setup.manager.calls == []


async def test_mcp_routes_the_guards_cap_the_id_lists(setup: Setup) -> None:
    """guard: trần số phần tử và độ dài mỗi id của danh sách gán"""
    too_many = await setup.client.put(
        f"{BASE}/agents/agent-a/servers", json={"ids": [str(i) for i in range(501)]}
    )
    assert too_many.status_code == 422
    too_long = await setup.client.put(f"{BASE}/agents/agent-a/servers", json={"ids": ["x" * 65]})
    assert too_long.status_code == 422
    too_many_agents = await setup.client.put(
        f"{BASE}/servers/some-id/agents", json={"ids": [str(i) for i in range(201)]}
    )
    assert too_many_agents.status_code == 422


async def test_mcp_routes_patch_with_a_bad_header_is_rejected_and_changes_nothing(setup: Setup) -> None:
    """PATCH với header sai -> 422, giữ nguyên server"""
    server_id = await _make(setup)
    res = await setup.client.patch(f"{BASE}/servers/{server_id}", json={"headers": {"X": "a\nb"}})
    assert res.status_code == 422
    assert setup.manager.calls == []
    assert (await setup.store.list_servers(FAKE_CLINIC_ID))[0].name == "svr"


# ---------------------------------------------------------------- package G (SECURITY-REVIEW-AI01 SEC-29)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/",
        "http://[fe80::1]/mcp",
        "http://0.0.0.0:8080/mcp",
        "http://224.0.0.1/mcp",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://METADATA.GOOGLE.INTERNAL./x",
        "https://user:pw@mcp.example.test/mcp",
        "https://mcp.example.test:notaport/mcp",
    ],
)
def test_an_mcp_url_that_reaches_a_metadata_service_or_carries_a_credential_is_refused(url: str) -> None:
    """URL MCP trỏ tới dịch vụ metadata, địa chỉ đặc biệt hoặc chứa mật khẩu thì bị từ chối"""
    with pytest.raises(DomainError):
        check_server_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://mcp.example.test/mcp",
        "http://127.0.0.1:8123/mcp",
        "http://192.168.1.20:9000/mcp",
        "http://[::1]:9/x",
    ],
)
def test_a_server_on_the_clinic_network_is_still_accepted(url: str) -> None:
    """máy chủ MCP trong mạng nội bộ của phòng khám vẫn được phép (quyết định sản phẩm ghi ở báo cáo)"""
    check_server_url(url)

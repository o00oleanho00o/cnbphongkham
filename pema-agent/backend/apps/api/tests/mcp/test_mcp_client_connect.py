# ported from: src/mcp/mcp-client-connect.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The last two tests are additions of the Python port: they exercise the REAL adapter over the ``mcp`` SDK against
a server on the loopback interface (127.0.0.1, an ephemeral port, started in the test), so no real network is
touched but the HTTP transport, the headers and the owner-task design are covered for real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer

from pema.mcp.mcp_client_connect import (
    ConnectConfig,
    ConnectDeps,
    McpConnectError,
    McpConnection,
    connect_server,
    safe_url,
)
from pema.mcp.testing import FakeMcpConnection
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi


def _deps(impl: object) -> ConnectDeps:
    return ConnectDeps(create_client=impl)  # type: ignore[arg-type]


async def test_connect_server_ok_returns_a_handle_with_list_tools_and_close() -> None:
    """nối ok trả handle có tools()/close()"""

    async def create(url: str, headers: Mapping[str, str]) -> McpConnection:
        return FakeMcpConnection([])

    handle = await connect_server(
        ConnectConfig(url="https://x/mcp", headers={}, connect_timeout_ms=1000), _deps(create)
    )
    assert callable(handle.list_tools)
    assert callable(handle.close)


async def test_connect_server_hanging_past_the_timeout_raises_mcp_connect_error() -> None:
    """nối treo quá timeout -> ném LoiKetNoiMcp"""

    async def never(url: str, headers: Mapping[str, str]) -> McpConnection:
        await asyncio.Event().wait()  # never resolves
        raise AssertionError

    with pytest.raises(McpConnectError) as caught:
        await connect_server(
            ConnectConfig(url="https://x/mcp", headers={}, connect_timeout_ms=10), _deps(never)
        )
    assert caught.value.error_kind == "ket_noi"


async def test_connect_server_failure_is_typed_and_the_message_keeps_no_token() -> None:
    """lỗi nối có KIỂU, thông điệp không chứa user info hay query của URL (có thể là token)"""

    async def boom(url: str, headers: Mapping[str, str]) -> McpConnection:
        raise ConnectionError("refused")

    with pytest.raises(McpConnectError) as caught:
        await connect_server(
            ConnectConfig(
                url="https://user:pw-synthetic@x.test:8443/mcp?token=tok-synthetic",
                headers={},
                connect_timeout_ms=1000,
            ),
            _deps(boom),
        )
    message = str(caught.value)
    assert "x.test:8443/mcp" in message
    assert "pw-synthetic" not in message
    assert "tok-synthetic" not in message


def test_safe_url_drops_user_info_and_query() -> None:
    """safe_url chỉ giữ scheme, host, port, path"""
    assert safe_url("https://u:p@h.test:81/p?q=1#f") == "https://h.test:81/p"
    assert safe_url("http://[::1") == "(url không hợp lệ)"


# ------------------------------------------------------------------ real adapter, loopback server


@pytest.fixture
async def loopback_server() -> AsyncIterator[int]:
    server = MCPServer("synthetic-server")

    @server.tool()
    def tra_cuu(q: str) -> str:
        """Tra cứu giả."""
        return f"ket qua cho {q}"

    config = uvicorn.Config(server.streamable_http_app(), host="127.0.0.1", port=0, log_level="error")
    uvi = uvicorn.Server(config)
    task = asyncio.create_task(uvi.serve())
    await doi_cho_den_khi(lambda: uvi.started, WaitOptions(mo_ta="server loopback sẵn sàng"))
    try:
        yield int(uvi.servers[0].sockets[0].getsockname()[1])
    finally:
        uvi.should_exit = True
        await task


async def test_real_adapter_lists_tools_and_calls_one_over_streamable_http(loopback_server: int) -> None:
    """adapter thật: liệt kê tool và gọi tool qua HTTP streamable (loopback)"""
    handle = await connect_server(
        ConnectConfig(
            url=f"http://127.0.0.1:{loopback_server}/mcp",
            headers={"X-Synthetic": "1"},
            connect_timeout_ms=10000,
        )
    )
    try:
        tools = await handle.list_tools()
        assert [t.name for t in tools] == ["tra_cuu"]
        assert tools[0].input_schema["type"] == "object"
        result = await handle.call_tool("tra_cuu", {"q": "abc"})
        assert isinstance(result, dict)
        assert result["content"][0]["text"] == "ket qua cho abc"
        assert result["isError"] is False
    finally:
        await handle.close()
    with pytest.raises(McpConnectError):
        await handle.call_tool("tra_cuu", {"q": "abc"})


async def test_real_adapter_unreachable_server_raises_mcp_connect_error() -> None:
    """adapter thật: server không lên -> McpConnectError (không rò task)"""
    before = len(asyncio.all_tasks())
    with pytest.raises(McpConnectError):
        await connect_server(ConnectConfig(url="http://127.0.0.1:1/mcp", headers={}, connect_timeout_ms=3000))
    await asyncio.sleep(0)
    assert len(asyncio.all_tasks()) <= before

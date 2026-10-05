# ported from: src/mcp/mcp-client-connect.ts
"""Connect to ONE external MCP server over Streamable HTTP, with a time ceiling.

An external server is not operated by us, so it may hang forever during the handshake (``initialize``). With
no ceiling, ``mcp_manager`` would wait forever on ONE broken server and boot/health would never finish. The
``redirect`` of ``@ai-sdk/mcp`` defaulted to ``'error'`` (no automatic redirect), which the original kept as
an SSRF-through-redirect defence "without writing anything". The Python ``mcp`` SDK has the same defence built
in: ``streamable_http_client`` follows a redirect only inside the endpoint's own origin and for the same
method, and fails the request otherwise (``create_mcp_http_client`` leaves ``follow_redirects`` off).

Forced deviation (``@ai-sdk/mcp`` -> ``mcp`` Python SDK, HTTP streamable transport; JS promise -> asyncio):

* ``KetNoiMcp`` (``tools()`` returning ready-to-run ``Tool`` objects, ``close()``) becomes ``McpConnection``
  (``list_tools()`` returning ``McpRemoteTool`` metadata, ``call_tool(name, args)``, ``close()``);
* ``LoiKetNoiMcp`` (an ``Error`` with ``loaiLoi: "ket_noi"``) becomes ``McpConnectError`` with
  ``error_kind == "ket_noi"``, a TYPED error so a caller can tell it from any other failure;
* ``Promise.race`` with a timer becomes ``asyncio.timeout``. Unlike JS, losing the race really CANCELS the
  connection attempt (the original comment: "cannot cancel ``fn()`` when it loses the race"), so no half-open
  handle is left behind;
* the ``mcp`` ``Client`` is built on anyio task groups, which must be entered and exited by the SAME task, but
  the pool keeps a connection open across many tasks and closes it from another. ``StreamableHttpConnection``
  therefore runs the ``async with Client(...)`` block in ONE owner task and talks to it through the client
  object; ``close()`` asks that task to leave the block;
* error text never contains the query string or the user info of the URL (both may carry a token); the
  original put the whole URL in the message that is stored in ``mcp_servers.error`` and shown on the
  dashboard.

``ConnectDeps`` is the test seam: inject a fake client factory instead of calling HTTP for real.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast
from urllib.parse import urlsplit

from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from pema.mcp.mcp_types import McpRemoteTool
from pema_contracts.common import JsonObject

MAX_TOOL_PAGES: Final = 20
"""A server that keeps returning ``next_cursor`` must not hold ``list_tools`` forever."""

MAX_TOOLS: Final = 500
"""Hard ceiling on tools taken from one server (a hostile server could list millions)."""

_CLOSE_GRACE_SECONDS: Final = 5.0
_MAX_ERROR_CHARS: Final = 300


class McpConnectError(Exception):
    """``LoiKetNoiMcp``: typed so callers can tell it from any other error."""

    error_kind: Literal["ket_noi"] = "ket_noi"


class McpConnection(Protocol):
    """``KetNoiMcp``: a live handle to one server."""

    async def list_tools(self) -> list[McpRemoteTool]:
        """``tools()``: the ``tools/list`` of the server (all pages, capped)."""
        ...

    async def call_tool(self, name: str, args: JsonObject) -> object:
        """Run a tool. Returns the MCP ``CallToolResult`` as a plain JSON-style dict
        (``content``, ``isError``, ``structuredContent``)."""
        ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class ConnectConfig:
    url: str
    headers: dict[str, str] = field(repr=False)
    connect_timeout_ms: int


CreateClient = Callable[[str, Mapping[str, str]], Awaitable[McpConnection]]


@dataclass(frozen=True)
class ConnectDeps:
    """Test seam: inject a fake client builder instead of calling HTTP for real."""

    create_client: CreateClient


ConnectFn = Callable[[ConnectConfig], Awaitable[McpConnection]]
"""The shape of ``connect_server``; the pool takes one of these (a test passes a fake)."""


def safe_url(url: str) -> str:
    """Scheme, host, port and path only: no user info and no query (either may hold a token)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "(url không hợp lệ)"
    return f"{parts.scheme}://{host}{port}{parts.path}"


def _first_leaf(exc: BaseException) -> BaseException:
    members = cast(
        object, getattr(exc, "exceptions", None)
    )  # an exception group, without naming its generics
    if isinstance(members, tuple) and members:
        first = cast("tuple[object, ...]", members)[0]
        if isinstance(first, BaseException):
            return _first_leaf(first)
    return exc


def describe_error(exc: BaseException) -> str:
    """One short line for an error: unwraps exception groups (anyio raises them), drops line breaks, caps
    length."""
    leaf = _first_leaf(exc)
    text = " ".join(str(leaf).split()) or type(leaf).__name__
    return text[:_MAX_ERROR_CHARS]


class StreamableHttpConnection:
    """Real adapter over the ``mcp`` Python SDK (see the module docstring for why a dedicated owner task)."""

    def __init__(self, url: str, headers: Mapping[str, str]) -> None:
        self._url = url
        self._headers = dict(headers)
        self._client: Client | None = None
        self._closing = asyncio.Event()
        self._ready: asyncio.Future[None] | None = None
        self._task: asyncio.Task[None] | None = None

    async def open(self) -> None:
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        self._task = loop.create_task(self._run(self._ready), name="mcp-connection")
        try:
            await self._ready
        except BaseException:
            await self.close()
            raise

    async def _run(self, ready: asyncio.Future[None]) -> None:
        try:
            http = create_mcp_http_client(headers=self._headers)
            async with http, Client(streamable_http_client(self._url, http_client=http)) as client:
                self._client = client
                if not ready.done():
                    ready.set_result(None)
                await self._closing.wait()
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
        finally:
            self._client = None

    def _require_client(self) -> Client:
        if self._client is None:
            raise McpConnectError("Kết nối MCP đã đóng")
        return self._client

    async def list_tools(self) -> list[McpRemoteTool]:
        client = self._require_client()
        tools: list[McpRemoteTool] = []
        cursor: str | None = None
        for _ in range(MAX_TOOL_PAGES):
            page = await client.list_tools(cursor=cursor)
            for tool in page.tools:
                tools.append(
                    McpRemoteTool(
                        name=tool.name,
                        description=tool.description or "",
                        title=tool.title,
                        input_schema=dict(tool.input_schema),
                    )
                )
                if len(tools) >= MAX_TOOLS:
                    return tools
            cursor = page.next_cursor
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, args: JsonObject) -> object:
        result = await self._require_client().call_tool(name, args)
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    async def close(self) -> None:
        self._closing.set()
        task = self._task
        if task is None or task.done():
            return
        with contextlib.suppress(Exception, asyncio.CancelledError):
            async with asyncio.timeout(_CLOSE_GRACE_SECONDS):
                await asyncio.shield(task)
        if not task.done():
            task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await task


async def _create_streamable_http_client(url: str, headers: Mapping[str, str]) -> McpConnection:
    connection = StreamableHttpConnection(url, headers)
    await connection.open()
    return connection


DEFAULT_DEPS: Final = ConnectDeps(create_client=_create_streamable_http_client)


async def connect_server(cfg: ConnectConfig, deps: ConnectDeps = DEFAULT_DEPS) -> McpConnection:
    """``ketNoiServer``. Raises ``McpConnectError`` on failure or timeout."""
    target = safe_url(cfg.url)
    ceiling = asyncio.timeout(cfg.connect_timeout_ms / 1000)
    try:
        async with ceiling:
            return await deps.create_client(cfg.url, cfg.headers)
    except TimeoutError as exc:
        if ceiling.expired():
            raise McpConnectError(f"Nối {target} quá {cfg.connect_timeout_ms}ms") from None
        raise McpConnectError(f"Không nối được {target}: {describe_error(exc)}") from exc
    except McpConnectError:
        raise
    except Exception as exc:
        raise McpConnectError(f"Không nối được {target}: {describe_error(exc)}") from exc

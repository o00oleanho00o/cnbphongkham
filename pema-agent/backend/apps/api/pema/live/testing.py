"""Test support for the live routes (ST-R; not imported by production code).

``httpx.ASGITransport`` buffers a whole response before it returns, so it cannot read a stream that never
ends. ``OpenStream`` drives the ASGI app by hand instead: it starts the request in a task, collects the body
chunks as they are sent, and ``close`` sends the ``http.disconnect`` a browser sends when the tab goes away.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import httpx
from starlette.types import Message, Scope

from pema.config.env import get_settings


def session_cookie(client: httpx.AsyncClient) -> str:
    """``Cookie`` header of a signed-in test client."""
    name = get_settings().session_cookie_name
    value = client.cookies.get(name)
    assert value, "the client is not signed in"  # noqa: S101
    return f"{name}={value}"


class OpenStream:
    def __init__(self, app: Any, path: str, *, cookie: str | None = None) -> None:
        self._app = app
        self._path = path
        self._cookie = cookie
        self._chunks: asyncio.Queue[str] = asyncio.Queue()
        self._disconnect = asyncio.Event()
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.status = 0
        self.headers: dict[str, str] = {}
        self.body = ""
        """Everything received so far."""

    async def start(self) -> OpenStream:
        self._task = asyncio.get_running_loop().create_task(self._run())
        await asyncio.wait_for(self._started.wait(), 5)
        return self

    async def _run(self) -> None:
        headers: list[tuple[bytes, bytes]] = [(b"host", b"test")]
        if self._cookie is not None:
            headers.append((b"cookie", self._cookie.encode("latin-1")))
        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("test", 80),
        }
        sent_request = False

        async def receive() -> Message:
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.status = int(message["status"])
                self.headers = {k.decode().lower(): v.decode() for k, v in message["headers"]}
                self._started.set()
            elif message["type"] == "http.response.body":
                text = bytes(message.get("body", b"")).decode()
                if text:
                    self.body += text
                    self._chunks.put_nowait(text)

        try:
            await self._app(scope, receive, send)
        finally:
            self._started.set()
            self._finished.set()

    async def read(self, wait_s: float = 2.0) -> str:
        """The next chunk the server sent."""
        return await asyncio.wait_for(self._chunks.get(), wait_s)

    async def read_until(self, needle: str, wait_s: float = 3.0) -> str:
        """Read chunks until one contains ``needle``; returns that chunk."""
        async with asyncio.timeout(wait_s):
            while True:
                chunk = await self._chunks.get()
                if needle in chunk:
                    return chunk

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    async def wait_finished(self, wait_s: float = 3.0) -> None:
        await asyncio.wait_for(self._finished.wait(), wait_s)

    async def close(self) -> None:
        """The browser went away."""
        self._disconnect.set()
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, 3)
